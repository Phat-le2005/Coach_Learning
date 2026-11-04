"""Setup-time downloads only, from official PaddlePaddle model repositories."""
import argparse, hashlib, json, pathlib, urllib.request, datetime
ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE = ROOT / '.tmp/ocr-layout/models'
MODELS = {'M': 'PP-DocLayout-M'}
REVISIONS = {'M':'7dbfcce3154a55776dc71ca026a4a2a8388dad8d', 'V3':'241f8bdfc77a7c7bee915a5057aaee58c235a8d3'}
def download(key):
    model = MODELS[key]
    with urllib.request.urlopen(f'https://huggingface.co/api/models/PaddlePaddle/{model}/revision/{REVISIONS[key]}', timeout=40) as r:
        info = json.load(r)
    revision = info['sha']
    card_license = info.get('cardData', {}).get('license')
    if card_license != 'apache-2.0':
        raise RuntimeError(f'License needs review: {card_license}')
    target = CACHE / model; target.mkdir(parents=True, exist_ok=True)
    if (target/'manifest.json').exists():
        previous=json.loads((target/'manifest.json').read_text(encoding='utf-8'))
        if previous['revision']!=revision: raise RuntimeError('CACHE_REVISION_MISMATCH; preserve existing cache and use a separate cache for another revision')
        for filename,meta in previous['files'].items():
            if hashlib.sha256((target/filename).read_bytes()).hexdigest()!=meta['sha256']: raise RuntimeError('EXISTING_CACHE_CHECKSUM_MISMATCH')
    files = {}
    for item in info['siblings']:
        name = item['rfilename']
        if name not in ('inference.json', 'inference.yml', 'inference.pdiparams', 'inference.pdmodel', 'config.json', 'README.md', 'LICENSE'):
            continue
        dest = target / name
        url = f'https://huggingface.co/PaddlePaddle/{model}/resolve/{revision}/{name}'
        if not dest.exists():
            print(f'Downloading official {model}/{name}', flush=True)
            with urllib.request.urlopen(url, timeout=180) as response:
                data = response.read(300 * 1024 * 1024 + 1)
            if len(data) > 300 * 1024 * 1024: raise RuntimeError('Model asset size limit')
            dest.write_bytes(data)
        files[name] = {'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'bytes': dest.stat().st_size, 'source': url}
    if not (target / 'inference.pdiparams').exists(): raise RuntimeError('Official weights missing')
    manifest = {'modelId':f'PaddlePaddle/{model}', 'revision':revision, 'license':card_license,
                'downloadedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'files':files,
                'runtime':'paddlepaddle CPU; no cloud inference', 'source':f'https://huggingface.co/PaddlePaddle/{model}'}
    (target/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'model':model, 'revision':revision, 'license':card_license,'totalBytes':sum(f['bytes'] for f in files.values())}), flush=True)
if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',choices=MODELS,default='M');download(parser.parse_args().model)
