"""Read source-book entries from their hash-verified original PDFs.

The book is a selector, not an OCR source. Expected text/Markdown is never used
as input; ID-based exports may use a reference JSON's source coordinates.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import unicodedata
import uuid

from ..assemble import assemble
from ..native import mark_margins
from ..storage import file_hash,write_json,write_jsonl
from .boundaries import detach
from .corpus import CHAPTERS,CORPUS_HEADING
from .math_recovery import extract_page
from .selection_cli import all_records
from .transcription_v2.glyphs import canonical_page


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFD',value.casefold().replace('đ','d'))
                   if not unicodedata.combining(c))


REFERENCE=re.compile(r'\bcau\s+(?P<number>\d+)\s+'
    r'(?P<label>(?:vi du|bai|cau|example|exercise)\s+\d+(?:\.\d+)*)\s*'
    r'\|\s*tl\s+(?P<prefix>[0-9a-f]{8,64})\s*\|\s*trang nguon\s+'
    r'(?P<pages>\d+(?:\s*,\s*\d+)*)')


def references(text,page_number):
    return [{'number':int(m['number']),'label':m['label'],'source_hash_prefix':m['prefix'],
             'source_pages':[int(p.strip()) for p in m['pages'].split(',')],
             'book_page':page_number} for m in REFERENCE.finditer(plain(text))]


def id_reference(text,page_number):
    text=plain(text)
    number=re.search(r'\bcau\s+(\d+)\s*/\s*ma bo goc\s+(\d+)',text)
    identity=re.search(r'\bid:\s*([0-9a-f]{16,64}:[^\s]+)',text)
    if not number or not identity:return None
    return {'number':int(number[1]),'original_collection_number':int(number[2]),
            'source_question_id':identity[1],'source_hash_prefix':identity[1].split(':',1)[0],
            'book_page':page_number}


def reference_rows(entries,reference):
    """Use identities/coordinates only, never expected text or Markdown."""
    lookup={q['question_id']:q for q in reference}
    if len(lookup)!=len(reference):raise ValueError('DUPLICATE_REFERENCE_QUESTION_ID')
    rows=[]
    for entry in entries:
        q=lookup.get(entry['source_question_id'])
        if q is None:raise ValueError('BOOK_ID_MISSING_FROM_REFERENCE:'+entry['source_question_id'])
        if q['collection_number']!=entry['original_collection_number']:
            raise ValueError('ORIGINAL_COLLECTION_NUMBER_MISMATCH')
        if not q['source']['sha256'].startswith(entry['source_hash_prefix']):
            raise ValueError('BOOK_ID_SOURCE_HASH_MISMATCH')
        row={'question_id':q['question_id'],'collection_number':entry['number'],
             'source_label':'Source '+q['question_id'].split(':',1)[1],
             'chapter_title':q['chapter_title'],'source':deepcopy(q['source']),
             'source_book_reference':deepcopy(entry)}
        for role in ['question','solution','answer']:
            row[role]={'text_lossy':'','source_spans':deepcopy(q[role]['source_spans'])}
        if not row['question']['source_spans'] or not row['solution']['source_spans']:
            raise ValueError('REFERENCE_PAIR_SOURCE_SPANS_MISSING')
        rows.append(row)
    return rows


def prepare_from_reference(pdf,sources,output,reference_json):
    import pypdfium2 as pdfium
    pdf,output=Path(pdf).resolve(),Path(output).resolve();digest=file_hash(pdf);entries={}
    with pdfium.PdfDocument(pdf) as doc:
        for i in range(len(doc)):
            page=doc[i];tp=page.get_textpage()
            try:entry=id_reference(tp.get_text_range(),i+1)
            finally:tp.close();page.close()
            if entry:
                old=entries.get(entry['number'])
                if old and any(old[k]!=entry[k] for k in ['source_question_id','original_collection_number']):
                    raise ValueError('CONFLICTING_BOOK_ID_REFERENCE')
                entries.setdefault(entry['number'],entry)
    if not entries:raise ValueError('NO_ID_BASED_BOOK_REFERENCES_FOUND')
    entries=[entries[n] for n in sorted(entries)]
    reference=json.loads(Path(reference_json).read_text(encoding='utf-8-sig'))
    rows=reference_rows(entries,reference);originals=find_sources(sources,entries);documents={}
    for row in rows:
        source=originals[row['source_book_reference']['source_hash_prefix']]
        if source['sha256']!=row['source']['sha256']:raise ValueError('ORIGINAL_FULL_HASH_MISMATCH')
        row['chapter_id']=next((c for c in CHAPTERS if c in Path(source['path']).parts),'unclassified')
        documents[source['sha256']]={**source,'page_count':row['source']['page_count']}
    output.mkdir(parents=True,exist_ok=True)
    metadata=output/'questions.source.jsonl';plan=output/'plan.json';selection=output/'selection.json'
    write_jsonl(metadata,rows);write_json(plan,{'documents':list(documents.values())});all_records(metadata,selection)
    write_json(output/'source-replay.json',{'mode':'ORIGINAL_PDFS_WITH_ID_AND_SOURCE_COORDINATE_SELECTION',
        'book_pdf':str(pdf),'book_sha256':digest,'question_count':len(rows),'source_documents':len(documents),
        'reference_json':str(Path(reference_json).resolve()),'reference_sha256':file_hash(Path(reference_json)),
        'reference_fields_used':['question_id','collection_number','chapter_title','source','source_spans'],
        'expected_text_or_markdown_used':False,'source_book_images_ocr':False,'entries':entries})
    return metadata,plan,selection


def read_book(pdf):
    import pypdfium2 as pdfium
    result={}
    with pdfium.PdfDocument(pdf) as doc:
        for i in range(len(doc)):
            page=doc[i];tp=page.get_textpage()
            try:found=references(tp.get_text_range(),i+1)
            finally:tp.close();page.close()
            for entry in found:
                number=entry['number']
                if number in result and any(result[number][k]!=entry[k] for k in
                        ['label','source_hash_prefix','source_pages']):
                    raise ValueError('CONFLICTING_SOURCE_BOOK_REFERENCE:'+str(number))
                result.setdefault(number,entry)
    if not result:raise ValueError('NO_SOURCE_BOOK_PROVENANCE_FOUND')
    return [result[n] for n in sorted(result)]


def find_sources(folder,entries):
    prefixes={e['source_hash_prefix'] for e in entries};found={}
    for path in sorted(Path(folder).rglob('*.pdf')):
        digest=file_hash(path)
        for prefix in prefixes:
            if digest.startswith(prefix):
                if prefix in found and found[prefix]['sha256']!=digest:
                    raise ValueError('AMBIGUOUS_SOURCE_HASH_PREFIX:'+prefix)
                found.setdefault(prefix,{'path':str(path.resolve()),'sha256':digest})
    missing=prefixes-found.keys()
    if missing:raise ValueError('ORIGINAL_SOURCE_PDFS_MISSING:'+','.join(sorted(missing)))
    return found


def label_key(value):
    match=re.search(r'(vi du|bai|cau|example|exercise)\s+(\d+(?:\.\d+)*)',plain(value))
    return match.group(0) if match else None


def select_item(items,entry):
    found=[q for q in items if label_key(q['source_label'])==label_key(entry['label'])
           and q['stem']['source_spans']
           and q['stem']['source_spans'][0]['page_number']==entry['source_pages'][0]]
    if len(found)!=1:raise ValueError('SOURCE_ENTRY_NOT_UNIQUE:'+str(entry['number']))
    item=found[0]
    if not item['stem']['text_raw'].strip() or not item['solution']['text_raw'].strip():
        raise ValueError('ORIGINAL_SOURCE_PAIR_INCOMPLETE:'+str(entry['number']))
    used={s['page_number'] for role in ['stem','solution','answer'] for s in item[role]['source_spans']}
    if not used<=set(entry['source_pages']):
        raise ValueError('SOURCE_PAIR_EXCEEDS_BOOK_PAGE_REFERENCE:'+str(entry['number']))
    return item


def prepare(pdf,sources,output):
    import pdfplumber
    pdf,output=Path(pdf).resolve(),Path(output).resolve()
    digest=file_hash(pdf);entries=read_book(pdf);originals=find_sources(sources,entries)
    output.mkdir(parents=True,exist_ok=True);rows=[];documents=[];bindings=[]
    for prefix,source in originals.items():
        own=[e for e in entries if e['source_hash_prefix']==prefix]
        path=Path(source['path']);pages=[]
        with pdfplumber.open(path) as doc:
            count=len(doc.pages)
            requested=sorted({pn for entry in own for pn in entry['source_pages']})
            if any(pn<1 or pn>count for pn in requested):raise ValueError('INVALID_ORIGINAL_PAGE_REFERENCE')
            for pn in requested:
                raw=doc.pages[pn-1]
                page=canonical_page(extract_page(raw,pn,source['sha256']))
                for block in page['blocks']:block.setdefault('review_flags',[])
                pages.append(page);raw.close()
        mark_margins(pages);items,orphans=assemble(pages,source['sha256'])
        items,_,_=detach(items,pages,orphans,heading_pattern=CORPUS_HEADING,title_size=20)
        chapter=next((c for c in CHAPTERS if c in path.parts),'unclassified')
        documents.append({**source,'page_count':count})
        for entry in own:
            item=select_item(items,entry)
            row={'question_id':f"{source['sha256'][:16]}:book{digest[:8]}:q{entry['number']}",
                 'collection_number':entry['number'],'source_number':item['source_number'],
                 'source_label':item['source_label'],'chapter_id':chapter,
                 'chapter_title':CHAPTERS.get(chapter,'Chưa phân loại'),
                 'source':{'name':path.name,'catalog_label':str(path),'sha256':source['sha256'],
                           'page_count':count,'coordinate_unit':'pdf_point','coordinate_origin':'top-left'},
                 'source_book_reference':deepcopy(entry)}
            for role,part in [('question','stem'),('solution','solution'),('answer','answer')]:
                row[role]={'text_lossy':item[part]['text_raw'],'source_spans':deepcopy(item[part]['source_spans'])}
            rows.append(row);bindings.append({**entry,'original_pdf':str(path),'original_sha256':source['sha256'],
                                             'question_id':row['question_id']})
        if file_hash(path)!=source['sha256']:raise ValueError('ORIGINAL_SOURCE_CHANGED')
    if file_hash(pdf)!=digest:raise ValueError('SOURCE_BOOK_CHANGED')
    rows.sort(key=lambda q:q['collection_number'])
    metadata=output/'questions.source.jsonl';plan=output/'plan.json';selection=output/'selection.json'
    write_jsonl(metadata,rows);write_json(plan,{'documents':documents});all_records(metadata,selection)
    write_json(output/'source-replay.json',{'mode':'READ_ORIGINAL_PDFS_SELECTED_BY_BOOK_PROVENANCE',
        'book_pdf':str(pdf),'book_sha256':digest,'question_count':len(rows),'entries':bindings,
        'source_book_images_ocr':False,'reference_json_or_markdown_used':False})
    return metadata,plan,selection


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['pdf','sources','storage','repo']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--reference',type=Path,help='ID/source-coordinate reference for the 200-item exported book')
    p.add_argument('--plan-only',action='store_true')
    p.add_argument('--output',type=Path);p.add_argument('--profile',choices=['native','ocr'],default='ocr')
    p.add_argument('--workers',type=int,choices=[1,2],default=1);p.add_argument('--timeout',type=int,default=7200)
    p.add_argument('--memory-limit-mb',type=int,default=4096);a=p.parse_args()
    output=a.output or a.storage/'pdf-jobs'/file_hash(a.pdf)[:24]/('source-replay-'+uuid.uuid4().hex[:8])
    metadata,plan,selection=(prepare_from_reference(a.pdf,a.sources,output,a.reference)
        if a.reference else prepare(a.pdf,a.sources,output))
    print(f'Original-source input: {metadata}',flush=True)
    from .transcription_v2.batch import parser,run
    args=['--input',str(metadata),'--plan',str(plan),'--selection',str(selection),
          '--output',str(output/'transcription'),'--runtime',str(a.storage/'pdf-pipeline-runtime'),
          '--katex',str(a.repo/'frontend/node_modules/katex/dist'),'--workers',str(a.workers),
          '--run-timeout',str(a.timeout),'--memory-limit-mb',str(a.memory_limit_mb),'--cache-mode','cold']
    if a.profile=='native':args.append('--native-only')
    if a.plan_only:args.append('--plan-only')
    result=run(parser().parse_args(args))
    print(json.dumps({'status':result['status'],'output':str(output),
                     'content':str(output/'transcription/content.draft.pretty.json')},ensure_ascii=False,indent=2))
    return 0 if result['status'] in {'COMPLETE_DRAFT','PLANNED'} else 1


if __name__=='__main__':raise SystemExit(main())
