"""Read-only JPEG auditing, train-only vocabulary fitting, model-time preprocessing."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageOps

DEFAULT_DATA = '/kaggle/input/datasets/lhngphc/data-finetune-comer'
TOKEN = re.compile(r'\\[A-Za-z]+|\\.|[^\s]')
EXPECTED = {'train': 400, 'validation': 50, 'test': 50}
PREPROCESS = 'jpeg-gray-invert-aspect128x1024-min32-pad32-v1'


def tokens(text):
    # Preserve stored LaTeX verbatim. This alias is applied only to model tokens.
    return TOKEN.findall(text.replace("'", r'\prime'))


def safe_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError('IMAGE_PATH_ESCAPE')
    return path


def resolve_metadata(requested=DEFAULT_DATA, search_root='/kaggle/input'):
    requested = Path(requested)
    if requested.is_file() and requested.name == 'metadata.json':
        return requested.resolve()
    found = sorted(requested.rglob('metadata.json')) if requested.is_dir() else []
    if not found and Path(search_root).is_dir():
        # Kaggle currently exposes both /input/<slug> and /input/datasets/<owner>/<slug>.
        candidates = sorted(Path(search_root).rglob('metadata.json'))
        found = [p for p in candidates if 'data-finetune-comer' in str(p).lower()
                 or p.parent.name == 'CoachLearning_500_HME100K']
    if len(found) != 1:
        raise ValueError(f'Expected one HME500 metadata.json, found {len(found)}. '
                         'Set --data to its exact path. Candidates: ' + str([str(p) for p in found]))
    return found[0].resolve()


def infer_group(label):
    if re.search(r'\\(?:int|sum|lim|partial|prime)\b', label): return 'Giải tích'
    if re.search(r'\\(?:sin|cos|tan|cot|sec|csc)\b', label): return 'Lượng giác'
    if r'\sqrt' in label: return 'Căn thức'
    if r'\frac' in label: return 'Phân số'
    if '^' in label: return 'Lũy thừa'
    return 'Cơ bản'


def audit(metadata):
    metadata = Path(metadata).resolve()
    source = json.loads(metadata.read_text(encoding='utf-8'))
    if not isinstance(source, list) or len(source) != 500:
        raise ValueError('EXPECTED_500_METADATA_ROWS')
    seen = {k: set() for k in ('id', 'original_id', 'bytes', 'pixels', 'label')}
    rows = []
    for item in source:
        r = dict(item)
        for key in ('id', 'image_path', 'latex', 'split', 'source', 'original_id'):
            if not isinstance(r.get(key), str) or not r[key].strip():
                raise ValueError('MISSING_FIELD: ' + key)
        if r['split'] not in EXPECTED: raise ValueError('INVALID_SPLIT')
        p = safe_path(metadata.parent, r['image_path'])
        if p.suffix.lower() not in ('.jpg', '.jpeg'): raise ValueError('EXPECTED_ORIGINAL_JPEG')
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        with Image.open(p) as im:
            if im.format != 'JPEG': raise ValueError('EXPECTED_ORIGINAL_JPEG')
            im.load()  # decode every file in full, not just the JPEG header
            width, height = im.size
            rgb = im.convert('RGB')
            pixels = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
            gray = np.asarray(im.convert('L'))
            if min(width, height) < 8 or np.std(gray) < 2:
                raise ValueError('EMPTY_OR_UNUSABLE_IMAGE: ' + r['id'])
        ts = tokens(r['latex'])
        if not ts or len(ts) > 180: raise ValueError('INVALID_LABEL_LENGTH: ' + r['id'])
        if ts.count('{') != ts.count('}'): raise ValueError('UNBALANCED_LABEL: ' + r['id'])
        for key, value in (('id', r['id']), ('original_id', r['original_id']),
                           ('bytes', digest), ('pixels', pixels), ('label', ''.join(ts))):
            if value in seen[key]: raise ValueError('DUPLICATE_' + key.upper() + ': ' + r['id'])
            seen[key].add(value)
        r.update(_image=p, _words=ts, image_sha256=digest, pixel_sha256=pixels,
                 width=width, height=height, group=r.get('group') or infer_group(r['latex']))
        rows.append(r)
    counts = dict(Counter(r['split'] for r in rows))
    if counts != EXPECTED: raise ValueError('INVALID_SPLIT_COUNTS: ' + str(counts))
    paired = [{k: r[k] for k in ('id', 'original_id', 'image_path', 'latex', 'split',
                                'source', 'image_sha256', 'pixel_sha256')} for r in sorted(rows, key=lambda r:r['id'])]
    fingerprint = hashlib.sha256(json.dumps(paired, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    report = {'samples': len(rows), 'splits': counts, 'fingerprint': fingerprint,
              'metadata_sha256': hashlib.sha256(metadata.read_bytes()).hexdigest(),
              'groups': {s: dict(Counter(r['group'] for r in rows if r['split'] == s)) for s in EXPECTED},
              'jpeg_decoded': len(rows), 'duplicate_bytes': 0, 'duplicate_pixels': 0,
              'duplicate_token_labels': 0, 'preprocess': PREPROCESS,
              'writer_split_claim': 'Unknown: HME metadata does not provide writer IDs.',
              'label_audit': 'Nonempty/token syntax/brace checks; no automatic proof of image-label agreement.',
              'selection_scope': 'Curated 500 sample subset; scores do not estimate all HME100K handwriting.'}
    return rows, report


def fit_vocabulary(rows, base):
    words = sorted({t for r in rows if r['split'] == 'train' for t in r['_words']} - set(base))
    vocab = dict(base)
    for t in words: vocab[t] = len(vocab)
    unseen = {s: sorted({t for r in rows if r['split'] == s for t in r['_words']} - set(vocab))
              for s in ('validation', 'test')}
    if any(unseen.values()):
        raise ValueError('HELDOUT_UNKNOWN_TOKENS: ' + json.dumps(unseen) +
                         '. Supply a fixed external vocabulary; do not silently drop samples or map tokens to PAD.')
    for r in rows: r['_tokens'] = [vocab[t] for t in r['_words']]
    return vocab, words


def input_array(row):
    # In-memory model tensor only. The original JPEG and W&B gallery remain untouched.
    with Image.open(row['_image']) as image:
        image = ImageOps.invert(image.convert('L'))
        w, h = image.size
        scale = min(128 / h, 1024 / w, max(1., 32 / h))
        size = (max(1, round(w * scale)), max(1, round(h * scale)))
        if size != image.size: image = image.resize(size, Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.float32) / 255.


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', default=DEFAULT_DATA)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    _, report = audit(resolve_metadata(a.data))
    if a.output:
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
