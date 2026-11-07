"""Fetch a bounded official excerpt and prepare local vector source records. No OCR/DB calls."""
import os, argparse, collections, datetime, hashlib, json, math, pathlib, tarfile, urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / '.tmp/tri-ocr-v2-evaluation'
URL = 'https://storage.googleapis.com/mathwriting_data/mathwriting-2024-excerpt.tgz'
EXPECTED = 'cba038def001480a89962b25cb20a60df4c4145e94c86ef9d2af65f192cb82bc'

def parse_inkml(data, source_id, source_path, dataset='MathWriting2024'):
    if len(data) > 2_000_000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Unsupported or oversized XML')
    root = ET.fromstring(data)
    local = lambda node: node.tag.split('}')[-1]
    annotations = {n.attrib.get('type', ''): (n.text or '').strip() for n in root if local(n) == 'annotation'}
    channels = [n.attrib.get('name', '').upper() for n in root.iter() if local(n) == 'channel'] or ['X', 'Y']
    if 'X' not in channels or 'Y' not in channels: raise ValueError('X/Y channels required')
    traces = []
    for i, n in enumerate(n for n in root.iter() if local(n) == 'trace'):
        text = (n.text or '').strip()
        # InkML delta encodings require an explicit decoder; never interpret them as absolute coordinates.
        if any(char in text for char in ('!', '"', "'")): raise ValueError('Delta encoded trace unsupported')
        points = []
        for value in text.split(','):
            if not value.strip(): continue
            values = [float(v) for v in value.split()]
            if len(values) < len(channels): raise ValueError('Missing trace channels')
            if not all(math.isfinite(v) for v in values): raise ValueError('Non-finite trace coordinate')
            p = {'x': values[channels.index('X')], 'y': values[channels.index('Y')]}
            if 'T' in channels: p['t'] = values[channels.index('T')]
            points.append(p)
        if not points: raise ValueError('Empty trace')
        traces.append({'id': n.attrib.get('id', str(i)), 'points': points})
    if not traces: raise ValueError('No vector traces')
    if len({trace['id'] for trace in traces}) != len(traces): raise ValueError('Duplicate trace ID')
    return {'id': source_id, 'dataset': dataset, 'sourcePath': source_path,
            'checksum': hashlib.sha256(data).hexdigest(), 'license': 'CC-BY-NC-SA-4.0' if dataset == 'MathWriting2024' else 'USER_SUPPLIED_VERIFY_LICENSE',
            'url': URL if dataset == 'MathWriting2024' else None, 'annotations': annotations,
            'label': annotations.get('normalizedLabel') or annotations.get('label') or annotations.get('truth'),
            'labelField': 'normalizedLabel' if annotations.get('normalizedLabel') else 'label' if annotations.get('label') else 'truth',
            'inkCreationMethod': annotations.get('inkCreationMethod', 'UNKNOWN'),
            'originalSplit': annotations.get('splitTagOriginal', 'UNKNOWN'), 'traces': traces}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--offline', action='store_true'); args = parser.parse_args()
    data_dir = OUT / 'data'; data_dir.mkdir(parents=True, exist_ok=True)
    archive = data_dir / 'mathwriting-2024-excerpt.tgz'
    if not archive.exists():
        if args.offline: raise ValueError('MISSING_EXCERPT_OFFLINE')
        with urllib.request.urlopen(URL, timeout=45) as response: content = response.read(10_000_001)
        if len(content) > 10_000_000: raise ValueError('DOWNLOAD_LIMIT')
        if hashlib.sha256(content).hexdigest() != EXPECTED: raise ValueError('ARCHIVE_CHECKSUM_MISMATCH')
        archive.write_bytes(content)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != EXPECTED: raise ValueError('ARCHIVE_CHECKSUM_MISMATCH')
    records, rejected, license_text = [], [], ''
    # Read members without extractall: no archive-controlled filesystem paths.
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar.getmembers():
            if not member.isfile(): continue
            if member.size > 2_000_000: raise ValueError('ARCHIVE_MEMBER_LIMIT')
            if member.name.lower().endswith('readme.md'): license_text = tar.extractfile(member).read().decode('utf-8')
            if not member.name.endswith('.inkml'): continue
            try:
                raw = tar.extractfile(member).read()
                record = parse_inkml(raw, 'mw-' + pathlib.PurePosixPath(member.name).stem, member.name)
                records.append(record)
                if record['inkCreationMethod'] == 'human' and record['originalSplit'] == 'train' and not (data_dir / 'example-human.inkml').exists():
                    (data_dir / 'example-human.inkml').write_bytes(raw)
            except ValueError as e: rejected.append({'file': member.name, 'error': str(e)})
    if license_text: (data_dir / 'MATHWRITING_ARCHIVE_README.md').write_text(license_text, encoding='utf-8')
    native = []
    paths = [(f'handoff-{n}', ROOT / f'.tmp/tri-ocr-root-cause/{n}.capture.json') for n in ('quadratic', 'derivative', 'sigma', 'old-native-integral')]
    paths += [('native14', ROOT / '.tmp/tri-ocr-v2-remediation/user-equation-14.capture.json'), ('native71', ROOT / '.tmp/tri-ocr-v2-remediation/user-mixed-71.capture.json')]
    newest = pathlib.Path(os.environ['OCR_NATIVE_CAPTURE']) if os.environ.get('OCR_NATIVE_CAPTURE') else OUT / 'native-import.json'
    for sample_id, file in paths:
        if file.exists():
            raw = file.read_bytes(); native.append({'id': sample_id, 'capture': json.loads(raw), 'checksum': hashlib.sha256(raw).hexdigest(), 'origin': str(file.relative_to(ROOT)), 'annotationStatus': 'DRAFT', 'groundTruth': None})
    if newest.exists():
        raw = newest.read_bytes(); bundle = json.loads(raw); source = bundle.get('source', {})
        if source.get('strokes'): native.append({'id': 'native-user-latest', 'capture': {'pageIndex': source['pageIndex'], 'strokes': source['strokes']}, 'checksum': hashlib.sha256(raw).hexdigest(), 'origin': str(newest), 'annotationStatus': 'DRAFT', 'groundTruth': None})
    counts = dict(collections.Counter(r['originalSplit'] for r in records))
    manifest = {'schemaVersion': 'ocr-eval-source-index/1', 'createdAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'archive': {'url': URL, 'sha256': EXPECTED, 'bytes': archive.stat().st_size, 'license': 'CC-BY-NC-SA-4.0; source LaTeX may also require CC-BY-SA attribution', 'source': 'Google Research / Google LLC'},
                'counts': counts, 'records': records, 'native': native, 'rejected': rejected,
                'writerMetadata': 'MathWriting does not publish writer IDs',
                'crohme': {'status': 'OPTIONAL_NOT_DOWNLOADED', 'official': 'https://tc11.cvc.uab.es/datasets/CROHME-2014_2', 'license': 'CC-BY-NC-SA-3.0', 'reason': 'Official MathWriting excerpt suffices for initial benchmark; generic InkML import available'}}
    (OUT / 'source-index.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'status': 'PREPARED', 'records': len(records), 'splits': counts, 'native': len(native), 'rejected': len(rejected), 'archiveSha256': EXPECTED}))

if __name__ == '__main__': main()
