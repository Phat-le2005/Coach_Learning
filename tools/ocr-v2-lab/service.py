"""Loopback-only experimental detector. Never imports the application backend/DB.

One disposable inference worker bounds timeout/RAM failure and serializes Paddle sessions.
Inference reads only server-created images and explicitly cached model directories.
"""
import os, sys, json, pathlib, time, hashlib, contextlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
RUNTIME=ROOT/'.tmp/tri-ocr-v2-runtime'
MODELS={'LAYOUT_M':'PP-DocLayout-M','LAYOUT_V3':'PP-DocLayoutV3'}
os.environ.update({'PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK':'True','DISABLE_MODEL_SOURCE_CHECK':'True',
                   'HF_HUB_OFFLINE':'1','HF_HUB_DISABLE_TELEMETRY':'1','PADDLE_PDX_CACHE_HOME':str(RUNTIME/'paddlex'),
                   'FLAGS_enable_pir_api':'0','OMP_NUM_THREADS':'3'})
def manifest(key):
    directory=RUNTIME/'models'/MODELS[key]; file=directory/'manifest.json'
    if not file.exists(): return None
    value=json.loads(file.read_text(encoding='utf-8'))
    for name,meta in value['files'].items():
        if pathlib.Path(name).name != name: raise ValueError('Invalid cached model manifest')
        data=(directory/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=meta['sha256']: raise ValueError('MODEL_CHECKSUM_MISMATCH')
    return value
def worker():
    # Enforce offline inference, including unexpected telemetry/download attempts by dependencies.
    import socket
    original_connect=socket.socket.connect
    def loopback_connect(sock,address):
        if isinstance(address,tuple) and str(address[0]) not in ('127.0.0.1','::1','localhost'):
            raise RuntimeError('EXTERNAL_NETWORK_DISABLED_DURING_INFERENCE')
        return original_connect(sock,address)
    socket.socket.connect=loopback_connect
    models={}
    for line in sys.stdin:
        try:
            job=json.loads(line); key=job['model']; name=MODELS[key]
            before=time.perf_counter(); cold=key not in models
            with contextlib.redirect_stdout(sys.stderr):
                if cold:
                    manifest(key)
                    from paddleocr import LayoutDetection
                    models[key]=LayoutDetection(model_name=name, model_dir=str(RUNTIME/'models'/name), device='cpu',cpu_threads=3,enable_mkldnn=False)
                loaded=time.perf_counter()
                result=list(models[key].predict(job['image'],batch_size=1,threshold=.35,layout_nms=True))[0].json
            raw=result.get('res',result); import psutil
            print(json.dumps({'status':'DETECTED' if raw.get('boxes') else 'NO_DETECTIONS','model':key,
                 'raw':raw,'timings':{'loadMs':(loaded-before)*1000,'inferenceMs':(time.perf_counter()-loaded)*1000,
                 'cold':int(cold),'rssMB':psutil.Process().memory_info().rss/1024**2}},default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v)),flush=True)
        except Exception as e: print(json.dumps({'status':'ERROR','model':job.get('model') if 'job' in locals() else None,'error':f'{type(e).__name__}: {e}'[:2000]}),flush=True)
if '--worker' in sys.argv:
    worker();sys.exit()

import base64, io, secrets, subprocess, threading, queue, tempfile, importlib.metadata
from fastapi import FastAPI, Request, HTTPException
from PIL import Image
Image.MAX_IMAGE_PIXELS=6_000_000
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
TOKEN=os.environ.get('OCR_V2_SIDECAR_TOKEN','')
if len(TOKEN)<32: raise RuntimeError('OCR_V2_SIDECAR_TOKEN of at least 32 characters is required')
lock=threading.Lock(); child=None; replies=queue.Queue(); loaded=set(); unsupported=set(); calls=0
def auth(request):
    if request.client and request.client.host not in ('127.0.0.1','::1','testclient'): raise HTTPException(403,'LOOPBACK_ONLY')
    token=request.headers.get('authorization','').removeprefix('Bearer ')
    if not secrets.compare_digest(token,TOKEN): raise HTTPException(401,'LOCAL_TOKEN_REQUIRED')
    if request.headers.get('origin'): raise HTTPException(403,'USE_SAME_ORIGIN_NEXT_PROXY')
def stop_worker():
    global child
    if child and child.poll() is None: child.kill(); child.wait(timeout=5)
    child=None; loaded.clear()
def start_worker():
    global child,replies
    if child and child.poll() is None: return
    replies=queue.Queue(); RUNTIME.mkdir(parents=True,exist_ok=True)
    log=open(RUNTIME/'worker.log','a',encoding='utf-8')
    child=subprocess.Popen([sys.executable,__file__,'--worker'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,encoding='utf-8',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log.close(); target_queue=replies; process=child
    def reader():
        for line in process.stdout:
            try: target_queue.put(json.loads(line))
            except (ValueError,TypeError): pass
        target_queue.put({'status':'ERROR','error':'WORKER_EXITED'})
    threading.Thread(target=reader,daemon=True).start()
@app.get('/health')
def health(request:Request):
    auth(request)
    packages={}
    for name in ('paddlepaddle','paddleocr','paddlex','fastapi','Pillow'):
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]='MISSING'
    return {'status':'BUSY' if lock.locked() else 'READY','models':{k:{'status':'UNSUPPORTED_RUNTIME' if k in unsupported else 'LOADED' if k in loaded else 'CACHED' if (RUNTIME/'models'/v/'manifest.json').exists() else 'MISSING','modelId':f'PaddlePaddle/{v}'} for k,v in MODELS.items()},
            'htr':{'status':'UNRESOLVED_MANUAL','reason':'No independently verified offline Vietnamese HTR checkpoint enabled'},
            'packages':packages,'device':'cpu','calls':calls,'inferenceNetwork':'LOCAL_ONLY; setup downloads are separate'}
@app.post('/infer')
async def infer(request:Request):
    auth(request); body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>4_000_000: raise HTTPException(413,'IMAGE_REQUEST_TOO_LARGE')
    try:
        job=json.loads(body); key=job['model']
        if key not in MODELS: raise ValueError('Unsupported model')
        raw=base64.b64decode(job['png'].split(',')[-1],validate=True)
        if len(raw)>3_000_000: raise ValueError('PNG too large')
        image=Image.open(io.BytesIO(raw))
        if image.format!='PNG' or image.width>2300 or image.height>3200 or image.width*image.height>6_000_000: raise ValueError('Invalid PNG dimensions')
        image.load()
    except Exception: raise HTTPException(400,'INVALID_IMAGE_OR_MODEL')
    if not (RUNTIME/'models'/MODELS[key]/'manifest.json').exists(): return {'status':'MODEL_MISSING','model':key,'regions':[],'error':'Run download_models.py during setup; runtime never downloads weights'}
    if not lock.acquire(blocking=False): raise HTTPException(429,'INFERENCE_BUSY')
    try:
        # Run blocking inference in a worker thread so /health remains responsive.
        import asyncio
        try: return await asyncio.to_thread(run_inference,key,raw,image.size)
        except Exception as e: return {'status':'ERROR','model':key,'regions':[],'error':f'{type(e).__name__}: {e}'[:1000]}
    finally: lock.release()
def run_inference(key,raw,size):
    global calls
    start=time.perf_counter(); meta=manifest(key); RUNTIME.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix='.png',dir=RUNTIME,delete=False) as f: f.write(raw); filename=f.name
    try:
        start_worker(); child.stdin.write(json.dumps({'model':key,'image':filename})+'\n');child.stdin.flush();calls+=1
        try: result=replies.get(timeout=75)
        except queue.Empty: stop_worker();return {'status':'TIMEOUT','model':key,'regions':[],'error':'75s worker deadline exceeded; worker stopped'}
        if result.get('status')=='ERROR' and 'not registered' in result.get('error',''): unsupported.add(key)
        regions=[]; invalid=[]
        for i,box in enumerate(result.get('raw',{}).get('boxes',[])[:96]):
            coords=box.get('coordinate',[])
            import math
            if len(coords)!=4 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in coords) or not (0<=coords[0]<coords[2]<=size[0]+1 and 0<=coords[1]<coords[3]<=size[1]+1): invalid.append(box); continue
            regions.append({'id':f'{key}-{i+1}','label':box.get('label','UNKNOWN'),'score':box.get('score'),'box':coords,'raw':box})
        return {**{k:v for k,v in result.items() if k!='raw'},'regions':regions,'invalidBoxes':invalid,
                'rawDetectorOutput':{k:v for k,v in result.get('raw',{}).items() if k not in ('input_path','page_index')},
                'manifest':meta,'imageSha256':hashlib.sha256(raw).hexdigest(),'device':'cpu','totalMs':(time.perf_counter()-start)*1000,
                'htr':{'status':'UNRESOLVED_MANUAL'}}
    finally:
        pathlib.Path(filename).unlink(missing_ok=True)
        if 'result' in locals() and result.get('status') in ('DETECTED','NO_DETECTIONS'): loaded.add(key)
if __name__=='__main__':
    import argparse,uvicorn
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8014)
    uvicorn.run(app,host='127.0.0.1',port=parser.parse_args().port,access_log=False)
