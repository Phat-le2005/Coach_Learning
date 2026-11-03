"""Independent checks and an honest evaluation summary for transcript drafts."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
import re
from pathlib import Path
from jsonschema import Draft202012Validator
from copy import deepcopy

from ..safe_math import UnsupportedMath,parse_expression,latex_plain
from ..storage import file_hash,read_json,write_json,write_jsonl
from .transcript_batch import publish


def numeric_equality(latex):
    if len(latex)>500 or not 1<=latex.count('=')<=3:return {'status':'NOT_ASSESSED'}
    try:
        expressions=[parse_expression(latex_plain(p)).expression for p in latex.split('=')]
        if not all(v.is_Rational for v in expressions):return {'status':'NOT_ASSESSED'}
        ok=all(a==b for a,b in zip(expressions,expressions[1:]))
        return {'status':'PASS' if ok else 'INCONSISTENCY_CANDIDATE',
                'kind':'EXACT_NUMERIC_EQUALITY_IN_SOURCE_DRAFT',
                'values':[str(v) for v in expressions],
                'note':'Check the original image; do not silently rewrite the source or infer a grading rubric.'}
    except (UnsupportedMath,ValueError,TypeError,NotImplementedError):return {'status':'NOT_ASSESSED'}


def inspect_record(record):
    checks=[]
    for f in record['formula_candidates']:
        # Wrong options are expected. Never audit alternatives as reference proofs.
        if f['role']!='solution' or not f.get('display_latex'):continue
        check=numeric_equality(f['display_latex'])
        if check['status']!='NOT_ASSESSED':checks.append({'formula_id':f['formula_id'],
            'asset_path':f['asset_path'],'latex':f['display_latex'],'method':f['method'],**check})
    return {'question_id':record['question_id'],'collection_number':record['collection_number'],
            'source_sha256':record['source']['sha256'],'checks':checks,
            'academic_review':'PENDING','publishable':False}


def inspect_assets(output,records):
    output=Path(output).resolve();errors=[];checked=set()
    for q in records:
        assets=[(f['asset_path'],f['asset_sha256']) for f in q['formula_candidates']]
        assets += [(f['source_asset'],f['source_asset_sha256']) for p in q['parts'].values() for f in p['fragments']]
        for relative,digest in assets:
            if (relative,digest) in checked:continue
            checked.add((relative,digest));path=(output/relative).resolve()
            issue=None
            if not path.is_relative_to(output) or not relative.startswith('assets/'):issue='ASSET_PATH_OUTSIDE_OUTPUT'
            elif not path.is_file():issue='ASSET_MISSING'
            elif file_hash(path)!=digest:issue='ASSET_HASH_MISMATCH'
            if issue:errors.append({'question_id':q['question_id'],'asset_path':relative,'issue':issue})
    return {'checked_assets':len(checked),'errors':errors}


def content_record(record):
    """Readable content projection; full records retain raw/glyph diagnostics."""
    label=record['source_label']
    heading=re.search(r'(?:Câu|Bài|Ví dụ|Example)\s*\d',label,re.I)
    if heading:label=label[heading.start():]
    return {'question_id':record['question_id'],'collection_number':record['collection_number'],
        'chapter_title':record['chapter_title'],'source_label':label,
        'question_markdown':record['parts']['question']['markdown'],
        'choices':deepcopy(record['parts']['question']['choices']),
        'solution_markdown':record['parts']['solution']['markdown'],
        'answer_markdown':record['parts']['answer']['markdown'],'source':deepcopy(record['source']),
        'source_images':[{'role':role,'page_number':f['page_number'],'bbox':f['bbox'],
            'asset_path':f['source_asset'],'asset_sha256':f['source_asset_sha256']}
            for role,p in record['parts'].items() for f in p['fragments']],
        'transcript_status':record['transcript_status'],'issues':deepcopy(record['issues']),
        'academic_review':record['academic_review'],'grading_support':record['grading_support'],
        'publishable':record['publishable']}


def run(output):
    output=Path(output);selection=read_json(output/'selection.json')
    evaluation={q['question_id'] for q in selection['questions'] if q['evaluation']}
    records=[read_json(p) for p in sorted((output/'records').glob('*.json'))]
    report=read_json(output/'report.json')
    allowed={q['question_id'] for q in selection['questions']}
    records=[q for q in records if q['question_id'] in allowed and q.get('pipeline_identity')==report['pipeline_identity']]
    schema=read_json(Path(__file__).parents[2]/'schemas/paired-transcript-draft.v1.schema.json')
    validator=Draft202012Validator(schema)
    schema_errors=[{'question_id':q['question_id'],'path':list(e.absolute_path),'message':e.message}
        for q in records for e in validator.iter_errors(q)]
    checks=[inspect_record(q) for q in records]
    assets=inspect_assets(output,records)
    formulas=[f for q in records for f in q['formula_candidates']]
    eval_rows=[q for q in records if q['question_id'] in evaluation]
    review=[]
    for p in (output/'reviews').glob('*.json'):
        r=read_json(p)
        if r['question_id'] in evaluation and any(q['question_id']==r['question_id'] for q in records):review.append(r)
    metrics={'selected_records':selection['count'],'exported_records':len(records),
        'evaluation_selected':len(evaluation),'evaluation_exported':len(eval_rows),
        'evaluation_chapters':dict(Counter(q['chapter_id'] for q in eval_rows)),
        'evaluation_source_documents':len({q['source']['sha256'] for q in eval_rows}),
        'formula_regions':len(formulas),'syntax_counts':dict(Counter(f['syntax']['status'] for f in formulas)),
        'source_review_image_fallbacks':sum(not f.get('display_latex') for f in formulas),
        'ocr_digit_conflict_regions':sum('SOURCE_DIGITS_CHANGED' in f.get('transcription_checks',{}).get('issues',[]) for f in formulas),
        'model_disagreement_regions':sum('LOCAL_FORMULA_MODELS_DISAGREE' in f.get('transcription_checks',{}).get('issues',[]) for f in formulas),
        'question_statuses':dict(Counter(q['transcript_status'] for q in records)),
        'source_image_only_extraction_failed_records':sum(q.get('transcript_status')=='SOURCE_IMAGE_ONLY_EXTRACTION_FAILED' for q in records),
        'failed_attempt_model_calls_fully_accounted':not any(q.get('rescue') for q in records),
        'advisory_review_statuses':dict(Counter(r['status'] for r in review)),
        'advisory_verdicts':dict(Counter(r['result']['verdict'] for r in review if r['status']=='ADVISORY_COMPLETE')),
        'numeric_equality_check_counts':dict(Counter(c['status'] for q in checks for c in q['checks'])),
        'schema_errors':len(schema_errors),
        'asset_files_checked':assets['checked_assets'],'asset_errors':len(assets['errors']),
        'academic_review':'PENDING','publishable':False,'cloud_calls':0,
        'not_measured':['FULL_FORMULA_DETECTION_RECALL','TRANSCRIPTION_ACCURACY_AGAINST_COMPLETE_GOLD','WHOLE_SOLUTION_MATHEMATICAL_CORRECTNESS'],
        'ready_for_full_corpus_core_ingestion':False,
        'policy':'Automated diagnostics on a fixed sample. Source images retained; no model approval or silent correction.'}
    write_jsonl(output/'reference-checks.jsonl',checks)
    content=[content_record(q) for q in sorted(records,key=lambda q:q['collection_number'])]
    write_jsonl(output/'content.draft.jsonl',content)
    write_json(output/'content.draft.pretty.json',content)
    write_json(output/'evaluation-40.json',{'metrics':metrics,
        'questions':[{'question_id':q['question_id'],'number':q['collection_number'],'source':q['source'],
            'transcript_status':q['transcript_status'],'issues':q['issues'],
            'formula_count':len(q['formula_candidates'])} for q in eval_rows]})
    write_json(output/'quality-summary.json',metrics)
    write_json(output/'schema-errors.json',schema_errors)
    write_json(output/'asset-errors.json',assets['errors'])
    # A rescue may add a source-only record after the main worker export.
    # Rebuild all views from the same records rather than leaving a 99-item JSONL
    # alongside a 100-item content projection.
    refreshed=publish(output,selection,report['pipeline_identity'],report['source_jsonl_sha256'])
    for key in ['elapsed_seconds','peak_process_tree_rss_bytes','workers','monitor_recovered','failures']:
        if key in report:refreshed[key]=report[key]
    if len(records)!=selection['count']:refreshed['status']='INCOMPLETE_DRAFT'
    refreshed['qwen_review_files']=len(review)
    write_json(output/'report.json',refreshed)
    catalog=read_json(output/'catalog.json');catalog['report']=refreshed
    for entry in catalog['questions']:
        review_path='reviews/'+Path(entry['record']).name
        if (output/review_path).is_file():entry['qwen_review']=review_path
    catalog['report']['qwen_review_files']=len(review)
    write_json(output/'catalog.json',catalog)
    lines=['# Báo cáo bản nháp nội dung toán','',
        f"Đã xuất {len(records)}/{selection['count']} câu; bộ đánh giá có {len(eval_rows)}/{len(evaluation)} câu.",
        f"Tìm được {len(formulas)} vùng công thức; giữ ảnh thay công thức chưa đủ kiểm tra ở {metrics['source_review_image_fallbacks']} vùng.",
        '', '## Kiểm tra tự động','',
        '```json',json.dumps(metrics,ensure_ascii=False,indent=2),'```','',
        'Đây là bản nháp phục vụ đối chiếu, chưa đưa trực tiếp vào core chấm. Số công thức render được và nhận xét Qwen không phải độ chính xác học thuật.',
        'Các trường hợp chưa khớp được giữ bằng ảnh nguồn. Không tự sửa phương án nhiễu hoặc lỗi có sẵn trong lời giải in.',
        '', '## File dùng tiếp','',
        '- `content.draft.pretty.json`: đề, lựa chọn, lời giải, nguồn và cảnh báo; không chứa text thô lỗi font.',
        '- `metadata.transcribed.draft.jsonl`: dữ liệu theo từng câu để xử lý tiếp.',
        '- `metadata.transcribed.draft.pretty.json`: cùng dữ liệu, trình bày dễ đọc.',
        '- `evaluation-40.json`: kết quả kiểm tra của bộ 40 câu cố định.',
        '- `reference-checks.jsonl`: kiểm tra đẳng thức số trong lời giải, có ảnh truy nguyên.',
        '- `reviews/`: nhận xét Qwen local từ metadata; không có ảnh đầu vào.',
        '- `selection.json`: danh sách mẫu, seed, chương, nguồn và phân chia đánh giá.','']
    (output/'quality-summary.md').write_text('\n'.join(lines),encoding='utf-8')
    return metrics


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    result=run(p.parse_args().output)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['schema_errors'] or result['asset_errors'] or result['exported_records']!=result['selected_records']:sys.exit(1)
