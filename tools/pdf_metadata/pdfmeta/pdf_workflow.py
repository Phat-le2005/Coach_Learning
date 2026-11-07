"""One PDF in: isolated, resumable local metadata with explicit review boundaries."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
from html import escape
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import time
from jsonschema import Draft202012Validator

from .assemble import assemble
from .auto_ocr import LocalOCR,needs_text_ocr
from .auto_tables import AutoTables
from .enrich import attach_evidence
from .gemini_client import content_hash
from .math_audit import run as audit_run
from .native import NATIVE_VERSION,extract_native,mark_margins
from .review import crop_sources
from .step_segmentation import propose_steps,validate_grounding
from .storage import configure_storage,file_hash,read_json,write_json,write_jsonl
from .text_cleanup import normalize_block
from .validate import validate_candidates
from .progress import Progress
from .paths import storage_root, runtime_root
from .paired.corpus_layout import source_book_labels


VERSION='one-pdf-workflow/v1'


def fingerprint():
    root=Path(__file__).parent
    files=[*root.glob('*.py'),root/'paired/corpus_layout.py',*(root.parent/'schemas').glob('*.json')]
    return content_hash({p.name:file_hash(p) for p in sorted(files)})[:16]


def stamp():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def local_lock(root):
    """Recover only demonstrably dead local owners, never an active process."""
    import psutil
    root.mkdir(parents=True,exist_ok=True);path=root/'.workflow.lock'
    if path.exists():
        owner=read_json(path)
        try:
            process=psutil.Process(int(owner['pid']))
            alive=abs(process.create_time()-float(owner['created']))<.01
        except psutil.NoSuchProcess:
            alive=False
        if alive:raise ValueError('PDF_JOB_ALREADY_RUNNING')
        path.unlink()
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:
        os.write(fd,json.dumps({'pid':os.getpid(),'created':psutil.Process().create_time()}).encode());os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class Checkpoints:
    def __init__(self,root,event):
        self.root,self.event=Path(root),event
        self.path=self.root/'state.json'
        self.state=read_json(self.path) if self.path.exists() else {'schema_version':VERSION,'stages':{}}
        self.hits=0

    def run(self,name,inputs,operation):
        identity=content_hash(inputs)
        previous=self.state['stages'].get(name,{})
        if previous.get('status')=='COMPLETE' and previous.get('identity')==identity:
            if all((self.root/path).is_file() and file_hash(self.root/path)==digest for path,digest in previous['files'].items()):
                self.hits+=1;self.event('cache',name)
                return previous.get('result')
        self.event('stage',name)
        self.state['stages'][name]={'status':'RUNNING','identity':identity,'started':stamp()};write_json(self.path,self.state)
        try:
            result,files=operation()
            checked={Path(path).resolve().relative_to(self.root.resolve()).as_posix():file_hash(Path(path)) for path in files}
            self.state['stages'][name].update(status='COMPLETE',files=checked,result=result,finished=stamp())
        except BaseException as error:
            self.state['stages'][name].update(status='INTERRUPTED' if isinstance(error,(KeyboardInterrupt,SystemExit)) else 'FAILED',error_type=type(error).__name__)
            write_json(self.path,self.state);raise
        write_json(self.path,self.state)
        self.event('done',name)
        return result


def cache_roots(repo,digest,excluded):
    """Find raw caches by source hash, without source-specific names or fixtures."""
    found=[]
    for manifest_path in (repo/'.tmp').glob('*/manifest.json'):
        root=manifest_path.parent.resolve()
        if root==excluded.resolve():continue
        try:manifest=read_json(manifest_path)
        except (ValueError,OSError):continue
        if manifest.get('source_sha256')==digest:found.append(root)
    return found


def ensure_native(pdf,job,roots,event):
    output=job/'native';manifest_path=output/'manifest.json'
    digest=file_hash(pdf)
    def valid(root):
        manifest=read_json(root/'manifest.json')
        if manifest.get('source_sha256')!=digest or manifest.get('parser_version')!=NATIVE_VERSION:return False
        for number in range(1,manifest['page_count']+1):
            path=root/'pages'/f'page-{number:03}.json'
            if not path.exists():return False
            page=read_json(path)
            image=(root/page['image_path']).resolve()
            if (not image.is_relative_to(root.resolve()) or not image.is_file() or page.get('source_sha256')!=digest
                    or page.get('library_version')!=importlib.metadata.version('pdfplumber') or page.get('image_dpi')!=120):return False
        return True
    if manifest_path.exists() and valid(output):
        event('cache','native-pages')
        return output
    for root in roots:
        if not valid(root):continue
        event('import_cache',str(root))
        manifest=read_json(root/'manifest.json');(output/'pages').mkdir(parents=True,exist_ok=True)
        for number in range(1,manifest['page_count']+1):
            page_path=root/'pages'/f'page-{number:03}.json';page=read_json(page_path)
            shutil.copy2(page_path,output/'pages'/page_path.name)
            shutil.copy2(root/page['image_path'],output/page['image_path'])
        manifest['source_path']=str(pdf.resolve());manifest['raw_cache_origin']=str(root)
        write_json(manifest_path,manifest)
        return output
    event('stage','native-extraction')
    extract_native(pdf,output,dpi=120,progress=lambda done,total:event('native_page',{'done':done,'total':total}))
    return output


def formulas_needed(page):
    return page.get('extraction_status')=='OCR_CANDIDATE' or any(
        re.search(r'[=^√∫\uE000-\uF8FF]',b['text_raw']) for b in page['blocks'])


def run(pdf:Path,*,repo:Path,output_root:Path,runtime:Path):
    try:
        return _run(pdf,repo=repo,output_root=output_root,runtime=runtime)
    except BaseException as error:
        if pdf.is_file() and str(error)!='PDF_JOB_ALREADY_RUNNING':
            job=output_root.resolve()/file_hash(pdf)[:24]
            if job.is_dir():
                Progress(job).fail(error)
                write_json(job/'status.json',{'status':'INTERRUPTED' if isinstance(error,(KeyboardInterrupt,SystemExit)) else 'FAILED',
                    'error_type':type(error).__name__,'updated':stamp(),'resume':'Run the same PDF command again; keep this folder.'})
        raise


def _run(pdf:Path,*,repo:Path,output_root:Path,runtime:Path):
    pdf,repo,output_root,runtime=(p.resolve() for p in (pdf,repo,output_root,runtime))
    if not pdf.is_file() or pdf.suffix.lower()!='.pdf':raise ValueError('INPUT_MUST_BE_AN_EXISTING_PDF')
    configure_storage(runtime)
    digest=file_hash(pdf);job=output_root/digest[:24];version=fingerprint();output=job/'versions'/version
    if pdf.is_relative_to(job):raise ValueError('INPUT_PDF_MUST_NOT_BE_AN_OUTPUT_ARTIFACT')
    with local_lock(job):
        started=time.perf_counter();output.mkdir(parents=True,exist_ok=True)
        progress=Progress(job);progress.begin(pdf.name)
        def event(kind,value):
            progress.extract_event(kind,value)
            state={'schema_version':VERSION,'source_sha256':digest,'version':version,'status':'RUNNING',
                   'event':kind,'detail':str(value),'updated':stamp(),'output':str(output)}
            write_json(job/'status.json',state);print(f'[{kind}] {value}',flush=True)
        event('input',pdf.name)
        snapshot=job/'input.pdf'
        if snapshot.exists():
            if file_hash(snapshot)!=digest:raise ValueError('JOB_SOURCE_SNAPSHOT_CHANGED')
        else:shutil.copy2(pdf,snapshot)
        roots=cache_roots(repo,digest,job)
        native=ensure_native(snapshot,job,roots,event)
        checkpoints=Checkpoints(output,event);ocr=LocalOCR(runtime,job/'ocr',event)
        pilot=output/'pilot';pilot.mkdir(exist_ok=True)
        manifest=read_json(native/'manifest.json');write_json(pilot/'manifest.json',{**manifest,'source_path':str(snapshot)})
        native_pages=[read_json(f) for f in sorted((native/'pages').glob('page-*.json'))]
        def effective_pages():
            (pilot/'pages').mkdir(exist_ok=True);records=[];routes=[]
            for page in native_pages:
                target=pilot/page['image_path'];target.parent.mkdir(parents=True,exist_ok=True)
                if not target.exists() or file_hash(target)!=file_hash(native/page['image_path']):shutil.copy2(native/page['image_path'],target)
                needs=needs_text_ocr(page)
                effective=ocr.text_page(page,target) if needs else page
                records.append(effective);routes.append({'page_number':page['page_number'],'route':'LOCAL_TEXT_OCR' if needs else 'NATIVE_GLYPHS'})
                event('page',f"{page['page_number']}/{manifest['page_count']} {'OCR' if needs else 'native'}")
            mark_margins(records)
            for page in records:write_json(pilot/'pages'/f"page-{page['page_number']:03}.json",page)
            write_json(output/'routes.json',routes)
            return routes,[output/'routes.json',*(pilot/'pages').glob('*')]
        routes=checkpoints.run('page-routing',{'native':file_hash(native/'manifest.json'),
            'packages':ocr.packages,'text_weights':ocr.weights(['PP-OCRv5_mobile_det','latin_PP-OCRv5_mobile_rec']) if any(needs_text_ocr(p) for p in native_pages) else None,
            'pages':[file_hash(native/'pages'/f"page-{p['page_number']:03}.json") for p in native_pages]},effective_pages)
        pages=[source_book_labels(read_json(pilot/'pages'/f"page-{p['page_number']:03}.json")) for p in native_pages]
        page_lookup={p['page_number']:p for p in pages}
        def questions():
            items,orphans=assemble(pages,digest);crop_sources(items,pages,pilot)
            validation=validate_candidates(items,pages,pilot)
            write_jsonl(pilot/'questions.candidates.jsonl',items);write_jsonl(output/'unassigned-blocks.jsonl',orphans)
            write_json(output/'structure-report.json',validation)
            return {'count':len(items),'structural_errors':validation['structural_errors']},[pilot/'questions.candidates.jsonl',output/'structure-report.json',output/'unassigned-blocks.jsonl',*(pilot/'assets').glob('*')]
        question_report=checkpoints.run('question-assembly',{'pages':[file_hash(pilot/'pages'/f"page-{p['page_number']:03}.json") for p in pages]},questions)
        event('counts',{'pages':len(pages),'questions':question_report['count']})
        items=[json.loads(line) for line in (pilot/'questions.candidates.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        import pdfplumber
        def enrich():
            results=[]
            with pdfplumber.open(snapshot) as document:
                work_pages=[page for page in pages if formulas_needed(page)]
                for index,page in enumerate(work_pages,1):
                    cached=[]
                    for root in roots:
                        cached=ocr.imported_formulas(root,page,pilot/page['image_path'])
                        if cached:break
                    if cached:
                        event('cache',f"formula-page-{page['page_number']}");results.extend(cached)
                    else:results.append(ocr.formula_page(page,pilot/page['image_path'],document.pages[page['page_number']-1]))
                    event('formula_progress',{'done':index,'total':len(work_pages)})
            ambiguous,findings=attach_evidence(items,results,pages)
            write_jsonl(pilot/'questions.enriched.candidates.jsonl',items)
            write_json(output/'ocr-findings.json',{'findings':findings,'unassigned_regions':ambiguous})
            return {'pages':len({r['page_number'] for r in results})},[pilot/'questions.enriched.candidates.jsonl',output/'ocr-findings.json']
        checkpoints.run('formula-evidence',{'questions':file_hash(pilot/'questions.candidates.jsonl'),'packages':ocr.packages,
            'weights':ocr.weights(['PP-DocLayoutV3','PP-FormulaNet_plus-S','PP-FormulaNet_plus-M'])},enrich)
        items=[json.loads(line) for line in (pilot/'questions.enriched.candidates.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        def audit():
            audits,report=audit_run(pilot,output/'math',pdf=snapshot)
            proposals=[]
            generation=file_hash(pilot/'questions.enriched.candidates.jsonl')
            for item in items:
                proposal=propose_steps(item,page_lookup,corrections=[]);validate_grounding(proposal,item,page_lookup)
                proposals.append({**proposal,'candidate_generation':generation})
            write_jsonl(output/'steps.jsonl',proposals)
            return report,[output/'math/questions.math-audit.jsonl',output/'math/questions.math-audit.pretty.json',output/'math/math-report.json',output/'steps.jsonl']
        page_identities=[file_hash(pilot/'pages'/f"page-{p['page_number']:03}.json") for p in pages]
        math=checkpoints.run('steps-and-math',{'candidates':file_hash(pilot/'questions.enriched.candidates.jsonl'),'pages':page_identities},audit)
        audits=read_json(output/'math/questions.math-audit.pretty.json');audit_lookup={a['question_id']:a for a in audits}
        def tables():
            reader=AutoTables(ocr,output/'tables',version,event);records=[]
            with pdfplumber.open(snapshot) as document:
                for index,item in enumerate(items,1):
                    records.extend(reader.question(item,page_lookup,audit_lookup[item['question_id']],document))
                    event('table_progress',{'done':index,'total':len(items)})
            write_json(output/'tables.json',records)
            return {'count':len(records),'status_counts':dict(Counter(r['status'] for r in records))},[output/'tables.json',*(output/'tables/assets').glob('*')]
        table_report=checkpoints.run('tables',{'candidates':file_hash(pilot/'questions.enriched.candidates.jsonl'),
            'math':file_hash(output/'math/questions.math-audit.jsonl'),'packages':ocr.packages,
            'pages':page_identities,'images':[file_hash(pilot/p['image_path']) for p in pages],
            'weights':ocr.weights(['PP-FormulaNet_plus-M'])},tables)
        table_records=read_json(output/'tables.json')
        exported,issues=[],[]
        proposals={p['question_id']:p for p in (json.loads(line) for line in (output/'steps.jsonl').read_text(encoding='utf-8').splitlines())}
        for item in items:
            own_tables=[t for t in table_records if t['question_id']==item['question_id']]
            stem_text='\n'.join(normalize_block(b)[0] for s in item['stem']['source_spans'] for b in page_lookup[s['page_number']]['blocks'] if b['block_id'] in s['block_ids'])
            flags=sorted(set(item['review_flags']+audit_lookup[item['question_id']]['flags']))
            exported.append({'schema_version':'pdf-content/v1','question_id':item['question_id'],'source_number':item['source_number'],
                'source':{'pdf_sha256':digest,'spans':item['source_regions']},
                'student_view':{'stem_text_lossy':stem_text,'assets':['pilot/'+s['asset_path'] for s in item['stem']['source_spans'] if s.get('asset_path')]},
                'source_answer':item['answer']['text_raw'],'reference_solution':{'raw_text':item['solution']['text_raw'],
                    'steps':proposals[item['question_id']]['steps'],'math_audit':audit_lookup[item['question_id']],'tables':own_tables},
                'quality_flags':flags,'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False})
            issues.append({'question_id':item['question_id'],'source_number':item['source_number'],'reasons':flags,
                           'table_issues':[t.get('reason') for t in own_tables if t['status']!='STRUCTURED_CANDIDATE']})
        for page in pages:
            if not any(s['page_number']==page['page_number'] for item in items for s in item['source_regions']):
                issues.append({'page_number':page['page_number'],'reason':'PAGE_CONTENT_NOT_ASSEMBLED_INTO_QUESTIONS'})
        if question_report['structural_errors']:
            issues.append({'reason':'STRUCTURAL_VALIDATION_ERRORS','errors':question_report['structural_errors']})
        validator=Draft202012Validator(read_json(Path(__file__).parents[1]/'schemas/pdf-content.v1.schema.json'))
        for item in exported:validator.validate(item)
        write_jsonl(output/'metadata/questions.jsonl',exported);write_json(output/'metadata/questions.pretty.json',exported)
        write_jsonl(output/'metadata/student-preview.jsonl',[{'question_id':i['question_id'],**i['student_view']} for i in exported])
        write_jsonl(output/'metadata/pages.jsonl',[{'page_number':p['page_number'],'text_lossy':'\n'.join(normalize_block(b)[0] for b in p['blocks']),
                      'source_image':'pilot/'+p['image_path'],'blocks':p['blocks'],'parser_id':p['parser_id']} for p in pages])
        write_json(output/'review-queue.json',issues)
        if file_hash(pdf)!=digest or file_hash(snapshot)!=digest:raise ValueError('SOURCE_CHANGED_DURING_WORKFLOW')
        report={'schema_version':VERSION,'source_path':str(pdf),'source_sha256':digest,'job_directory':str(job),
            'output_directory':str(output),'workflow_fingerprint':version,'status':'METADATA_DRAFT_READY' if exported else 'PAGE_METADATA_ONLY',
            'page_count':len(pages),'question_count':len(exported),'routes':dict(Counter(r['route'] for r in routes)),
            'tables':table_report,'supported_derivative_questions':math['questions_with_supported_checks'],
            'stage_cache_hits':checkpoints.hits,'ocr_cache_hits':ocr.cache_hits,'local_inference_calls':ocr.calls,
            'cloud_api_calls':0,'source_unchanged':True,'seconds':round(time.perf_counter()-started,3),
            'academic_approved_count':0,'grading_ready_count':0,'publishable_count':0,
            'artifacts':{'metadata_jsonl':str(output/'metadata/questions.jsonl'),'metadata_pretty':str(output/'metadata/questions.pretty.json'),
                         'page_metadata':str(output/'metadata/pages.jsonl'),'review_queue':str(output/'review-queue.json'),
                         'review_html':str(job/'review.html')}}
        write_json(output/'report.json',report);build_view(output,report,exported,table_records,issues)
        write_json(job/'latest.json',{'version':version,'output_directory':str(output),'report':report})
        write_json(job/'result.json',report['artifacts'])
        relative=output.relative_to(job).as_posix()
        (job/'review.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url='+relative+'/review.html"><a href="'+relative+'/review.html">Mở metadata PDF</a>',encoding='utf-8')
        write_json(job/'status.json',{'status':report['status'],'finished':stamp(),'report':str(output/'report.json')})
        progress.extracted(report)
        build_index(output_root)
        event_message=f"{len(pages)} pages / {len(exported)} question candidates / {table_report['count']} table regions"
        print('[complete] '+event_message,flush=True);print('Review: '+str(job/'review.html'),flush=True)
        print('Metadata: '+str(output/'metadata/questions.jsonl'),flush=True)
        return report


def build_index(root):
    links=[]
    for path in sorted(root.glob('*/latest.json')):
        try:report=read_json(path)['report']
        except (OSError,ValueError,KeyError):continue
        href=path.parent.name+'/review.html'
        links.append('<li><a href="'+escape(href,quote=True)+'">'+escape(Path(report['source_path']).name)+'</a> · '+str(report['page_count'])+' trang · '+str(report['question_count'])+' câu ứng viên</li>')
    (root/'review.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><title>Thư viện metadata PDF</title><style>body{font:16px/1.8 system-ui;max-width:1100px;margin:40px auto;padding:0 24px;color:#234}li{padding:12px 0}a{color:#087467}</style><h1>Thư viện metadata PDF</h1><p>Các bản nháp đã xử lý local; chưa tự duyệt để chấm.</p><ul>'+''.join(links)+'</ul></html>',encoding='utf-8')


def build_view(output,report,items,tables,issues):
    e=lambda v:escape(str(v),quote=True)
    rows=[]
    for item in items:
        assets=''.join('<img loading="lazy" src="'+e(path)+'" alt="Ảnh đề nguồn">' for path in item['student_view']['assets'])
        rows.append('<details><summary>Câu '+str(item['source_number'])+' · '+str(len(item['reference_solution']['steps']))+' bước ứng viên</summary><pre>'+e(item['student_view']['stem_text_lossy'])+'</pre>'+assets+'<details><summary>Lời giải nguồn · chỉ dành cho biên soạn</summary><pre>'+e(item['reference_solution']['raw_text'])+'</pre></details><p>'+e(', '.join(item['quality_flags']))+'</p></details>')
    table_html=[]
    for record in tables:
        text=record.get('reason','Có cấu trúc; chưa duyệt')
        if record.get('table'):text=json.dumps(record['table'],ensure_ascii=False,indent=2)
        table_html.append('<details><summary>Bảng · câu '+str(record['source_number'])+' · '+e(record['status'])+'</summary><img loading="lazy" src="tables/'+e(record['asset_path'])+'" alt="Ảnh bảng nguồn"><pre>'+e(text)+'</pre></details>')
    html='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Metadata PDF</title>
<style>body{font:15px/1.65 system-ui,sans-serif;background:#f3f7fa;color:#203b4c;margin:0}main{max-width:1120px;margin:32px auto;padding:0 24px}h1{font-size:28px}.notice{padding:18px;background:#fff2d4;border:1px solid #eed194;border-radius:10px}details{background:white;border:1px solid #dbe5eb;border-radius:12px;margin:12px 0;padding:16px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}img{max-width:100%;height:auto}a{color:#007466}.stats{display:flex;gap:22px;flex-wrap:wrap;padding:18px 0}</style><main>'''
    html+='<h1>Metadata PDF · '+e(Path(report['source_path']).name)+'</h1><div class="stats"><b>'+str(report['page_count'])+' trang</b><b>'+str(report['question_count'])+' câu ứng viên</b><b>'+str(report['tables']['count'])+' vùng bảng</b><b>Cloud API: 0</b></div>'
    html+='<div class="notice">Đã xử lý tự động thành bản nháp có nguồn. Các công thức, lời giải và cách tách bước chưa được duyệt học thuật; chưa dùng làm đáp án chấm tự động.</div>'
    html+='<p><a href="metadata/questions.pretty.json">Metadata câu</a> · <a href="metadata/questions.jsonl">JSONL</a> · <a href="metadata/pages.jsonl">Nội dung từng trang</a> · <a href="review-queue.json">Hàng chờ kiểm tra</a> · <a href="report.json">Báo cáo</a></p>'
    if not items:html+='<p>Chưa nhận ra cấu trúc câu hỏi của tài liệu này. Nội dung từng trang và ảnh nguồn đã được giữ để xử lý tiếp.</p>'
    html+=''.join(rows)+'<h2>Bảng đã phát hiện</h2>'+''.join(table_html)+'</main></html>'
    (output/'review.html').write_text(html,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pdf',type=Path,required=True)
    parser.add_argument('--repo',type=Path,default=Path(__file__).parents[3])
    parser.add_argument('--output-root',type=Path);parser.add_argument('--runtime',type=Path)
    args=parser.parse_args();repo=args.repo.resolve()
    result=run(args.pdf,repo=repo,output_root=args.output_root or storage_root()/'pdf-jobs',runtime=args.runtime or runtime_root())
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
