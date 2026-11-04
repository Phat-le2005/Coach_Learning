"""Run source-backed v2 batches or replay an explicitly frozen old selection."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
import json
import multiprocessing
from pathlib import Path
import shutil
import time

from ...storage import configure_storage,file_hash,read_json,write_json,write_jsonl,inference_versions
from ..transcript_batch import publish as publish_v1,code_identity as v1_code_identity,content_hash,now
from .engine import worker
from . import VERSION


def code_identity():
    root=Path(__file__).parent
    return content_hash({'v1_dependencies':v1_code_identity(),
        'v2':{p.name:file_hash(p) for p in sorted(root.glob('*.py'))}})


def publish(output,selection,identity,source_sha,running=True):
    report=publish_v1(output,selection,identity,source_sha,running=running)
    records=[read_json(p) for p in sorted((output/'records').glob('*.json'))
             if read_json(p).get('pipeline_identity')==identity]
    tables=[t for q in records for t in q['tables']]
    report.update(schema_version=VERSION,table_regions=len(tables),table_cells=sum(len(t['cells']) for t in tables),
        table_cells_native_draft=sum(c['display_text'] is not None for t in tables for c in t['cells']),
        failed_regions=sum(bool(f.get('region_error')) for q in records for f in q['formula_candidates']),
        source_images_provided_to_vision_model=False,vision_stage='NOT_RUN',full_grading_ready=False)
    write_json(output/'report.json',report);catalog=read_json(output/'catalog.json');catalog['report']=report;write_json(output/'catalog.json',catalog)
    content=[{'collection_number':q['collection_number'],'question_id':q['question_id'],'chapter_title':q['chapter_title'],
        'source':q['source'],'question':q['parts']['question'],'solution':q['parts']['solution'],
        'answer':q['parts']['answer'],'tables':q['tables'],'academic_review':'PENDING',
        'grading_support':'NOT_ASSESSED','publishable':False} for q in records]
    content.sort(key=lambda q:q['collection_number'])
    write_jsonl(output/'content.draft.jsonl',content);write_json(output/'content.draft.pretty.json',content)
    return report


def raw_cache_index(baseline,root):
    index={}
    for relative,sha in baseline.items():
        if '\\ocr-cache\\' not in relative and '/ocr-cache/' not in relative:continue
        p=root/relative
        if file_hash(p)!=sha:raise ValueError('V1_CACHE_CHANGED_BEFORE_REUSE')
        row=read_json(p);key=content_hash(row['identity'])
        # FormulaReader uses json.dumps default ensure_ascii=True; identity is
        # ASCII-only, but preserve its exact cache serialization nonetheless.
        import hashlib
        key=hashlib.sha256(json.dumps(row['identity'],sort_keys=True).encode()).hexdigest()
        index[key]={'path':str(p),'sha256':sha}
    return index


def viewer(output,katex):
    vendor=output/'vendor';vendor.mkdir(exist_ok=True)
    for name in ['katex.min.js','katex.min.css']:shutil.copy2(katex/name,vendor/name)
    shutil.copytree(katex/'fonts',vendor/'fonts',dirs_exist_ok=True)
    shutil.copy2(Path(__file__).with_name('review.html'),output/'review.html')


def run(args):
    from .runner import run as run_batch
    return run_batch(args)


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['input','plan','output','runtime','katex']:
        p.add_argument('--'+name,type=Path,required=True)
    for name in ['v1','baseline','selection']:
        p.add_argument('--'+name,type=Path)
    p.add_argument('--exclude-selection',type=Path,action='append',default=[])
    p.add_argument('--count',type=int,default=100)
    p.add_argument('--seed',default='pdf-scale-trial-20261104')
    p.add_argument('--workers',type=int,choices=[1,2],default=2)
    p.add_argument('--chunk-size',type=int,default=10)
    p.add_argument('--max-page-cache',type=int,default=8)
    p.add_argument('--chunk-timeout',type=float,default=1800)
    p.add_argument('--run-timeout',type=float,default=14400)
    p.add_argument('--memory-limit-mb',type=int,default=8192)
    p.add_argument('--min-free-disk-mb',type=int,default=2048)
    p.add_argument('--cache-mode',choices=['local','cold','import-v1'],default='local')
    p.add_argument('--stop-after-chunks',type=int,default=0)
    p.add_argument('--plan-only',action='store_true')
    p.add_argument('--native-only',action='store_true')
    return p


def main(argv=None):
    result=run(parser().parse_args(argv))
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    if result['status']=='PAUSED_DRAFT':return 3
    return 0 if result['status'] in {'COMPLETE_DRAFT','PLANNED'} else 1


if __name__=='__main__':
    raise SystemExit(main())
