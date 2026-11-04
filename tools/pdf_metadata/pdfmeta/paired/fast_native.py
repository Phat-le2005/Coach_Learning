"""Page-streamed PDFium text geometry for source-image corpus collection.

This is a separate adapter, not a replacement for frozen math transcription.
"""
from __future__ import annotations

import importlib.metadata
from pathlib import Path
import time

import pypdfium2 as pdfium
from pypdfium2 import raw

from ..native import mark_margins
from ..storage import file_hash,read_json,write_json


VERSION='pdfium-source-lines/v2'


def extract_page(page, index, digest, dpi):
    width,height=page.get_size();tp=page.get_textpage();blocks=[];gs=[];text=[]
    def flush():
        nonlocal gs,text
        value=''.join(text).strip()
        if value and gs:
            bounds=[min(g['bbox'][0] for g in gs),min(g['bbox'][1] for g in gs),max(g['bbox'][2] for g in gs),max(g['bbox'][3] for g in gs)]
            blocks.append({'block_id':f'p{index:04}-l{len(blocks):04}','block_type':'native_line','bbox':bounds,
                'reading_order':len(blocks),'text_raw':value,'glyphs':gs,'is_margin':False,
                'review_flags':['PDFIUM_NATIVE_TEXT_NOT_MATH_TRANSCRIPTION']+
                    (['PDFIUM_INVALID_UNICODE_REPLACED'] if any(g.get('unicode_replaced') for g in gs) else [])})
        gs=[];text=[]
    try:
        for i in range(tp.count_chars()):
            code=raw.FPDFText_GetUnicode(tp.raw,i)
            if code in {10,13}:flush();continue
            if not code or code<32:continue
            replaced=0xD800<=code<=0xDFFF or code>0x10FFFF
            char='\ufffd' if replaced else chr(code);text.append(char)
            if char.isspace():continue
            try:left,bottom,right,top=tp.get_charbox(i)
            except pdfium.PdfiumError:continue
            x0,x1=max(0,min(left,right)),min(width,max(left,right))
            y0,y1=max(0,height-max(top,bottom)),min(height,height-min(top,bottom))
            if x1<=x0 or y1<=y0:continue
            gs.append({'text':char,'bbox':[round(x0,3),round(y0,3),round(x1,3),round(y1,3)],
                'font':'PDFium-font-unmapped','size':round(float(raw.FPDFText_GetFontSize(tp.raw,i)),3),'color':None})
            if replaced:gs[-1]['unicode_replaced']=True;gs[-1]['source_unicode_code']=hex(code)
        flush()
    finally:tp.close()
    blocks.sort(key=lambda b:(round(b['bbox'][1]/2),b['bbox'][0]))
    for i,b in enumerate(blocks):b['reading_order']=i
    images=[]
    for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE]):
        left,bottom,right,top=obj.get_bounds()
        box=[max(0,left),max(0,height-top),min(width,right),min(height,height-bottom)]
        if box[2]>box[0] and box[3]>box[1]:images.append({'bbox':box})
    return {'schema_version':'page-document/v1','source_sha256':digest,'parser_id':VERSION,'parser_version':VERSION,
        'library_version':importlib.metadata.version('pypdfium2'),'page_number':index,'width':width,'height':height,
        'rotation':page.get_rotation(),'coordinate_origin':'top-left','coordinate_unit':'pdf_point','blocks':blocks,
        'vectors':[],'images':images,
        'image_path':f'pages/page-{index:04}.png','image_dpi':dpi,
        'extraction_status':'NATIVE_TEXT_CANDIDATE' if blocks else 'OCR_REQUIRED'}


def extract(pdf,output,*,dpi=110,event=lambda *args:None):
    pdf,output=Path(pdf),Path(output);output.mkdir(parents=True,exist_ok=True);(output/'pages').mkdir(exist_ok=True)
    digest=file_hash(pdf);version=importlib.metadata.version('pypdfium2');records=[];hits=0;started=time.perf_counter()
    if (output/'manifest.json').exists() and read_json(output/'manifest.json')['source_sha256']!=digest:
        raise ValueError('FAST_NATIVE_OUTPUT_BELONGS_TO_ANOTHER_PDF')
    doc=pdfium.PdfDocument(pdf)
    try:
        for i in range(len(doc)):
            index=i+1;path=output/f'pages/page-{index:04}.json';image=output/f'pages/page-{index:04}.png'
            record=read_json(path) if path.exists() else None
            reuse=record and (record.get('source_sha256'),record.get('parser_version'),record.get('library_version'),record.get('image_dpi'))==(digest,VERSION,version,dpi)
            if reuse and image.exists() and record.get('image_sha256')==file_hash(image):
                hits+=1
            else:
                page=doc[i]
                try:
                    record=extract_page(page,index,digest,dpi)
                    bitmap=page.render(scale=dpi/72)
                    try:bitmap.to_pil().save(image)
                    finally:bitmap.close()
                    record['image_sha256']=file_hash(image);write_json(path,record)
                finally:page.close()
            records.append(record)
            if index%25==0 or index==len(doc):event('native',{'done':index,'total':len(doc),'cache_hits':hits})
    finally:doc.close()
    mark_margins(records)
    summary={'adapter':VERSION,'source_sha256':digest,'pages':len(records),'cache_hits':hits,
        'low_text_pages':[p['page_number'] for p in records if sum(len(b['text_raw']) for b in p['blocks'] if not b.get('is_margin'))<60],
        'seconds':round(time.perf_counter()-started,3)}
    write_json(output/'manifest.json',summary)
    return summary,records
