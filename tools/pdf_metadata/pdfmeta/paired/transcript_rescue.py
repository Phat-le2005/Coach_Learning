"""Retain failed sample items as explicit source-image-only drafts, never success."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import shutil

from ..storage import read_json,write_json,file_hash
from .transcript_batch import content_hash,VERSION


def run(source,plan,output):
    import pdfplumber
    source,output=Path(source),Path(output)
    report=read_json(output/'report.json');selection=read_json(output/'selection.json')
    if file_hash(source)!=selection['canonical_metadata_sha256']:raise ValueError('CANONICAL_INPUT_CHANGED')
    records={q['question_id']:q for line in source.open(encoding='utf-8') if line.strip() if (q:=json.loads(line))}
    docs={d['sha256']:Path(d['path']) for d in read_json(Path(plan))['documents']};rescued=[]
    for failure_path in (output/'failures').glob('*.json'):
        failed=read_json(failure_path)
        if failed['pipeline_identity']!=report['pipeline_identity']:continue
        target=output/'records'/failure_path.name
        if target.exists():
            old=read_json(target)
            if not old.get('rescue'):continue
            if old['rescue']['failure_sha256']==file_hash(failure_path):
                rescued.append(old['question_id']);continue
            history=output/'rescue-history'/(target.stem+'-'+file_hash(target)[:16]+'.json')
            history.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,history)
        q=records[failed['question_id']];digest=q['source']['sha256'];pdf_path=docs[digest]
        if file_hash(pdf_path)!=digest:raise ValueError('ORIGINAL_PDF_HASH_MISMATCH')
        started=time.perf_counter();parts={};issues=[]
        with pdfplumber.open(pdf_path) as pdf:
            for role in ['question','solution','answer']:
                fragments=[]
                for si,span in enumerate(q[role]['source_spans']):
                    asset=f"assets/q{q['collection_number']:04}/{role}-{si:02}-rescue-source.png"
                    (output/asset).parent.mkdir(parents=True,exist_ok=True)
                    pdf.pages[span['page_number']-1].crop(tuple(span['bbox'])).to_image(resolution=150).save(output/asset)
                    text='![Vùng nguồn chưa trích được]('+asset+')'
                    fragments.append({'page_number':span['page_number'],'bbox':span['bbox'],'source_asset':asset,
                        'source_asset_sha256':file_hash(output/asset),'markdown':text,'choices':[],
                        'coverage':{'method':'NOT_EXTRACTED_MODEL_FAILED','complete_formula_recall_established':False},
                        'source_errors':[{'reason':failed['error']}],'visual_flags':['TRANSCRIPTION_FAILED']})
                    issues.append({'role':role,'page_number':span['page_number'],'code':'TRANSCRIPTION_FAILED'})
                parts[role]={'markdown':'\n\n'.join(f['markdown'] for f in fragments),'choices':[],
                    'source_spans':q[role]['source_spans'],'raw_text_lossy':q[role].get('text_lossy',q[role].get('text_raw')),'fragments':fragments}
        row={'schema_version':VERSION,'question_id':q['question_id'],'collection_number':q['collection_number'],
            'source_label':q['source_label'],'chapter_id':q['chapter_id'],'chapter_title':q['chapter_title'],'source':q['source'],
            'pipeline_identity':report['pipeline_identity'],
            # Distinct identity forces a real extraction retry on a normal resume.
            'checkpoint_identity':content_hash({'rescue':True,'failure_sha256':file_hash(failure_path),'source_record':q}),
            'source_record_sha256':content_hash(q),'parts':parts,'formula_candidates':[],'issues':issues,
            'transcript_status':'SOURCE_IMAGE_ONLY_EXTRACTION_FAILED','academic_review':'PENDING',
            'grading_support':'NOT_ASSESSED','publishable':False,
            'rescue':{'failure_record':str(failure_path.relative_to(output)),'failure_sha256':file_hash(failure_path),
                      'reason':failed['error'],'math_transcription_completed':False,'inference_calls_in_rescue':0},
            'runtime':{'seconds':round(time.perf_counter()-started,3),'model_calls':0,'secondary_model_calls':0,
                       'failed_attempt_model_call_count_known':False,'ocr_cache_hits':0,'rss_bytes':0,'cloud_calls':0}}
        write_json(target,row);rescued.append(q['question_id'])
    write_json(output/'rescue-report.json',{'source_image_only_records':rescued,'math_transcription_completed':False,
        'academic_review':'PENDING','publishable':False,'cloud_calls':0})
    return rescued


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['input','plan','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.input,a.plan,a.output),ensure_ascii=False,indent=2))
