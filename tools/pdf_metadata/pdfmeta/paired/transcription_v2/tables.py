"""Native PDF grids, excluding invisible text/background rectangles."""
from __future__ import annotations
from statistics import median
import re

from .glyphs import glyph_lookup
from ..math_recovery import center


SETTINGS={'vertical_strategy':'lines','horizontal_strategy':'lines','snap_tolerance':2,
          'join_tolerance':2,'intersection_tolerance':3,'edge_min_length':3}


def ink_edge(obj):
    kind=obj['object_type']
    if kind=='curve':return False
    if kind!='rect':return True
    if obj.get('stroke'):return True
    color=obj.get('non_stroking_color')
    dark=(isinstance(color,(int,float)) and color<.8) or (isinstance(color,(tuple,list)) and bool(color) and min(color)<.8)
    # Filled white text backgrounds have edges in pdfplumber, but no ink grid.
    return bool(dark and min(obj['width'],obj['height'])<1.5)


def inside(g,bbox):
    x,y=center(g)
    return bbox[0]<=x<bbox[2] and bbox[1]<=y<bbox[3]


def overlap(a,b):
    w=max(0,min(a[2],b[2])-max(a[0],b[0]));h=max(0,min(a[3],b[3])-max(a[1],b[1]))
    return w*h


def native_text(glyphs):
    """Plain text only: multi-baseline math is handled by the geometry reader."""
    if not glyphs:return ''
    rows=[]
    for g in sorted(glyphs,key=lambda g:(g['bbox'][3],g['bbox'][0])):
        y=(g['bbox'][1]+g['bbox'][3])/2
        row=next((r for r in rows if abs(r['y']-y)<max(2,g['size']*.25)),None)
        if row is None:row={'y':y,'glyphs':[]};rows.append(row)
        row['glyphs'].append(g)
    lines=[]
    for r in sorted(rows,key=lambda r:r['y']):
        previous=None;parts=[]
        for g in sorted(r['glyphs'],key=lambda g:g['bbox'][0]):
            if previous and g['bbox'][0]-previous['bbox'][2]>min(g['size'],previous['size'])*.18:parts.append(' ')
            parts.append(g['text']);previous=g
        lines.append(''.join(parts).strip())
    return '\n'.join(lines).strip()


def detect(raw_page,page):
    lookup=glyph_lookup(page);result=[]
    # Detect on the full page: cropping vector bboxes first can invent edges at
    # the crop boundary and join a decorative frame to the real table.
    for i,t in enumerate(raw_page.filter(ink_edge).find_tables(SETTINGS)):
        if len(t.rows)<2 or len(t.columns)<2:continue
        bbox=list(map(float,t.bbox))
        if bbox[2]-bbox[0]<30 or bbox[3]-bbox[1]<16:continue
        cells=[];seen=set()
        for ri,row in enumerate(t.rows):
            for ci,b in enumerate(row.cells):
                if b is None or tuple(b) in seen:continue
                seen.add(tuple(b));b=list(map(float,b))
                gs=[g for g in lookup.values() if inside(g,b)]
                text=native_text(gs)
                cells.append({'row':ri,'column':ci,'bbox':b,'text_native_display':text,
                    'source_glyph_keys':[g['key'] for g in gs],
                    'unmapped_glyph_keys':[g['key'] for g in gs if g.get('mapping_flag') in {'UNMAPPED_SOURCE_GLYPH','UNSUPPORTED_MULTICODEPOINT_GLYPH'}]})
        # Distinct physical cells can overlap only because of an invalid grid.
        if any(overlap(a['bbox'],b['bbox'])>.5 for j,a in enumerate(cells) for b in cells[j+1:]):continue
        result.append({'page_number':page['page_number'],'bbox':bbox,'rows':len(t.rows),'columns':len(t.columns),
            'cells':cells,'detector':'PDF_INK_GRID_V2','settings':dict(SETTINGS),
            'source_glyph_keys':sorted({k for c in cells for k in c['source_glyph_keys']}),
            'source_status':'NATIVE_GRID_CANDIDATE_NOT_ACADEMICALLY_REVIEWED'})
    return result


def for_span(tables,span):
    result=[]
    for t in tables:
        area=(t['bbox'][2]-t['bbox'][0])*(t['bbox'][3]-t['bbox'][1])
        intersection=overlap(t['bbox'],span['bbox'])
        if intersection<area*.85:continue
        if intersection<area*.999:
            # Keep a partial image/table flag; do not claim all cells were read.
            result.append({**t,'clipped_by_source_span':True})
        else:result.append({**t,'clipped_by_source_span':False})
    return result


def cell_kind(glyphs,plain):
    if not glyphs:return 'EMPTY'
    if any(g.get('mapping_flag') in {'UNMAPPED_SOURCE_GLYPH','UNSUPPORTED_MULTICODEPOINT_GLYPH'} for g in glyphs):return 'UNMAPPED'
    if re.fullmatch(r'[+-]?\d+(?:[.,]\d+)?%?',plain.strip()):return 'NUMBER'
    if re.search(r'[àáạảãâăèéẹêìíịòóọôơùúụưỳýỵđ]',plain,re.I):return 'TEXT'
    return 'MATH_OR_SYMBOLS'


def markdown(table):
    if len(table['cells'])!=table['rows']*table['columns']:
        return '![Bảng có ô gộp cần đối chiếu]('+table['asset_path']+')'
    grid=[['' for _ in range(table['columns'])] for _ in range(table['rows'])]
    for cell in table['cells']:
        value=cell.get('display_text')
        if value is None:
            if cell.get('asset_path'):value='![Ô bảng từ ảnh nguồn]('+cell['asset_path']+')'
            else:return '![Bảng nguồn cần đối chiếu]('+table['asset_path']+')'
        grid[cell['row']][cell['column']]=value.replace('|',r'\|').replace('\n','<br>')
    lines=['| '+' | '.join(row)+' |' for row in grid]
    if lines:lines.insert(1,'| '+' | '.join(['---']*table['columns'])+' |')
    return '\n'.join(lines)
