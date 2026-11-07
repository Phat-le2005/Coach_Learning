"""A sequential, hash-deduplicated queue. Each PDF still uses the public entry."""
from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile
import zlib

from ..gemini_client import content_hash
from ..pdf_workflow import local_lock
from ..progress import now,owner
from ..storage import file_hash,read_json,write_json


def discover(inputs,storage):
    storage=Path(storage).resolve();found=[]
    for value in inputs:
        path=Path(value).resolve()
        if path.is_dir():found.extend(sorted(path.rglob('*.pdf')))
        elif path.suffix.lower()=='.pdf' and path.is_file():found.append(path)
        elif path.suffix.lower()=='.zip' and path.is_file():
            archive_hash=file_hash(path);directory=storage/'archive-inputs'/archive_hash[:24]
            with zipfile.ZipFile(path) as archive:
                for info in sorted(archive.infolist(),key=lambda v:v.filename):
                    if not info.filename.lower().endswith('.pdf') or info.is_dir():continue
                    if info.file_size>512*1024**2:raise ValueError('ARCHIVE_MEMBER_TOO_LARGE')
                    # Flatten and namespace by full member name; never extract paths.
                    name=content_hash(info.filename)[:12]+'-'+Path(info.filename.replace('\\','/')).name
                    target=directory/name;directory.mkdir(parents=True,exist_ok=True)
                    if target.is_symlink() or not target.resolve().is_relative_to(directory.resolve()):raise ValueError('ARCHIVE_CACHE_PATH_ESCAPE')
                    crc=0
                    if target.exists():
                        with target.open('rb') as stream:
                            for chunk in iter(lambda:stream.read(1024*1024),b''):crc=zlib.crc32(chunk,crc)
                    if not target.exists() or target.stat().st_size!=info.file_size or crc!=info.CRC:
                        temp=target.with_suffix('.pdf.pending')
                        with archive.open(info) as source,temp.open('wb') as output:shutil.copyfileobj(source,output,1024*1024)
                        temp.replace(target)
                    found.append(target)
        else:raise ValueError('INPUT_MUST_BE_PDF_FOLDER_OR_ZIP: '+str(path))
    unique={}
    for pdf in found:
        digest=file_hash(pdf)
        if digest not in unique:unique[digest]={'pdf':str(pdf),'sha256':digest,'job_id':digest[:24]}
    return list(unique.values())


def code_identity(repo):
    root=Path(repo)/'tools/pdf_metadata'
    paths=[p for p in root.rglob('*') if p.suffix in {'.py','.ps1','.cmd','.json','.html'} and '__pycache__' not in p.parts
           and not p.is_relative_to(root/'tests') and not p.is_relative_to(root/'fixtures')]
    return content_hash({p.relative_to(root).as_posix():file_hash(p) for p in sorted(paths)})


def stop_owned(process):
    import psutil
    try:root=psutil.Process(process.pid);children=root.children(recursive=True)
    except psutil.NoSuchProcess:return
    for child in reversed(children):
        try:child.terminate()
        except psutil.NoSuchProcess:pass
    try:root.terminate()
    except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs([*children,root],timeout=3)
    for proc in alive:
        try:proc.kill()
        except psutil.NoSuchProcess:pass


def execute(item,*,repo,storage,log,review_limit,visual_limit,skip_qwen,timeout):
    shell=shutil.which('pwsh') or shutil.which('powershell')
    if not shell:raise ValueError('POWERSHELL_REQUIRED_FOR_WINDOWS_WORKFLOW')
    command=[shell,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(Path(repo)/'tools/pdf_metadata/process_pdf.ps1'),
             item['pdf'],'-Storage',str(storage),'-ReviewLimit',str(review_limit),'-VisualLimit',str(visual_limit)]
    if skip_qwen:command.append('-SkipQwen')
    with log.open('ab') as stream:
        process=subprocess.Popen(command,cwd=repo,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,
                                  creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name=='nt' else 0)
        started=time.monotonic();peak=0
        try:
            import psutil
            while process.poll() is None:
                try:
                    parent=psutil.Process(process.pid)
                    total=0
                    for worker in [parent,*parent.children(recursive=True)]:
                        try:total+=worker.memory_info().rss
                        except psutil.Error:pass
                    peak=max(peak,total)
                except psutil.Error:pass
                if time.monotonic()-started>timeout:raise TimeoutError('PDF_TIME_BUDGET_REACHED')
                try:process.wait(timeout=.5)
                except subprocess.TimeoutExpired:pass
            code=process.returncode
            if code:raise ValueError('PDF_WORKER_FAILED_SEE_LOG')
        except BaseException:
            stop_owned(process);raise
    job=Path(storage)/'pdf-jobs'/item['job_id']
    final=read_json(job/'final.json');image=read_json(job/'image-check.json');core=read_json(job/'core-package.json')
    return {'job':str(job),'final':str(job/'final.json'),'final_status':final['status'],
            'question_count':final['question_count'],'image_regions':image['selected_regions'],
            'core_steps':core['step_count'],'grading_ready_count':core['grading_ready_count'],
            'sampled_peak_ram_mb':round(peak/1024**2,1),'ram_sample_interval_seconds':.5}


def run(inputs,*,repo,storage,review_limit=3,visual_limit=8,skip_qwen=False,max_pages=100,max_pdfs=0,
        timeout=3600,retry_failed=False,oversize_policy='run',executor=None):
    repo,storage=Path(repo).resolve(),Path(storage).resolve()
    if min(review_limit,visual_limit,max_pages,max_pdfs)<0 or timeout<=0:raise ValueError('INVALID_QUEUE_BUDGET')
    if oversize_policy not in {'run','defer'}:raise ValueError('INVALID_OVERSIZE_POLICY')
    import pypdfium2 as pdfium
    items=discover(inputs,storage)
    for item in items:
        with pdfium.PdfDocument(item['pdf']) as doc:item['pages']=len(doc)
    config={'code':code_identity(repo),'review_limit':review_limit,'visual_limit':visual_limit,'skip_qwen':skip_qwen}
    identity=content_hash({'sources':[i['sha256'] for i in items],'config':config})[:24]
    directory=storage/'pdf-queues'/identity;state_path=directory/'queue.json'
    with local_lock(storage/'pdf-queues/worker'):
        previous=read_json(state_path) if state_path.exists() else {}
        lookup={i['sha256']:i for i in previous.get('items',[])};entries=[]
        for item in items:
            old=lookup.get(item['sha256'],{})
            entry={**item,'status':old.get('status','PENDING'),'result':old.get('result'),
                   'attempts':old.get('attempts',0),'log':str(directory/(item['job_id']+'.log'))}
            for key in ['seconds','started_at','finished_at','error']:
                if key in old:entry[key]=old[key]
            if entry['status']=='RUNNING':entry['status']='INTERRUPTED'
            # A queue checkpoint is valid only while all pointed-to reports remain unchanged.
            if entry['status']=='COMPLETED':
                hashes=old.get('result_hashes',{})
                if not hashes or any(not Path(p).is_file() or file_hash(Path(p))!=h for p,h in hashes.items()):entry['status']='PENDING'
                else:entry['result_hashes']=hashes
            entries.append(entry)
        state={'schema_version':'pdf-batch/v1','queue_id':identity,'owner':owner(),'config':config,
               'status':'RUNNING','started_at':now(),'items':entries,'max_pages_this_run':max_pages,'max_pdfs_this_run':max_pdfs,
               'page_budget_policy':'SOFT_WHOLE_DOCUMENT_BUDGET_PRESERVES_CROSS_PAGE_SOLUTIONS','oversize_policy':oversize_policy}
        def save():
            state.update(updated_at=now(),counts=dict(Counter(i['status'] for i in entries)))
            write_json(state_path,state);write_json(storage/'pdf-queues/latest.json',{'queue':str(state_path),'queue_id':identity})
        save();pages=count=0
        try:
            for item in entries:
                if item['status']=='COMPLETED':continue
                if item['status'] in {'FAILED','INTERRUPTED'} and not retry_failed:continue
                if max_pdfs and count>=max_pdfs:
                    item['defer_reason']='MAX_PDFS_THIS_RUN';save();continue
                if max_pages and pages+item['pages']>max_pages:
                    if count==0 and item['pages']>max_pages and oversize_policy=='run':
                        item['budget_overrun_pages']=item['pages']-max_pages
                        print('[queue] OVERSIZE_DOCUMENT_RUN_WHOLE · '+item['pdf'],flush=True)
                    else:
                        item['defer_reason']='DOCUMENT_EXCEEDS_PAGE_BUDGET' if item['pages']>max_pages else 'PAGE_BUDGET_THIS_RUN'
                        save();continue
                item.pop('defer_reason',None)
                if file_hash(Path(item['pdf']))!=item['sha256']:raise ValueError('QUEUED_SOURCE_CHANGED')
                item.update(status='RUNNING',attempts=item['attempts']+1,started_at=now());save()
                started=time.perf_counter()
                try:
                    item['result']=(executor or execute)(item,repo=repo,storage=storage,
                        log=Path(item['log']),review_limit=review_limit,visual_limit=visual_limit,
                        skip_qwen=skip_qwen,timeout=timeout)
                    if file_hash(Path(item['pdf']))!=item['sha256']:raise ValueError('QUEUED_SOURCE_CHANGED')
                    item['result_hashes']={str(p):file_hash(p) for p in [Path(item['result']['final']),Path(item['result']['job'])/'image-check.json',Path(item['result']['job'])/'core-package.json']}
                    item['status']='COMPLETED';item.pop('error',None)
                except Exception as error:item.update(status='FAILED',error=type(error).__name__+': '+str(error)[:160])
                finally:item.update(seconds=round(time.perf_counter()-started,3),finished_at=now());pages+=item['pages'];count+=1;save()
                print(f"[queue] {item['job_id']} · {item['status']}",flush=True)
            state['status']='COMPLETED' if all(i['status']=='COMPLETED' for i in entries) else 'PARTIAL'
            state.update(pages_attempted=pages,documents_attempted=count,finished_at=now());save()
            return {'queue':str(state_path),'status':state['status'],'counts':state['counts'],'pages_attempted':pages}
        except BaseException:
            state['status']='INTERRUPTED'
            for item in entries:
                if item['status']=='RUNNING':item['status']='INTERRUPTED'
            save();raise
