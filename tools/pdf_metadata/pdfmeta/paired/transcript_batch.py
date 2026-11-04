"""Checkpointed source-preserving text/math transcription and trial dashboard."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from ..native import box
from ..safe_math import UnsupportedMath, parse_expression, latex_plain, assignment
from ..source_layout import inspect
from ..storage import configure_storage, file_hash, inference_versions, read_json, write_json, write_jsonl
from .math_recovery import FormulaReader, compare, extract_page
from .transcript_regions import propose, crop_box, visual_flags, native_latex, assemble, audit_coverage
from .transcript_plan import select
from .transcript_quality import display_decision


VERSION='paired-transcript-draft/v1'


def now():return datetime.now(timezone.utc).isoformat()


def content_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def code_identity():
    root=Path(__file__).parent
    paths=[root/n for n in ['transcript_batch.py','transcript_regions.py','choice_layout.py','transcript_quality.py','transcript_plan.py','transcript_syntax.cjs','math_recovery.py']]
    paths += [root.parent/n for n in ['native_math.py','text_cleanup.py','safe_math.py','source_layout/__init__.py']]
    return content_hash({str(p.name):file_hash(p) for p in paths})


class Syntax:
    def __init__(self,katex):
        self.process=subprocess.Popen(['node',str(Path(__file__).with_name('transcript_syntax.cjs')),str(Path(katex)/'katex.js')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    def __call__(self,text):
        self.process.stdin.write(json.dumps(text,ensure_ascii=False)+'\n');self.process.stdin.flush()
        value=self.process.stdout.readline()
        if not value:raise RuntimeError('KATEX_SYNTAX_PROCESS_STOPPED')
        return json.loads(value)
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=5)


def trusted_native(region,page):
    value=region.get('native_candidate')
    if not value:return None
    try:
        signals=inspect(page,region['bbox'])
        if any(signals[k] for k in ['absolute_bars','overlines','lower_glyphs','top_bars']):return None
        result=native_latex(value)
        # recover_slice already refuses ambiguous baselines and fractions. Keep
        # source notation (including intervals or a false answer alternative)
        # rather than solving/simplifying it to decide what to transcribe.
        if not result.strip():return None
        return result
    except (UnsupportedMath,ValueError,TypeError,NotImplementedError):return None


def worker(items,documents,output,runtime,katex,identity):
    import pdfplumber,psutil
    configure_storage(Path(runtime));os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
    if os.name=='nt':psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    output=Path(output);local=output/'workers'/str(os.getpid());local.mkdir(parents=True,exist_ok=True)
    reader=FormulaReader(runtime,local,'PP-FormulaNet_plus-M')
    secondary=FormulaReader(runtime,local,'PP-FormulaNet_plus-S');syntax=Syntax(katex)
    results=[];started=time.perf_counter()
    try:
        # Each worker keeps its model resident; PDF handles are scoped per source.
        for digest in sorted({q['source']['sha256'] for q in items}):
            pdf_path=Path(documents[digest]);
            if file_hash(pdf_path)!=digest:raise ValueError('ORIGINAL_PDF_HASH_MISMATCH')
            with pdfplumber.open(pdf_path) as pdf:
                pages={}
                for q in [q for q in items if q['source']['sha256']==digest]:
                    target=output/'records'/('q-'+content_hash(q['question_id'])[:24]+'.json')
                    record_identity=content_hash({'source_record':q,'pipeline':identity})
                    if target.is_file():
                        old=read_json(target)
                        if old.get('checkpoint_identity')==record_identity:
                            results.append({'path':str(target),'cache_hit':True});continue
                    try:
                        qstart=time.perf_counter();calls_before=reader.calls;hits_before=reader.hits;secondary_before=secondary.calls
                        destination=output/'assets'/f"q{q['collection_number']:04}";destination.mkdir(parents=True,exist_ok=True)
                        row={'schema_version':VERSION,'question_id':q['question_id'],'collection_number':q['collection_number'],
                             'source_label':q['source_label'],'chapter_id':q['chapter_id'],'chapter_title':q['chapter_title'],
                             'source':q['source'],'pipeline_identity':identity,'checkpoint_identity':record_identity,'source_record_sha256':content_hash(q),
                             'parts':{},'formula_candidates':[],'issues':[],
                             'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False}
                        for role in ['question','solution','answer']:
                            part={'markdown':'','choices':[],'source_spans':q[role].get('source_spans',[]),
                                  'raw_text_lossy':q[role].get('text_lossy',q[role].get('text_raw')),'fragments':[]}
                            texts=[]
                            for si,span in enumerate(part['source_spans']):
                                pn=span['page_number'];raw=pdf.pages[pn-1]
                                if pn not in pages:
                                    pages[pn]=extract_page(raw,pn,digest);pages[pn]['images']=[{'bbox':box(i)} for i in raw.images]
                                page=pages[pn];formulas,rows,errors=propose(page,span);flags=visual_flags(page,span)
                                source_asset=f"assets/q{q['collection_number']:04}/{role}-{si:02}-source.png"
                                raw.crop(tuple(span['bbox'])).to_image(resolution=150).save(output/source_asset)
                                processed=[]
                                for fi,f in enumerate(formulas):
                                    asset=f"assets/q{q['collection_number']:04}/{role}-{si:02}-formula-{fi:03}.png"
                                    crop=crop_box(page,f,span,rows)
                                    raw.crop(tuple(crop)).to_image(resolution=288).save(output/asset)
                                    native=trusted_native(f,page)
                                    quality={'issues':[]}
                                    second=None
                                    if native:
                                        latex=native;method='NATIVE_SUPPORTED_GEOMETRY_DRAFT'
                                    else:
                                        latex=reader.read(output/asset);second=secondary.read(output/asset);method='LOCAL_FORMULA_IMAGE_READING'
                                    check=syntax(latex)
                                    if not native:
                                        source_glyphs={g['key']:g['text'] for r in rows for g in r['glyphs']}
                                        source_chars=''.join(source_glyphs[k] for k in f['source_glyph_keys'])
                                        quality=display_decision(source_chars,latex,second,check,inspect(page,f['bbox']))
                                    record={**f,'formula_id':f"{role}-{si:02}-{fi:03}",'role':role,'page_number':pn,
                                            'crop_bbox':crop,'asset_path':asset,'asset_sha256':file_hash(output/asset),
                                            'latex_candidate':latex,'secondary_latex_candidate':second,
                                            'display_latex':(latex if check['status']=='PASS' else None) if native else quality['display_latex'],
                                            'transcription_checks':quality,
                                            'syntax':check,'method':method,
                                            'comparison':compare(f['native_candidate'],latex) if not native else 'NATIVE_ONLY_REQUIRES_SOURCE_CHECK',
                                            'status':'INFERRED_NOT_ACADEMICALLY_REVIEWED'}
                                    processed.append(record)
                                coverage=audit_coverage(rows,processed,errors)
                                transcription=assemble(rows,processed)
                                fragment={'page_number':pn,'bbox':span['bbox'],'source_asset':source_asset,
                                          'source_asset_sha256':file_hash(output/source_asset),
                                          'markdown':transcription['markdown'],'choices':transcription['choices'],
                                          'coverage':coverage,'source_errors':errors,'visual_flags':flags}
                                if not rows:flags.append('NO_READABLE_SOURCE_GLYPHS')
                                if coverage['uncovered_suspect_glyph_keys']:flags.append('UNCOVERED_SUSPECT_MATH_GLYPHS')
                                if errors:flags.append('UNMAPPED_SOURCE_ROWS')
                                if any(f['syntax']['status']!='PASS' for f in processed):flags.append('LATEX_SYNTAX_FAILURE')
                                if any(f['comparison']=='NATIVE_OCR_CONFLICT' for f in processed):flags.append('NATIVE_OCR_CONFLICT')
                                if any(f.get('transcription_checks',{}).get('issues') for f in processed):flags.append('FORMULA_CANDIDATES_HELD_FOR_SOURCE_REVIEW')
                                if flags:
                                    fragment['markdown']+='\n\n![Vùng nguồn cần đối chiếu]('+source_asset+')'
                                texts.append(fragment['markdown']);part['choices'].extend(fragment['choices'])
                                part['fragments'].append(fragment);row['formula_candidates'].extend(processed)
                                row['issues'].extend({'role':role,'page_number':pn,'code':flag} for flag in set(flags))
                            part['markdown']='\n\n'.join(texts).strip()
                            row['parts'][role]=part
                        row['transcript_status']='SOURCE_REVIEW_REQUIRED' if row['issues'] else 'TEXT_AND_LATEX_DRAFT'
                        row['runtime']={'seconds':round(time.perf_counter()-qstart,3),'model_calls':reader.calls-calls_before,
                                        'ocr_cache_hits':reader.hits-hits_before,'secondary_model_calls':secondary.calls-secondary_before,'worker_pid':os.getpid(),
                                        'rss_bytes':psutil.Process().memory_info().rss,'cloud_calls':0}
                        write_json(target,row);results.append({'path':str(target),'cache_hit':False})
                        write_json(local/'progress.json',{'updated_at':now(),'pid':os.getpid(),'completed':len(results),
                            'total':len(items),'current_number':q['collection_number'],'seconds':round(time.perf_counter()-started,1),
                            'model_calls':reader.calls,'rss_bytes':psutil.Process().memory_info().rss})
                        print(f"[transcript] {q['collection_number']} · {len(row['formula_candidates'])} formulas · {row['transcript_status']}",flush=True)
                    except Exception as error:
                        write_json(output/'failures'/target.name,{'question_id':q['question_id'],
                            'collection_number':q['collection_number'],'pipeline_identity':identity,
                            'error':str(error),'at':now(),'source_sha256':digest,
                            'status':'FAILED_NOT_EXPORTED','publishable':False})
                        print(f"[transcript-failed] {q['collection_number']}: {error}",flush=True)
            if file_hash(pdf_path)!=digest:raise ValueError('ORIGINAL_PDF_CHANGED_DURING_TRANSCRIPTION')
    finally:syntax.close()
    return results


def publish(output,selection,identity,source_sha,*,running=False):
    output=Path(output);records=[];index=[]
    allowed={q['question_id'] for q in selection['questions']}
    for p in sorted((output/'records').glob('*.json')):
        row=read_json(p)
        if row['question_id'] not in allowed:continue
        if row.get('pipeline_identity')!=identity:continue
        records.append(row)
    records.sort(key=lambda q:q['collection_number'])
    for q in records:
        entry={'question_id':q['question_id'],'number':q['collection_number'],'label':q['source_label'],
            'chapter_id':q['chapter_id'],'chapter_title':q['chapter_title'],'source_name':q['source']['name'],
            'evaluation':next(s['evaluation'] for s in selection['questions'] if s['question_id']==q['question_id']),
            'status':q['transcript_status'],'issues':len(q['issues']),'formulas':len(q['formula_candidates']),
            'record':'records/q-'+content_hash(q['question_id'])[:24]+'.json'}
        review='reviews/q-'+content_hash(q['question_id'])[:24]+'.json'
        if (output/review).is_file():entry['qwen_review']=review
        index.append(entry)
    write_jsonl(output/'metadata.transcribed.draft.jsonl',records)
    write_json(output/'metadata.transcribed.draft.pretty.json',records)
    formulas=[f for q in records for f in q['formula_candidates']]
    report={'schema_version':VERSION,'status':'RUNNING' if running else 'COMPLETE_DRAFT',
        'updated_at':now(),'pipeline_identity':identity,'source_jsonl_sha256':source_sha,
        'selected_questions':selection['count'],'completed_questions':len(records),
        'evaluation_selected':selection['evaluation_count'],'evaluation_completed':sum(q['evaluation'] for q in index),
        'chapter_counts':dict(Counter(q['chapter_id'] for q in records)),
        'source_documents':len({q['source']['sha256'] for q in records}),
        'formula_regions':len(formulas),'syntax_counts':dict(Counter(f['syntax']['status'] for f in formulas)),
        'methods':dict(Counter(f['method'] for f in formulas)),
        'displayed_latex_regions':sum(bool(f.get('display_latex')) for f in formulas),
        'image_fallback_regions':sum(not f.get('display_latex') for f in formulas),
        'transcription_check_counts':dict(Counter(i for f in formulas for i in f.get('transcription_checks',{}).get('issues',[]))),
        'comparison_counts':dict(Counter(f['comparison'] for f in formulas)),
        'question_statuses':dict(Counter(q['transcript_status'] for q in records)),
        'issue_counts':dict(Counter(i['code'] for q in records for i in q['issues'])),
        'total_model_calls':sum(q['runtime']['model_calls'] for q in records),
        'secondary_model_calls':sum(q['runtime'].get('secondary_model_calls',0) for q in records),
        'qwen_review_files':sum('qwen_review' in q for q in index),
        'max_worker_rss_bytes':max([q['runtime']['rss_bytes'] for q in records]+[0]),
        'source_glyph_coverage_is_heuristic':True,'mathematical_accuracy_established':False,
        'academic_review':'PENDING','publishable':False,'cloud_calls':0,'canonical_modified':False}
    write_json(output/'catalog.json',{'report':report,'questions':index})
    write_json(output/'report.json',report)
    return report


def run(source,plan,output,runtime,katex,*,count=100,workers=2):
    import psutil
    source,output,runtime,katex=map(lambda p:Path(p).resolve(),[source,output,runtime,katex])
    if workers not in {1,2}:raise ValueError('USE_ONE_OR_TWO_WORKERS')
    if output==source.parent:raise ValueError('SEPARATE_OUTPUT_DIRECTORY_REQUIRED')
    output.mkdir(parents=True,exist_ok=True);(output/'records').mkdir(exist_ok=True)
    if os.name=='nt':psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    configure_storage(runtime);before=file_hash(source);records=[json.loads(l) for l in source.open(encoding='utf-8') if l.strip()]
    selection=select(records,count);selection['canonical_metadata_sha256']=before
    saved=output/'selection.json'
    if saved.exists() and read_json(saved)!=selection:raise ValueError('SELECTION_OR_INPUT_CHANGED_USE_NEW_OUTPUT_DIRECTORY')
    write_json(saved,selection)
    identity=content_hash({'code':code_identity(),'packages':inference_versions(),
        'weights':{name:file_hash(runtime/'paddlex/official_models'/name/'inference.pdiparams')
            for name in ['PP-FormulaNet_plus-M','PP-FormulaNet_plus-S']},
        'katex_js':file_hash(katex/'katex.js'),'source_sha256':before,'dpi':288,'threads':3})
    ids={q['question_id'] for q in selection['questions']};chosen=[q for q in records if q['question_id'] in ids]
    # Runtime identity is stored per record, never accepted from the catalogue.
    documents={d['sha256']:d['path'] for d in read_json(Path(plan))['documents']}
    vendor=output/'vendor';vendor.mkdir(exist_ok=True)
    for name in ['katex.min.js','katex.min.css']:shutil.copy2(katex/name,vendor/name)
    shutil.copytree(katex/'fonts',vendor/'fonts',dirs_exist_ok=True)
    shutil.copy2(Path(__file__).with_name('transcript.html'),output/'review.html')
    started=time.perf_counter();peak=0;own=psutil.Process();failures=[]
    batches=[chosen[i::workers] for i in range(workers)]
    publish(output,selection,identity,before,running=True)
    with ProcessPoolExecutor(max_workers=workers,mp_context=multiprocessing.get_context('spawn')) as pool:
        futures=[pool.submit(worker,batch,documents,str(output),str(runtime),str(katex),identity) for batch in batches]
        while not all(f.done() for f in futures):
            rss=own.memory_info().rss
            for p in own.children(recursive=True):
                try:rss+=p.memory_info().rss
                except psutil.Error:pass
            peak=max(peak,rss)
            status=publish(output,selection,identity,before,running=True)
            write_json(output/'runtime.json',{'pid':os.getpid(),'updated_at':now(),'workers':workers,'threads_per_ocr_worker':3,
                'elapsed_seconds':round(time.perf_counter()-started,1),'process_tree_rss_bytes':rss,
                'peak_process_tree_rss_bytes':peak,'system_available_bytes':psutil.virtual_memory().available,
                'cpu_percent':psutil.cpu_percent(),'completed':status['completed_questions'],'selected':count})
            time.sleep(2)
        for future in futures:
            try:future.result()
            except Exception as error:failures.append(str(error))
    if file_hash(source)!=before:raise ValueError('CANONICAL_METADATA_CHANGED_DURING_TRANSCRIPTION')
    result=publish(output,selection,identity,before,running=False)
    result.update(elapsed_seconds=round(time.perf_counter()-started,2),peak_process_tree_rss_bytes=peak,
                  workers=workers,failures=failures)
    if failures or result['completed_questions']!=count:result['status']='INCOMPLETE_DRAFT'
    write_json(output/'report.json',result)
    catalog=read_json(output/'catalog.json');catalog['report']=result;write_json(output/'catalog.json',catalog)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['input','plan','output','runtime','katex']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--count',type=int,default=100);p.add_argument('--workers',type=int,default=2)
    a=p.parse_args();result=run(a.input,a.plan,a.output,a.runtime,a.katex,count=a.count,workers=a.workers)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']=='INCOMPLETE_DRAFT':sys.exit(1)
