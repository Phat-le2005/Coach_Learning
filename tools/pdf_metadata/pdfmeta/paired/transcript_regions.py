"""Source glyph ownership, inline math proposals and faithful draft assembly.

No repaired string is inferred from PDFium lossy text. Ambiguous source regions
remain image-backed candidates. Detection coverage is a glyph heuristic, not
measured formula recall or academic approval.
"""
from __future__ import annotations

from copy import deepcopy
import re
from statistics import median

from ..native_math import recover_slice
from ..safe_math import UnsupportedMath
from ..text_cleanup import is_suspicious
from .math_recovery import aligned, bounds, center, choice_labels, regions, within


MATH_WORDS = {'sin','cos','tan','cot','ln','log','exp','lim','dx','dy','dt','dv','du','max','min','det','mod','arcsin','arccos'}
SYMBOLS = set('=+−–-*/^_()[]{}<>≤≥≠≈∈∉∪∩∫∑π√∞∂∏|')
WORD = re.compile(r'[^\W\d_]+', re.UNICODE)


def rows_for(page, span):
    rows, errors = [], []
    for block in page['blocks']:
        local = [g for g in block['glyphs'] if within(g, span['bbox'])]
        if not local:continue
        try:
            text, glyphs = aligned(block)
        except UnsupportedMath as error:
            errors.append({'block_id':block['block_id'],'reason':str(error),'bbox':bounds(local)})
            continue
        glyphs = [g for g in glyphs if within(g, span['bbox'])]
        labels = [m for m in choice_labels(text,glyphs) if text[m.end():].strip()]
        rows.append({'block':block,'text':text,'glyphs':glyphs,'labels':labels})
    return rows, errors


def math_seed(glyph, body_size):
    char, font = glyph['text'], glyph['font'].lower()
    return (char in SYMBOLS or 'symbol' in font or 'math' in font or
            (re.fullmatch(r'[A-Za-zα-ωΑ-Ω]',char) and ('italic' in font or 'oblique' in font)) or
            (char.isdigit() and glyph['size'] < body_size*.82))


def propose(page, span):
    rows, errors = rows_for(page,span)
    if not rows:return [],rows,errors
    sizes = [g['size'] for r in rows for g in r['glyphs'] if g['text'].strip()]
    body_size = median(sizes)
    candidates, old_errors = regions(page,span)
    errors.extend(old_errors)
    occupied = {key for f in candidates for key in f['source_glyph_keys']}
    for f in candidates:f['detector']='ASSIGNMENT_OR_INTEGRAL_ANCHOR'
    for row in rows:
        blocked = set()
        for word in WORD.finditer(row['text']):
            value = word[0]
            if (len(value)>1 and value.lower() not in MATH_WORDS) or any(ord(c)>127 and c.isalpha() and c not in 'αβγδθλμπσφωΔΩΣ' for c in value):
                blocked.update(range(word.start(),word.end()))
        for label in row['labels']:blocked.update(range(label.start(),label.end()))
        available = {g['offset']:g for g in row['glyphs'] if g['key'] not in occupied}
        groups, current = [], []
        for offset,char in enumerate(row['text']):
            if offset in blocked or (offset not in available and not char.isspace()):
                if current:groups.append(current);current=[]
            elif offset in available:current.append(available[offset])
        if current:groups.append(current)
        for glyphs in groups:
            while glyphs and glyphs[0]['text'] in ' .,:;':glyphs.pop(0)
            while glyphs and glyphs[-1]['text'] in ' .,:;':glyphs.pop()
            if not glyphs or not any(math_seed(g,body_size) for g in glyphs):continue
            # A sentence dash or punctuation alone is not a formula region.
            if not any(g['text'].isalnum() or g['text'] in '∞∫∑π√' for g in glyphs):continue
            candidate={'label':None,'bbox':bounds(glyphs),'source_block_id':row['block']['block_id'],
                       'source_glyph_keys':[g['key'] for g in glyphs], 'native_candidate':None,
                       'native_rejection':None,'detector':'INLINE_STYLE_AND_SYMBOLS'}
            lo,hi=glyphs[0]['offset'],glyphs[-1]['offset']+1
            original=row['block']
            selected={g['key'] for g in glyphs}
            local={**original,'text_raw':original['text_raw'][lo:hi],
                   'glyphs':[g for i,g in enumerate(original['glyphs']) if original['block_id']+':'+str(i) in selected]}
            try:candidate['native_candidate']=recover_slice(local,0,len(local['text_raw']),page['vectors'])[0]
            except (UnsupportedMath,ValueError,TypeError) as error:candidate['native_rejection']=str(error)
            candidates.append(candidate);occupied.update(selected)
    # Numeric-only fractions have no italic/operator anchor (e.g. choices 1/190).
    glyph_lookup={g['key']:g for r in rows for g in r['glyphs']}
    for v in page['vectors']:
        b=v['bbox']
        if v['kind'] not in {'line','rect'} or b[3]-b[1]>.8 or not 4<b[2]-b[0]<body_size*5:continue
        local=[g for g in glyph_lookup.values() if b[0]-1<=center(g)[0]<=b[2]+1
               and abs(center(g)[1]-b[1])<body_size*1.6 and (g['text'].isdigit() or math_seed(g,body_size))]
        above=[g for g in local if g['bbox'][3]<=b[1]+1]
        below=[g for g in local if g['bbox'][1]>=b[1]-1]
        if not above or not below:continue
        free=[g for g in local if g['key'] not in occupied]
        if not free:continue
        touched=[i for i,f in enumerate(candidates) if set(f['source_glyph_keys'])&{g['key'] for g in local}]
        anchors=[i for i in touched if candidates[i]['detector']=='ASSIGNMENT_OR_INTEGRAL_ANCHOR']
        if len(anchors)>1:continue
        keys={g['key'] for g in local}|{k for i in touched for k in candidates[i]['source_glyph_keys']}
        local=[glyph_lookup[k] for k in keys]
        anchor=max(local,key=lambda g:g['bbox'][1])
        anchor_block=candidates[anchors[0]]['source_block_id'] if anchors else anchor['key'].rsplit(':',1)[0]
        candidates=[f for i,f in enumerate(candidates) if i not in touched]
        candidates.append({'label':None,'bbox':bounds(local),'source_block_id':anchor_block,
            'source_glyph_keys':sorted(keys),'native_candidate':None,'native_rejection':'NUMERIC_FRACTION_REQUIRES_LAYOUT',
            'detector':'SOURCE_NUMERIC_FRACTION_BAR'})
        occupied.update(keys)
    # Source fraction rules link numerator/denominator fragments. Long table rules
    # are excluded, and every glyph remains owned once after a merge.
    all_glyphs={g['key']:g for r in rows for g in r['glyphs']}
    for vector in page['vectors']:
        b=vector['bbox']
        if vector['kind'] not in {'line','rect'} or b[3]-b[1]>.8 or not 4<b[2]-b[0]<body_size*14:continue
        near=[]
        for i,f in enumerate(candidates):
            glyphs=[all_glyphs[k] for k in f['source_glyph_keys']]
            if any(b[0]-1<=center(g)[0]<=b[2]+1 and abs(center(g)[1]-b[1])<body_size*2.2 for g in glyphs):near.append(i)
        if len(near)<2:continue
        combined={k for i in near for k in candidates[i]['source_glyph_keys']}
        glyphs=[all_glyphs[k] for k in combined]
        if not (any(g['bbox'][3]<=b[1]+1 for g in glyphs) and any(g['bbox'][1]>=b[1]-1 for g in glyphs)):continue
        # Do not merge two full assignments on neighboring answer rows.
        anchored=[i for i in near if candidates[i]['detector']=='ASSIGNMENT_OR_INTEGRAL_ANCHOR']
        if len(anchored)>1:continue
        anchor=candidates[anchored[0] if anchored else max(near,key=lambda i:len(candidates[i]['source_glyph_keys']))]
        merged={**anchor,'bbox':bounds(glyphs),'source_glyph_keys':sorted(combined),'native_candidate':None,
                'native_rejection':'SOURCE_FRACTION_FRAGMENTS_MERGED','detector':'SOURCE_FRACTION_CONNECTED_COMPONENT'}
        candidates=[f for i,f in enumerate(candidates) if i not in near]+[merged]
    candidates.sort(key=lambda f:(f['bbox'][1],f['bbox'][0]))
    return candidates,rows,errors


def crop_box(page, region, span, rows):
    b=list(region['bbox']);size=median(g['size'] for r in rows for g in r['glyphs'])
    original=list(b)
    # A radical can extend left/above its text. Never grow transitively through
    # table-cell borders, which previously made the model read an entire table.
    for v in page['vectors']:
        a=v['bbox']
        if v['kind']!='line' or max(a[2]-a[0],a[3]-a[1])>max(size*1.8,original[2]-original[0]):continue
        if (original[0]-size*.8<=a[0]<=original[2] and a[2]<=original[2]+1
                and original[1]-size*.8<=a[1] and a[3]<=original[3]+1):
            b=[min(b[0],a[0]),min(b[1],a[1]),max(b[2],a[2]),max(b[3],a[3])]
    clip=span['bbox']
    return [max(clip[0],b[0]-1.5),max(clip[1],b[1]-1.5),min(clip[2],b[2]+1.5),min(clip[3],b[3]+1.5)]


def visual_flags(page,span):
    inside=lambda b:b[0]>=span['bbox'][0] and b[2]<=span['bbox'][2] and b[1]>=span['bbox'][1] and b[3]<=span['bbox'][3]
    vectors=[v for v in page['vectors'] if inside(v['bbox'])]
    horizontal=[v for v in vectors if v['bbox'][2]-v['bbox'][0]>55 and v['bbox'][3]-v['bbox'][1]<1]
    vertical=[v for v in vectors if v['bbox'][3]-v['bbox'][1]>20 and v['bbox'][2]-v['bbox'][0]<1]
    flags=[]
    if len(horizontal)>=3 and len(vertical)>=2:flags.append('TABLE_OR_SIGN_CHART_REQUIRES_SOURCE_IMAGE')
    if sum(v['kind']=='curve' for v in vectors)>15 or len(vectors)>100:flags.append('VECTOR_FIGURE_REQUIRES_SOURCE_IMAGE')
    if any(inside(i['bbox']) for i in page.get('images',[])):flags.append('EMBEDDED_IMAGE_REQUIRES_SOURCE_IMAGE')
    return flags


def native_latex(text):
    return (text.strip().replace('−','-').replace('–','-').replace('∫',r'\int ')
            .replace('∞',r'\infty ').replace('≤',r'\leq ').replace('≥',r'\geq ')
            .replace('≠',r'\ne ').replace('∈',r'\in ').replace('∪',r'\cup ').replace('∩',r'\cap ')
            .replace('%',r'\%'))


def assemble(rows, formulas):
    """Replace owned glyphs with one formula at its actual source anchor."""
    owned,insertions={},{}
    glyphs={g['key']:g for r in rows for g in r['glyphs']}
    for f in formulas:
        keys=f['source_glyph_keys']
        if set(keys)&set(owned):raise ValueError('TRANSCRIPT_DUPLICATE_GLYPH_OWNERSHIP')
        source=[glyphs[k] for k in keys]
        local=[g for g in source if g['key'].rsplit(':',1)[0]==f['source_block_id']]
        if not local:raise ValueError('TRANSCRIPT_ANCHOR_WITHOUT_GLYPHS')
        anchor=min(local,key=lambda g:g['offset'])
        latex=f.get('display_latex',f.get('latex_candidate'))
        token=('$'+latex+'$') if latex else '!['+'Công thức cần đọc từ ảnh'+']('+f['asset_path']+')'
        insertions[anchor['key']]=token
        for key in keys:owned[key]=f['formula_id']
    output=[]
    for row in rows:
        by_offset={g['offset']:g for g in row['glyphs']};parts=[]
        labels={m.start():m for m in row['labels']}
        label_offsets={i for m in row['labels'] for i in range(m.start(),m.end())}
        for i,char in enumerate(row['text']):
            if i in labels:parts.append('\n\x00CHOICE_'+labels[i][0][0]+'\x00')
            if i in label_offsets:continue
            g=by_offset.get(i)
            if g:
                if g['key'] in insertions:parts.append(insertions[g['key']])
                if g['key'] not in owned:parts.append(g['text'])
            elif char.isspace() and parts:parts.append(' ')
        text=''.join(parts).strip()
        if text:output.append(text)
    value='\n'.join(output)
    pieces=re.split(r'\x00CHOICE_([ABCD])\x00',value)
    choices=[]
    if len(pieces)>1:
        labels=pieces[1::2]
        if len(labels)!=len(set(labels)):
            value=re.sub(r'\x00CHOICE_([ABCD])\x00',r'\1. ',value)
        else:
            for i in range(1,len(pieces),2):choices.append({'label':pieces[i],'markdown':pieces[i+1].strip()})
            value=pieces[0].strip()
    # Unknown encodings cannot become clean math merely by being pretty-printed.
    if any(is_suspicious(c) for c in value):raise ValueError('UNMAPPED_GLYPH_IN_TRANSCRIPT')
    choice_issues=[]
    from .choice_layout import meaningful,recover
    if choices and any(not meaningful(c['markdown']) for c in choices):
        recovered=recover(rows,formulas,owned,insertions)
        if recovered:value,choices=recovered['markdown'],recovered['choices']
        else:choice_issues.append('CHOICE_LAYOUT_AMBIGUOUS_SOURCE_REQUIRED')
    return {'markdown':value,'choices':choices,'choice_issues':choice_issues}


def audit_coverage(rows, formulas, errors):
    glyphs={g['key']:g for r in rows for g in r['glyphs']}
    size=median(g['size'] for g in glyphs.values()) if glyphs else 0
    suspect={k for k,g in glyphs.items() if math_seed(g,size)}
    covered={k for f in formulas for k in f['source_glyph_keys']}
    uncovered=sorted(suspect-covered)
    return {'method':'FONT_STYLE_AND_SYMBOL_HEURISTIC_NOT_FORMULA_RECALL','suspect_glyphs':len(suspect),
            'covered_suspect_glyphs':len(suspect&covered),'uncovered_suspect_glyph_keys':uncovered,
            'unmapped_source_rows':len(errors),'source_glyphs':len(glyphs),
            'complete_formula_recall_established':False}
