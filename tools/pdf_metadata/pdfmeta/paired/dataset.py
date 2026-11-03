from __future__ import annotations

import base64
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

from jsonschema import Draft202012Validator

from ..assemble import assemble
from ..native import extract_native
from ..pdf_workflow import local_lock
from ..review import crop_sources
from ..storage import file_hash, read_json, write_json, write_jsonl


VERSION = 'paired-source-dataset/v1'
PAYLOAD_ID = 'paired-dataset'
SECTION = re.compile(r'^\s*(?:DẠNG\s+\d|PHẦN\s+[A-ZIVX\d]|CHỦ ĐỀ\b|BÀI TẬP\b|LÝ THUYẾT\b)', re.I)


def schema():
    span = {'type': 'object', 'required': ['page_number', 'bbox', 'block_ids'],
            'properties': {'page_number': {'type': 'integer', 'minimum': 1},
                           'bbox': {'type': 'array', 'minItems': 4, 'maxItems': 4, 'items': {'type': 'number'}},
                           'block_ids': {'type': 'array', 'items': {'type': 'string'}}}}
    part = {'type': 'object', 'required': ['text_lossy', 'source_spans'],
            'properties': {'text_lossy': {'type': 'string'},
                           'source_spans': {'type': 'array', 'items': span}}}
    question = {'type': 'object', 'required': ['question_id', 'source_number', 'question', 'solution', 'answer',
                    'pair_status', 'quality_flags', 'academic_review', 'grading_support', 'publishable'],
                'properties': {'question_id': {'type': 'string', 'minLength': 1},
                    'source_number': {'type': 'integer', 'minimum': 0}, 'question': part, 'solution': part,
                    'answer': {'type': 'object', 'required': ['text_raw', 'source_spans', 'status'],
                        'properties': {'text_raw': {'type': ['string', 'null']},
                            'source_spans': {'type': 'array', 'items': span},
                            'status': {'enum': ['EXPLICIT_SOURCE_LABEL_UNVERIFIED', 'NOT_EXPLICITLY_LABELLED']}}},
                    'pair_status': {'enum': ['PAIRED_LAYOUT_CANDIDATE', 'MISSING_QUESTION', 'MISSING_SOLUTION']},
                    'quality_flags': {'type': 'array', 'items': {'type': 'string'}},
                    'academic_review': {'const': 'PENDING'}, 'grading_support': {'const': 'NOT_ASSESSED'},
                    'publishable': {'const': False}}}
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema', 'type': 'object',
        'required': ['schema_version', 'source', 'policy', 'questions', 'unassigned_blocks', 'page_coverage', 'images'],
        'properties': {'schema_version': {'const': VERSION},
            'source': {'type': 'object', 'required': ['name', 'sha256', 'page_count'], 'properties': {
                'name': {'type': 'string'}, 'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                'page_count': {'type': 'integer', 'minimum': 1}}},
            'policy': {'type': 'object', 'required': ['production_grade', 'cloud_api_calls', 'local_inference_calls'],
                'properties': {'production_grade': {'const': False}, 'cloud_api_calls': {'const': 0},
                    'local_inference_calls': {'const': 0}}},
            'questions': {'type': 'array', 'items': question}, 'unassigned_blocks': {'type': 'array'},
            'page_coverage': {'type': 'array'}, 'images': {'type': 'object'}}}


def validate(payload, *, embedded=True):
    Draft202012Validator(schema()).validate(payload)
    ids = [q['question_id'] for q in payload['questions']]
    if len(ids) != len(set(ids)):
        raise ValueError('DUPLICATE_QUESTION_ID')
    page_count = payload['source']['page_count']
    for q in payload['questions']:
        for part in ['question', 'solution', 'answer', 'collection_source_spans']:
            spans=q.get(part,[]) if part=='collection_source_spans' else q[part]['source_spans']
            for span in spans:
                if not 1 <= span['page_number'] <= page_count:
                    raise ValueError('PAGE_OUTSIDE_SOURCE')
                x0, y0, x1, y1 = span['bbox']
                if not (0 <= x0 < x1 and 0 <= y0 < y1):
                    raise ValueError('INVALID_SOURCE_BOX')
                key = span.get('asset_path')
                if key and key not in payload['images']:
                    raise ValueError('MISSING_SOURCE_IMAGE')
    for key, image in payload['images'].items():
        if not re.fullmatch(r'assets/[A-Za-z0-9_-]+\.png', key):
            raise ValueError('IMAGE_PATH_NOT_ALLOWED')
        if embedded:
            data = image.get('data_url', '')
            if not data.startswith('data:image/png;base64,'):
                raise ValueError('IMAGE_FORMAT_NOT_ALLOWED')
            raw = base64.b64decode(data.split(',', 1)[1], validate=True)
            if not raw.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(raw).hexdigest() != image['sha256']:
                raise ValueError('SOURCE_IMAGE_CHANGED')


def compose(items, orphans, pages, source, output):
    records = []
    for item in items:
        flags = set(item['review_flags']) | {'NATIVE_TEXT_IS_LOSSY', 'MATHEMATICS_NOT_VERIFIED'}
        if any(SECTION.match(line) for line in item['solution']['text_raw'].splitlines()):
            flags.add('POSSIBLE_SECTION_CONTEXT_ATTACHED_TO_SOLUTION')
        part = lambda name: {'text_lossy': item[name]['text_raw'].strip(),
                             'source_spans': deepcopy(item[name]['source_spans'])}
        question, solution = part('stem'), part('solution')
        pair_status = 'MISSING_QUESTION' if not question['text_lossy'] else 'MISSING_SOLUTION' if not solution['text_lossy'] else 'PAIRED_LAYOUT_CANDIDATE'
        records.append({'question_id': item['question_id'], 'source_number': item['source_number'],
            'source_label': item.get('source_label'),
            'question': question, 'solution': solution,
            'boundary_resolution': item.get('boundary_resolution'),
            'answer': {'text_raw': item['answer']['text_raw'], 'source_spans': deepcopy(item['answer']['source_spans']),
                'status': 'EXPLICIT_SOURCE_LABEL_UNVERIFIED' if item['answer']['text_raw'] else 'NOT_EXPLICITLY_LABELLED'},
            'pair_status': pair_status, 'quality_flags': sorted(flags), 'academic_review': 'PENDING',
            'grading_support': 'NOT_ASSESSED', 'publishable': False})
    images = {}
    for q in records:
        for role in ['question', 'solution', 'answer']:
            for span in q[role]['source_spans']:
                if 'asset_path' not in span:
                    continue
                key = span['asset_path']; path = output / key
                images[key] = {'sha256': file_hash(path),
                    'data_url': 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')}
    coverage = []
    for page in pages:
        ids = [q['question_id'] for q in records if any(s['page_number'] == page['page_number']
            for role in ['question', 'solution', 'answer'] for s in q[role]['source_spans'])]
        coverage.append({'page_number': page['page_number'], 'question_ids': ids,
            'status': 'QUESTION_REGIONS_FOUND' if ids else 'OCR_REQUIRED' if not page['blocks'] else 'NO_QUESTION_REGION_FOUND'})
    payload = {'schema_version': VERSION, 'source': source,
        'policy': {'production_grade': False, 'cloud_api_calls': 0, 'local_inference_calls': 0,
            'images': 'SOURCE_EVIDENCE_NOT_MATHEMATICAL_APPROVAL', 'text': 'LOSSY_NATIVE_SEARCH_HELPER',
            'answer': 'ONLY_EXPLICIT_SOURCE_LABEL_NO_INFERRED_EXPECTED_ANSWER',
            'steps': 'KEEP_WHOLE_SOURCE_SOLUTION_NO_FORCED_RUBRIC'},
        'questions': records, 'unassigned_blocks': orphans, 'page_coverage': coverage, 'images': images}
    validate(payload)
    return payload


def from_html(path):
    html = Path(path).read_text(encoding='utf-8')
    match = re.search(r'<script type="application/json" id="paired-dataset">(.*?)</script>', html, re.S)
    if not match:
        raise ValueError('PAIRED_DATASET_PAYLOAD_NOT_FOUND')
    payload = json.loads(match.group(1))
    validate(payload)
    return payload


def export(html, output):
    """Metadata is read from the single converted file, never re-OCRed."""
    html, output = Path(html).resolve(), Path(output).resolve()
    payload = from_html(html)
    # The single HTML is portable: a fresh export recreates its source crops.
    for key, image in payload['images'].items():
        target = output / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(image['data_url'].split(',', 1)[1], validate=True))
    compact = deepcopy(payload)
    for image in compact['images'].values():
        image.pop('data_url', None)
    paired = [q for q in payload['questions'] if q['pair_status'] == 'PAIRED_LAYOUT_CANDIDATE']
    unpaired = [q for q in payload['questions'] if q['pair_status'] != 'PAIRED_LAYOUT_CANDIDATE']
    compact['questions'] = paired
    compact['unpaired_questions'] = unpaired
    compact['metadata_export_policy'] = 'PAIRED_SOURCE_CANDIDATES_ONLY_NOT_ACADEMIC_APPROVAL'
    write_json(output / 'questions.metadata.json', compact)
    write_jsonl(output / 'questions.metadata.jsonl', [
        {'schema_version': 'paired-question/v1', 'source': payload['source'], **q} for q in paired])
    write_jsonl(output / 'questions.unpaired.jsonl', [
        {'schema_version': 'paired-question/v1', 'source': payload['source'], **q} for q in unpaired])
    write_json(output / 'metadata.schema.json', schema())
    return {'html_sha256': file_hash(html), 'metadata_json': str(output / 'questions.metadata.json'),
            'metadata_jsonl': str(output / 'questions.metadata.jsonl'),
            'metadata_question_count': len(paired), 'unpaired_question_count': len(unpaired),
            'metadata_sha256': file_hash(output / 'questions.metadata.json')}


def build(pdf, job):
    from .viewer import render
    pdf, job = Path(pdf).resolve(), Path(job).resolve()
    digest = file_hash(pdf)
    job.mkdir(parents=True, exist_ok=True)
    with local_lock(job):
        snapshot = job / 'input.pdf'
        if snapshot.exists() and file_hash(snapshot) != digest:
            raise ValueError('JOB_BELONGS_TO_ANOTHER_PDF')
        if not snapshot.exists():
            shutil.copy2(pdf, snapshot)
        manifest, pages = extract_native(snapshot, job / 'native', dpi=110)
        # Reuse source line IDs, question IDs and cross-page assembly.
        items, orphans = assemble(pages, digest)
        from .boundaries import detach
        items, orphans, boundary_audit = detach(items, pages, orphans)
        code = {str(p.name): file_hash(p) for p in Path(__file__).parent.iterdir() if p.suffix in {'.py', '.html'}}
        for helper in ['assemble.py', 'native.py', 'review.py']:
            code[helper] = file_hash(Path(__file__).parents[1] / helper)
        version = hashlib.sha256(json.dumps({'source': digest, 'code': code,
            'pages': {str(p['page_number']): file_hash(job / 'native/pages' / f"page-{p['page_number']:03}.json")
                for p in pages},
            'images': {str(p['page_number']): file_hash(job / 'native' / p['image_path']) for p in pages}},
            sort_keys=True).encode()).hexdigest()[:16]
        output = job / 'paired/versions' / version
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / 'boundary-audit.json', boundary_audit)
        # Shared cropper reads native page images relative to its output root.
        for page in pages:
            page['image_path'] = str((job / 'native' / page['image_path']).resolve())
        crop_sources(items, pages, output)
        from ..validate import validate_candidates
        # The resolution annotation belongs to the paired contract, not to the
        # older acquisition schema. All original content/spans are still checked.
        structure = validate_candidates([{k:v for k,v in item.items() if k != 'boundary_resolution'} for item in items], pages, output)
        payload = compose(items, orphans, pages, {'name': pdf.name, 'sha256': digest,
            'page_count': manifest['page_count'], 'coordinate_unit': 'pdf_point', 'coordinate_origin': 'top-left'}, output)
        html = output / 'questions-and-solutions.html'
        render(html, payload)
        exports = export(html, output)
        if file_hash(pdf) != digest or file_hash(snapshot) != digest:
            raise ValueError('SOURCE_CHANGED_DURING_CONVERSION')
        report = {'schema_version': VERSION, 'status': 'SOURCE_PAIRED_DRAFT',
            'source': payload['source'], 'question_count': len(items),
            'pair_status_counts': dict(Counter(q['pair_status'] for q in payload['questions'])),
            'explicit_answer_count': sum(q['answer']['text_raw'] is not None for q in payload['questions']),
            'cross_page_questions': sum(len({s['page_number'] for role in ['question', 'solution', 'answer']
                for s in q[role]['source_spans']}) > 1 for q in payload['questions']),
            'page_coverage_counts': dict(Counter(p['status'] for p in payload['page_coverage'])),
            'quality_flag_counts': dict(Counter(f for q in payload['questions'] for f in q['quality_flags'])),
            'unassigned_block_count': len(orphans), 'source_image_count': len(payload['images']),
            'detached_section_boundaries': len(boundary_audit),
            'structural_errors': structure['structural_errors'],
            'single_file_html': str(html), 'single_file_bytes': html.stat().st_size, **exports,
            'source_unchanged': True, 'cloud_api_calls': 0, 'local_inference_calls': 0,
            'grading_ready_count': 0, 'publishable_count': 0}
        write_json(output / 'report.json', report)
        write_json(job / 'paired.json', report)
        write_json(output / 'pairing-review-queue.json', [
            {'question_id': q['question_id'], 'source_number': q['source_number'],
                'pair_status': q['pair_status'], 'flags': q['quality_flags']} for q in payload['questions']])
        stable = job / 'paired/review.html'
        stable.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=versions/' + version + '/questions-and-solutions.html">', encoding='utf-8')
        return report
