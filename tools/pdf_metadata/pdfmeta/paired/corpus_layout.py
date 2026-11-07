"""Explicit virtual columns; all exported boxes are restored to original PDF coordinates."""
from copy import deepcopy
import re
import unicodedata

from ..assemble import QUESTION


def source_book_labels(page):
    """Keep a source-book entry's outer number and its printed inner label.

    Only activate after an outer caption with document hash/page provenance;
    ordinary adjacent questions must continue to create separate entries.
    """
    result=deepcopy(page);blocks=result['blocks'];active=False
    def plain(text):
        return ''.join(c for c in unicodedata.normalize('NFD',text.casefold())
                       if not unicodedata.combining(c))
    for i,block in enumerate(blocks):
        text=block['text_raw']
        outer=bool(re.fullmatch(r'cau\s+\d+[.:]?',plain(text).strip()))
        provenance=outer and any(
            re.search(r'\btl\s+[0-9a-f]{8,64}\b.*\btrang\b',plain(b['text_raw']))
            and abs(b['bbox'][1]-block['bbox'][1])<25 for b in blocks[i+1:i+4])
        if provenance:
            active=True
        elif active and QUESTION.match(text):
            block['source_book_inner_label']=True
    return result


def split_columns(pages):
    result=[];mapping={};uncertain=[]
    for page in pages:
        width=page['width'];starts=[b for b in page['blocks'] if not b.get('is_margin')
            and not b.get('source_book_inner_label') and QUESTION.match(b['text_raw'])]
        left=[b for b in starts if b['bbox'][0]<width*.35]
        right=[b for b in starts if b['bbox'][0]>width*.48]
        two=bool(left and right)
        clips=[(0,width)] if not two else [(0,width/2),(width/2,width)]
        for col,(x0,x1) in enumerate(clips,1):
            virtual=len(result)+1;blocks=[];crossings=[]
            for original in page['blocks']:
                if two and not x0<=original['bbox'][0]<x1:
                    continue
                b=deepcopy(original)
                if two and b['bbox'][2]>x1+3 and not b.get('is_margin'):
                    crossings.append(b['block_id'])
                b['bbox']=[max(0,b['bbox'][0]-x0),b['bbox'][1],min(x1-x0,b['bbox'][2]-x0),b['bbox'][3]]
                if b['bbox'][2]<=b['bbox'][0]:continue
                for g in b.get('glyphs',[]):g['bbox']=[g['bbox'][0]-x0,g['bbox'][1],g['bbox'][2]-x0,g['bbox'][3]]
                blocks.append(b)
            if not blocks:
                blocks=[{'block_id':f'p{page["page_number"]:04}-image-only','block_type':'image_context',
                    'bbox':[0,1,x1-x0,page['height']-1],'text_raw':'','glyphs':[],
                    'review_flags':['IMAGE_REGION_WITHOUT_TEXT'],'is_margin':False}]
            vp={**page,'page_number':virtual,'width':x1-x0,'blocks':blocks,
                'content_bounds':[0,page['content_bounds'][1],x1-x0,page['content_bounds'][3]]}
            result.append(vp)
            mapping[virtual]={'page_number':page['page_number'],'x_offset':x0,'width':x1-x0,
                'column':col if two else None,'method':'TWO_COLUMN_MARKER_GEOMETRY' if two else 'SINGLE_PAGE_FLOW',
                'crossing_block_ids':crossings,'ocr_failed':page.get('ocr_failed',False)}
            if crossings:uncertain.append({'page_number':page['page_number'],'column':col,'reason':'TEXT_CROSSES_COLUMN_BOUNDARY','block_ids':crossings})
    return result,mapping,uncertain


def restore(span,mapping):
    m=mapping[span['page_number']];x0,y0,x1,y1=span['bbox']
    return {**span,'page_number':m['page_number'],'bbox':[x0+m['x_offset'],y0,x1+m['x_offset'],y1],
        'column':m['column'],'layout_method':m['method']}
