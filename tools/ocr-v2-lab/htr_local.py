"""Selected-crop CPU VietOCR service. References never enter this process.
Start/health/stop use an owned loopback process; no backend or grading client.
"""
import argparse, base64, datetime, hashlib, json, os, pathlib, secrets, socket, subprocess, sys, time, unicodedata, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / '.tmp/tri-vietnamese-htr'
SESSION = OUT / 'server-session.json'
KEY = OUT / 'server-key.txt'
PORT = 8041

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(data): return hashlib.sha256(data).hexdigest()

def candidate(candidate_id):
    counts = {'HTR-1': 6, 'HTR-2': 4, 'HTR-3': 19}
    if candidate_id not in counts: raise ValueError('ONLY_THREE_CONFIRMED_CANDIDATES_ALLOWED')
    item = next(i for i in read(OUT/'inputs.json') if i['candidateId'] == candidate_id)
    ids = item['sourceStrokeIds']
    if len(ids) != counts[candidate_id] or len(set(ids)) != len(ids): raise ValueError('CONFIRMED_MEMBERSHIP_MISMATCH')
    file = (ROOT/item['pngFile']).resolve()
    if file.parent != (ROOT/'.tmp/tri-native-page-validation').resolve() or file.name != candidate_id+'.png': raise ValueError('INVALID_FIXED_CROP')
    data = file.read_bytes()
    if sha(data) != item['inputImageHash']: raise ValueError('INPUT_PNG_HASH_MISMATCH')
    return item, file, data

def request(route):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}'+route, headers={'Authorization': 'Bearer '+KEY.read_text().strip()})
    with urllib.request.urlopen(req, timeout=3) as r: return json.load(r)

def identity():
    import psutil
    s = read(SESSION); p = psutil.Process(s['pid'])
    if str(pathlib.Path(p.exe()).resolve()).lower() != s['executable'].lower() or str(pathlib.Path(__file__).resolve()).lower() not in ' '.join(p.cmdline()).lower(): raise RuntimeError('PID_IDENTITY_CHANGED; process preserved')
    return p

def start():
    OUT.mkdir(exist_ok=True)
    if SESSION.exists():
        try: identity(); print(json.dumps(request('/health'))); return
        except Exception: pass  # do not kill a process with unverified identity
    with socket.socket() as probe: probe.bind(('127.0.0.1', PORT))
    KEY.write_text(secrets.token_urlsafe(48), encoding='ascii')
    with (OUT/'server.log').open('a', encoding='utf-8') as log:
        p = subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), 'serve'], stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    SESSION.write_text(json.dumps({'pid': p.pid, 'port': PORT, 'root': str(ROOT), 'executable': str(pathlib.Path(sys.executable).resolve()), 'startedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}, indent=2), encoding='utf-8')
    for _ in range(100):
        if p.poll() is not None: raise RuntimeError('SERVER_START_FAILED; inspect server.log')
        try: print(json.dumps(request('/health'))); return
        except Exception: time.sleep(.15)
    raise RuntimeError('SERVER_HEALTH_TIMEOUT')

def serve():
    import threading, io, importlib.metadata
    from fastapi import FastAPI, Request, HTTPException
    from PIL import Image
    import uvicorn
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    lock = threading.Lock(); engine = {}; calls = 0
    # No network inference/download/telemetry is allowed; loopback serving remains valid.
    connect = socket.socket.connect
    def local_connect(sock, address):
        if isinstance(address, tuple) and str(address[0]) not in ('127.0.0.1', 'localhost', '::1'): raise RuntimeError('NETWORK_DISABLED_DURING_HTR')
        return connect(sock, address)
    socket.socket.connect = local_connect
    def auth(r):
        if r.client and r.client.host not in ('127.0.0.1', '::1'): raise HTTPException(403, 'LOOPBACK_ONLY')
        if r.headers.get('origin'): raise HTTPException(403, 'USE_DEV_PROXY')
        if not secrets.compare_digest(r.headers.get('authorization', '').removeprefix('Bearer '), KEY.read_text().strip()): raise HTTPException(401, 'LOCAL_KEY_REQUIRED')
    @app.get('/health')
    def health(r: Request):
        auth(r)
        return {'status': 'LOADED' if engine else 'READY_MODEL_NOT_LOADED', 'modelId': 'DungHugging/vietocr-handwritten-finetune', 'device': 'cpu', 'inferenceCalls': calls, 'packages': {p: importlib.metadata.version(p) for p in ['torch', 'torchvision', 'vietocr', 'Pillow']}}
    @app.post('/infer')
    async def infer(r: Request):
        auth(r)
        body = bytearray()
        async for chunk in r.stream():
            body.extend(chunk)
            if len(body) > 200: raise HTTPException(413, 'CANDIDATE_REQUEST_TOO_LARGE')
        try:
            value = json.loads(body)
            if set(value) != {'candidateId'}: raise ValueError('CANDIDATE_ID_ONLY; no reference/image/path accepted')
            item, file, data = candidate(value['candidateId'])
        except Exception as e: raise HTTPException(400, str(e))
        return predict(item, data)

    @app.post('/infer-scope')
    async def infer_scope(r: Request):
        auth(r); body = bytearray()
        async for chunk in r.stream():
            body.extend(chunk)
            if len(body) > 3_000_000: raise HTTPException(413, 'SCOPE_IMAGE_TOO_LARGE')
        try:
            value = json.loads(body)
            if set(value) != {'png', 'scopeId', 'sourceStrokeIds', 'sourceSnapshotSha256', 'sourceRevision', 'pageIndex', 'originalKind'}: raise ValueError('IMAGE_AND_SOURCE_METADATA_ONLY')
            ids = value['sourceStrokeIds']
            if not isinstance(ids,list) or not 1 <= len(ids) <= 400 or any(not isinstance(i,str) or not i or len(i)>300 for i in ids) or len(set(ids)) != len(ids): raise ValueError('INVALID_SCOPE_IDS')
            if not isinstance(value['scopeId'],str) or len(value['scopeId'])>300: raise ValueError('INVALID_SCOPE_ID')
            if len(value['sourceSnapshotSha256'])!=64 or any(c not in '0123456789abcdef' for c in value['sourceSnapshotSha256']): raise ValueError('INVALID_SOURCE_HASH')
            if not isinstance(value['sourceRevision'],int) or value['sourceRevision']<0 or not isinstance(value['pageIndex'],int) or not 0<=value['pageIndex']<30 or value['originalKind'] not in ['TEXT','UNKNOWN']: raise ValueError('INVALID_SOURCE_METADATA')
            if not value['png'].startswith('data:image/png;base64,'): raise ValueError('PNG_REQUIRED')
            data = base64.b64decode(value['png'].split(',')[1],validate=True)
            image = Image.open(io.BytesIO(data))
            if image.format!='PNG' or image.width*image.height>2_000_000: raise ValueError('INVALID_IMAGE')
            item = {k:v for k,v in value.items() if k!='png'}
            item['candidateId'] = 'auto-'+sha(data)[:16]
        except Exception as e: raise HTTPException(400,str(e))
        return predict(item,data)

    def predict(item, data):
        nonlocal calls
        if not lock.acquire(blocking=False): raise HTTPException(429, 'HTR_BUSY')
        try:
            cold = not engine; loading = time.perf_counter()
            import torch, yaml
            from vietocr.tool.translate import build_model, process_input, translate
            if cold:
                torch.set_num_threads(3)
                manifest = read(OUT/'model-manifest.json'); weights = OUT/'model/transformerocr.pth'
                if sha(weights.read_bytes()) != manifest['files']['transformerocr.pth']['sha256']: raise ValueError('MODEL_HASH_MISMATCH')
                config = yaml.safe_load((OUT/'model/config.yml').read_text(encoding='utf-8'))
                config['device'] = 'cpu'; config['cnn']['pretrained'] = False
                model, vocab = build_model(config)
                model.load_state_dict(torch.load(weights, map_location='cpu', weights_only=True), strict=True)
                model.eval(); engine.update(model=model, vocab=vocab, config=config, manifest=manifest)
            load_ms = (time.perf_counter()-loading)*1000 if cold else 0
            image = Image.open(io.BytesIO(data))
            if image.mode != 'RGB':
                background = Image.new('RGBA', image.size, 'white'); background.alpha_composite(image.convert('RGBA')); image = background.convert('RGB')
            cfg = engine['config']['dataset']; started = time.perf_counter()
            tensor = process_input(image, cfg['image_height'], cfg['image_min_width'], cfg['image_max_width'])
            calls += 1
            tokens, _uncalibrated_prob = translate(tensor, engine['model'])
            raw = engine['vocab'].decode(tokens[0].tolist())
            duration = (time.perf_counter()-started)*1000
            result = {'status': 'COMPLETED', 'candidateId': item['candidateId'], 'modelId': engine['manifest']['modelId'], 'modelVersion': engine['manifest']['revision'], 'weightSha256': engine['manifest']['files']['transformerocr.pth']['sha256'], 'runtime': f"torch{torch.__version__}/vietocr0.3.13/CPU", 'device': 'cpu', 'rawTranscript': raw, 'normalizedTranscript': unicodedata.normalize('NFC', raw), 'durationMs': duration, 'durationBoundary': 'image preprocessing + greedy model decode; model load excluded', 'modelLoadMs': load_ms, 'cold': cold, 'inputImageHash': sha(data), 'sourceStrokeIds': item['sourceStrokeIds'], 'sourceSnapshotSha256': item['sourceSnapshotSha256'], 'sourceRevision': item['sourceRevision'], 'pageIndex': item['pageIndex'], 'originalKind': item['originalKind'], 'reviewRequired': True, 'inferenceCalls': 1, 'tokenIds': tokens[0].tolist(), 'preprocessing': {'imageMode': image.mode, 'sourceSize': list(image.size), 'tensorShape': list(tensor.shape), 'resize': 'VietOCR process_input; PIL LANCZOS/RGB/255; width rounded10 clamped32..512, height32', 'beamsearch': False}}
            evidence = OUT/'evidence'; evidence.mkdir(exist_ok=True)
            (evidence/f"{time.time_ns()}-{item['candidateId']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            return result
        except Exception as e: raise HTTPException(503, f'{type(e).__name__}: {str(e)[:500]}')
        finally: lock.release()
    uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='warning')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['start', 'serve', 'health', 'stop']); args = parser.parse_args()
    if args.action == 'start': start()
    elif args.action == 'serve': serve()
    elif args.action == 'health': print(json.dumps(request('/health')))
    elif args.action == 'stop':
        import psutil
        # Windows venv python can be a small launcher with the serving Python child.
        # Terminate only verified descendants of the owned launcher, not a port owner.
        p = identity(); script = str(pathlib.Path(__file__).resolve()).lower()
        # Windows may add an owned conhost alongside the Python child. Let the
        # OS close that host when its launcher exits; never treat it as Python.
        children = [child for child in p.children(recursive=True) if pathlib.Path(child.exe()).name.lower() != 'conhost.exe']
        for child in children:
            if script not in ' '.join(child.cmdline()).lower(): raise RuntimeError('CHILD_IDENTITY_CHANGED; processes preserved')
        for process in [*reversed(children), p]:
            try: process.terminate()
            except psutil.NoSuchProcess: pass
        _, alive = psutil.wait_procs([p, *children], timeout=10)
        if alive: raise RuntimeError('OWNED_PROCESS_STOP_TIMEOUT; no force kill')
        print('Owned HTR service tree stopped')
