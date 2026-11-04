"""Evaluate bounded, source-transcribed formula samples without fitting to holdout."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from html import escape
import json
import os
from pathlib import Path
import re

from ..latex_stage import catalog,normalize_formula
from ..safe_math import assignment,equivalent
from ..source_layout import resolve
from ..storage import file_hash,read_json,write_json


def assess(row,gold):
    if row is None or row.get('status')!='NORMALIZED':return 'DEFERRED'
    value=row['latex']
    for feature in gold.get('required_features',[]):
        if feature=='overline' and not re.search(r'\\(?:overline|bar)',value):return 'WRONG'
        if feature=='sqrt' and not re.search(r'\\sqrt|sqrt\(',value):return 'WRONG'
        if feature=='absolute_value' and not re.search(r'\||\\[lr]?vert|abs\(',value):return 'WRONG'
        if feature=='subscript' and '_' not in value:return 'WRONG'
        if feature=='unit_suffix' and not row.get('units_raw'):return 'WRONG'
        if feature=='function_application' and not re.search(r'\bf\s*(?:\\left)?\(',value):return 'WRONG'
    try:return 'CORRECT' if equivalent(assignment(value),assignment(gold['expected_latex'])) else 'WRONG'
    except (ValueError,TypeError,NotImplementedError):return 'UNASSESSED'


def pick(rows,case,item):
    if case['baseline_selected_latex'] is None:return None
    text_id='stem' if case['part']=='stem' else next(s['step_id'] for s in item['reference_solution']['math_audit']['steps'] if s['number']==case['part'])
    return next((r for r in rows if r['origin']=='GEOMETRY_OR_OCR' and r['text_id']==text_id
                 and r['raw_text']==case['baseline_selected_latex']),None)


def run(directory,pilot_job,baseline_file,*,repo=None):
    directory,pilot_job,baseline_file=(Path(p).resolve() for p in (directory,pilot_job,baseline_file))
    repo=Path(repo).resolve() if repo else Path(__file__).parents[4]
    freeze=read_json(directory/'frozen-candidate.json')
    changed=[path for path,digest in freeze['files'].items() if file_hash(repo/path)!=digest]
    if changed:raise ValueError('PRODUCTION_CHANGED_AFTER_HOLDOUT_FREEZE: '+','.join(changed))
    cases=read_json(directory/'pilot-sample.json')+read_json(directory/'external-sample.json')
    gold={g['id']:g for g in read_json(directory/'gold-all.json')}
    if len(gold)!=len(cases) or set(gold)!={c['id'] for c in cases}:raise ValueError('SOURCE_LABEL_CASE_MISMATCH')
    baseline=read_json(baseline_file)
    if not baseline:raise ValueError('BASELINE_HAS_NO_SOURCE_RECORDS')
    source_file=Path(baseline[0]['source_metadata_file']).resolve()
    root=source_file.parent.parent
    if not root.is_relative_to(pilot_job/'versions'):raise ValueError('BASELINE_SOURCE_OUTSIDE_PILOT_JOB')
    items=[json.loads(line) for line in (root/'metadata/questions.jsonl').read_text(encoding='utf-8').splitlines()]
    page_lookup={p['page_number']:p for p in (read_json(f) for f in (root/'pilot/pages').glob('page-*.json'))}
    results=[];cache={}
    for case in cases:
        label=gold[case['id']];before=None;after=None
        if case['split']=='external_holdout':
            page=read_json(directory/f"external-native/pages/page-{case['page_number']:03}.json")
            selected=case.get('selected_latex')
            if selected:
                candidate=next(c for c in case['candidates'] if c['latex']==selected)
                try:
                    value,proof=resolve(page,candidate)
                    after={'status':'NORMALIZED','latex':normalize_formula(value),'source_layout_evidence':proof}
                except (ValueError,TypeError,NotImplementedError) as error:
                    after={'status':'DEFERRED','latex':None,'reason':str(error)}
        else:
            found=[i for i in items if i['source_number']==case['source_number']]
            if len(found)!=1:raise ValueError('AUDIT_SOURCE_NUMBER_NOT_UNIQUE')
            item=found[0]
            old=next(b for b in baseline if b['question_id']==item['question_id'])
            before=pick(old['latex_normalization'],case,item)
            if item['question_id'] not in cache:cache[item['question_id']]=catalog(item,page_lookup)[1]
            after=pick(cache[item['question_id']],case,item)
        result={'id':case['id'],'split':case['split'],'source_pdf_sha256':case['source_pdf_sha256'],
                'page_number':case['page_number'],'source_number':case['source_number'],'bbox':case['bbox'],
                'source_crop':case['crop_path'],'gold':label,'baseline':before,'candidate':after,
                'before':'NOT_BASELINED' if case['split']=='external_holdout' else assess(before,label),
                'after':assess(after,label)}
        results.append(result)
    groups=defaultdict(list)
    for result in results:groups[result['split']].append(result)
    report={'schema_version':'formula-source-audit/v1','sample_count':len(results),
        'selection':'TARGETED_DIAGNOSTIC_SAMPLE_NOT_RANDOM','comparison':'EXPRESSION_FIDELITY_WITH_REQUIRED_SOURCE_STRUCTURES',
        'scope':'FORMULA_CANDIDATES_IN_SPECIFIED_SOURCE_REGIONS_NOT_END_TO_END_GRADING_ACCURACY',
        'baseline_file':str(baseline_file),'baseline_sha256':file_hash(baseline_file),
        'source_metadata_file':str(source_file),'source_metadata_sha256':file_hash(source_file),
        'production_frozen_files_verified':True,'source_images_manually_reviewed':True,
        'before':dict(Counter(r['before'] for r in results if r['before']!='NOT_BASELINED')),
        'after':dict(Counter(r['after'] for r in results)),
        'by_split':{split:{'count':len(rows),'before':dict(Counter(r['before'] for r in rows)),
                           'after':dict(Counter(r['after'] for r in rows))} for split,rows in groups.items()},
        'cloud_api_calls':0,'academic_approved_count':0,'grading_ready_count':0}
    write_json(directory/'audit-results.json',results);write_json(directory/'audit-report.json',report)
    view(directory,results,report,repo)
    return report


def view(directory,results,report,repo):
    e=lambda value:escape(str(value),quote=True)
    html='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đối chiếu công thức với nguồn</title><style>body{font:15px/1.7 system-ui;color:#234;background:#f3f7fa;max-width:1200px;margin:28px auto;padding:0 24px}details{background:white;border:1px solid #cfdce5;border-radius:12px;margin:14px 0;padding:18px}summary{cursor:pointer;font-weight:650}img{max-width:100%;height:auto}.math{padding:14px 0;overflow:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere}.notice{background:#fff2d4;padding:18px;border-radius:12px}a{color:#007466}</style><h1>Đối chiếu công thức với ảnh PDF</h1>'''
    html+='<div class="notice">Mẫu chẩn đoán có chủ đích, không phải benchmark ngẫu nhiên. CORRECT đánh giá phần biểu thức được chỉ định và các cấu trúc bắt buộc; không xác nhận lời giải/đáp án. Các điều kiện được ghi riêng; không tính thành độ chính xác toàn bài.</div><pre>'+e(json.dumps(report['by_split'],ensure_ascii=False,indent=2))+'</pre><p><a href="audit-report.json">Báo cáo JSON</a> · <a href="audit-results.json">Từng trường hợp</a></p>'
    for row in results:
        source=Path(os.path.relpath(row['source_crop'],directory)).as_posix()
        html+='<details><summary>'+e(row['id'])+' · '+e(row['split'])+' · '+e(row['before'])+' → '+e(row['after'])+'</summary><img loading="lazy" src="'+e(source)+'" alt="Công thức nguồn"><h3>Bản chép từ ảnh</h3><div class="math" data-latex="'+e(row['gold']['expected_latex'])+'"></div>'
        for title,key in [('Trước sửa','baseline'),('Sau sửa','candidate')]:
            value=row[key] or {};html+='<h3>'+title+'</h3><div class="math" data-latex="'+e(value.get('latex') or '')+'"></div><pre>'+e(value.get('reason') or value.get('status') or 'Không có bản chọn hợp lệ')+'</pre>'
        html+='</details>'
    dist=repo/'frontend/node_modules/katex/dist'
    if dist.exists():
        prefix=Path(os.path.relpath(dist,directory)).as_posix()
        html+='<link rel="stylesheet" href="'+e(prefix)+'/katex.min.css"><script src="'+e(prefix)+'/katex.min.js"></script><script>for(const n of document.querySelectorAll(".math")){try{katex.render(n.dataset.latex,n,{throwOnError:false,trust:false,maxExpand:100});}catch(e){}}</script>'
    (directory/'review.html').write_text(html+'</html>',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample-dir',type=Path,required=True);parser.add_argument('--pilot-job',type=Path,required=True)
    parser.add_argument('--baseline-file',type=Path,required=True);parser.add_argument('--repo',type=Path)
    args=parser.parse_args();print(json.dumps(run(args.sample_dir,args.pilot_job,args.baseline_file,repo=args.repo),ensure_ascii=False,indent=2))
