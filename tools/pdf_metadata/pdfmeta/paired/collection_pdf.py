"""Standalone renderer; usable with the bundled ReportLab/Pillow runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

import PIL
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab import rl_config


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(metadata, output, font_dir):
    # PDF is a binary format; ASCII85 adds 25% to every JPEG with no benefit.
    rl_config.useA85=False
    metadata, output = Path(metadata).resolve(), Path(output).resolve()
    data = json.loads(metadata.read_text(encoding='utf-8'))
    questions = data['questions']
    if not questions or data.get('unpaired_questions') or any(q['pair_status']!='PAIRED_LAYOUT_CANDIDATE' for q in questions):
        raise ValueError('COLLECTION_MUST_CONTAIN_SOLVED_OCCURRENCES_ONLY')
    pdfmetrics.registerFont(TTFont('Collection', str(Path(font_dir)/'arial.ttf')))
    pdfmetrics.registerFont(TTFont('CollectionBold', str(Path(font_dir)/'arialbd.ttf')))
    width, height = A4
    margin=42; bottom=44; content_width=width-2*margin
    output.parent.mkdir(parents=True,exist_ok=True)
    c = Canvas(str(output), pagesize=A4, pageCompression=1, invariant=1)
    c.setTitle(data.get('title','Xác suất có điều kiện - Câu hỏi kèm lời giải'))
    c.setAuthor('Coach Learning - Tổng hợp từ tài liệu nguồn')
    number=1; y=height-70; placements=[]; question_pages={}
    chapter_rows=data.get('chapters',[]);header_title='XÁC SUẤT CÓ ĐIỀU KIỆN';chapter_ranges={};current_chapter=None

    def chrome():
        c.setFillColorRGB(.12,.31,.29);c.setFont('CollectionBold',10)
        c.drawString(margin,height-31,header_title)
        c.setFillColorRGB(.42,.48,.49);c.setFont('Collection',8)
        c.drawRightString(width-margin,height-31,'Câu hỏi kèm lời giải')
        c.setStrokeColorRGB(.83,.89,.86);c.line(margin,height-41,width-margin,height-41)
        c.setFont('Collection',8);c.drawString(margin,24,'Giữ nội dung nguồn - Chưa xác minh học thuật')
        c.drawRightString(width-margin,24,str(number))

    def new_page():
        nonlocal number,y
        c.showPage();number+=1;y=height-65;chrome()

    def need(space):
        if y-space<bottom:new_page()

    cached_images={};encoding_cache=metadata.parent/'.pdf-images';encoding_cache.mkdir(exist_ok=True)
    cache_manifest=encoding_cache/'manifest.json'
    encoded=json.loads(cache_manifest.read_text(encoding='utf-8')) if cache_manifest.exists() else {}
    def source_image(span):
        key=span.get('asset_path')
        if not key:raise ValueError('SOLVED_COLLECTION_SOURCE_CROP_MISSING')
        if key not in cached_images:
            path=(metadata.parent/key).resolve()
            if not path.is_relative_to(metadata.parent) or digest(path)!=data['images'][key]['sha256']:
                raise ValueError('COLLECTION_SOURCE_IMAGE_CHANGED')
            with Image.open(path) as im:iw,ih=im.size
            scale=min(content_width/iw,(height-165)/ih)
            identity=f"{data['images'][key]['sha256']}-q94-{PIL.__version__}"
            jpeg=encoding_cache/(hashlib.sha256(identity.encode()).hexdigest()+'.jpg')
            if not jpeg.exists() or encoded.get(jpeg.name)!=digest(jpeg):
                with Image.open(path) as im:
                    rgb=Image.new('RGB',im.size,'white')
                    rgb.paste(im,mask=im.getchannel('A') if 'A' in im.getbands() else None)
                    rgb.save(jpeg,'JPEG',quality=94,subsampling=0,optimize=True)
                encoded[jpeg.name]=digest(jpeg)
            cached_images[key]=(jpeg,iw*scale,ih*scale)
        return cached_images[key]

    if chapter_rows:
        c.setFillColorRGB(.10,.36,.29);c.setFont('CollectionBold',25)
        c.drawString(margin,height-92,'TOÁN 12')
        c.setFont('CollectionBold',20);c.drawString(margin,height-126,'Câu hỏi kèm lời giải')
        c.setFont('Collection',11);c.setFillColorRGB(.38,.46,.43)
        c.drawString(margin,height-158,f"{len(questions):,} mục có nguồn | {len(data.get('documents',[]))} tài liệu | {len(chapter_rows)} nhóm kiến thức")
        c.setFont('CollectionBold',12);c.setFillColorRGB(.10,.36,.29);c.drawString(margin,height-220,'MỤC LỤC')
        pos=height-255
        for i,chapter in enumerate(chapter_rows,1):
            c.setFont('CollectionBold',12);c.drawString(margin,pos,f"{i:02}. {chapter['title']}")
            c.setFont('Collection',10);c.setFillColorRGB(.38,.46,.43)
            c.drawString(margin+24,pos-20,f"{chapter['questions']:,} mục | {chapter['documents']} tài liệu nguồn")
            if chapter['questions']:
                c.linkRect('', 'chapter-'+chapter['id'],(margin,pos-24,width-margin,pos+16),relative=0,thickness=0)
            c.setFillColorRGB(.10,.36,.29);pos-=67
        c.setFont('Collection',10);c.setFillColorRGB(.38,.46,.43)
        c.drawString(margin,115,'Bấm vào tên chương hoặc dùng bookmark để chuyển đến nội dung.')
        c.drawString(margin,94,'Chưa xác minh học thuật để chấm tự động. Metadata giữ ảnh PNG nguồn.')
        c.setFont('Collection',8);c.drawString(margin,76,'Ảnh trong PDF được nén JPEG chất lượng 94 để giảm dung lượng.')
        c.setFont('Collection',8);c.drawRightString(width-margin,24,'1')
    else:chrome()
    for order,q in enumerate(questions,1):
        combined=q.get('collection_source_spans')
        first=combined[0] if combined else q['question']['source_spans'][0]
        if chapter_rows and q['chapter_id']!=current_chapter:
            current_chapter=q['chapter_id'];header_title=q['chapter_title'].upper();new_page()
            c.bookmarkPage('chapter-'+current_chapter);c.addOutlineEntry(q['chapter_title'],'chapter-'+current_chapter,0)
            chapter_ranges[current_chapter]={'first_page':number,'last_page':number}
            # A tall first crop already has the chapter in the running header.
            # Do not strand a chapter title on an otherwise empty page.
            if y-32-max(135,source_image(first)[2]+56)>=bottom:
                c.setFillColorRGB(.08,.39,.30);c.setFont('CollectionBold',15)
                c.drawString(margin,y,q['chapter_title']);y-=32
        need(max(135,source_image(first)[2]+56))
        c.bookmarkPage(q['question_id']);c.addOutlineEntry(f"Mục {order:03} (gốc: {q['source_number']})",q['question_id'],1 if chapter_rows else 0)
        c.setFillColorRGB(.08,.39,.30);c.setFont('CollectionBold',12)
        c.drawString(margin,y,f"Câu {order:03}")
        c.setFont('Collection',8);c.setFillColorRGB(.43,.49,.49)
        source_pages=sorted({s['page_number'] for part in ['question','solution','answer'] for s in q[part]['source_spans']})
        source_label=q.get('source_label') or f"Câu {q['source_number']}"
        source_label=re.sub(r'^[\s\uE000-\uF8FF☞☛◆►➤•✓✔]+','',source_label).strip(' .:)')
        page_label=', '.join(map(str,source_pages[:5]))+('…' if len(source_pages)>5 else '')
        document_label=(' | TL '+q['document_id'][:8]) if q.get('document_id') else ''
        c.drawRightString(width-margin,y,f"{source_label}{document_label} | Trang nguồn "+page_label)
        y-=20
        roles=[('question_and_solution','Đề bài và lời giải nguồn')] if combined else [('question','Đề bài'),('solution','Lời giải'),('answer','Đáp án ghi riêng trong nguồn')]
        for role,label in roles:
            sources=combined if combined else q[role]['source_spans']
            if not sources:continue
            need(source_image(sources[0])[2]+35);c.setFont('CollectionBold',9);c.setFillColorRGB(.15,.42,.34)
            c.drawString(margin,y,label);y-=13
            for span in sources:
                key=span['asset_path'];path,draw_w,draw_h=source_image(span)
                need(draw_h+8)
                c.drawImage(ImageReader(str(path)),margin,y-draw_h,width=draw_w,height=draw_h,mask='auto')
                placements.append({'question_id':q['question_id'],'collection_number':order,'role':role,
                    'source_page_number':span['page_number'],'source_bbox':span['bbox'], 'source_asset':key,
                    'collection_page_number':number,'collection_bbox':[margin,height-y,margin+draw_w,height-y+draw_h]})
                question_pages.setdefault(q['question_id'],set()).add(number)
                y-=draw_h+9
        y-=15
        if y>bottom:
            c.setStrokeColorRGB(.89,.93,.90);c.line(margin,y+3,width-margin,y+3)
        if current_chapter:chapter_ranges[current_chapter]['last_page']=number
    c.save()
    cache_manifest.write_text(json.dumps(encoded,sort_keys=True)+'\n',encoding='utf-8')
    for q in questions:
        q['collection_pdf_pages']=sorted(question_pages[q['question_id']])
        q['collection_placements']=[p for p in placements if p['question_id']==q['question_id']]
    data['collection_pdf']={'file':output.name,'sha256':digest(output),'pages':number,
        'rendering':'SOURCE_CROP_JPEG_DERIVATIVES_WITH_CANONICAL_PNG_METADATA','jpeg_quality':94,
        'canonical_source_image_format':'PNG','production_grade':False,
        'chapter_page_ranges':chapter_ranges,'contents_page_count':1 if chapter_rows else 0}
    target=output.parent/'cau-hoi-co-loi-giai.metadata.json'
    target.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    jsonl=output.parent/'cau-hoi-co-loi-giai.metadata.jsonl'
    jsonl.write_text(''.join(json.dumps({'schema_version':'paired-question/v1','source':data['source'],**q},ensure_ascii=False)+'\n' for q in questions),encoding='utf-8')
    report={'questions':len(questions),'pdf_pages':number,'pdf':str(output),'pdf_sha256':digest(output),
        'pdf_bytes':output.stat().st_size,'metadata':str(target),'metadata_jsonl':str(jsonl),'placements':len(placements),
        'original_source_sha256':data['source']['sha256'],'source_kind':data['source'].get('kind','PDF'),
        'chapter_page_ranges':chapter_ranges,'production_grade':False}
    if __package__:
        from .metadata_readable import export as format_metadata
    else:
        from metadata_readable import export as format_metadata
    readable=format_metadata(jsonl)
    report.update(pretty_metadata_json=readable['pretty_json'],metadata_viewer=readable['viewer'])
    (output.parent/'pdf-collection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--font-dir',type=Path,default=Path('C:/Windows/Fonts'))
    a=p.parse_args();print(json.dumps(build(a.metadata,a.output,a.font_dir),ensure_ascii=False,indent=2))
