"""PDF to source-backed, routed metadata with one reusable entry point."""
import argparse
import json
from pathlib import Path
import shutil
import time
import unicodedata
import subprocess
import sys
import os

from .storage import configure_storage,file_hash,read_json,write_json,write_jsonl
from .pdf_workflow import local_lock
from .paired.fast_native import extract
from .paired.corpus import document,code_identity as source_code_identity
from .paired.transcript_batch import content_hash
from .paired.selection_cli import all_records
from .paired.transcription_v2.batch import parser as transcript_parser,run as transcribe,code_identity
from .curation import export as curate


def chapter_name(path):
    text=''.join(c for c in unicodedata.normalize('NFKD',path.name.lower()) if not unicodedata.combining(c))
    for name,keys in {'derivative_applications':['dao-ham'],'integrals':['tich-phan','nguyen-ham'],
                      'grouped_statistics':['thong-ke','ghep-nhom'],'probability':['xac-suat']}.items():
        if any(key in text for key in keys):return name
    return 'unclassified'


def run(pdf,storage,repo,*,profile='native',workers=2,timeout=1800,memory_limit_mb=8192):
    pdf,storage,repo=map(lambda p:Path(p).resolve(),(pdf,storage,repo))
    if not pdf.is_file() or pdf.suffix.lower()!='.pdf':raise ValueError('PDF_FILE_REQUIRED')
    runtime=storage/'pdf-pipeline-runtime';configure_storage(runtime);digest=file_hash(pdf)
    identity=content_hash({'pdf':digest,'profile':profile,'code':code_identity(),
        'workflow':file_hash(Path(__file__)),'curation':file_hash(Path(__file__).with_name('curation.py')),
        'source_recheck':file_hash(Path(__file__).with_name('source_recheck.py')),
        'source_parser':source_code_identity()})[:16]
    job=storage/'pdf-jobs'/digest[:24];output=job/'usable-dataset'/identity
    output.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    with local_lock(output):
        def progress(stage,counts=None):
            write_json(output/'progress.json',{'stage':stage,'profile':profile,'source':pdf.name,
                'elapsed_seconds':round(time.perf_counter()-started,2),**(counts or {})})
        work=output/'source';chapter=chapter_name(pdf)
        source={'document_id':digest[:16],'label':pdf.name,'path':str(pdf),'sha256':digest,'chapter':chapter}
        progress('EXTRACT_SOURCE')
        native,native_pages=extract(pdf,work/'native',event=lambda stage,counts:progress('EXTRACT_SOURCE',counts))
        del native_pages
        source['pages']=native['pages'];write_json(work/'source.json',source)
        progress('PAIR_QUESTIONS_AND_SOLUTIONS')
        raw=document(work/'source.json',work,runtime,use_ocr=profile=='ocr')
        questions=[]
        with Path(raw['questions_jsonl']).open(encoding='utf-8') as stream:
            for line in stream:
                if line.strip():
                    row=json.loads(line);row['collection_number']=len(questions)+1;questions.append(row)
        metadata=output/'questions.source.jsonl';write_jsonl(metadata,questions)
        plan=output/'plan.json';write_json(plan,{'documents':[{'path':str(pdf),'sha256':digest,'page_count':source['pages']}]})
        target=output/'final';target.mkdir(exist_ok=True)
        if questions:
            selection=output/'selection.json';all_records(metadata,selection)
            transcripts=output/'transcription';progress('TRANSCRIBE',{'questions':len(questions)})
            args=['--input',str(metadata),'--plan',str(plan),'--selection',str(selection),'--output',str(transcripts),
                  '--runtime',str(runtime),'--katex',str(repo/'frontend/node_modules/katex/dist'),
                  '--workers',str(workers),'--run-timeout',str(timeout),'--chunk-timeout',str(min(timeout,1800)),
                  '--memory-limit-mb',str(memory_limit_mb),'--cache-mode','local']
            if profile=='native':args.append('--native-only')
            result=transcribe(transcript_parser().parse_args(args));progress('ROUTE_WHOLE_QUESTIONS')
            summary=curate(transcripts,target,plan=plan,katex=repo/'frontend/node_modules/katex/dist')
        else:
            result={'status':'NO_PAIRED_QUESTIONS'}
            for name in ['metadata.final','core_candidates','image_reference','held_items']:write_jsonl(target/(name+'.jsonl'),[])
            write_json(target/'metadata.final.pretty.json',[])
            summary={'status':'SOURCE_ONLY_NO_PAIRED_QUESTIONS','questions':0,
                     'counts':{'core_candidates':0,'image_reference':0,'held_items':0},'production_grading_ready':0}
            shutil.copy2(Path(__file__).with_name('curation_view.html'),target/'index.html')
            write_json(target/'catalog.json',{'summary':summary,'questions':[]})
        # Unpaired occurrences and page references remain separate record kinds;
        # never invent a question or a solution just to make counts look complete.
        shutil.copy2(raw['review_jsonl'],target/'held_source_occurrences.jsonl')
        page_refs=[]
        for p in read_json(work/'solved/page-review-queue.json'):
            pn=p['page_number'];source_image=work/f'native/pages/page-{pn:04}.png'
            asset=f'assets/source-pages/page-{pn:04}.png';destination=target/asset;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source_image,destination)
            page_refs.append({'kind':'PAGE_REFERENCE','page_number':pn,'asset_path':asset,
                              'asset_sha256':file_hash(destination),'reason':p['reason'],'publishable':False})
        write_jsonl(target/'held_pages.jsonl',page_refs)
        if file_hash(pdf)!=digest:raise ValueError('SOURCE_PDF_CHANGED')
        summary.update({'profile':profile,'source_pdf':str(pdf),'source_sha256':digest,'source_pages':source['pages'],
            'unpaired_source_occurrences':raw['unselected_occurrences'],'page_references':len(page_refs),
            'transcription_status':result['status'],'elapsed_seconds':round(time.perf_counter()-started,2),
            'cloud_api_calls':0,'source_unchanged':True,'final_directory':str(target),
            'final_jsonl':str(target/'metadata.final.jsonl'),'review':str(target/'index.html')})
        write_json(target/'summary.json',summary);catalog=read_json(target/'catalog.json');catalog['summary']=summary;write_json(target/'catalog.json',catalog)
        write_json(job/'dataset-final.json',summary);progress(summary['status'],summary)
        return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['pdf','storage','repo']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--profile',choices=['native','ocr'],default='native');p.add_argument('--workers',type=int,choices=[1,2],default=2)
    p.add_argument('--timeout',type=int,default=1800);p.add_argument('--memory-limit-mb',type=int,default=8192)
    p.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    a=p.parse_args()
    if not a.worker:
        import psutil
        from .readiness.batch import stop_owned
        child=subprocess.Popen([sys.executable,'-B','-u','-m','pdfmeta.dataset_workflow',*sys.argv[1:],'--worker'],
            stdin=subprocess.DEVNULL,creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name=='nt' else 0)
        started=time.monotonic()
        try:
            while child.poll() is None:
                rss=0
                try:
                    owned=psutil.Process(child.pid)
                    for process in [owned,*owned.children(recursive=True)]:
                        try:rss+=process.memory_info().rss
                        except psutil.Error:pass
                except psutil.Error:pass
                if time.monotonic()-started>a.timeout:raise TimeoutError('DATASET_TIME_BUDGET_REACHED_RESUME_SAME_COMMAND')
                if rss>a.memory_limit_mb*1024**2:raise MemoryError('DATASET_MEMORY_BUDGET_REACHED')
                if shutil.disk_usage(a.storage).free<2048*1024**2:raise OSError('DATASET_FREE_DISK_FLOOR_REACHED')
                time.sleep(.5)
        except BaseException:
            stop_owned(child);child.wait(timeout=10);raise
        raise SystemExit(child.returncode)
    options=vars(a);options.pop('worker');result=run(**options);print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if result['status'] in {'CURATED_DRAFT_COMPLETE','SOURCE_ONLY_NO_PAIRED_QUESTIONS'} else 1)
