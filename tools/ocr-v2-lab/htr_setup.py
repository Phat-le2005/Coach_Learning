"""Pinned local HTR assets and UTF-8 references. Never alters native diagnostics."""
import hashlib, json, pathlib, shutil, unicodedata, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / '.tmp/tri-vietnamese-htr'
REPO = 'DungHugging/vietocr-handwritten-finetune'
REVISION = '0827b42e17cb0e1c1bbda5aac11f7cc5c816e0ca'
WEIGHT_SHA = 'd5357730c328e40dd1aeae7288994d8ad85979f8334c03c9bfad53c320114fa7'
WEIGHT_BYTES = 151811471

def sha(data): return hashlib.sha256(data).hexdigest()

def download(name):
    dest = OUT / 'model' / name
    if dest.exists(): return dest
    part = dest.with_suffix(dest.suffix + '.part')
    offset = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}', headers={'Range': f'bytes={offset}-'} if offset else {})
    with urllib.request.urlopen(req, timeout=60) as response:
        with part.open('ab' if offset and response.status == 206 else 'wb') as target: shutil.copyfileobj(response, target)
    part.replace(dest)
    return dest

def prepare_references():
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'model').mkdir(exist_ok=True)
    diagnostic_file = ROOT / '.tmp/tri-native-page-validation/native-diagnostics.json'
    original = diagnostic_file.read_bytes(); diagnostics = json.loads(original)
    report = (diagnostic_file.parent / 'NATIVE_VALIDATION.md').read_text(encoding='utf-8')
    # These are the user's confirmed phrases in the report/conversation, not predictions.
    labels = ['Ta c\u00f3', 'N\u00ean', 'X\u00e9t \u0111\u1ec1 b\u00e0i ta']
    counts = [6, 4, 19]; inputs = []; references = []
    for index, (item, label, count) in enumerate(zip(diagnostics['htrPrototypeInputs'], labels, counts), 1):
        if label not in report or '?' in label or unicodedata.normalize('NFC', label) != label: raise ValueError('REFERENCE_UNICODE_NOT_VERIFIED')
        if json.loads(json.dumps(label, ensure_ascii=False).encode('utf-8')) != label: raise ValueError('REFERENCE_UTF8_ROUNDTRIP_FAILED')
        ids = item['sourceStrokeIds']
        if len(ids) != count or len(set(ids)) != count: raise ValueError('CONFIRMED_STROKE_MEMBERSHIP_MISMATCH')
        case = next(c for c in diagnostics['cases'] if c['id'] == item['pageId'])
        if not all(sid in {s['id'] for s in case['source']['strokes']} for sid in ids): raise ValueError('UNKNOWN_SOURCE_ID')
        png = diagnostic_file.parent / item['image']['file']; digest = sha(png.read_bytes())
        if digest != item['image']['pngSha256']: raise ValueError('INPUT_PNG_CHECKSUM_MISMATCH')
        inputs.append({k: item[k] for k in ['candidateId', 'pageId', 'scopeId', 'pageIndex', 'sourceRevision', 'sourceSnapshotSha256', 'sourceStrokeIds', 'originalKind']})
        inputs[-1].update({'pngFile': str(png.relative_to(ROOT)), 'inputImageHash': digest, 'referenceId': f'ref-{index}'})
        references.append({'id': f'ref-{index}', 'candidateId': item['candidateId'], 'text': label, 'encoding': 'UTF-8', 'normalization': 'NFC', 'status': 'HUMAN_CONFIRMED_ASSISTED', 'source': 'User confirmation + NATIVE_VALIDATION.md; restored via Unicode escapes, never OCR', 'originalDiagnosticTranscript': diagnostics['confirmedAnnotations'][index-1]['transcript']})
    (OUT / 'inputs.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT / 'references.utf8.json').write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding='utf-8')
    if diagnostic_file.read_bytes() != original: raise ValueError('ORIGINAL_DIAGNOSTICS_CHANGED')
    return counts

def prepare():
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'model').mkdir(exist_ok=True)
    files = {name: download(name) for name in ['config.yml', 'README.md', 'transformerocr.pth']}
    if files['transformerocr.pth'].stat().st_size != WEIGHT_BYTES or sha(files['transformerocr.pth'].read_bytes()) != WEIGHT_SHA: raise ValueError('CHECKPOINT_CHECKSUM_MISMATCH')
    manifest = {'modelId': REPO, 'revision': REVISION, 'license': 'MIT declared in pinned model card; no standalone LICENSE file in checkpoint repo', 'source': f'https://huggingface.co/{REPO}/tree/{REVISION}', 'files': {name: {'sha256': sha(f.read_bytes()), 'bytes': f.stat().st_size} for name, f in files.items()}, 'modelA': {'id': 'ANZ-Innovation/OCeanpaRk-small-v1', 'access': 'GATED_MANUAL; README401; existing HF token absent; no weights downloaded'}, 'originalDiagnosticsSha256': None, 'preprocessing': {'source': 'vietocr0.3.13 process_input; pinned checkpoint config', 'imageHeight': 32, 'minWidth': 32, 'maxWidth': 512, 'resize': 'aspect-based width rounded up to multiple10, clamped; PIL LANCZOS; RGB /255', 'device': 'cpu', 'beamsearch': False, 'cnnPretrained': False, 'reason': 'Full strict checkpoint state supplies every weight; no extra ImageNet/base OCR download'}}
    (OUT / 'model-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    # Private research fixtures are optional and are never downloaded with weights.
    diagnostic_file = ROOT / '.tmp/tri-native-page-validation/native-diagnostics.json'
    counts = prepare_references() if diagnostic_file.exists() else []
    print(json.dumps({'status': 'PREPARED', 'model': REPO, 'weightSha256': WEIGHT_SHA,
                      'referenceCatalogue': 'PREPARED' if counts else 'NOT_IMPORTED; live-scope inference available',
                      'sourceStrokeCounts': counts}))

if __name__ == '__main__': prepare()
