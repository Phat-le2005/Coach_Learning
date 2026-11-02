"""Complete a PDF job: text-to-LaTeX, local review, consolidated final artifact."""
from __future__ import annotations

import argparse
from collections import Counter,defaultdict
from copy import deepcopy
from datetime import datetime,timezone
from html import escape
import json
import os
from pathlib import Path
import shutil
import time

from jsonschema import Draft202012Validator

from ..gemini_client import content_hash
from ..gemini_contracts import obj,arr
from ..latex_stage import run as normalize
from ..local_client import LocalClient,LocalConfig
from ..pdf_workflow import local_lock
from ..qwen_review import run as review
from ..storage import file_hash,read_json,write_json,write_jsonl
from ..progress import Progress


FINAL_SCHEMA=obj(schema_version={'const':'pdf-final/v1'},question_id={'type':'string'},
    source_number={'type':'integer'},source_metadata_file={'type':'string'},source_metadata={'type':'object'},
    latex_normalization=arr({'type':'object'}),machine_review={'type':'object'},
    processing_status={'enum':['MACHINE_CLEARED','MACHINE_FLAGGED','DEFERRED']},
    academic_review={'const':'PENDING'},grading_support={'const':'NOT_ASSESSED'},publishable={'const':False})


def apply_source_guards(formulas):
    """A model's formatting agreement cannot override a source-layout warning."""
    rows=deepcopy(formulas)
    key=lambda r:(r['question_id'],r['text_id'],r['raw_text'])
    blocked={key(r):r['reason'] for r in rows if r['origin']!='QWEN_TEXT_PROPOSAL'
             and r['status']=='SOURCE_LAYOUT_UNRESOLVED'}
    count=0
    for row in rows:
        if row['origin']=='QWEN_TEXT_PROPOSAL' and key(row) in blocked:
            count+=int(row['status']=='NORMALIZED')
            row.update(status='MODEL_PROPOSAL_NEEDS_SOURCE',reason=blocked[key(row)],source_layout_guard='BLOCKED')
    return rows,count


def viewer(job,root,output,items,report,repo):
    e=lambda value:escape(str(value),quote=True)
    # Reuse the application's installed KaTeX assets, entirely offline.
    source=repo/'frontend/node_modules/katex/dist';assets=job/'final/assets/katex'
    if (source/'katex.min.js').is_file():
        assets.mkdir(parents=True,exist_ok=True)
        for name in ['katex.min.js','katex.min.css']:
            shutil.copy2(source/name,assets/name)
        shutil.copytree(source/'fonts',assets/'fonts',dirs_exist_ok=True)
        if (source.parent/'LICENSE').is_file():shutil.copy2(source.parent/'LICENSE',assets/'LICENSE')
    cards=[]
    for item in items:
        raw=item['source_metadata'];formulas=[]
        for formula in item['latex_normalization']:
            text=formula.get('latex')
            formulas.append('<div class="formula"><small>'+e(formula['status'])+' · '+e(formula['origin'])+
                '</small><pre>'+e(formula['raw_text'])+'</pre>'+('<div class="math" data-latex="'+e(text)+'">'+e(text)+'</div>' if text else '')+
                ('<p class="reason">'+e(formula.get('reason'))+'</p>' if formula.get('reason') else '')+'</div>')
        images=[]
        for path in raw['student_view']['assets']:
            target=(root/path).resolve()
            if target.is_relative_to(root.resolve()) and target.is_file():
                images.append('<img loading="lazy" src="'+e(Path(os.path.relpath(target,output)).as_posix())+'" alt="Ảnh đề gốc">')
        cards.append('<details data-status="'+e(item['processing_status'])+'"><summary>Câu '+e(item['source_number'])+
            ' <span class="badge">'+e(item['processing_status'])+'</span> · '+str(len(formulas))+' công thức ứng viên</summary>'+
            '<h3>Text nguồn</h3><pre>'+e(raw['student_view']['stem_text_lossy'])+'</pre>'+''.join(images)+
            '<h3>LaTeX từ text và bằng chứng công thức</h3>'+(''.join(formulas) or '<p>Không tìm được công thức thuộc phạm vi hỗ trợ.</p>')+
            '<h3>Qwen review</h3><pre>'+e(json.dumps(item['machine_review'].get('model_result'),ensure_ascii=False,indent=2))+
            '</pre><details><summary>Lời giải nguồn · biên soạn</summary><pre>'+e(raw['reference_solution']['raw_text'])+'</pre></details></details>')
    html='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PDF · Kết quả cuối</title>
<style>body{font:15px/1.65 system-ui;background:#f3f7fa;color:#243b4a;margin:0}main{max-width:1140px;margin:30px auto;padding:0 22px}h1{margin-bottom:6px}.intro{color:#527080}.notice{background:#fff2d4;border:1px solid #efd59c;border-radius:12px;padding:16px}details{background:white;border:1px solid #dbe5eb;border-radius:12px;padding:16px;margin:12px 0}summary{cursor:pointer;font-weight:650}.badge{font-size:11px;background:#e4f1ed;color:#106c57;padding:4px 8px;border-radius:8px}details[data-status="MACHINE_FLAGGED"]>summary .badge{background:#fff1d6;color:#875912}details[data-status="DEFERRED"]>summary .badge{background:#edf1f5;color:#536477}.stats{display:flex;gap:18px;flex-wrap:wrap;margin:20px 0}.stats b{background:#fff;border-radius:10px;padding:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}.formula{border-left:3px solid #16856c;background:#f7fbfa;padding:12px;margin:12px 0}.math{overflow-x:auto;padding:14px 0}img{max-width:100%;height:auto}.reason{color:#875912;font-size:12px}a{color:#007466}input,select{padding:10px;border:1px solid #bdcfd5;border-radius:8px;margin:6px}small{color:#526e78}</style><main>'''
    html+='<h1>Kết quả xử lý PDF</h1><p class="intro">Text gốc · LaTeX chuẩn hóa · Qwen review · Nguồn truy vết</p>'
    html+='<div class="stats"><b>'+str(len(items))+' câu ứng viên</b><b>'+str(report['latex']['formula_count'])+' công thức ứng viên</b><b>Cloud API: 0</b></div>'
    html+='<div class="notice">Đây là bản nháp tự động. NORMALIZED xác nhận chuyển cách biểu diễn trong phạm vi parser, chưa xác nhận đọc đúng ảnh. Các cách đọc mơ hồ được giữ riêng. Chưa dùng các record này làm đáp án chấm đã xác minh.</div>'
    html+='<p><a href="questions.final.pretty.json">JSON dễ đọc</a> · <a href="questions.final.jsonl">File cuối JSONL</a> · <a href="report.json">Báo cáo</a> · <a href="../../../review.html">Nguồn trích xuất</a></p>'
    if not items:html+='<p>Chưa nhận được cấu trúc câu hỏi. Mở Nguồn trích xuất để xem nội dung từng trang; file câu hiện trống, chưa phải tài liệu đã xử lý đầy đủ.</p>'
    html+='<input id="search" placeholder="Tìm câu hoặc công thức"><select id="filter"><option value="">Mọi trạng thái</option><option>MACHINE_CLEARED</option><option>MACHINE_FLAGGED</option><option>DEFERRED</option></select><section id="cards">'+''.join(cards)+'</section>'
    if (assets/'katex.min.js').is_file():
        html+='<link rel="stylesheet" href="../../assets/katex/katex.min.css"><script src="../../assets/katex/katex.min.js"></script><script>for(const n of document.querySelectorAll(".math")){try{katex.render(n.dataset.latex,n,{throwOnError:false,trust:false,strict:"error",maxExpand:100});}catch(e){}}</script>'
    html+='''<script>function apply(){let q=document.getElementById('search').value.toLowerCase(),s=document.getElementById('filter').value;for(const n of document.querySelectorAll('#cards>details'))n.hidden=!!((s&&n.dataset.status!==s)||(q&&!n.textContent.toLowerCase().includes(q)));}document.getElementById('search').addEventListener('input',apply);document.getElementById('filter').addEventListener('change',apply);</script></main></html>'''
    (output/'review.html').write_text(html,encoding='utf-8')


def library(root):
    links=[]
    for path in sorted(root.glob('*/latest.json')):
        try:record=read_json(path)['report']
        except (ValueError,OSError,KeyError):continue
        name=Path(record.get('source_path',path.parent.name)).name
        page='final.html' if (path.parent/'final.html').exists() else 'review.html'
        links.append('<li><a href="'+escape(path.parent.name+'/'+page,quote=True)+'">'+escape(name)+'</a></li>')
    (root/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>Thư viện PDF</title><style>body{font:16px/1.8 system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#234}li{padding:12px;overflow-wrap:anywhere}a{color:#007466}</style><h1>Thư viện kết quả PDF</h1><p>Bản xuất tự động có nguồn; xem trạng thái của từng câu trước khi sử dụng.</p><ul>'+''.join(links)+'</ul>',encoding='utf-8')


def run(job,runtime,*,repo=None,limit=0,retry_failed=False,rules_only=False,client=None):
    job,runtime=Path(job).resolve(),Path(runtime).resolve()
    if limit<0:raise ValueError('INVALID_REVIEW_LIMIT')
    repo=Path(repo).resolve() if repo else Path(__file__).parents[4]
    started=time.perf_counter();latest=read_json(job/'latest.json');root=Path(latest['output_directory']).resolve()
    if not root.is_relative_to(job/'versions'):raise ValueError('SOURCE_VERSION_OUTSIDE_JOB')
    source=root/'metadata/questions.jsonl';generation=file_hash(source)
    metadata=[json.loads(line) for line in source.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({i['question_id'] for i in metadata})!=len(metadata):raise ValueError('DUPLICATE_SOURCE_QUESTION_ID')
    source_validator=Draft202012Validator(read_json(Path(__file__).parents[2]/'schemas/pdf-content.v1.schema.json'))
    for item in metadata:source_validator.validate(item)
    count=min(limit,len(metadata)) if limit else len(metadata)
    progress=Progress(job)
    rules_only=rules_only or not metadata
    owned=client is None and not rules_only
    if owned:client=LocalClient(LocalConfig(runtime=runtime,input_mode='metadata',timeout=240,
        max_output_tokens=512,max_calls=max(1,count*2),max_total_tokens=max(1,count*32000)),job/'pipeline-usage.jsonl')
    def event(message):
        progress.document_event(message)
        write_json(job/'pipeline-status.json',{'status':'RUNNING','detail':message,'at':datetime.now(timezone.utc).isoformat()})
        print(message,flush=True)
    try:
        with local_lock(job):
            progress.begin_document(latest,limit,rules_only)
            if client:client.preflight()
            event('[pipeline] text-to-latex')
            formulas,latex_report=normalize(job,runtime,client=None if rules_only else client,limit=limit,retry_failed=retry_failed,event=event)
            formulas,source_overrides=apply_source_guards(formulas)
            progress.latex_done({**latex_report,'status_counts':dict(Counter(r['status'] for r in formulas))})
            lookup=defaultdict(list)
            for formula in formulas:lookup[formula['question_id']].append(formula)
            event('[pipeline] qwen-review')
            if rules_only:
                review_report={'status':'SKIPPED','local_inference_calls':0,'cache_hits':0,'cloud_api_calls':0}
                reviews={i['question_id']:{'status':'DEFERRED','reasons':['QWEN_REVIEW_SKIPPED'],
                                         'model_result':None,'source_images_reviewed_by_model':False} for i in metadata}
            else:
                review_report=review(job,runtime,limit=limit,retry_failed=retry_failed,client=client,event=event,normalizations=dict(lookup))
                reviews={r['question_id']:r for r in read_json(Path(review_report['output_directory'])/'questions.qwen-reviewed.pretty.json')}
            progress.review_done(review_report)
            event('[pipeline] export')
            final=[]
            for item in metadata:
                machine=reviews[item['question_id']]
                record={'schema_version':'pdf-final/v1','question_id':item['question_id'],'source_number':item['source_number'],
                    'source_metadata_file':str(source),'source_metadata':item,'latex_normalization':lookup[item['question_id']],
                    'machine_review':machine,'processing_status':machine['status'],'academic_review':'PENDING',
                    'grading_support':'NOT_ASSESSED','publishable':False}
                Draft202012Validator(FINAL_SCHEMA).validate(record);final.append(record)
            if file_hash(source)!=generation:raise ValueError('SOURCE_METADATA_CHANGED_DURING_PIPELINE')
            version=content_hash({'code':file_hash(Path(__file__)),'records':final})[:16]
            output=job/'final/versions'/version;output.mkdir(parents=True,exist_ok=True)
            write_jsonl(output/'questions.final.jsonl',final);write_json(output/'questions.final.pretty.json',final)
            write_json(output/'schema.json',FINAL_SCHEMA)
            status='PAGE_METADATA_ONLY' if not final else 'DRAFT_READY' if all(r['processing_status']!='DEFERRED' for r in final) else 'DRAFT_PARTIAL'
            report={'schema_version':'pdf-complete-pipeline/v1','status':status,
                'question_count':len(final),'source_metadata_sha256':generation,'latex':latex_report,'qwen_review':review_report,
                'source_guard_overrides':source_overrides,'effective_latex_status_counts':dict(Counter(r['status'] for r in formulas)),
                'status_counts':dict(Counter(r['processing_status'] for r in final)),'cloud_api_calls':0,
                'seconds':round(time.perf_counter()-started,3),'source_unchanged':True,'grading_ready_count':0,
                'final_jsonl':str(output/'questions.final.jsonl'),'final_pretty_json':str(output/'questions.final.pretty.json'),
                'final_review_html':str(job/'final.html'),'output_directory':str(output)}
            viewer(job,root,output,final,report,repo);write_json(output/'report.json',report)
            write_json(job/'final.json',report)
            relative=(output/'review.html').relative_to(job).as_posix()
            (job/'final.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='+relative+'"><a href="'+relative+'">Mở kết quả cuối</a>',encoding='utf-8')
            result=read_json(job/'result.json') if (job/'result.json').exists() else {}
            write_json(job/'result.json',{**result,'final_metadata_jsonl':report['final_jsonl'],
                'final_metadata_pretty':report['final_pretty_json'],'final_review_html':report['final_review_html']})
            library(job.parent)
            write_json(job/'pipeline-status.json',{'status':report['status'],'result':str(job/'final.json')})
            progress.finish(report)
            print('Final metadata: '+report['final_jsonl'],flush=True)
            return report
    except BaseException as error:
        progress.fail(error)
        write_json(job/'pipeline-status.json',{'status':'INTERRUPTED' if isinstance(error,KeyboardInterrupt) else 'FAILED',
            'error_type':type(error).__name__,'resume':'Run the same PDF again; keep checkpoints.'})
        raise
    finally:
        if owned:client.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True);parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=0);parser.add_argument('--repo',type=Path)
    parser.add_argument('--retry-failed',action='store_true');parser.add_argument('--rules-only',action='store_true')
    args=parser.parse_args()
    print(json.dumps(run(args.job,args.runtime,repo=args.repo,limit=args.limit,retry_failed=args.retry_failed,
                         rules_only=args.rules_only),ensure_ascii=False,indent=2))
