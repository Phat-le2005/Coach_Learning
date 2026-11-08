"""Stream large final exports once; keep dashboard catalog small."""
from collections import Counter
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import time
import uuid

from ...storage import read_json, write_json
from ..transcript_batch import now
from . import VERSION
from .checkpoints import record_name


def compact_content(row):
    """Shared public content shape; acquisition methods keep their own provenance."""
    content = {'collection_number': row['collection_number'], 'question_id': row['question_id'],
            'chapter_title': row['chapter_title'], 'source': row['source'],
            'question': row['parts']['question'], 'solution': row['parts']['solution'],
            'answer': row['parts']['answer'], 'tables': row['tables'],
            'academic_review': 'PENDING', 'grading_support': 'NOT_ASSESSED', 'publishable': False}
    if 'visual_assets' in row:
        content['visual_assets'] = row['visual_assets']
    for key in ['topic_context', 'source_number']:
        if key in row:content[key] = row[key]
    return content


@contextmanager
def atomic_text(path):
    pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        with pending.open('w', encoding='utf-8', newline='\n') as stream:
            yield stream
        for attempt in range(20):
            try:
                pending.replace(path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.05)
    finally:
        pending.unlink(missing_ok=True)


def publish(output, selection, identity, source_sha, valid_ids, *, status, extra=None):
    output = Path(output)
    catalog, formulas, syntax, methods, checks, issues, statuses, chapters = [], Counter(), Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    documents = set()
    metrics = Counter()
    names = ['metadata.transcribed.draft.jsonl', 'metadata.transcribed.draft.pretty.json',
             'content.draft.jsonl', 'content.draft.pretty.json']
    with ExitStack() as stack:
        streams = [stack.enter_context(atomic_text(output / name)) for name in names]
        streams[1].write('[\n')
        streams[3].write('[\n')
        for item in sorted(selection['questions'], key=lambda q: q['collection_number']):
            if item['question_id'] not in valid_ids:
                continue
            row = read_json(output / 'records' / record_name(item['question_id']))
            content = compact_content(row)
            for stream, value in [(streams[0], row), (streams[2], content)]:
                stream.write(json.dumps(value, ensure_ascii=False) + '\n')
            for stream, value in [(streams[1], row), (streams[3], content)]:
                if catalog:
                    stream.write(',\n')
                stream.write(json.dumps(value, ensure_ascii=False, indent=2))
            catalog.append({'question_id': row['question_id'], 'number': row['collection_number'],
                            'label': row['source_label'], 'chapter_id': row['chapter_id'],
                            'chapter_title': row['chapter_title'], 'source_name': row['source']['name'],
                            'evaluation': item['evaluation'], 'status': row['transcript_status'],
                            'issues': len(row['issues']), 'formulas': len(row['formula_candidates']),
                            'record': 'records/' + record_name(row['question_id'])})
            documents.add(row['source']['sha256'])
            chapters[row['chapter_id']] += 1
            statuses[row['transcript_status']] += 1
            issues.update(i['code'] for i in row['issues'])
            for formula in row['formula_candidates']:
                formulas['total'] += 1
                formulas['display'] += bool(formula.get('display_latex'))
                formulas['failed'] += bool(formula.get('region_error'))
                syntax[formula['syntax']['status']] += 1
                methods[formula['method']] += 1
                checks.update(formula.get('transcription_checks', {}).get('issues', []))
            metrics['table_regions'] += len(row['tables'])
            for table in row['tables']:
                metrics['table_cells'] += len(table['cells'])
                metrics['table_cells_native_draft'] += sum(c['display_text'] is not None for c in table['cells'])
            for key in ['model_calls', 'secondary_model_calls', 'ocr_cache_hits']:
                metrics[key] += row['runtime'].get(key, 0)
            metrics['max_worker_rss_bytes'] = max(metrics['max_worker_rss_bytes'], row['runtime']['rss_bytes'])
        streams[1].write('\n]\n')
        streams[3].write('\n]\n')
    report = {
        'schema_version': VERSION, 'status': status, 'updated_at': now(),
        'pipeline_identity': identity, 'source_jsonl_sha256': source_sha,
        'selected_questions': selection['count'], 'completed_questions': len(catalog),
        'evaluation_selected': selection['evaluation_count'],
        'evaluation_completed': sum(q['evaluation'] for q in catalog),
        'chapter_counts': dict(chapters), 'source_documents': len(documents),
        'formula_regions': formulas['total'], 'displayed_latex_regions': formulas['display'],
        'image_fallback_regions': formulas['total'] - formulas['display'],
        'failed_regions': formulas['failed'], 'syntax_counts': dict(syntax),
        'methods': dict(methods), 'transcription_check_counts': dict(checks),
        'question_statuses': dict(statuses), 'issue_counts': dict(issues),
        **dict(metrics), 'total_model_calls': metrics['model_calls'],
        'source_glyph_coverage_is_heuristic': True, 'mathematical_accuracy_established': False,
        'academic_review': 'PENDING', 'publishable': False, 'grading_support': 'NOT_ASSESSED',
        'cloud_calls': 0, 'full_grading_ready': False, 'source_images_provided_to_vision_model': False,
        'vision_stage': 'NOT_RUN', 'qwen_review_files': 0,
        'export_policy': 'STREAM_RECORDS_ONCE_AT_INVOCATION_END',
        **(extra or {}),
    }
    write_json(output / 'report.json', report)
    write_json(output / 'catalog.json', {'report': report, 'questions': catalog})
    return report
