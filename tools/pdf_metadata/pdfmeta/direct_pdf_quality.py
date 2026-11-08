"""Validate LaTeX and confirm ambiguous relation symbols against source pixels."""
import io
import hashlib
import base64
import json
from pathlib import Path
import re
import shutil
import subprocess
import uuid

from .storage import file_hash, read_json, write_json
from .math_display import prepare as prepare_display, CODE_SHA256 as DISPLAY_CODE_SHA256

VERSION = 'source-latex-quality/v1'
# Pin the loaded validator's identity before a checkout can replace its source.
_CODE_SHA256 = file_hash(Path(__file__))
RELATION = re.compile(r'\\(?:Leftrightarrow|Rightarrow|Leftarrow|leftrightarrow|rightarrow|leftarrow|rightleftharpoons|leftrightharpoons|triangleq|doteq)\b|[⇔⇒⇐↔→←⇌≜≐]')
AMBIGUOUS = re.compile(r'\\(?:rightleftharpoons|leftrightharpoons|triangleq|doteq)\b|[⇌≜≐]')
MATH = re.compile(r'(?<!\\)(\$\$|\$)([\s\S]*?)(?<!\\)\1')
KATEX = Path(__file__).parents[3] / 'frontend/node_modules/katex/dist/katex.js'
VALIDATOR = r'''
const fs=require('fs'),katex=require(process.argv[1]);
const math=JSON.parse(fs.readFileSync(0,'utf8'));
const failures=[];
for(let i=0;i<math.length;i++){
 try{katex.renderToString(math[i],{throwOnError:true,trust:false,
  strict:code=>code==='unknownSymbol'?'ignore':'error',maxExpand:100,maxSize:20});}
 catch(e){failures.push({index:i,error:e.message});}
}
process.stdout.write(JSON.stringify(failures));
'''
RETRY_PROMPT = (
    'Transcribe exactly the visible Vietnamese source crop. Do not solve, correct, '
    'summarize or omit text. Return JSON with markdown and uncertain. '
    'Write valid LaTeX inside $ delimiters. Keep numbers, signs and words exactly. '
    'Preserve arrow shapes: equivalence ⇔, implication ⇒, a single arrow →, opposed harpoons ⇌. '
    'Prefer these Unicode arrow characters inside math to avoid JSON backslash escapes. '
    'Every LaTeX backslash in a JSON string must be escaped as two backslashes. '
    'Do not invent image links or missing content. Mark uncertain if unreadable.')


def signature(value):
    value = RELATION.sub(' RELATION ', value)
    value = re.sub(r'\\(?:left|right|text|mathrm|mathit|operatorname)\b', '', value)
    value = value.replace(r'\tfrac', r'\frac')
    return re.findall(r'\\[A-Za-z]+|\w+|[^\w\s$]', value, flags=re.UNICODE)


def relation_kinds(value):
    aliases = {r'\Leftrightarrow': '⇔', r'\Rightarrow': '⇒', r'\Leftarrow': '⇐',
               r'\leftrightarrow': '↔', r'\rightarrow': '→', r'\leftarrow': '←',
               r'\rightleftharpoons': '⇌'}
    return [aliases.get(m[0], m[0]) for m in RELATION.finditer(value)]


def equivalent_arrows(image_bytes):
    """Only intact double-headed, double-stroke closed glyphs are accepted."""
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError:
        return []
    with Image.open(io.BytesIO(image_bytes)) as image:
        ink = (np.asarray(image.convert('L')) < 160).astype('uint8')
    _, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    arrows = []
    for label, (x, y, width, height, count) in enumerate(stats[1:], 1):
        x, y, width, height = map(int, (x, y, width, height))
        if height < 8 or not 1.55 <= width / height <= 3.5:
            continue
        component = (labels[y:y + height, x:x + width] == label).astype('uint8')
        contours, hierarchy = cv2.findContours(component * 255, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        holes = [cv2.contourArea(contours[i]) for i, h in enumerate(hierarchy[0]) if h[3] >= 0] if hierarchy is not None else []
        if len(holes) != 1 or not .15 < holes[0] / (width * height) < .65:
            continue
        length = max(3, round(.55 * width))
        horizontal = np.array([np.convolve(row, np.ones(length, dtype=int), mode='valid').max() >= length
                               for row in component])
        if not horizontal[:max(1, round(.4 * height))].any() or not horizontal[round(.6 * height):].any():
            continue
        left, right = np.flatnonzero(component[:, 0]), np.flatnonzero(component[:, -1])
        if not all(len(tip) and .3 <= tip.mean() / height <= .7
                   and (tip[-1] - tip[0] + 1) <= .4 * height for tip in [left, right]):
            continue
        arrows.append({'kind': 'EQUIVALENT', 'bbox': [x, y, x + width, y + height],
                       'inner_hole_fraction': holes[0] / (width * height)})
    lines = []
    for arrow in sorted(arrows, key=lambda a: a['bbox'][1]):
        if lines and abs(arrow['bbox'][1] - lines[-1][0]['bbox'][1]) < .6 * (arrow['bbox'][3] - arrow['bbox'][1]):
            lines[-1].append(arrow)
        else:
            lines.append([arrow])
    return [a for line in lines for a in sorted(line, key=lambda a: a['bbox'][0])]


def validate(markdown):
    prepared = prepare_display(markdown)
    math = [t['latex'] for t in prepared['tokens'] if t['kind']=='math']
    issues = [{'kind': code} for code in prepared['issues']]
    if 'EXPLICIT_EQUATION_DELIMITED' in prepared['repairs']:
        issues.append({'kind': 'MATH_DELIMITERS_MISSING'})
    if any(code in prepared['repairs'] for code in ['ESCAPED_CLOSING_MATH_DELIMITER_FIXED','MISSING_CLOSING_MATH_DELIMITER_ADDED']):
        issues.append({'kind': 'MATH_DELIMITERS_REPAIRED_FOR_DISPLAY'})
    if any(re.search(r'[\x00-\x08\x0b-\x1f]', expression) for expression in math):
        issues.append({'kind': 'MATH_CONTROL_CHARACTER'})
    if any('\n' in m[2] for m in MATH.finditer(markdown) if m[1] == '$'):
        issues.append({'kind': 'INLINE_MATH_LINE_BREAK'})
    if not math:
        return issues
    if not shutil.which('node') or not KATEX.is_file():
        return issues + [{'kind': 'LATEX_VALIDATION_UNAVAILABLE'}]
    try:
        result = subprocess.run(['node', '-e', VALIDATOR, str(KATEX)],
                                input=json.dumps(math), text=True, encoding='utf-8', capture_output=True,
                                timeout=15, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result.check_returncode()
        issues.extend(dict(kind='LATEX_RENDER_ERROR', **issue) for issue in json.loads(result.stdout))
    except (OSError, ValueError, subprocess.SubprocessError):
        issues.append({'kind': 'LATEX_VALIDATION_UNAVAILABLE'})
    return issues


def review(markdown, image_bytes, binding, output, generate=None):
    identity = hashlib.sha256(json.dumps({
        'version': VERSION, 'binding': binding, 'image': hashlib.sha256(image_bytes).hexdigest(),
        'markdown': markdown, 'code': _CODE_SHA256, 'display_code': DISPLAY_CODE_SHA256,
        'katex': file_hash(KATEX) if KATEX.is_file() else None}, sort_keys=True).encode()).hexdigest()
    path = output / 'quality' / (identity + '.json')
    if path.exists():
        try:
            cached = read_json(path)
            if (cached.get('identity') == identity and not cached.get('errors')
                    and (generate is None or cached.get('status') == 'FORMAT_VALIDATED' or cached.get('response') is not None)):
                return cached
        except (ValueError, OSError):
            pass
    original = markdown
    display = prepare_display(markdown)
    markdown = display['markdown']
    evidence, flags = [], list(display['repairs'])
    spans = list(MATH.finditer(markdown))
    relation_count = sum(len(RELATION.findall(m[2])) for m in spans)
    if any(AMBIGUOUS.search(m[2]) for m in spans):
        evidence = equivalent_arrows(image_bytes)
        # All printed relations must be accounted for. Never globally replace
        # harpoons: mixed/uncertain source relations require another source read.
        if evidence and len(evidence) == relation_count:
            for match in reversed(spans):
                repaired = AMBIGUOUS.sub(lambda m: r'\Leftrightarrow', match[2])
                markdown = markdown[:match.start(2)] + repaired + markdown[match.end(2):]
            flags.append('RELATION_SYMBOL_SOURCE_GEOMETRY_VERIFIED')
        else:
            flags.append('RELATION_SYMBOL_SOURCE_REVIEW_REQUIRED')
    issues = validate(markdown)
    response, errors = None, []
    requires_retry = ('RELATION_SYMBOL_SOURCE_REVIEW_REQUIRED' in flags
                      or any(i['kind'] != 'LATEX_VALIDATION_UNAVAILABLE' for i in issues))
    if generate is not None and requires_retry:
        schema = {'type': 'object', 'additionalProperties': False, 'required': ['markdown', 'uncertain'],
                  'properties': {'markdown': {'type': 'string'}, 'uncertain': {'type': 'boolean'}}}
        response = generate([
            {'text': 'Read this source crop again, preserving every word and mathematical sign. Ensure math renders.'},
            {'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(image_bytes).decode('ascii')}}
        ], schema, RETRY_PROMPT, identity)
        if response.get('status') == 'RESPONSE_RECEIVED':
            from .direct_pdf_ocr import clean_markdown
            candidate = response.get('result', {}).get('markdown')
            if isinstance(candidate, str) and candidate.strip():
                candidate, repaired_flags = clean_markdown(candidate)
                candidate_issues = validate(candidate)
                if (not candidate_issues and signature(candidate) == signature(markdown)
                        and relation_kinds(candidate) == relation_kinds(markdown)
                        and not AMBIGUOUS.search(candidate)):
                    markdown, issues = candidate, []
                    flags = [f for f in flags if f != 'RELATION_SYMBOL_SOURCE_REVIEW_REQUIRED']
                    flags.extend(['SOURCE_FORMAT_RETRY_ACCEPTED', *repaired_flags])
                else:
                    flags.append('SOURCE_FORMAT_RETRY_REQUIRES_REVIEW')
        elif response.get('status') in {'LOCAL_REQUEST_ERROR', 'QUALITY_RETRY_BUDGET_REACHED'}:
            errors.append(response['status'])
    flags.extend(dict.fromkeys(i['kind'] for i in issues))
    result = {'version': VERSION, 'identity': identity, 'markdown': markdown, 'original_markdown': original,
              'flags': flags, 'issues': issues, 'errors': errors, 'response': response,
              'relation_evidence': evidence,
              'status': 'REVIEW_REQUIRED' if issues or 'RELATION_SYMBOL_SOURCE_REVIEW_REQUIRED' in flags else 'FORMAT_VALIDATED',
              'audit': str(path.relative_to(output)).replace('\\', '/')}
    if path.exists():
        try:
            previous = read_json(path)
            if previous != result:
                write_json(path.parent/'history'/(identity+'-'+uuid.uuid4().hex+'.json'), previous)
        except (OSError, ValueError):
            pass
    write_json(path, result)
    return result
