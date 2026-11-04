"""Bounded, source-grounded LaTeX trial for selected paired-corpus records.

The fast PDFium text is never an input to formula recognition. Reopen original
pages with actual font names, locate anchored math regions, and read their image
crops with a local model. Outputs are partial candidates, never approved content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from statistics import median

from ..native import box
from ..native_math import LHS, PROSE_WORD, recover_slice
from ..safe_math import UnsupportedMath, assignment, equivalent
from ..storage import configure_storage, file_hash, inference_versions, read_json, write_json
from ..text_cleanup import normalize_block


VERSION = 'paired-source-formula-trial/v1'
OPTIONS = re.compile(r'(?<![A-Za-z])[ABCD]\.')
ANCHOR = re.compile(LHS.pattern + '|∫')


def aligned(block):
    text, quality = normalize_block(block)
    if quality['unresolved_glyph_count']:
        raise UnsupportedMath('UNMAPPED_SOURCE_FONT')
    result, cursor = [], 0
    for index, glyph in enumerate(block['glyphs']):
        char = normalize_block({'text_raw': glyph['text'], 'glyphs': [glyph]})[0]
        at = text.find(char, cursor)
        if len(char) != 1 or at < 0:
            raise UnsupportedMath('SOURCE_GLYPH_ALIGNMENT_AMBIGUOUS')
        result.append({**glyph, 'text': char, 'offset': at,
                       'key': block['block_id'] + ':' + str(index)})
        cursor = at + 1
    return text, result


def bounds(glyphs):
    return [min(g['bbox'][0] for g in glyphs), min(g['bbox'][1] for g in glyphs),
            max(g['bbox'][2] for g in glyphs), max(g['bbox'][3] for g in glyphs)]


def center(glyph):
    b = glyph['bbox']
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def within(glyph, bbox):
    x, y = center(glyph)
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def choice_labels(text, glyphs):
    # A final integration constant C. is not the start of option C.
    return [m for m in OPTIONS.finditer(text)
            if m.start() < 3 or any(g['offset'] == m.start() and 'bold' in g['font'].lower()
                                   for g in glyphs)]


def regions(page, span):
    """Find conservative assignment/integral anchors; do not claim full coverage.

    Floating numerator/denominator glyphs belong to the nearest anchored/prose
    row vertically, inside the formula's horizontal extent. A separate column,
    choice or question cannot contribute glyphs to that region.
    """
    rows, rejected = [], []
    for block in page['blocks']:
        if not any(within(g, span['bbox']) for g in block['glyphs']):
            continue
        try:
            text, glyphs = aligned(block)
        except UnsupportedMath as error:
            rejected.append({'block_id': block['block_id'], 'reason': str(error)})
            continue
        glyphs = [g for g in glyphs if within(g, span['bbox'])]
        if not glyphs:
            continue
        # Never use the same-line text from an adjacent column as an anchor.
        valid_offsets = {g['offset'] for g in glyphs}
        matches = [m for m in ANCHOR.finditer(text) if m.start() in valid_offsets]
        labels = choice_labels(text, glyphs)
        rows.append({'block': block, 'text': text, 'glyphs': glyphs, 'matches': matches, 'labels': labels,
                     'main': bool(matches or PROSE_WORD.search(text) or labels)})
    anchors = []
    for row in rows:
        text, glyphs = row['text'], row['glyphs']
        previous_end = -1
        for match in row['matches']:
            if match.start() < previous_end:
                continue  # Integral chains stay one region.
            next_choice = next((m for m in row['labels'] if m.start() >= match.end()), None)
            prose = PROSE_WORD.search(text, match.end())
            end = min([m.start() for m in [next_choice, prose] if m] + [len(text)])
            while end > match.start() and text[end - 1] in ' .;,':
                end -= 1
            local = [g for g in glyphs if match.start() <= g['offset'] < end]
            if not local:
                continue
            normal_size = median(g['size'] for g in local)
            regular = [g for g in local if normal_size * .82 <= g['size'] <= normal_size * 1.2]
            y = median(center(g)[1] for g in (regular or local))
            labels = [m for m in row['labels'] if m.start() < match.start()]
            label = labels[-1][0].rstrip('.') if labels else None
            anchors.append({'row': row, 'local': local, 'y': y, 'size': normal_size,
                            'start': match.start(), 'end': end, 'label': label})
            previous_end = end
    result, used = [], set()
    for a in anchors:
        local = list(a['local']); b = bounds(local)
        # Do not cross another main row, even if it contains only prose.
        main_y = [other['y'] for other in anchors if abs(other['y'] - a['y']) > 2]
        for row in rows:
            if row['main'] and not row['matches']:
                main_y.append(median(center(g)[1] for g in row['glyphs']))
        lo = max([y for y in main_y if y < a['y']] + [a['y'] - 4 * a['size']])
        hi = min([y for y in main_y if y > a['y']] + [a['y'] + 4 * a['size']])
        for row in rows:
            if row['main']:
                continue
            for g in row['glyphs']:
                x, y = center(g)
                if b[0] - 1 <= x <= b[2] + 1 and (lo + a['y']) / 2 < y < (hi + a['y']) / 2:
                    local.append(g)
        keys = {g['key'] for g in local}
        if keys & used:
            rejected.append({'block_id': a['row']['block']['block_id'], 'reason': 'REGION_GLYPH_OWNERSHIP_CONFLICT'})
            continue
        used |= keys
        native, reason = None, None
        try:
            if len(local) != len(a['local']):
                raise UnsupportedMath('MULTILINE_FORMULA_REQUIRES_IMAGE_READING')
            original = a['row']['block']
            selected = [g for i, g in enumerate(original['glyphs'])
                        if original['block_id'] + ':' + str(i) in keys]
            local_block = {**original, 'text_raw': original['text_raw'][a['start']:a['end']], 'glyphs': selected}
            native = recover_slice(local_block, 0, len(local_block['text_raw']), page['vectors'])[0]
        except (UnsupportedMath, ValueError, TypeError) as error:
            reason = str(error)
        result.append({'label': a['label'], 'bbox': bounds(local),
                       'source_block_id': a['row']['block']['block_id'],
                       'source_glyph_keys': sorted(keys), 'native_candidate': native,
                       'native_rejection': reason})
    return result, rejected


def extract_page(page, page_number, digest):
    blocks = []
    for i, line in enumerate(page.extract_text_lines(x_tolerance=2, y_tolerance=3, return_chars=True)):
        blocks.append({'block_id': f'p{page_number:04}-font-l{i:04}', 'bbox': box(line),
                       'text_raw': line['text'], 'glyphs': [
                           {'text': c['text'], 'bbox': box(c), 'font': c['fontname'], 'size': float(c['size'])}
                           for c in line['chars']]})
    return {'page_number': page_number, 'source_sha256': digest, 'width': page.width,
            'height': page.height, 'blocks': blocks,
            'vectors': [{'kind': kind, 'bbox': box(v)}
                        for kind, values in [('line', page.lines), ('rect', page.rects), ('curve', page.curves)]
                        for v in values]}


def latex_tokens(text):
    """Compare notation only; never call equivalence a proof of source accuracy."""
    text = text.strip().strip('$').rstrip(' .;,')
    text = text.replace('−', '-').replace('∫', r'\int ')
    text = re.sub(r'\\(?:left|right)\b', '', text)
    text = re.sub(r'\\(?:mathrm|operatorname)\{d\}', 'd', text)
    text = re.sub(r'\\[,!;]', '', text)
    return re.sub(r'\s+', '', text)


def compare(native, ocr):
    if not ocr.strip():
        return 'EMPTY_MODEL_OUTPUT'
    if not native:
        return 'OCR_ONLY_REQUIRES_SOURCE_CHECK'
    if latex_tokens(native) == latex_tokens(ocr):
        return 'NATIVE_OCR_NOTATION_AGREEMENT'
    try:
        a, b = assignment(native.rstrip(' .')), assignment(ocr.rstrip(' .'))
        if equivalent(a, b):
            return 'EQUIVALENT_SUPPORTED_EXPRESSION_REQUIRES_SOURCE_CHECK'
        return 'NATIVE_OCR_CONFLICT'
    except (UnsupportedMath, ValueError, TypeError, NotImplementedError):
        return 'UNSUPPORTED_COMPARISON_REQUIRES_SOURCE_CHECK'


class FormulaReader:
    def __init__(self, runtime, output, model):
        self.runtime, self.output, self.name = Path(runtime), Path(output), model
        self.weights = self.runtime / 'paddlex/official_models' / model / 'inference.pdiparams'
        if not self.weights.is_file():
            raise FileNotFoundError('LOCAL_FORMULA_WEIGHTS_REQUIRED: ' + str(self.weights))
        self.identity = {'adapter': VERSION, 'adapter_sha256': file_hash(Path(__file__)),
                         'model': model, 'weights_sha256': file_hash(self.weights),
                         'packages': inference_versions(), 'device': 'cpu', 'threads': 3, 'mkldnn': False}
        self.instance = None
        self.calls = self.hits = 0

    def read(self, image, *, use_cache=True):
        identity = {**self.identity, 'image_sha256': file_hash(image)}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        target = self.output / 'ocr-cache' / (key + '.json')
        if use_cache and target.is_file() and read_json(target).get('identity') == identity:
            self.hits += 1
            return read_json(target)['latex']
        if self.instance is None:
            from paddleocr import FormulaRecognition
            self.instance = FormulaRecognition(model_name=self.name, model_dir=str(self.weights.parent),
                                               device='cpu', cpu_threads=3, enable_mkldnn=False)
        raw = list(self.instance.predict(str(image), batch_size=1))[0].json
        latex = raw.get('res', raw).get('rec_formula', '')
        if not isinstance(latex, str) or len(latex) > 4000:
            raise ValueError('INVALID_FORMULA_MODEL_OUTPUT')
        write_json(target, {'identity': identity, 'latex': latex, 'raw_result': raw})
        self.calls += 1
        return latex


def run(source, plan, output, runtime, numbers, *, model='PP-FormulaNet_plus-M', katex=None):
    import pdfplumber
    from contextlib import ExitStack
    source, output = Path(source).resolve(), Path(output).resolve()
    if not numbers or len(set(numbers)) > 40:
        raise ValueError('SELECT_1_TO_40_RECORDS_FOR_THIS_TRIAL')
    if output == source.parent:
        raise ValueError('SEPARATE_OUTPUT_DIRECTORY_REQUIRED')
    output.mkdir(parents=True, exist_ok=True)
    configure_storage(Path(runtime))
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
    if os.name == 'nt':
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    before = file_hash(source)
    chosen = [q for line in source.read_text(encoding='utf-8-sig').splitlines() if line.strip()
              if (q := json.loads(line)).get('collection_number') in numbers]
    if {q['collection_number'] for q in chosen} != set(numbers):
        raise ValueError('REQUESTED_COLLECTION_NUMBER_NOT_FOUND')
    documents = {d['sha256']: Path(d['path']) for d in read_json(Path(plan))['documents']}
    reader = FormulaReader(runtime, output, model)
    records, pages = [], {}
    with ExitStack() as stack:
        opened = {}
        for q in chosen:
            digest = q['source']['sha256']; path = documents[digest]
            if digest not in opened:
                if file_hash(path) != digest:
                    raise ValueError('ORIGINAL_PDF_HASH_MISMATCH')
                opened[digest] = stack.enter_context(pdfplumber.open(path))
            formulas, rejected = [], []
            for role in ['question', 'solution']:
                for si, span in enumerate(q[role]['source_spans']):
                    number = span['page_number']; key = (digest, number)
                    raw = opened[digest].pages[number - 1]
                    if key not in pages:
                        pages[key] = extract_page(raw, number, digest)
                        write_json(output / 'font-pages' / digest[:24] / f'p{number:04}.json', pages[key])
                    found, failures = regions(pages[key], span)
                    rejected.extend(dict(role=role, page_number=number, **r) for r in failures)
                    for fi, region in enumerate(found):
                        asset = f"assets/q{q['collection_number']:04}-{role}-{si:02}-{fi:02}.png"
                        b = region['bbox']; clip = span['bbox']
                        crop = [max(clip[0], b[0] - 1), max(clip[1], b[1] - 1),
                                min(clip[2], b[2] + 1), min(clip[3], b[3] + 1)]
                        (output / 'assets').mkdir(exist_ok=True)
                        raw.crop(tuple(crop)).to_image(resolution=288).save(output / asset)
                        candidate = reader.read(output / asset)
                        formulas.append({**region, 'role': role, 'page_number': number, 'crop_bbox': crop,
                                         'asset_path': asset, 'asset_sha256': file_hash(output / asset),
                                         'latex_candidate': candidate, 'comparison': compare(region['native_candidate'], candidate),
                                         'status': 'INFERRED_NOT_ACADEMICALLY_REVIEWED'})
            record = {'question_id': q['question_id'], 'collection_number': q['collection_number'],
                      'source_label': q['source_label'], 'chapter_title': q['chapter_title'], 'source': q['source'],
                      'coverage': 'PARTIAL_ANCHORED_FORMULAS_ONLY', 'formula_candidates': formulas,
                      'rejected_regions': rejected, 'academic_review': 'PENDING',
                      'grading_support': 'NOT_ASSESSED', 'publishable': False}
            records.append(record)
            print(f"Mục {q['collection_number']}: {len(formulas)} formula candidates", flush=True)
    if file_hash(source) != before:
        raise ValueError('CANONICAL_METADATA_CHANGED_DURING_RECOVERY')
    write_json(output / 'formula-candidates.json', {'schema_version': VERSION,
        'source_jsonl_sha256': before, 'model_identity': reader.identity, 'questions': records})
    if katex:
        katex = Path(katex)
        if not (katex / 'katex.min.js').is_file():
            raise ValueError('LOCAL_KATEX_DIST_REQUIRED')
        (output / 'vendor').mkdir(exist_ok=True)
        for name in ['katex.min.js', 'katex.min.css', 'LICENSE']:
            if (katex / name).is_file():shutil.copy2(katex / name, output / 'vendor' / name)
        shutil.copytree(katex / 'fonts', output / 'vendor/fonts', dirs_exist_ok=True)
        shutil.copy2(Path(__file__).with_name('math_recovery.html'), output / 'review.html')
    report = {'schema_version': VERSION, 'questions': len(records), 'formula_candidates': sum(len(q['formula_candidates']) for q in records),
              'source_jsonl_sha256': before, 'canonical_modified': False, 'model_calls': reader.calls,
              'cache_hits': reader.hits, 'cloud_calls': 0, 'coverage': 'PARTIAL_ANCHORED_FORMULAS_ONLY',
              'academic_review': 'PENDING', 'publishable': False,
              'adapter_sha256': reader.identity['adapter_sha256'],
              'candidates_sha256': file_hash(output / 'formula-candidates.json')}
    write_json(output / 'report.json', report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['input', 'plan', 'output', 'runtime']:p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--numbers', type=int, nargs='+', required=True)
    p.add_argument('--model', choices=['PP-FormulaNet_plus-S', 'PP-FormulaNet_plus-M'], default='PP-FormulaNet_plus-M')
    p.add_argument('--katex', type=Path)
    a = p.parse_args()
    print(json.dumps(run(a.input, a.plan, a.output, a.runtime, a.numbers, model=a.model, katex=a.katex), ensure_ascii=False, indent=2))
