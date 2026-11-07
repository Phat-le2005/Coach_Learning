"""Local-only Uni-MuMER lifecycle, image inference and evidence collection. No cloud inference."""
import argparse, base64, datetime, hashlib, json, os, pathlib, re, secrets, socket, subprocess, sys, threading, time, urllib.error, urllib.request
import psutil
from PIL import Image
from unimumer_setup import MODEL_FILES, REVISION, checksum

ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'.tmp/tri-unimumer-lab'; CACHE=OUT/'cache'; SESSION=OUT/'server-session.json'; KEY=OUT/'server-key.txt'
MODEL_ID='phxember/Uni-MuMER-Qwen3.5-2B'
PROMPTS={
 'reference':'I have an image of a handwritten mathematical expression. Please write out the expression of the formula in the image using LaTeX format.',
 'strict':'Transcribe exactly the mathematical expression written in the image into LaTeX. Preserve all symbols and any mathematical mistakes as written. Do not solve, simplify, correct, complete, or explain. Output only the LaTeX transcription. If a symbol is unreadable, do not invent missing content.',
}

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def session():return json.loads(SESSION.read_text())
def request(path,body=None,timeout=5):
    config=session();headers={'Authorization':'Bearer '+KEY.read_text().strip()}
    if body is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(f"http://127.0.0.1:{config['port']}"+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=timeout) as response:return json.load(response)

def gpu():
    try:
        raw=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=5).strip().split(',')
        return {'usedMiB':float(raw[0]),'freeMiB':float(raw[1]),'utilizationPercent':float(raw[2])}
    except Exception:return {'status':'NOT_AVAILABLE'}

def identity():
    s=session();p=psutil.Process(s['pid'])
    if pathlib.Path(p.exe()).resolve()!=pathlib.Path(s['executable']).resolve() or str(s['port']) not in p.cmdline():raise RuntimeError('PID_IDENTITY_CHANGED; process preserved')
    return p

def health():
    if not SESSION.exists():return {'status':'NOT_STARTED','modelId':MODEL_ID}
    s=session()
    try:
        p=identity();answer=request('/health');props=request('/props')
        return {'status':'READY' if answer.get('status')=='ok' else answer.get('status','UNKNOWN'),'modelId':MODEL_ID,'revision':REVISION,'quantization':'Q4_K_M','projector':'Q8_0','profile':s['profile'],'gpuLayers':s.get('verifiedGpuLayers',s['layers']),'projectorDevice':s['projectorDevice'],'runtime':s['runtimeVersion'],'rssMiB':p.memory_info().rss/1024**2,'gpu':gpu(),'loadMs':s.get('loadMs'),'capabilities':props.get('modalities',props.get('model_meta',{}))}
    except Exception as error:return {'status':'UNAVAILABLE','error':str(error),'profile':s.get('profile')}

def start(args):
    OUT.mkdir(exist_ok=True)
    if not 8026 <= args.port <= 8035 or not 0 <= args.layers <= 25: raise ValueError('Use loopback ports8026..8035 and layers0..25')
    if SESSION.exists():
        try:
            identity();print(json.dumps(health()));return
        except psutil.NoSuchProcess:pass
        except RuntimeError:raise
    for name,(size,digest) in MODEL_FILES.items():
        file=CACHE/'models'/name
        if not file.exists() or file.stat().st_size!=size or checksum(file)!=digest:raise RuntimeError('MODEL_NOT_DOWNLOADED_OR_CHECKSUM_MISMATCH: '+name)
    family='llama-cpu' if args.profile=='cpu' else 'llama-cuda'
    binaries=list((CACHE/family).rglob('llama-server.exe'))
    if len(binaries)!=1:raise RuntimeError('RUNTIME_BINARY_MISSING; run unimumer_setup.py')
    executable=binaries[0]
    with socket.socket() as sock:sock.bind(('127.0.0.1',args.port))
    if not KEY.exists():KEY.write_text(secrets.token_hex(32))
    command=[str(executable),'-m',str(CACHE/'models/Uni-MuMER-Qwen3.5-2B.Q4_K_M.gguf'),'--mmproj',str(CACHE/'models/Uni-MuMER-Qwen3.5-2B.mmproj-Q8_0.gguf'),'--host','127.0.0.1','--port',str(args.port),'--api-key-file',str(KEY),'--alias','uni-mumer-qwen3.5-2b-q4_k_m','--ctx-size','2048','--parallel','1','--threads','6','--threads-batch','6','--batch-size','256','--ubatch-size','128','--cache-ram','0','--image-min-tokens','64','--image-max-tokens','512','--reasoning-budget','0','--jinja','--no-webui','--metrics','--verbosity','4','--n-gpu-layers',str(0 if args.profile=='cpu' else args.layers)]
    if args.profile in ['hybrid','cpu']:command.append('--no-mmproj-offload')
    if args.profile=='cpu':command+=['--device','none']
    version=subprocess.check_output([str(executable),'--version'],stderr=subprocess.STDOUT,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),timeout=15)
    log=OUT/f'server-{int(time.time())}-{args.profile}.log';before=time.perf_counter()
    with log.open('ab') as stream:
        p=subprocess.Popen(command,cwd=executable.parent,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'DETACHED_PROCESS',0))
    s={'pid':p.pid,'port':args.port,'executable':str(executable.resolve()),'root':str(ROOT),'startedAt':utc(),'profile':args.profile,'layers':0 if args.profile=='cpu' else args.layers,'projectorDevice':'CPU' if args.profile in ['hybrid','cpu'] else 'GPU_REQUESTED','runtimeVersion':version,'log':str(log),'commandWithoutSecrets':command,'gpuBefore':gpu()};SESSION.write_text(json.dumps(s,indent=2))
    for _ in range(180):
        if p.poll() is not None:raise RuntimeError('SERVER_EXITED; inspect '+str(log))
        try:
            h=request('/health',timeout=2)
            if h.get('status')=='ok':
                startup_log=log.read_text(encoding='utf-8',errors='replace')
                offload=re.search(r'offloaded (\d+)/\d+ layers to GPU',startup_log)
                vision=re.search(r'CLIP using (\S+) backend',startup_log)
                s['verifiedGpuLayers']=int(offload.group(1)) if offload else (0 if args.profile=='cpu' else 'NOT_AVAILABLE')
                s['projectorDevice']=vision.group(1) if vision else ('CPU' if args.profile in ['hybrid','cpu'] else 'NOT_AVAILABLE')
                s['loadMs']=(time.perf_counter()-before)*1000;s['gpuAfter']=gpu();SESSION.write_text(json.dumps(s,indent=2));print(json.dumps(health()));return
        except (urllib.error.URLError,TimeoutError,OSError):pass
        time.sleep(1)
    raise RuntimeError('MODEL_LOAD_TIMEOUT; process recorded for explicit stop')

def infer(image,prompt='reference',max_tokens=384):
    file=pathlib.Path(image);raw=file.read_bytes()
    if len(raw)>3_000_000:raise ValueError('PNG_TOO_LARGE')
    with Image.open(file) as img:
        if img.format!='PNG' or img.width*img.height>2_000_000:raise ValueError('INVALID_PNG_OR_DIMENSIONS')
        dimensions=list(img.size)
    if prompt not in PROMPTS:raise ValueError('UNKNOWN_PROMPT')
    body={'model':'uni-mumer-qwen3.5-2b-q4_k_m','messages':[{'role':'system','content':'You are a helpful assistant.'},{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(raw).decode()}},{'type':'text','text':PROMPTS[prompt]}]}],'temperature':0,'seed':20261104,'max_tokens':max_tokens,'stream':False,'chat_template_kwargs':{'enable_thinking':False},'cache_prompt':False}
    stop=threading.Event();samples=[];p=identity();p.cpu_percent()
    def monitor():
        while not stop.is_set():
            try:samples.append({'t':time.time(),'rssMiB':p.memory_info().rss/1024**2,'processCpuPercent':p.cpu_percent(),'availableRamMiB':psutil.virtual_memory().available/1024**2,'gpu':gpu()})
            except psutil.Error:break
            stop.wait(2)
    thread=threading.Thread(target=monitor,daemon=True);thread.start();t=time.perf_counter()
    try:
        response=request('/v1/chat/completions',body,timeout=180);choice=response['choices'][0];text=choice['message'].get('content','')
        result={'status':'COMPLETED','modelId':MODEL_ID,'modelVersion':REVISION,'quantization':'Q4_K_M','projector':'Q8_0','runtime':session()['runtimeVersion'],'profile':session()['profile'],'rawOutput':text,'rawLatex':text,'finishReason':choice.get('finish_reason'),'usage':response.get('usage'),'timings':response.get('timings'),'durationMs':(time.perf_counter()-t)*1000,'inputImageHash':hashlib.sha256(raw).hexdigest(),'dimensions':dimensions,'promptId':prompt,'prompt':PROMPTS[prompt],'requestParameters':{'temperature':0,'seed':20261104,'maxTokens':max_tokens,'enableThinking':False},'response':response}
    except Exception as error:result={'status':'ERROR','error':str(error),'durationMs':(time.perf_counter()-t)*1000,'inputImageHash':hashlib.sha256(raw).hexdigest(),'promptId':prompt}
    finally:stop.set();thread.join(timeout=6)
    result['resourceSamples']=samples
    return result

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='action',required=True)
    s=sub.add_parser('start');s.add_argument('--profile',choices=['cuda','hybrid','cpu'],default='hybrid');s.add_argument('--layers',type=int,default=12);s.add_argument('--port',type=int,default=8026)
    sub.add_parser('health');sub.add_parser('stop')
    i=sub.add_parser('infer');i.add_argument('image');i.add_argument('--prompt',choices=PROMPTS,default='reference');i.add_argument('--output');i.add_argument('--max-tokens',type=int,default=384)
    args=parser.parse_args()
    if args.action=='start':start(args)
    elif args.action=='health':print(json.dumps(health()))
    elif args.action=='stop':
        if SESSION.exists():
            try:p=identity();p.terminate();p.wait(timeout=15)
            except psutil.NoSuchProcess:pass
            SESSION.rename(OUT/f'stopped-{int(time.time())}.json')
        print('UNI_MUMER_STOPPED; model files and other services preserved')
    elif args.action=='infer':
        result=infer(args.image,args.prompt,args.max_tokens)
        if args.output:pathlib.Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ['resourceSamples','response']},ensure_ascii=False))
        if result['status']!='COMPLETED':sys.exit(1)

if __name__=='__main__':main()
