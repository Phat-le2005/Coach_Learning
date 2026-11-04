"""Conservative source geometry for fractions, scripts and assembled brackets.

No equation solving, spelling correction or inferred missing characters. Every
accepted tree owns every input glyph exactly once; ambiguous layouts stay images.
"""
from statistics import median
import re

from ...safe_math import UnsupportedMath
from ..math_recovery import bounds, center
from ..transcript_regions import native_latex


COMMANDS={'∫':r'\int ', '∑':r'\sum ', '∏':r'\prod ', 'π':r'\pi ',
          'α':r'\alpha ', 'β':r'\beta ', 'μ':r'\mu ', 'σ':r'\sigma ',
          'Δ':r'\Delta ', '⇒':r'\Rightarrow ', '⇔':r'\Leftrightarrow ',
          '∉':r'\notin ', '≈':r'\approx ', '∂':r'\partial ', '×':r'\times ',
          '·':r'\cdot ', '′':"'", '∅':r'\varnothing '}
ASSEMBLED={'⎛⎝':'(', '⎛⎜⎝':'(', '⎞⎠':')', '⎞⎟⎠':')',
           '⎡⎣':'[','⎡⎢⎣':'[','⎤⎦':']','⎤⎥⎦':']'}


def token(text):
    if any(c in text for c in '□⎧⎨⎩⎪⎫⎬⎭⎮√'):raise UnsupportedMath('COMPOUND_OR_RADICAL_IMAGE_REQUIRED')
    value=''.join(COMMANDS.get(c,c) for c in text)
    value=native_latex(value)
    for name in ['arcsin','arccos','sin','cos','tan','cot','ln','log','lim']:
        value=re.sub(r'(?<![A-Za-z\\])'+name+r'(?![A-Za-z])',lambda m:'\\'+m[0]+' ',value)
    return value


def render(glyphs,vectors,depth=0):
    gs=[dict(g,keys={g['key']}) for g in glyphs if g['text'].strip()]
    if not gs or len(gs)>250 or depth>4:raise UnsupportedMath('V2_GEOMETRY_BOUND')
    if len({g['key'] for g in gs})!=len(gs):raise UnsupportedMath('DUPLICATE_SOURCE_GLYPH')
    remaining={g['key']:g for g in gs};nodes=[];evidence=[]
    size=median(g['size'] for g in gs)
    # MathType can draw absolute delimiters as vectors with no text glyph.
    # Own the enclosed glyphs before handling scripts and integral limits.
    verticals=[]
    for v in vectors:
        b=v['bbox']
        if (v['kind'] in {'line','rect'} and b[2]-b[0]<.9
                and size*.8<b[3]-b[1]<size*3.5):
            if not any(max(abs(x-y) for x,y in zip(b,a))<.6 for a in verticals):verticals.append(b)
    paired=set()
    for left in sorted(verticals):
        if tuple(left) in paired:continue
        rights=[r for r in verticals if r[0]-left[0]>size*.4 and tuple(r) not in paired
                and abs(r[1]-left[1])<1.2 and abs(r[3]-left[3])<1.2]
        for right in sorted(rights):
            inner=[g for g in remaining.values() if left[0]<center(g)[0]<right[0]
                   and left[1]-size*.3<center(g)[1]<left[3]+size*.3]
            if not inner:continue
            if min(g['bbox'][0] for g in inner)-left[0]>size*.8 or right[0]-max(g['bbox'][2] for g in inner)>size*.8:continue
            nested=[v for v in vectors if v['bbox'] not in [left,right]
                    and left[0]<v['bbox'][0]<=v['bbox'][2]<right[0]]
            value,ev=render(inner,nested,depth+1);keys={g['key'] for g in inner}
            nodes.append({'text':r'\left|'+value+r'\right|','bbox':[left[0],left[1],right[0],right[3]],
                          'size':size,'keys':keys,'fraction':True})
            evidence += [{'kind':'ABSOLUTE_VALUE','bar_bboxes':[left,right],'glyph_keys':sorted(keys)},*ev]
            for k in keys:del remaining[k]
            paired.update([tuple(left),tuple(right)]);break
    # Join bracket pieces only when top and bottom and all intervening pieces
    # are present in the same narrow source column. A lone piece is ambiguous.
    for g in sorted(gs,key=lambda g:g['bbox'][0]):
        if g['key'] not in remaining or g['text'] not in '⎛⎞⎡⎤':continue
        group=[a for a in remaining.values() if a['text'] in '⎛⎜⎝⎞⎟⎠⎡⎢⎣⎤⎥⎦'
               and abs(center(a)[0]-center(g)[0])<max(1,size*.25)]
        group.sort(key=lambda a:a['bbox'][1]);chars=''.join(a['text'] for a in group)
        compressed=re.sub(r'(⎜|⎟|⎢|⎥)\1+',r'\1',chars)
        if compressed not in ASSEMBLED:raise UnsupportedMath('ASSEMBLY_BRACKET_INCOMPLETE')
        b=bounds(group);keys={a['key'] for a in group}
        nodes.append({'text':ASSEMBLED[compressed],'bbox':b,'size':size,'keys':keys,'bracket':True})
        evidence.append({'kind':'ASSEMBLED_BRACKET','glyph_keys':sorted(keys)})
        for k in keys:del remaining[k]
    bbox=bounds(gs)
    bars=[v['bbox'] for v in vectors if v['kind'] in {'line','rect'} and v['bbox'][3]-v['bbox'][1]<.9
          and 3<v['bbox'][2]-v['bbox'][0]<size*18
          and bbox[0]-size*2<=v['bbox'][0]<v['bbox'][2]<=bbox[2]+size*2 and bbox[1]-3<v['bbox'][1]<bbox[3]]
    unique=[]
    for b in bars:
        if not any(max(abs(x-y) for x,y in zip(b,a))<.6 for a in unique):unique.append(b)
    for b in sorted(unique,key=lambda b:b[2]-b[0],reverse=True):
        x0,y,x1,_=b
        local=[g for g in remaining.values() if x0-1<=center(g)[0]<=x1+1]
        above=[g for g in local if g['bbox'][3]<=y+1]
        below=[g for g in local if g['bbox'][1]>=y-1]
        if not above and below and len(below)==len(local):
            if (max(g['bbox'][1]-y for g in below)<size*.55 and
                    abs(min(g['bbox'][0] for g in below)-x0)<size*.7 and
                    abs(max(g['bbox'][2] for g in below)-x1)<size*.7):
                inner=[v for v in vectors if v['bbox']!=b and v['bbox'][1]>y]
                value,ev=render(below,inner,depth+1);keys={g['key'] for g in below}
                nodes.append({'text':r'\overline{'+value+'}','bbox':bounds(below),'size':size,'keys':keys,'fraction':True})
                evidence += [{'kind':'OVERLINE','bar_bbox':b,'glyph_keys':sorted(keys)},*ev]
                for k in keys:del remaining[k]
                continue
        if not above or not below:continue
        if len(above)+len(below)!=len(local):raise UnsupportedMath('BAR_CROSSES_SOURCE_GLYPH')
        if y-min(g['bbox'][1] for g in above)>size*4 or max(g['bbox'][3] for g in below)-y>size*4:
            raise UnsupportedMath('FRACTION_OWNERSHIP_AMBIGUOUS')
        upper=[v for v in vectors if v['bbox'][1]<y and x0-1<=v['bbox'][0]<v['bbox'][2]<=x1+1]
        lower=[v for v in vectors if v['bbox'][1]>y and x0-1<=v['bbox'][0]<v['bbox'][2]<=x1+1]
        u,ue=render(above,upper,depth+1);d,de=render(below,lower,depth+1)
        keys={g['key'] for g in local}
        nodes.append({'text':r'\frac{'+u+'}{'+d+'}','bbox':[x0,y-size*.45,x1,y+size*.45],
                      'size':size,'keys':keys,'fraction':True})
        evidence += [{'kind':'FRACTION','bar_bbox':b,'glyph_keys':sorted(keys)},*ue,*de]
        for k in keys:del remaining[k]
    nodes += list(remaining.values())
    ordinary=[g for g in nodes if not g.get('fraction') and not g.get('bracket')]
    # Largest ordinary source font determines baseline, not a majority of small
    # numerator/index characters. Long multi-line systems deliberately reject.
    regular=[g for g in ordinary if g['text'] not in {'∫','∑','∏'}]
    maxsize=max(g['size'] for g in regular) if regular else size
    normal=[g for g in regular if g['size']>=maxsize*.83]
    baseline=median(g['bbox'][3] for g in normal) if normal else median(g['bbox'][3] for g in nodes)
    if normal and max(g['bbox'][3] for g in normal)-min(g['bbox'][3] for g in normal)>maxsize*.48:
        raise UnsupportedMath('MULTILINE_LAYOUT_REQUIRES_IMAGE_REVIEW')
    main=[];scripts=[]
    for g in nodes:
        if any(c in g['text'] for c in '⎜⎝⎟⎠⎢⎣⎥⎦'):raise UnsupportedMath('ORPHAN_ASSEMBLY_GLYPH')
        offset=g['bbox'][3]-baseline
        if not g.get('fraction') and not g.get('bracket') and g['text'] not in {'∫','∑','∏'} and g['size']<maxsize*.83:
            if offset < -maxsize*.20:kind='^'
            elif offset > maxsize*.10:kind='_'
            else:raise UnsupportedMath('SMALL_GLYPH_BASELINE_AMBIGUOUS')
            scripts.append((g,kind))
        else:main.append(g)
    main.sort(key=lambda g:g['bbox'][0]);groups={}
    for g,kind in scripts:
        candidates=[a for a in main if a['bbox'][0]<center(g)[0] and g['bbox'][0]-a['bbox'][2]<maxsize*.9]
        if not candidates:raise UnsupportedMath('SCRIPT_WITHOUT_SOURCE_BASE')
        base=max(candidates,key=lambda a:a['bbox'][0])
        if base['text'] in '=+-<>':raise UnsupportedMath('SCRIPT_INVALID_BASE')
        groups.setdefault((id(base),kind),[]).append(g)
    output=[];used=set()
    for g in main:
        text=g['text'] if g.get('fraction') else token(g['text'])
        used |= g['keys']
        for kind in ['_','^']:
            group=groups.get((id(g),kind),[])
            if group:
                group.sort(key=lambda a:a['bbox'][0])
                if max(a['bbox'][3] for a in group)-min(a['bbox'][3] for a in group)>maxsize*.25:
                    raise UnsupportedMath('NESTED_SCRIPT_AMBIGUOUS')
                text+=kind+'{'+token(''.join(a['text'] for a in group))+'}'
                keys={k for a in group for k in a['keys']};used |= keys
                evidence.append({'kind':'SUPERSCRIPT' if kind=='^' else 'SUBSCRIPT','base_keys':sorted(g['keys']),'glyph_keys':sorted(keys)})
        output.append(text)
    if used!={g['key'] for g in gs}:raise UnsupportedMath('GEOMETRY_INCOMPLETE_OWNERSHIP')
    latex=''.join(output)
    # A top rule must not silently vanish as ordinary text. Overlines require a
    # separate unambiguous tree; retain an image until that path is supported.
    consumed=[e['bar_bbox'] for e in evidence if e['kind'] in {'FRACTION','OVERLINE'}]
    for b in unique:
        if b not in consumed and any(b[0]<=center(g)[0]<=b[2] and 0<g['bbox'][1]-b[1]<maxsize*.5 for g in gs):
            raise UnsupportedMath('UNCONSUMED_TOP_RULE')
    return latex,evidence
