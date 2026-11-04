"""Read-only structural PDF/crop checks, separate from mathematical validation."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):result.update(chunk)
    return result.hexdigest()


def check(metadata,report_path):
    metadata=Path(metadata).resolve();data=json.loads(metadata.read_text(encoding='utf-8'))
    collection=data['collection_pdf'];pdf=metadata.parent/collection['file'];errors=[]
    if digest(pdf)!=collection['sha256']:errors.append('PDF_HASH_MISMATCH')
    reader=PdfReader(pdf);questions=data['questions'];placements=defaultdict(list);counts=Counter()
    if len(reader.pages)!=collection['pages']:errors.append('PAGE_COUNT_MISMATCH')
    if len({q['question_id'] for q in questions})!=len(questions):errors.append('DUPLICATE_IDS')
    for q in questions:
        if q['publishable'] is not False or q['grading_support']!='NOT_ASSESSED':errors.append('QUESTION_PROMOTED')
        if not q['question']['text_lossy'].strip() or not q['solution']['text_lossy'].strip():errors.append('MISSING_CONTENT')
        actual=sorted({p['collection_page_number'] for p in q['collection_placements']})
        if actual!=q['collection_pdf_pages']:errors.append('QUESTION_PAGE_MAPPING_MISMATCH')
        if len(q['collection_placements'])!=len(q['collection_source_spans']):errors.append('CROP_PLACEMENT_COUNT_MISMATCH')
        for span,place in zip(q['collection_source_spans'],q['collection_placements']):
            if (span['page_number'],span['bbox'],span['asset_path'])!=(place['source_page_number'],place['source_bbox'],place['source_asset']):
                errors.append('SOURCE_PLACEMENT_MISMATCH')
            if not 1<=span['page_number']<=q['source']['page_count']:errors.append('SOURCE_PAGE_OUT_OF_RANGE')
            n=place['collection_page_number'];p=reader.pages[n-1];x0,y0,x1,y1=place['collection_bbox']
            if not (0<=x0<x1<=float(p.mediabox.width) and 42<=y0<y1<=float(p.mediabox.height)-40):
                errors.append('PLACEMENT_OUT_OF_BOUNDS')
            placements[n].append((q['question_id'],place['collection_bbox']));counts[q['chapter_id']]+=1
    for n,rows in placements.items():
        rows.sort(key=lambda r:r[1][1])
        for i,(qid,a) in enumerate(rows):
            for oid,b in rows[i+1:]:
                if b[1]>=a[3]:break
                if min(a[2],b[2])-max(a[0],b[0])>.5 and min(a[3],b[3])-max(a[1],b[1])>.5:
                    errors.append(f'PDF_IMAGES_OVERLAP:{n}:{qid}:{oid}')
    for key,info in data['images'].items():
        path=(metadata.parent/key).resolve()
        if not path.is_relative_to(metadata.parent) or not path.is_file() or digest(path)!=info['sha256']:
            errors.append('SOURCE_IMAGE_HASH_MISMATCH:'+key)
    expected=set(range(1+collection.get('contents_page_count',0),len(reader.pages)+1))
    if set(placements)!=expected:errors.append('BLANK_OR_TITLE_ONLY_CONTENT_PAGE')
    outline=reader.outline
    def bookmarks(rows):
        return sum(bookmarks(r) if isinstance(r,list) else 1 for r in rows)
    if bookmarks(outline)!=len(questions)+sum(c['questions']>0 for c in data.get('chapters',[])):
        errors.append('BOOKMARK_COUNT_MISMATCH')
    report={'status':'PASS' if not errors else 'FAILED','questions':len(questions),'pdf_pages':len(reader.pages),
        'source_images':len(data['images']),'placements':sum(len(v) for v in placements.values()),
        'bookmarks':bookmarks(outline),'errors':errors,'pdf_sha256':digest(pdf),
        'mathematical_correctness_assessed':False,'production_grade':False}
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if errors:raise ValueError('COLLECTION_CHECK_FAILED: '+str(errors[:8]))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    print(json.dumps(check(a.metadata,a.report),ensure_ascii=False,indent=2))
