"""Bounded native fraction trees, retaining every glyph used by an equation.

Only source horizontal rules with glyphs on both sides can form a fraction.
Unsupported or ambiguously owned glyphs reject the candidate instead of vanishing.
"""
from __future__ import annotations

import re
from statistics import median

from .native_math import LHS, PROSE_WORD, glyph_positions
from .safe_math import UnsupportedMath, assignment


VERSION = "native-fraction-tree/v1"


def _box(items):
    return [min(g['bbox'][0] for g in items), min(g['bbox'][1] for g in items),
            max(g['bbox'][2] for g in items), max(g['bbox'][3] for g in items)]


def render(glyphs, bars, *, depth=0):
    if depth > 4 or not glyphs or len(glyphs) > 300 or len(bars) > 12:
        raise UnsupportedMath('FRACTION_TREE_COMPLEXITY_LIMIT')
    if len({g['key'] for g in glyphs}) != len(glyphs):
        raise UnsupportedMath('FRACTION_DUPLICATE_GLYPH')
    letters=[g['size'] for g in glyphs if re.fullmatch(r'[A-Za-zν]',g['text'])]
    size = median(letters) if letters else median(g['size'] for g in glyphs)
    remaining = {g['key']:g for g in glyphs}
    nodes, evidence = [], []
    # Wider containing bars own nested fractions before smaller inner bars.
    for bar in sorted(bars,key=lambda b:b[2]-b[0],reverse=True):
        x0,y,x1,_ = bar
        local = [g for g in remaining.values() if x0-1 <= (g['bbox'][0]+g['bbox'][2])/2 <= x1+1]
        above = [g for g in local if g['bbox'][3] <= y+1]
        below = [g for g in local if g['bbox'][1] >= y-1]
        if not above or not below:
            continue
        if len(above)+len(below) != len(local):
            raise UnsupportedMath('FRACTION_BAR_CROSSES_GLYPH')
        if y-min(g['bbox'][1] for g in above) > 5*size or max(g['bbox'][3] for g in below)-y > 5*size:
            raise UnsupportedMath('FRACTION_VERTICAL_OWNERSHIP_AMBIGUOUS')
        upper_bars = [b for b in bars if b!=bar and x0-1<=b[0]<b[2]<=x1+1 and b[1]<y]
        lower_bars = [b for b in bars if b!=bar and x0-1<=b[0]<b[2]<=x1+1 and b[1]>y]
        numerator,up_evidence = render(above,upper_bars,depth=depth+1)
        denominator,down_evidence = render(below,lower_bars,depth=depth+1)
        nodes.append({'text':r'\frac{'+numerator+'}{'+denominator+'}',
                      'bbox':[x0,y-size*.5,x1,y+size*.5],'size':size,'fraction':True,
                      'keys':{g['key'] for g in local}})
        evidence += [{'bar_bbox':bar,'numerator_glyph_keys':[g['key'] for g in above],
                      'denominator_glyph_keys':[g['key'] for g in below]},*up_evidence,*down_evidence]
        for g in local:
            del remaining[g['key']]
    nodes += [{**g,'keys':{g['key']}} for g in remaining.values()]
    if not nodes:
        raise UnsupportedMath('FRACTION_EMPTY_REGION')
    # All ordinary glyphs must share one baseline after replacing fractions.
    ordinary = [g for g in nodes if not g.get('fraction')]
    normal = [g for g in ordinary if g['size'] >= size*.82]
    baseline = median(g['bbox'][3] for g in normal) if normal else median(g['bbox'][3] for g in nodes)
    if normal and max(g['bbox'][3] for g in normal)-min(g['bbox'][3] for g in normal)>size*.45:
        raise UnsupportedMath('FRACTION_UNCONSUMED_BASELINES')
    nodes.sort(key=lambda g:(g['bbox'][0],g['bbox'][1]))
    output, used = [], set()
    last_power=None
    for node in nodes:
        if used & node['keys']:
            raise UnsupportedMath('FRACTION_DUPLICATE_GLYPH')
        used |= node['keys']
        if not node.get('fraction') and node['size']<size*.82:
            if (baseline-node['bbox'][3] < size*.23 or not re.fullmatch(r'[0-9+-]',node['text']) or not output):
                raise UnsupportedMath('FRACTION_SMALL_GLYPH_UNSUPPORTED')
            if (last_power and node['bbox'][0]-last_power['bbox'][2]<size*.5
                    and abs(node['bbox'][3]-last_power['bbox'][3])<size*.2):
                output[-1]=output[-1][:-1]+node['text']+'}'
            else:
                output.append('^{'+node['text']+'}')
            last_power=node
        else:
            output.append(node['text'])
            last_power=None
    if used != {g['key'] for g in glyphs}:
        raise UnsupportedMath('FRACTION_GLYPH_COVERAGE_FAILURE')
    return ''.join(output),evidence


def candidates_for_step(step,pages):
    if step['kind_candidate'] not in {'MODEL_SETUP','DERIVATIVE_CALCULATION','UNCLASSIFIED'}:
        return [],[]
    candidates,rejected = [],[]
    for page_number in sorted({s['page_number'] for s in step.get('text_slices',[])}):
        page = pages[page_number]
        sections = [s for s in step['text_slices'] if s['page_number']==page_number]
        blocks = {b['block_id']:b for b in page['blocks']}
        local,anchors = [],[]
        try:
            for section in sections:
                block = blocks[section['block_id']]
                text,glyphs = glyph_positions(block)
                lo,hi = section['normalized_start'],section['normalized_end']
                part = text[lo:hi]
                match = LHS.search(part)
                if match:
                    stop = re.search(r'[;⇔⇒]|\s+(?:với|do|nên|trong|và|cho|khi)\b',part[match.end():],re.I)
                    end = match.end()+stop.start() if stop else len(part)
                    # Preserve conditions as source text, but keep them out of the tree.
                    boundary = re.search(r'[, ]*\(?\s*(?:[A-Za-zν]|\d+)\s*[<>≤≥≠]',part[match.end():end])
                    if boundary:
                        end = match.end()+boundary.start()
                    anchors.append((block,lo+match.start(),lo+end,part[end:],match[0]))
                    lower,upper = lo+match.start(),lo+end
                else:
                    if PROSE_WORD.search(part):
                        raise UnsupportedMath('FRACTION_EXTRA_PROSE_BLOCK')
                    lower,upper=lo,hi
                for g in glyphs:
                    if lower<=g['offset']<upper:
                        local.append({**g,'text':text[g['offset']],'key':block['block_id']+':'+str(g['glyph_index'])})
            if len(anchors)!=1 or not local:
                continue
            # A boundary in the baseline must clip raised numerator/denominator
            # fragments too, otherwise a following equation becomes multiplication.
            anchor,lo,hi,tail,_ = anchors[0]
            anchor_text,anchor_glyphs = glyph_positions(anchor)
            next_glyph = next((g for g in anchor_glyphs if g['offset']>=hi),None)
            if next_glyph is not None:
                edge = next_glyph['bbox'][0]
                local = [g for g in local if (g['bbox'][0]+g['bbox'][2])/2 < edge]
            box = _box(local)
            bars = [v['bbox'] for v in page.get('vectors',[]) if v['kind'] in {'line','rect'}
                    and v['bbox'][3]-v['bbox'][1]<1 and v['bbox'][2]-v['bbox'][0]>5
                    and box[0]-2<=v['bbox'][0]<v['bbox'][2]<=box[2]+2
                    and box[1]<v['bbox'][1]<box[3]]
            if not bars:
                continue
            text,evidence = render(local,bars)
            if not evidence:
                raise UnsupportedMath('FRACTION_NO_COMPLETE_BAR')
            # An unknown function substitution cannot be treated as multiplication.
            # Keep the final equality endpoint and explicitly retain the whole chain.
            full = text
            pieces = text.split('=')
            endpoint = len(pieces)>2 and any(re.search(r'[A-Za-z]\([A-Za-z]\)',p) for p in pieces[1:])
            if endpoint:
                text=pieces[0]+'='+pieces[-1]
            if re.search(r'[A-Za-z]\([A-Za-z]\)',text.split('=',1)[-1]):
                raise UnsupportedMath('FRACTION_UNKNOWN_FUNCTION_SUBSTITUTION')
            parsed=assignment(text)
            if not parsed['chain_consistent']:
                raise UnsupportedMath('FRACTION_EQUALITY_CHAIN_INCONSISTENT')
            block=anchors[0][0]
            candidates.append({'block_id':block['block_id']+':fraction-tree','source_block_id':block['block_id'],
                'parser_id':VERSION,'page_number':page_number,'bbox':box,'latex':text,'full_chain_latex':full,
                'derivation_scope':'FINAL_EQUALITY_ENDPOINT_ONLY' if endpoint else 'FULL_SOURCE_CHAIN',
                'conditions_raw':anchors[0][3],'fraction_evidence':evidence,
                'source_glyph_keys':[g['key'] for g in local],'status':'NATIVE_GEOMETRY_CANDIDATE_NOT_VERIFIED'})
        except (UnsupportedMath,ValueError,TypeError,NotImplementedError) as error:
            rejected.append({'page_number':page_number,'reason':str(error)})
    return candidates,rejected
