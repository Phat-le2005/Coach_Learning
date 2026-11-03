"""Bounded local formula/endpoint reading on source-grounded paired records."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import re
import time

from ..gemini_client import content_hash
from ..pdf_workflow import local_lock
from ..storage import configure_storage, file_hash, read_json, write_json, write_jsonl
from .dataset import from_html, export
from .probability import character, endpoint, event_guard, native_events
from .viewer import render


VERSION = 'paired-formula-quality/v1'


def region(question, pages, role='solution'):
    spans = question[role]['source_spans']; gs = []
    for span in spans:
        allowed = set(span['block_ids'])
        for b in pages[span['page_number']]['blocks']:
            if b['block_id'] not in allowed: continue
            gs.extend({'page': span['page_number'], 'block': b, **g, 'char': character(g)} for g in b.get('glyphs', []))
    equal = [g for g in gs if g['char'] in {'=', '≈', '≃', '≅'}]
    if not equal: raise ValueError('NO_EQUATION_ANCHOR_IN_SOURCE')
    last = max(equal, key=lambda g:(g['page'],round((g['bbox'][1]+g['bbox'][3])/8),g['bbox'][0]))
    number = last['page']; cy = (last['bbox'][1]+last['bbox'][3])/2; size=last['size']
    nearby = [g for g in gs if g['page']==number and abs((g['bbox'][1]+g['bbox'][3])/2-cy)<size*2.8]
    same = [g for g in nearby if abs((g['bbox'][1]+g['bbox'][3])/2-cy)<size*.8]
    ps = [g for g in same if g['char']=='P' and g['bbox'][0]<last['bbox'][0]]
    if ps: left=min(g['bbox'][0] for g in ps)
    else:
        numeric = [g for g in nearby if g['char'] and re.fullmatch(r'[0-9]',g['char']) and g['bbox'][0]<last['bbox'][0]]
        left=min((g['bbox'][0] for g in numeric),default=last['block']['bbox'][0])
    math = [g for g in nearby if g['bbox'][0]>=left-1 and g['char'] and re.fullmatch(r'[PA-Z0-9(),.=+−\-/%|∣∩∪≈≃⋅]',g['char'])
        and (g['block']['block_id']==last['block']['block_id'] or not re.search(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]',g['block']['text_raw'],re.I))]
    if not math: raise ValueError('MATH_REGION_UNRESOLVED')
    box=[min(g['bbox'][0] for g in math)-2,min(g['bbox'][1] for g in math)-3,max(g['bbox'][2] for g in math)+2,max(g['bbox'][3] for g in math)+3]
    source = next(s for s in spans if s['page_number']==number and s['bbox'][1]<=cy<=s['bbox'][3])
    box=[max(source['bbox'][0],box[0]),max(source['bbox'][1],box[1]),min(source['bbox'][2],box[2]),min(source['bbox'][3],box[3])]
    return {'question_id':question['question_id'],'role':role,'page_number':number,'bbox':box,
        'source_block_ids':source['block_ids'],'selection':'LAST_SOURCE_EQUATION_REGION_NOT_COMPLETE_SOLUTION'}


def prepare(job, selection, output):
    job, output = Path(job).resolve(), Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    report=read_json(job/'paired.json'); payload=from_html(report['single_file_html'])
    chosen=read_json(selection)
    if chosen['source_pdf_sha256']!=payload['source']['sha256']:raise ValueError('SAMPLE_PDF_MISMATCH')
    ids=chosen['question_ids']
    if len(ids)!=len(set(ids)) or not 1<=len(ids)<=30:raise ValueError('SAMPLE_SIZE_OR_DUPLICATE_ID')
    lookup={q['question_id']:q for q in payload['questions']};pages={}
    for qid in ids:
        if qid not in lookup or lookup[qid]['pair_status']!='PAIRED_LAYOUT_CANDIDATE':raise ValueError('SAMPLE_QUESTION_NOT_PAIRED')
        for part in ['question','solution']:
            for s in lookup[qid][part]['source_spans']:
                n=s['page_number']
                if n not in pages:pages[n]=read_json(job/f'native/pages/page-{n:03}.json')
    rows=[]
    import pdfplumber
    with pdfplumber.open(job/'input.pdf') as pdf:
        for qid in ids:
            for role in ['solution',*(['question'] if qid in chosen.get('additional_stem_ids',[]) else [])]:
                try:r=region(lookup[qid],pages,role)
                except ValueError as e:
                    rows.append({'question_id':qid,'role':role,'status':'REGION_NOT_LOCATED','reason':str(e)});continue
                r['region_id']=content_hash(r)[:24];r['crop']='assets/quality-'+r['region_id']+'.png'
                path=output/r['crop'];path.parent.mkdir(exist_ok=True)
                pdf.pages[r['page_number']-1].crop(tuple(r['bbox'])).to_image(resolution=240).save(path)
                r['crop_sha256']=file_hash(path)
                r['native_events'],r['source_event_issues']=native_events(pages[r['page_number']],r['bbox'],set(r['source_block_ids']))
                r['status']='REGION_LOCATED_NOT_VERIFIED';rows.append(r)
    manifest={'version':VERSION,'source_pdf_sha256':payload['source']['sha256'],
        'source_html':report['single_file_html'],'source_html_sha256':file_hash(Path(report['single_file_html'])),
        'selection':chosen,'regions':rows}
    write_json(output/'regions.json',manifest)
    return manifest


def run(job, prepared, runtime, *, reader=None, retry_failed=False):
    job,prepared,runtime=Path(job).resolve(),Path(prepared).resolve(),Path(runtime).resolve()
    manifest=read_json(prepared/'regions.json')
    if file_hash(job/'input.pdf')!=manifest['source_pdf_sha256'] or file_hash(Path(manifest['source_html']))!=manifest['source_html_sha256']:
        raise ValueError('QUALITY_SOURCE_CHANGED')
    configure_storage(runtime)
    from ..readiness.visual import FormulaReader
    reader=reader or FormulaReader(runtime)
    code={p.name:file_hash(p) for p in Path(__file__).parent.glob('*.py')}
    rows=[];calls=hits=0;started=time.perf_counter()
    with local_lock(prepared):
        for i,r in enumerate(manifest['regions'],1):
            if 'crop' not in r:rows.append(r);continue
            crop=prepared/r['crop']
            if file_hash(crop)!=r['crop_sha256']:raise ValueError('QUALITY_CROP_CHANGED')
            identity={'code':code,'pdf':manifest['source_pdf_sha256'],'crop':r['crop_sha256'],'reader':reader.identity}
            checkpoint=prepared/'ocr-cache'/content_hash(identity)/'response.json'
            raw=read_json(checkpoint) if checkpoint.exists() else None
            if raw is not None and (not raw.get('error') or not retry_failed):hits+=1
            else:
                try:raw={'identity':identity,'response':reader(crop)}
                except Exception as e:raw={'identity':identity,'error':type(e).__name__}
                calls+=1;write_json(checkpoint,raw)
            response=raw.get('response',{});body=response.get('res',response);latex=body.get('rec_formula','')
            status='LOCAL_OCR_FAILED' if raw.get('error') else event_guard(latex,r['native_events'],r['source_event_issues'])
            value=None
            if not raw.get('error'):
                try:value=endpoint(latex)
                except (ValueError,TypeError,NotImplementedError):pass
            rows.append({**r,'latex_candidate':latex,'event_symbol_status':status,'answer_candidate':value,
                'reader':reader.identity,'checkpoint':str(checkpoint),'academic_review':'PENDING','production_grade':False})
            print(f'[paired-quality] {i}/{len(manifest["regions"])} {status}',flush=True)
        generation=content_hash({'source':manifest['source_html_sha256'],'rows':rows,'code':code})[:16]
        output=job/'paired-quality/versions'/generation;output.mkdir(parents=True,exist_ok=True)
        payload=from_html(manifest['source_html']);lookup={q['question_id']:q for q in payload['questions']}
        for r in rows:
            q=lookup[r['question_id']]
            q.setdefault('formula_candidates',[]).append(r)
            if r.get('crop'):
                import base64
                image=(prepared/r['crop']).read_bytes()
                payload['images'][r['crop']]={'sha256':r['crop_sha256'],'data_url':'data:image/png;base64,'+base64.b64encode(image).decode()}
            if r.get('answer_candidate') and r['role']=='solution':
                q.setdefault('answer_candidates',[]).append({**r['answer_candidate'],'page_number':r['page_number'],
                    'bbox':r['bbox'],'asset_path':r['crop'],'event_symbol_status':r['event_symbol_status']})
        html=output/'questions-and-solutions.html';render(html,payload);exports=export(html,output)
        write_json(output/'formula-readings.json',rows)
        summary={'schema_version':VERSION,'sample_questions':len(manifest['selection']['question_ids']),
            'regions':len(rows),'status_counts':dict(Counter(r.get('event_symbol_status',r['status']) for r in rows)),
            'numeric_endpoint_candidates':sum(r.get('answer_candidate') is not None and r['role']=='solution' for r in rows),
            'inference_calls':calls,'cache_hits':hits,'seconds':round(time.perf_counter()-started,3),
            'cloud_api_calls':0,'grading_ready_count':0,'output_directory':str(output),'review_html':str(html),
            'source_pdf_sha256':manifest['source_pdf_sha256'],'source_html_sha256':manifest['source_html_sha256'],**exports}
        write_json(output/'report.json',summary);write_json(job/'paired-quality.json',summary)
        stable=job/'paired-quality/review.html';stable.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=versions/'+generation+'/questions-and-solutions.html">',encoding='utf-8')
        return summary
