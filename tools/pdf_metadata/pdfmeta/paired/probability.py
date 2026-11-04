"""Small source-geometry guard for P(event), overlines and conditional bars."""
from collections import Counter
import re

from ..math_value import expression
from ..text_cleanup import normalize_block


def character(g):
    text, quality = normalize_block({'text_raw': g['text'], 'glyphs': [g]})
    return text if not quality['unresolved_glyph_count'] and len(text) == 1 else None


def glyphs(page, bbox, allowed=None):
    result = []
    for block in page['blocks']:
        if allowed is not None and block['block_id'] not in allowed:
            continue
        for i, g in enumerate(block.get('glyphs', [])):
            x0, y0, x1, y1 = g['bbox']
            if bbox[0] <= (x0+x1)/2 <= bbox[2] and bbox[1] <= (y0+y1)/2 <= bbox[3]:
                result.append({**g, 'char': character(g), 'key': block['block_id']+':'+str(i), 'block_id': block['block_id']})
    return result


def native_events(page, bbox, allowed=None):
    gs = glyphs(page, bbox, allowed); atoms = []; rejected = []
    for p in sorted((g for g in gs if g['char'] == 'P'), key=lambda g: (g['bbox'][1], g['bbox'][0])):
        size = p['size']; cy = (p['bbox'][1]+p['bbox'][3])/2
        row = sorted([g for g in gs if abs((g['bbox'][1]+g['bbox'][3])/2-cy) < size*.55], key=lambda g:g['bbox'][0])
        opening = next((g for g in row if g['char'] == '(' and 0 <= g['bbox'][0]-p['bbox'][2] < size*.7), None)
        if opening is None:
            continue
        closing = next((g for g in row if g['char'] == ')' and g['bbox'][0] > opening['bbox'][2]), None)
        if closing is None:
            rejected.append('PROBABILITY_PARENTHESIS_UNRESOLVED'); continue
        inside = [g for g in row if opening['bbox'][2] <= (g['bbox'][0]+g['bbox'][2])/2 < closing['bbox'][0]]
        if not inside or any(g['char'] is None or not re.fullmatch(r'[A-Z|∣∩∪]', g['char']) for g in inside):
            rejected.append('EVENT_GRAMMAR_UNSUPPORTED'); continue
        letters = [g for g in inside if g['char'].isalpha()]
        tokens = [[g['bbox'][0], g['char'].replace('∣','|').replace('∩','').replace('∪','U')] for g in inside]
        bars = []; consumed = set()
        for vector in page.get('vectors', []):
            x0,y0,x1,y1 = vector['bbox']
            if vector['kind'] != 'line': continue
            covered = [g for g in letters if x0-.7 <= (g['bbox'][0]+g['bbox'][2])/2 <= x1+.7
                and -size*.6 <= y0-g['bbox'][1] <= 1.2]
            if y1-y0 < .4 and size*.2 < x1-x0 < size*3 and covered:
                keys = {g['key'] for g in covered}
                if consumed & keys: continue
                indices = [i for i,g in enumerate(inside) if g['key'] in keys]
                tokens[indices[0]][1] = '!'+('(' if len(indices)>1 else '')+tokens[indices[0]][1]
                if len(indices)>1: tokens[indices[-1]][1] += ')'
                consumed |= keys; bars.append(vector['bbox'])
            if x1-x0 < .4 and y1-y0 > size*.65 and y0 <= p['bbox'][1]+1 and y1 >= p['bbox'][3]-3:
                if opening['bbox'][2] < x0 < closing['bbox'][0] and not any(t == '|' for _,t in tokens):
                    if any(g['bbox'][2] <= x0+.5 for g in letters) and any(g['bbox'][0] >= x0-.5 for g in letters):
                        tokens.append([x0,'|']); bars.append(vector['bbox'])
        event = ''.join(t for _,t in sorted(tokens))
        atoms.append({'canonical': 'P('+event+')', 'bbox': [p['bbox'][0], min(p['bbox'][1], opening['bbox'][1]), closing['bbox'][2], max(p['bbox'][3], closing['bbox'][3])],
            'glyph_keys': [p['key'], opening['key'], *[g['key'] for g in inside], closing['key']], 'vector_bboxes': bars})
    return atoms, rejected


def latex_events(latex):
    if not isinstance(latex, str) or len(latex) > 4000:
        raise ValueError('FORMULA_LENGTH_LIMIT')
    s = re.sub(r'\\(?:mathrm|operatorname)\{P\}', 'P', latex)
    s = re.sub(r'\\(?:left|right|quad|qquad)\b|\\[,!;]', '', s)
    s = re.sub(r'\\(?:bar|overline)\s*\{([A-Z])\}', r'!\1', s)
    s = re.sub(r'\\(?:bar|overline)\s*([A-Z])', r'!\1', s)
    s = s.replace(r'\mid','|').replace(r'\vert','|').replace(r'\cap','').replace(r'\cup','U')
    s = re.sub(r'\s+', '', s)
    found = re.findall(r'P\(([A-Z!|]+)\)', s)
    if s.count('P(') != len(found):
        raise ValueError('MODEL_EVENT_GRAMMAR_UNSUPPORTED')
    return ['P('+v+')' for v in found]


def event_guard(latex, atoms, rejected):
    if rejected:
        return 'SOURCE_EVENT_GRAMMAR_UNSUPPORTED'
    try: parsed = latex_events(latex)
    except ValueError: return 'MODEL_EVENT_GRAMMAR_UNSUPPORTED'
    if not atoms and not parsed:
        return 'NO_EVENT_SYMBOLS_TO_COMPARE'
    if Counter(parsed) != Counter(a['canonical'] for a in atoms):
        return 'SOURCE_EVENT_SYMBOL_CONFLICT'
    return 'EVENT_SYMBOLS_AGREE_NOT_SOURCE_APPROVAL'


def endpoint(latex):
    """Last numeric endpoint only; never claim a complete multipart answer."""
    if not isinstance(latex, str) or len(latex)>4000: raise ValueError('FORMULA_LENGTH_LIMIT')
    tail = re.split(r'=|\\approx|\\simeq|≈|≃', latex)[-1].strip().strip('$')
    tail = re.sub(r'\\(?:text|mathrm)\{(?:lần|lan)\}', '', tail).strip()
    tail = tail.replace(r'\%', '%').replace(r'\dfrac', r'\frac').replace(r'\tfrac', r'\frac')
    tail = re.sub(r'[.;\s]+$', '', tail)
    if len(tail)>120 or any(len(n)>18 for n in re.findall(r'\d+',tail)): raise ValueError('NUMERIC_ENDPOINT_LIMIT')
    percent = tail.endswith('%'); value = expression(tail[:-1] if percent else tail)
    if value.free_symbols or value.is_real is not True or value.is_finite is not True: raise ValueError('NUMERIC_ENDPOINT_UNSUPPORTED')
    if percent: value /= 100
    return {'latex': tail, 'canonical_value': str(value), 'percent': percent,
        'scope': 'LAST_NUMERIC_ENDPOINT_ONLY_NOT_COMPLETE_MULTIPART_ANSWER', 'status': 'SOURCE_READING_CANDIDATE_NOT_GRADING_REFERENCE'}
