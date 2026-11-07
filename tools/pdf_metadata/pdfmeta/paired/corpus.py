"""All-document source-image collection with provenance, OCR queues and chapter labels."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import gc
import json
import re
from pathlib import Path
import time

from PIL import Image

from ..assemble import assemble
from ..native import mark_margins
from ..storage import configure_storage,file_hash,read_json,write_json,write_jsonl
from ..gemini_client import content_hash
from ..validate import validate_candidates
from .boundaries import detach
from .corpus_layout import restore,split_columns,source_book_labels


CHAPTERS={'derivative_applications':'Ứng dụng đạo hàm và đồ thị hàm số',
    'integrals':'Nguyên hàm, tích phân và ứng dụng','grouped_statistics':'Thống kê số liệu ghép nhóm',
    'probability':'Xác suất có điều kiện'}

# Textbooks use decorated section labels between worked examples. Keep this
# broader source-collection rule separate from the established pilot adapter.
CORPUS_HEADING=re.compile(r'^[\s\uE000-\uF8FF☞☛◆►➤•✓✔]*'
    r'(?:DẠNG\s+\d+\s*[.:]|PHẦN\s+[IVX\d]+\s*[:.]|BÀI\s*:\s*\S|CHỦ ĐỀ\s+\d+\s*[:.]'
    r'|[A-C]\s*[.:]\s*(?:LÝ THUYẾT|KIẾN THỨC|CÁC DẠNG BÀI TẬP|BÀI TẬP|VÍ DỤ MINH HỌA))',re.I)


def blank_solution_workspace(text):
    lines=[s.strip() for s in text.splitlines() if s.strip()]
    if not lines:return False  # Report the existing SOLUTION_NOT_FOUND reason.
    # A printed solution label followed by writing lines is a student template.
    # Later lesson text must not turn that blank workspace into a solved item.
    return (not any(c.isalnum() for c in text) or
        bool(re.fullmatch(r'[\s.…_·]{6,}',lines[0])))


def code_identity():
    folder=Path(__file__).parent
    files=[folder/'corpus.py',folder/'corpus_layout.py',folder/'fast_native.py',folder/'boundaries.py',
        *[folder.parent/n for n in ['assemble.py','validate.py','native.py','auto_ocr.py','section_markers.py']],
        folder.parent.parent/'schemas/question-candidate.v1.schema.json']
    return content_hash({str(p.name):file_hash(p) for p in files})


def document(source,work,runtime,*,use_ocr=True):
    started=time.perf_counter();adapter_identity=code_identity();work,runtime=Path(work).resolve(),Path(runtime).resolve()
    record=read_json(source) if isinstance(source,(str,Path)) else source
    if file_hash(Path(record['path']))!=record['sha256']:raise ValueError('CORPUS_SOURCE_HASH_MISMATCH')
    native=work/'native';pages=[read_json(p) for p in sorted((native/'pages').glob('*.json'))]
    if len(pages)!=record['pages']:raise ValueError('NATIVE_PAGE_COUNT_MISMATCH')
    if any(p['source_sha256']!=record['sha256'] for p in pages):raise ValueError('NATIVE_SOURCE_PAGE_MISMATCH')
    mark_margins(pages)
    configure_storage(runtime);ocr=None;ocr_errors=[];ocr_pages=[]
    from ..auto_ocr import LocalOCR,needs_text_ocr
    for i,p in enumerate(pages):
        if not needs_text_ocr(p):continue
        if not use_ocr:
            p['ocr_failed']=True;ocr_errors.append({'page_number':p['page_number'],'reason':'OCR_DEFERRED'});continue
        if ocr is None:ocr=LocalOCR(runtime,work/'ocr',lambda *args:print('[ocr-model] '+str(args),flush=True))
        try:
            pages[i]=ocr.text_page(p,native/p['image_path']);ocr_pages.append(p['page_number'])
            print(f'[ocr-page] {record["document_id"]} {p["page_number"]}/{len(pages)}',flush=True)
        except Exception as e:
            p['ocr_failed']=True;ocr_errors.append({'page_number':p['page_number'],'reason':type(e).__name__})
    mark_margins(pages)
    for p in pages:p['image_path']=str((native/p['image_path']).resolve())
    pages=[source_book_labels(p) for p in pages]
    virtual,mapping,layout_issues=split_columns(pages)
    items,orphans=assemble(virtual,record['sha256'])
    items,orphans,boundaries=detach(items,virtual,orphans,heading_pattern=CORPUS_HEADING,title_size=20)
    output=work/'solved';assets=output/'assets';assets.mkdir(parents=True,exist_ok=True)
    write_json(output/'boundary-audit.json',{'coordinate_system':'VIRTUAL_COLUMNS_WITH_EXPLICIT_SOURCE_MAPPING',
        'mapping':mapping,'decisions':boundaries});write_json(output/'layout-review.json',layout_issues)
    physical_orphans=[]
    for o in orphans:
        m=mapping[o['page_number']];r={**o,'page_number':m['page_number'],'column':m['column']}
        if 'bbox' in r:r['bbox']=[r['bbox'][0]+m['x_offset'],r['bbox'][1],r['bbox'][2]+m['x_offset'],r['bbox'][3]]
        physical_orphans.append(r)
    write_jsonl(output/'unassigned-blocks.jsonl',physical_orphans)
    lookup={p['page_number']:p for p in pages};accepted=[];rejected=[]
    for item in items:
        reasons=[]
        if not item['stem']['text_raw'].strip():reasons.append('QUESTION_TEXT_MISSING')
        if not item['solution']['text_raw'].strip():reasons.append('SOLUTION_NOT_FOUND')
        elif blank_solution_workspace(item['solution']['text_raw']):reasons.append('BLANK_SOLUTION_WORKSPACE')
        used={s['page_number'] for role in ['stem','solution','answer'] for s in item[role]['source_spans']}
        if any(mapping[v]['crossing_block_ids'] for v in used):reasons.append('COLUMN_LAYOUT_REQUIRES_REVIEW')
        if any(mapping[v]['ocr_failed'] for v in used):reasons.append('OCR_UNAVAILABLE_FOR_SOURCE_REGION')
        raw={k:v for k,v in item.items() if k!='boundary_resolution'}
        errors=validate_candidates([raw],virtual)['structural_errors']
        if errors:reasons.append('SOURCE_STRUCTURE_REQUIRES_REVIEW')
        if reasons:
            rejected.append({'question_id':item['question_id'],'source_number':item['source_number'],
                'source_label':item.get('source_label'),'source_pdf_sha256':record['sha256'],'reasons':reasons,
                'source_regions':[restore(s,mapping) for s in item['source_regions']], 'structure_errors':errors})
            continue
        parts={name:{'text_lossy':item[raw_name]['text_raw'].strip(),
            'source_spans':[restore(s,mapping) for s in item[raw_name]['source_spans']]}
            for name,raw_name in [('question','stem'),('solution','solution')]}
        q={'question_id':item['question_id'],'source_number':item['source_number'],'source_label':item.get('source_label'),
            'chapter_id':record['chapter'],'chapter_title':CHAPTERS.get(record['chapter'],'Chưa phân loại'),
            'document_id':record['document_id'],'source':{'name':Path(record['label']).name,
                'catalog_label':record['label'],'sha256':record['sha256'],'page_count':record['pages'],
                'coordinate_unit':'pdf_point','coordinate_origin':'top-left'}, **parts,
            'answer':{'text_raw':item['answer']['text_raw'],'source_spans':[restore(s,mapping) for s in item['answer']['source_spans']],
                'status':'EXPLICIT_SOURCE_LABEL_UNVERIFIED' if item['answer']['text_raw'] else 'NOT_EXPLICITLY_LABELLED'},
            'pair_status':'PAIRED_LAYOUT_CANDIDATE','quality_flags':sorted(set(item['review_flags']+['SOURCE_MATH_NOT_VERIFIED'])),
            'academic_review':'PENDING','grading_support':'NOT_ASSESSED','publishable':False,
            'collection_source_spans':[],'boundary_resolution':item.get('boundary_resolution')}
        if q['boundary_resolution']:
            b=q['boundary_resolution'];m=mapping[b['page_number']]
            q['boundary_resolution']={**b,'page_number':m['page_number'],'column':m['column']}
        # Keep virtual-column order. Two source columns must never be unioned
        # into one rectangle containing other questions.
        grouped={}
        for role in ['stem','solution','answer']:
            for s in item[role]['source_spans']:grouped.setdefault(s['page_number'],[]).append(s)
        for sequence,(v,spans) in enumerate(sorted(grouped.items()),1):
            box=[min(s['bbox'][0] for s in spans),min(s['bbox'][1] for s in spans),
                max(s['bbox'][2] for s in spans),max(s['bbox'][3] for s in spans)]
            src=restore({'page_number':v,'bbox':box,'block_ids':sorted({b for s in spans for b in s['block_ids']})},mapping)
            page=lookup[src['page_number']];key=f'assets/{len(accepted)+1:05}-{sequence:02}.png';target=output/key
            with Image.open(page['image_path']) as image:
                sx,sy=image.width/page['width'],image.height/page['height'];x0,y0,x1,y1=src['bbox']
                bounds=(max(0,int(x0*sx)),max(0,int(y0*sy)),min(image.width,round(x1*sx)),min(image.height,round(y1*sy)))
                if bounds[2]<=bounds[0] or bounds[3]<=bounds[1]:raise ValueError('CORPUS_CROP_INVALID')
                image.crop(bounds).save(target)
            q['collection_source_spans'].append({**src,'asset_path':key,'asset_sha256':file_hash(target)})
        accepted.append(q)
    write_jsonl(output/'questions.jsonl',accepted);write_jsonl(output/'review-queue.jsonl',rejected)
    covered={s['page_number'] for q in accepted for s in q['collection_source_spans']}
    page_queue=[{'page_number':p['page_number'],'reason':'NO_ACCEPTED_SOLVED_REGION_ON_PAGE',
        'native_block_count':len(p['blocks']),'ocr_attempted':p['page_number'] in ocr_pages} for p in pages if p['page_number'] not in covered]
    write_json(output/'page-review-queue.json',page_queue)
    summary={'document_id':record['document_id'],'label':record['label'],'source_pdf_sha256':record['sha256'],
        'chapter_id':record['chapter'],'pages':len(pages),'question_occurrences':len(items),'selected_pairs':len(accepted),
        'unselected_occurrences':len(rejected),'review_reasons':dict(Counter(r for q in rejected for r in q['reasons'])),
        'ocr_pages':ocr_pages,'ocr_errors':ocr_errors,'ocr_calls':ocr.calls if ocr else 0,'ocr_cache_hits':ocr.cache_hits if ocr else 0,
        'layout_issue_regions':len(layout_issues),'detached_boundaries':len(boundaries),'page_review_count':len(page_queue),
        'status':'DRAFT_WITH_REVIEW_QUEUE' if rejected or page_queue or ocr_errors else 'PAIRED_SOURCE_DRAFT',
        'questions_jsonl':str(output/'questions.jsonl'),'review_jsonl':str(output/'review-queue.jsonl'),
        'questions_sha256':file_hash(output/'questions.jsonl'),'review_sha256':file_hash(output/'review-queue.jsonl'),
        'source_code_hash':adapter_identity,
        'seconds':round(time.perf_counter()-started,3),'production_grade':False,'cloud_api_calls':0}
    if file_hash(Path(record['path']))!=record['sha256']:raise ValueError('SOURCE_CHANGED_DURING_CORPUS_COLLECTION')
    write_json(output/'report.json',summary)
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--skip-ocr',action='store_true');a=p.parse_args()
    import psutil
    process=psutil.Process()
    if hasattr(psutil,'BELOW_NORMAL_PRIORITY_CLASS'):process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    print(json.dumps(document(a.source,a.work,a.runtime,use_ocr=not a.skip_ocr),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
