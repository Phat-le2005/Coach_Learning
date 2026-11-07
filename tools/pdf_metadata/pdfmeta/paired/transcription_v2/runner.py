"""Reusable corpus runner with frozen selection and bounded subprocess chunks."""
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from ...pdf_workflow import local_lock
from ...storage import configure_storage, file_hash, inference_versions, read_json, write_json
from ..transcript_batch import Syntax, content_hash, now
from .batch import code_identity, raw_cache_index, viewer
from .checkpoints import record_name, valid_checkpoint
from .exports import publish
from .selection import select_new
from .supervisor import execute_chunks


def read_source(path):
    rows, ids = [], set()
    with path.open(encoding='utf-8-sig') as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if row['question_id'] in ids:
                raise ValueError('DUPLICATE_SOURCE_QUESTION_ID')
            ids.add(row['question_id'])
            rows.append(row)
    return rows


def prepare_selection(args, rows, source_sha):
    if args.v1:
        selection = read_json(args.v1 / 'selection.json')
    elif args.selection:
        selection = read_json(args.selection)
    else:
        excluded = set()
        for path in args.exclude_selection:
            excluded.update(q['question_id'] for q in read_json(path)['questions'])
        selection = select_new(rows, args.count, excluded, args.seed)
        selection['canonical_metadata_sha256'] = source_sha
    if selection.get('canonical_metadata_sha256') != source_sha:
        raise ValueError('CANONICAL_SOURCE_CHANGED')
    ids = [q['question_id'] for q in selection['questions']]
    if len(set(ids)) != len(ids) or len(ids) != selection['count']:
        raise ValueError('SELECTION_MISSING_OR_DUPLICATED')
    lookup = {q['question_id']: q for q in rows}
    if not set(ids) <= lookup.keys():
        raise ValueError('SELECTION_MISSING_FROM_INPUT')
    chosen = [lookup[qid] for qid in ids]
    for item, row in zip(selection['questions'], chosen):
        if (item['source_sha256'] != row['source']['sha256']
                or item['collection_number'] != row['collection_number']):
            raise ValueError('SELECTION_SOURCE_IDENTITY_MISMATCH')
    return selection, chosen


def build_tasks(chosen, documents, output, runtime, katex, identity, cache_index,
                *, chunk_size, cache_mode, max_page_cache, invocation, native_only=False):
    ordered = sorted(chosen, key=lambda q: (q['source']['sha256'], min(
        (s['page_number'] for role in ('question', 'solution', 'answer') for s in q[role]['source_spans']), default=0), q['question_id']))
    tasks = []
    for offset in range(0, len(ordered), chunk_size):
        rows = ordered[offset:offset + chunk_size]
        chunk_id = content_hash([q['question_id'] for q in rows])[:16]
        tasks.append({'chunk_id': chunk_id,
                      'task_path': str(output / 'chunks' / invocation / chunk_id / 'task.json'),
                      'payload': {'items': rows, 'documents': documents, 'output': str(output),
                                  'runtime': str(runtime), 'katex': str(katex), 'identity': identity,
                                  'cache_index': cache_index, 'options': {'chunk_id': chunk_id,
                                      'cache_mode': cache_mode, 'max_page_cache': max_page_cache,'native_only':native_only}}})
    return tasks


def run(args):
    for key in ('input', 'output', 'runtime', 'katex', 'plan'):
        setattr(args, key, getattr(args, key).resolve())
    for key in ('v1', 'baseline', 'selection'):
        if getattr(args, key):
            setattr(args, key, getattr(args, key).resolve())
    source, output = args.input, args.output
    if output == source.parent or (args.v1 and output == args.v1):
        raise ValueError('SEPARATE_V2_OUTPUT_REQUIRED')

    if (args.workers not in (1, 2) or args.chunk_size < 1 or args.max_page_cache < 1
            or args.chunk_timeout <= 0 or args.run_timeout <= 0 or args.memory_limit_mb < 0
            or args.min_free_disk_mb < 0 or args.stop_after_chunks < 0):
        raise ValueError('INVALID_TRANSCRIPTION_BUDGET')
    if args.cache_mode == 'import-v1' and (not args.v1 or not args.baseline):
        raise ValueError('IMPORT_V1_REQUIRES_V1_AND_BASELINE')
    output.mkdir(parents=True, exist_ok=True)
    configure_storage(args.runtime)
    with local_lock(output):
        source_sha = file_hash(source)
        selection, chosen = prepare_selection(args, read_source(source), source_sha)
        plan_sha = file_hash(args.plan)
        documents = {d['sha256']: str(Path(d['path']).resolve()) for d in read_json(args.plan)['documents']}
        source_hashes = {}
        for digest in {q['source']['sha256'] for q in chosen}:
            if digest not in documents or file_hash(Path(documents[digest])) != digest:
                raise ValueError('SOURCE_PDF_HASH_MISMATCH')
            source_hashes[documents[digest]] = digest
        if (output / 'selection.json').exists() and read_json(output / 'selection.json') != selection:
            raise ValueError('FIXED_SELECTION_CHANGED_USE_NEW_OUTPUT')
        write_json(output / 'selection.json', selection)
        semantic_config = {'code': code_identity(), 'source_sha256': source_sha, 'plan_sha256': plan_sha,
            'packages': inference_versions(), 'weights': {name: file_hash(args.runtime / 'paddlex/official_models' / name / 'inference.pdiparams')
                for name in ['PP-FormulaNet_plus-M', 'PP-FormulaNet_plus-S']},
            'katex_js': file_hash(args.katex / 'katex.js'), 'dpi': 288, 'ocr_threads': 3,
            'cache_mode': args.cache_mode, 'native_only':args.native_only,'selection_sha256': file_hash(output / 'selection.json')}
        identity = content_hash(semantic_config)
        identity_path = output / 'run-identity.json'
        if identity_path.exists() and read_json(identity_path)['pipeline_identity'] != identity:
            raise ValueError('PIPELINE_OR_INPUT_CHANGED_USE_NEW_OUTPUT')
        if not identity_path.exists():
            write_json(identity_path, {'pipeline_identity': identity, 'config': semantic_config,
                                      'created_at': now(), 'source_hashes': source_hashes})
        viewer(output, args.katex)
        if args.plan_only:
            result = {'status': 'PLANNED', 'selected_questions': selection['count'],
                      'chapter_counts': selection['chapter_counts'], 'document_counts': selection['document_counts'],
                      'layout_hint_counts': selection.get('layout_hint_counts', {}), 'cache_mode': args.cache_mode}
            write_json(output / 'plan-summary.json', result)
            return result
        precheck = Syntax(args.katex)
        try:
            if precheck('x^2')['status'] != 'PASS':
                raise ValueError('KATEX_PREFLIGHT_FAILED')
        finally:
            precheck.close()
        valid_before = {q['question_id'] for q in chosen if valid_checkpoint(output, q, identity)}
        pending = [q for q in chosen if q['question_id'] not in valid_before]
        cache_index = raw_cache_index(read_json(args.baseline), Path.cwd()) if args.cache_mode == 'import-v1' else {}
        invocation = now().replace(':', '').replace('+', '-') + '-' + uuid.uuid4().hex[:6]
        tasks = build_tasks(pending, documents, output, args.runtime, args.katex, identity, cache_index,
                            chunk_size=args.chunk_size, cache_mode=args.cache_mode,
                            max_page_cache=args.max_page_cache, invocation=invocation,native_only=args.native_only)
        state_path = output / 'batch-state.json'
        state = read_json(state_path) if state_path.exists() else {'invocations': []}
        started_at = now()
        metrics = {}
        stop_error = None
        # Small JSON only while work runs. Aggregate exports are written at the end.
        write_json(output / 'report.json', {'schema_version': 'layout-first-transcription/v2',
            'status': 'RUNNING', 'selected_questions': len(chosen), 'completed_questions': len(valid_before),
            'academic_review': 'PENDING', 'publishable': False, 'cloud_calls': 0,
            'cache_mode': args.cache_mode, 'updated_at': now()})
        def lightweight_catalog(event=None):
            report = read_json(output / 'report.json')
            selected = {q['question_id']: q for q in selection['questions']}
            entries = []
            for path in (output / 'checkpoints').glob('*.json'):
                checkpoint = read_json(path)
                if checkpoint['question_id'] not in selected:
                    continue
                item = dict(checkpoint['catalog_entry'])
                item['evaluation'] = selected[item['question_id']]['evaluation']
                entries.append(item)
            entries.sort(key=lambda item: item['number'])
            report.update(completed_questions=len(entries), updated_at=now(),
                          formula_regions=sum(i['formulas'] for i in entries))
            write_json(output / 'report.json', report)
            write_json(output / 'catalog.json', {'report': report, 'questions': entries})
            if event:
                print('[v2-chunk]', event['chunk_id'], 'exit', event['exit_code'], 'records', len(entries), flush=True)
        lightweight_catalog()
        try:
            metrics = execute_chunks(tasks, output, workers=args.workers, chunk_timeout=args.chunk_timeout,
                run_timeout=args.run_timeout, memory_limit_mb=args.memory_limit_mb,
                min_free_disk_mb=args.min_free_disk_mb, stop_after_chunks=args.stop_after_chunks,
                event=lightweight_catalog)
        except BaseException as error:
            stop_error = error
            metrics = {'stop_reason': type(error).__name__ + ': ' + str(error), 'chunks': []}
        valid_after = {q['question_id'] for q in chosen if valid_checkpoint(output, q, identity)}
        missing = sorted(q['question_id'] for q in chosen if q['question_id'] not in valid_after)
        immutable = file_hash(source) == source_sha and file_hash(args.plan) == plan_sha
        immutable = immutable and all(file_hash(Path(path)) == digest for path, digest in source_hashes.items())
        failed_chunks = [c for c in metrics.get('chunks', []) if c['exit_code'] or c.get('error')]
        if not immutable:
            status = 'SOURCE_INTEGRITY_FAILED'
        elif stop_error or failed_chunks or metrics.get('stop_reason'):
            status = 'INCOMPLETE_DRAFT'
        elif missing and args.stop_after_chunks:
            status = 'PAUSED_DRAFT'
        else:
            status = 'INCOMPLETE_DRAFT' if missing else 'COMPLETE_DRAFT'
        invocation_report = {'invocation_id': invocation, 'started_at': started_at, 'finished_at': now(),
            'status': status, 'resumed_records': len(valid_before), 'new_records': len(valid_after - valid_before),
            'missing_count': len(missing), 'workers': args.workers, 'chunk_size': args.chunk_size,
            'chunk_timeout_seconds': args.chunk_timeout, 'run_timeout_seconds': args.run_timeout,
            'memory_limit_mb': args.memory_limit_mb, 'max_page_cache_per_worker': args.max_page_cache,
            **metrics}
        state['invocations'].append(invocation_report)
        write_json(state_path, state)
        bytes_before_export = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
        report = publish(output, selection, identity, source_sha, valid_after, status=status, extra={
            'cache_mode': args.cache_mode, 'imported_cache_entries': len(cache_index),
            'source_integrity_unchanged': immutable, 'missing_question_ids': missing,
            'resumed_records_this_invocation': len(valid_before), 'new_records_this_invocation': len(valid_after - valid_before),
            'invocation': invocation_report, 'invocations': len(state['invocations']),
            'cumulative_active_seconds': round(sum(i.get('elapsed_seconds', 0) for i in state['invocations']), 3),
            'peak_process_tree_rss_bytes': max(i.get('peak_process_tree_rss_bytes', 0) for i in state['invocations']),
            'disk_bytes_before_final_export': bytes_before_export,
            'cold_cache_definition': 'NO_OCR_CACHE_READS_OR_IMPORTS' if args.cache_mode == 'cold' else None})
        write_json(output / 'runtime.json', {'status': status, 'completed': len(valid_after), 'total': len(chosen),
            'updated_at': now(), 'peak_rss_bytes': report['peak_process_tree_rss_bytes'],
            'elapsed_seconds': report['cumulative_active_seconds'], 'stop_reason': metrics.get('stop_reason')})
        write_json(output / 'benchmark.json', {**invocation_report,
            'output_bytes': sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
            'cumulative_active_seconds': report['cumulative_active_seconds'],
            'academic_review': 'PENDING', 'grading_ready': False, 'source_integrity_unchanged': immutable})
        if stop_error:
            raise stop_error
        return report
