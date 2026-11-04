"""Conservative checks for math structures omitted by PDF text extraction."""
from __future__ import annotations

from statistics import median
import re

from ..safe_math import UnsupportedMath
from ..text_cleanup import normalize_block


def glyph_text(glyph):
    return normalize_block({'text_raw':glyph['text'],'glyphs':[glyph]})[0]


def inspect(page,bbox):
    glyphs=[{**g,'source_block_id':block['block_id']} for block in page['blocks'] for g in block.get('glyphs',[])
            if bbox[0]-2<=g['bbox'][0]<=bbox[2]+2 and bbox[1]-3<=g['bbox'][3] and g['bbox'][1]<=bbox[3]+3]
    regular=[g for g in glyphs if 9<=g['size']<=14 and re.fullmatch(r'[A-Za-z0-9ν]',g['text'])]
    size=median(g['size'] for g in regular) if regular else 12
    head=[g for g in regular if g['bbox'][0]<bbox[0]+min(32,(bbox[2]-bbox[0])*.4)]
    bottom=median(g['bbox'][3] for g in head or regular) if regular else bbox[3]
    vectors=page.get('vectors',[])
    verticals=[v['bbox'] for v in vectors if v['kind'] in {'line','rect'} and v['bbox'][2]-v['bbox'][0]<.9
               and size*.8<v['bbox'][3]-v['bbox'][1]<size*2.8
               and bbox[0]-2<v['bbox'][0]<bbox[2]+size*.6
               and v['bbox'][1]<bottom-size*.55 and v['bbox'][3]>bottom-size*.15]
    bars=[]
    for left in verticals:
        for right in verticals:
            if right[0]-left[0]>size*.4 and abs(left[1]-right[1])<1 and abs(left[3]-right[3])<1:
                enclosed=[g for g in glyphs if left[0]<g['bbox'][0] and g['bbox'][2]<right[0]+.3]
                if enclosed and min(g['bbox'][0] for g in enclosed)-left[0]<size*.6 and right[0]-max(g['bbox'][2] for g in enclosed)<size*.6:
                    bars.append([left,right])
    overlines=[v['bbox'] for v in vectors if v['kind']=='line' and v['bbox'][3]-v['bbox'][1]<.35
               and size*.25<v['bbox'][2]-v['bbox'][0]<size*1.1
               and bbox[0]-1<=v['bbox'][0]<bbox[0]+size*.8
               and bottom-size*1.5<v['bbox'][1]<bottom-size*.9]
    lower=[g for g in glyphs if bbox[3]-bbox[1]<size*1.9 and g['size']<size*.82 and g['bbox'][3]>bottom+size*.1
           and g['bbox'][1]<bottom-size*.2 and re.fullmatch(r'[0-9A-Za-z]',g['text'])]
    topbars=[v['bbox'] for v in vectors if v['kind']=='line' and v['bbox'][3]-v['bbox'][1]<.35
             and v['bbox'][2]-v['bbox'][0]>size*.6 and bbox[0]+size<v['bbox'][0]
             and v['bbox'][2]<=bbox[2]+2 and bottom-size*1.8<v['bbox'][1]<bottom-size*.7]
    return {'absolute_bars':bars,'overlines':overlines,'lower_glyphs':lower,'top_bars':topbars,'baseline_bottom':bottom,'font_size':size}


def resolve(page,candidate):
    """Replay native extraction and refuse a parseable reading that lost structures."""
    value=candidate['latex'];bbox=candidate['bbox'];original=value
    proof={'source_page':page['page_number'],'original_bbox':bbox,'original_latex':value}
    if candidate.get('parser_id','').startswith('native-baseline'):
        from ..native_math import candidates_for_step,glyph_positions
        block_id=candidate.get('source_block_id') or candidate.get('block_id','').split(':')[0]
        block=next((b for b in page['blocks'] if b['block_id']==block_id),None)
        if block:
            text,positions=glyph_positions(block)
            start=min((g['offset'] for g in positions if abs(g['bbox'][0]-bbox[0])<1),default=0)
            step={'kind_candidate':'MODEL_SETUP','text_slices':[{'page_number':page['page_number'],'block_id':block_id,
                    'normalized_start':start,'normalized_end':len(text)}]}
            recovered,_=candidates_for_step(step,{page['page_number']:page})
            if recovered and abs(recovered[0]['bbox'][0]-bbox[0])<1:
                value,bbox=recovered[0]['latex'],recovered[0]['bbox']
                proof['recovered_bbox']=bbox
    signals=inspect(page,bbox)
    if signals['absolute_bars'] and not re.search(r'\||\\[lr]?vert|\babs\(',value):
        raise UnsupportedMath('SOURCE_ABSOLUTE_BARS_MISSING_FROM_TEXT')
    if signals['overlines'] and not re.search(r'\\(?:bar|overline)\b',value):
        raise UnsupportedMath('SOURCE_OVERLINE_MISSING_FROM_TEXT')
    if signals['lower_glyphs'] and '_' not in value:
        raise UnsupportedMath('SOURCE_SUBSCRIPT_GLYPH_MISSING_FROM_TEXT')
    if signals['top_bars'] and not re.search(r'\\(?:sqrt|frac|overline|bar)\b|sqrt\(',value):
        raise UnsupportedMath('SOURCE_TOP_BAR_REQUIRES_LAYOUT')
    return value,{**proof,'changed':value!=original,'structures':{k:len(signals[k]) for k in ['absolute_bars','overlines','lower_glyphs']}}


def text_candidate(raw,spans,page_lookup):
    """Bind a literal single-line text fragment to source glyphs before parsing it."""
    from ..native_math import glyph_positions
    matches=[]
    for span in spans:
        page=page_lookup.get(span['page_number'])
        if not page:continue
        allowed=span.get('block_ids')
        for block in page['blocks']:
            if allowed and block['block_id'] not in allowed:continue
            normalized=normalize_block(block)[0]
            if normalized.count(raw)!=1:continue
            lo=normalized.index(raw);hi=lo+len(raw)
            try:_,positions=glyph_positions(block)
            except UnsupportedMath:continue
            local=[g for g in positions if lo<=g['offset']<hi]
            if not local:continue
            box=[min(g['bbox'][0] for g in local),min(g['bbox'][1] for g in local),
                 max(g['bbox'][2] for g in local),max(g['bbox'][3] for g in local)]
            matches.append((page,{'latex':raw,'bbox':box,'source_block_id':block['block_id'],
                                  'parser_id':'native-baseline-replay/v1'}))
    # Repeated identical source text can be at several places. Refuse to choose a
    # different source silently; every matched occurrence must agree structurally.
    if not matches:return raw,None
    results=[resolve(page,candidate) for page,candidate in matches]
    if len({value for value,_ in results})!=1:raise UnsupportedMath('SOURCE_TEXT_MATCHES_DISAGREE')
    return results[0]
