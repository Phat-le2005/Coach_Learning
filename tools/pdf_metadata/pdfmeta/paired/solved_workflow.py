"""Sequential, resumable source-image collection for the four Toan12 groups.

No inference API, mathematical approval or grading promotion is performed.
The standalone PDF renderer is a separate final step with ReportLab installed.
"""
from __future__ import annotations

import argparse
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unicodedata

from ..corpus import inventory
from ..pdf_workflow import local_lock
from ..storage import file_hash,read_json,write_json
from .corpus import CHAPTERS,code_identity
from .corpus_merge import merge
from .fast_native import extract


def chapter_for(label,default=None):
    text=''.join(c for c in unicodedata.normalize('NFKD',label.lower()) if not unicodedata.combining(c))
    for chapter,keywords in {
        'derivative_applications':['derivative_applications','dao-ham','dao_ham'],
        'integrals':['integrals','nguyen-ham','tich-phan'],
        'grouped_statistics':['grouped_statistics','ghep-nhom','thong-ke'],
        'probability':['probability','xac-suat'],
    }.items():
        if any(k in text for k in keywords):return chapter
    if default in CHAPTERS:return default
    raise ValueError('CHAPTER_NOT_IDENTIFIED: '+label+'; specify --chapter or use a chapter folder')


def cached_report(work,source,identity):
    path=work/'solved/report.json'
    if not path.exists():return None
    report=read_json(path)
    if report.get('source_pdf_sha256')!=source['sha256'] or report.get('source_code_hash')!=identity:return None
    for key,hash_key in [('questions_jsonl','questions_sha256'),('review_jsonl','review_sha256')]:
        target=Path(report.get(key,''))
        if not target.is_file() or file_hash(target)!=report.get(hash_key):return None
    return report


def run(root,runtime,output,archive,*,input_path=None,default_chapter=None):
    root,runtime,output,archive=map(lambda p:Path(p).resolve(),(root,runtime,output,archive))
    with local_lock(root):
        profile_path=root/'profile.json'
        if input_path:
            sources=inventory(Path(input_path),root/'inventory')
            profile=[{**s,'pages':s['page_count'],'chapter':chapter_for(s['label'],default_chapter)} for s in sources]
            if profile_path.exists() and {s['sha256'] for s in read_json(profile_path)}!={s['sha256'] for s in profile}:
                raise ValueError('WORK_DIRECTORY_BELONGS_TO_ANOTHER_COLLECTION')
            write_json(profile_path,profile)
        else:profile=read_json(profile_path)
        if not profile or len({s['sha256'] for s in profile})!=len(profile):raise ValueError('EMPTY_OR_DUPLICATE_SOURCE_PROFILE')
        if not archive.is_file():raise ValueError('ARCHIVE_SOURCE_IDENTITY_FILE_REQUIRED')
        identity=code_identity();completed=[];failed=[];overall=time.perf_counter()
        for index,source in enumerate(profile,1):
            work=root/'documents'/source['sha256'][:24];write_json(work/'source.json',source)
            if file_hash(Path(source['path']))!=source['sha256']:raise ValueError('SOURCE_FILE_CHANGED')
            # Validate page image hashes even when the paired metadata is cached.
            def progress(stage,counters):
                write_json(root/'controller.json',{'status':'RUNNING','stage':stage,'document':source['document_id'],
                    'document_label':source['label'],'document_index':index,'documents_total':len(profile),
                    'completed':completed,'failed':failed,**counters})
            native,pages=extract(Path(source['path']),work/'native',event=progress)
            del pages;gc.collect()
            if native['pages']!=source['pages']:raise ValueError('SOURCE_PAGE_COUNT_CHANGED')
            report=cached_report(work,source,identity);cached=report is not None
            if report is None:
                command=[sys.executable,'-B','-u','-m','pdfmeta.paired.corpus','--source',str(work/'source.json'),
                    '--work',str(work),'--runtime',str(runtime)]
                flags=(subprocess.CREATE_NO_WINDOW|subprocess.BELOW_NORMAL_PRIORITY_CLASS) if os.name=='nt' else 0
                started=time.perf_counter()
                with (work/'worker.log').open('ab') as log:
                    worker=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=flags)
                    try:
                        while worker.poll() is None:
                            progress('pairing',{'pid':worker.pid,'seconds_current':round(time.perf_counter()-started,1)})
                            time.sleep(2)
                    except BaseException:
                        worker.terminate();worker.wait(timeout=15);raise
                if worker.returncode:
                    failed.append({'document_id':source['document_id'],'returncode':worker.returncode,'log':str(work/'worker.log')})
                    progress('failed',{});continue
                report=cached_report(work,source,identity)
                if report is None:raise ValueError('WORKER_DID_NOT_PRODUCE_VERIFIED_REPORT')
            completed.append({'document_id':source['document_id'],'selected_pairs':report['selected_pairs'],
                'question_occurrences':report['question_occurrences'],'cached':cached,'seconds':report['seconds'],
                'ocr_calls':report['ocr_calls'],'ocr_cache_hits':report['ocr_cache_hits']})
            write_json(root/'document-results.json',completed)
            print(json.dumps(completed[-1],ensure_ascii=False),flush=True)
        if failed:
            write_json(root/'controller.json',{'status':'COMPLETE_WITH_FAILURES','completed':completed,'failed':failed})
            raise ValueError('DOCUMENT_FAILURES_BLOCK_COLLECTION_EXPORT')
        report=merge(root,output,archive)
        from .metadata_readable import export as format_metadata
        format_metadata(output/'questions.metadata.jsonl')
        write_json(root/'controller.json',{'status':'SOURCE_COLLECTION_COMPLETE','completed':completed,'failed':[],
            'seconds':round(time.perf_counter()-overall,1),'result':report,'pdf_export_pending':True})
        return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['root','runtime','output','archive']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--input',type=Path);p.add_argument('--chapter',choices=CHAPTERS)
    a=p.parse_args()
    print(json.dumps(run(a.root,a.runtime,a.output,a.archive,input_path=a.input,default_chapter=a.chapter),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
