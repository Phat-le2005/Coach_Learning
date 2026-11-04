"""Stable glyph masking before formula proposal; grids never seed fractions."""
from copy import deepcopy
from statistics import median

from ..transcript_regions import propose
from ..math_recovery import bounds
from .glyphs import glyph_lookup
from .tables import inside, overlap


def prepare(page,span,tables):
    masked=deepcopy(page);keys={k for t in tables for k in t['source_glyph_keys']}
    figures=[i for i in page.get('images',[]) if overlap(i['bbox'],span['bbox'])>0
             and i['bbox'][2]-i['bbox'][0]>24 and i['bbox'][3]-i['bbox'][1]>20]
    lookup=glyph_lookup(page)
    keys |= {k for k,g in lookup.items() if any(inside(g,i['bbox']) for i in figures)}
    keys |= {k for k,g in lookup.items() if any(b.get('alignment_error') and b['block_id']==g['block_id'] for b in page['blocks'])}
    for block in masked['blocks']:
        raw=block['text_raw'];cursor=0;parts=[]
        for i,g in enumerate(block['glyphs']):
            at=raw.find(g['text'],cursor)
            if at<0:raise ValueError('MASK_ALIGNMENT_FAILED')
            parts.append(raw[cursor:at]);key=block['block_id']+':'+str(i)
            if key in keys:g['text']=' ';g['font']='layout-masked'
            parts.append(g['text']);cursor=at+1
        parts.append(raw[cursor:]);block['text_raw']=''.join(parts)
    masked['vectors']=[v for v in masked['vectors'] if not any(overlap(v['bbox'],t['bbox'])>0 or
        (t['bbox'][0]-.5<=v['bbox'][0]<=v['bbox'][2]<=t['bbox'][2]+.5 and t['bbox'][1]-.5<=v['bbox'][1]<=v['bbox'][3]<=t['bbox'][3]+.5) for t in tables)]
    masked['blocks']=[b for b in masked['blocks'] if any(g['text'].strip() for g in b['glyphs'])]
    if not any(g['text'].strip() and inside(g,span['bbox']) for b in masked['blocks'] for g in b['glyphs']):
        return masked,[],[],[],figures
    formulas,rows,errors=propose(masked,span)
    for f in formulas:
        f['source_glyph_keys']=[k for k in f['source_glyph_keys'] if k not in keys and lookup[k]['text'].strip()]
        if f['source_glyph_keys']:f['bbox']=bounds([lookup[k] for k in f['source_glyph_keys']])
    formulas=[f for f in formulas if f['source_glyph_keys']]
    if any(keys & set(f['source_glyph_keys']) for f in formulas):raise ValueError('TABLE_MATH_OWNERSHIP_OVERLAP')
    return masked,formulas,rows,errors,figures
