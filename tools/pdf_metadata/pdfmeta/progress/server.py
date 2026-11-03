"""Read-only dashboard API, restricted to the local PDF job directory."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime,timezone
from functools import partial
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
from urllib.parse import unquote,urlsplit

from . import STAGES,read


JOB=re.compile(r'^[0-9a-f]{24}$')
RUNNING={'RUNNING','PREPARING_MODEL','AWAITING_NEXT'}


def root_id(root):return hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:20]


def alive(record):
    try:
        import psutil
        process=psutil.Process(int(record['pid']))
        return record.get('created') is None or abs(process.create_time()-record['created'])<.01
    except Exception:return False


def iso_time(value):
    try:return datetime.fromisoformat(value).timestamp()
    except (ValueError,TypeError):return None


def legacy(job,latest,final):
    source=latest.get('report',{});pages=source.get('page_count');questions=source.get('question_count')
    stages=[{'id':key,'label':label,'unit':unit,'status':'pending','done':None,'total':None,'detail':''} for key,label,unit in STAGES]
    if latest:
        for stage in stages[:5]:stage.update(status='completed',detail='Có kết quả trích xuất đã lưu')
        stages[0].update(done=pages,total=pages);stages[1].update(done=questions,total=questions)
    if final:
        stages[5].update(status='completed',done=questions,total=questions,detail='Có bản chuẩn hóa đã lưu')
        q=final.get('qwen_review',{});scope=q.get('selected_count')
        stages[6].update(status='skipped' if q.get('status')=='SKIPPED' else 'partial' if q.get('status')=='PARTIAL' else 'completed',
                         done=scope,total=scope,detail='Không chạy Qwen' if q.get('status')=='SKIPPED' else f"{q.get('completed_count',0)} phản hồi hợp lệ trong lượt")
        stages[7].update(status='completed',done=3,total=3,detail='File cuối đã sẵn sàng')
    updated=datetime.fromtimestamp((job/('final.json' if final else 'latest.json')).stat().st_mtime,timezone.utc).isoformat()
    return {'schema_version':'pdf-progress/v1','job_id':job.name,'run_id':None,'source_name':Path(source.get('source_path',job.name)).name,
        'status':'COMPLETED_PARTIAL' if final and final.get('status')!='DRAFT_READY' else 'COMPLETED' if final else 'EXTRACTED',
        'detail':'Kết quả đã lưu · có phần cần xử lý tiếp' if final and final.get('status')!='DRAFT_READY' else 'Kết quả đã lưu' if final else 'Đã trích xuất · chưa hoàn thiện',
        'started_at':None,'finished_at':updated if final else None,'updated_at':updated,'stages':stages,
        'counters':{'pages':pages,'questions':questions,'table_regions':source.get('tables',{}).get('count')},
        'record_source':'stored-report','owner':{}}


def event_tail(job,run_id):
    path=job/'progress-events.jsonl'
    try:
        with path.open('rb') as stream:
            stream.seek(max(0,path.stat().st_size-24000));lines=stream.read().decode('utf-8',errors='replace').splitlines()
    except OSError:return []
    events=[]
    for line in lines:
        try:value=json.loads(line)
        except ValueError:continue
        if value.get('run_id')==run_id:events.append({k:value.get(k) for k in ['at','stage','message']})
    return events[-30:]


def artifact_link(job,value):
    if not value:return None
    try:
        path=Path(value).resolve()
        if not path.is_relative_to(job.resolve()) or not path.is_file():return None
        return '/artifacts/'+job.name+'/'+path.relative_to(job.resolve()).as_posix()
    except (OSError,ValueError):return None


def snapshot(job):
    latest=read(job/'latest.json') or {};final=read(job/'final.json') or {}
    state=read(job/'progress.json')
    if not state:
        if not latest:return None
        state=legacy(job,latest,final)
    else:state=deepcopy(state)
    updated=iso_time(state.get('updated_at'))
    if (state.get('status') in RUNNING and state.get('run_id') and updated
            and datetime.now(timezone.utc).timestamp()-updated>8
            and not alive(state.get('owner',{})) and not alive(state.get('controller',{}))):
        state.update(status='INTERRUPTED',detail='Tiến trình đã dừng · chạy lại cùng PDF để tiếp tục')
    running=state.get('status') in RUNNING
    state['record_source']=state.get('record_source','live-recorder')
    state['events']=event_tail(job,state.get('run_id')) if state.get('run_id') else []
    # Old results remain accessible, but never masquerade as the new run's counters.
    current_result=bool(final) and not running and state.get('status') not in {'FAILED','INTERRUPTED'}
    effective=final.get('effective_latex_status_counts') or final.get('latex',{}).get('status_counts',{})
    state['result']={'review':artifact_link(job,job/'final.html'),'jsonl':artifact_link(job,final.get('final_jsonl')),
                     'json':artifact_link(job,final.get('final_pretty_json')),'is_previous':bool(final) and not current_result}
    state['quality']=({'latex':effective,'review':final.get('status_counts',{}),
                       'review_selected':final.get('qwen_review',{}).get('selected_count'),
                       'review_completed':final.get('qwen_review',{}).get('completed_count'),
                       'questions':final.get('question_count'),'formula_count':final.get('latex',{}).get('formula_count'),
                       'cloud_api_calls':final.get('cloud_api_calls',0)} if current_result else None)
    if current_result:
        state['counters'].update(normalized=effective.get('NORMALIZED',0),
            formula_candidates=final.get('latex',{}).get('formula_count'),
            latex_cache_hits=final.get('latex',{}).get('cache_hits',0),review_cache_hits=final.get('qwen_review',{}).get('cache_hits',0))
    state['completed_stages']=sum(s['status'] in {'completed','cached','partial','skipped'} for s in state.get('stages',[]))
    state['total_stages']=len(STAGES)
    check=read(job/'readiness-status.json') or {}
    image_report=read(job/'image-check.json') or {};core_report=read(job/'core-package.json') or {}
    current_path=final.get('final_jsonl')
    state['readiness']={'image':image_report if image_report.get('source_final_file')==current_path else None,
        'core':core_report if core_report.get('source_final_file')==current_path else None,
        'review':artifact_link(job,job/'readiness/review.html'),'status':check.get('status'),
        'done':check.get('done'),'total':check.get('total')}
    trial=read(job/'grading-trial.json') or {}
    if trial.get('source_final_file')==current_path:
        state['readiness']['trial']={k:trial.get(k) for k in ['questions','ready_for_sandbox','held_for_source_conflict','synthetic_scenarios','assertions_passed','assertions_failed']}
        state['readiness']['trial']['review']=artifact_link(job,job/'grading-trial/review.html')
    if check.get('status')=='RUNNING':
        if alive(check.get('owner',{})):
            state['_post_owner']=check['owner']
            state['readiness']['status']='RUNNING'
        else:state['readiness']['status']='INTERRUPTED'
    # Only expose the few owner fields needed by resource sampling internally.
    return state


class Resources:
    def __init__(self):self.samples={}
    def get(self,jobs,runtime):
        try:import psutil
        except ImportError:return {'available':False}
        records=[j.get('owner',{}) for j in jobs if j['status'] in RUNNING]
        records.extend(j['_post_owner'] for j in jobs if j.get('_post_owner'))
        model=False
        manifest=read(runtime/'local-qwen-runtime.json') or {}
        try:
            pid=int((runtime/'local-qwen-server.pid').read_text().strip());process=psutil.Process(pid)
            if Path(process.exe()).resolve()==Path(manifest['server_path']).resolve():
                records.append({'pid':pid,'created':process.create_time()});model=True
        except (OSError,ValueError,KeyError,psutil.Error):pass
        ram=0;cpu=0;measured=False;seen=set()
        for record in records:
            if not alive(record) or record.get('pid') in seen:continue
            pid=record['pid'];seen.add(pid)
            try:
                key=(pid,record.get('created'));process=self.samples.get(key)
                if process is None:
                    process=psutil.Process(pid);process.cpu_percent();self.samples[key]=process
                else:cpu+=process.cpu_percent();measured=True
                ram+=process.memory_info().rss
            except psutil.Error:continue
        if len(self.samples)>32:self.samples={k:v for k,v in self.samples.items() if k[0] in seen}
        return {'available':True,'ram_mb':round(ram/1024**2,1),'system_ram_mb':round(psutil.virtual_memory().total/1024**2,1),
                'cpu_percent':round(min(100,cpu/(psutil.cpu_count() or 1)),1) if measured else None if seen else 0,
                'process_count':len(seen),'model_loaded':model,'threads':manifest.get('threads'),'gpu_layers':manifest.get('gpu_layers',0)}


class Handler(BaseHTTPRequestHandler):
    def __init__(self,*args,root,runtime,sampler,**kwargs):
        self.root,self.runtime,self.sampler=root.resolve(),runtime.resolve(),sampler
        super().__init__(*args,**kwargs)
    def log_message(self,*args):pass
    def allowed_host(self):return self.headers.get('Host','').lower() in {f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
    def send(self,data,kind='application/json',status=200,head=False):
        self.send_response(status);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.end_headers()
        if not head:self.wfile.write(data)
    def json(self,value,status=200,head=False):self.send(json.dumps(value,ensure_ascii=False).encode(),'application/json; charset=utf-8',status,head)
    def route(self,head=False):
        if not self.allowed_host():return self.json({'error':'Host not allowed'},403,head)
        path=unquote(urlsplit(self.path).path)
        if path in {'/','/progress'}:return self.send((Path(__file__).parent/'ui.html').read_bytes(),'text/html; charset=utf-8',head=head)
        if path=='/api/health':return self.json({'service':'pdf-progress/v1','root_id':root_id(self.root),'pid':os.getpid()},head=head)
        if path=='/api/jobs':
            jobs=[]
            for directory in self.root.iterdir():
                if not JOB.fullmatch(directory.name) or not directory.is_dir() or not directory.resolve().is_relative_to(self.root):continue
                try:state=snapshot(directory)
                except (OSError,ValueError,KeyError,TypeError):continue
                if state:jobs.append(state)
            jobs.sort(key=lambda j:j.get('updated_at') or '',reverse=True)
            resources=self.sampler.get(jobs,self.runtime)
            for job in jobs:job.pop('owner',None);job.pop('controller',None);job.pop('_post_owner',None)
            queue=None;queue_root=self.root.parent/'pdf-queues';pointer=read(queue_root/'latest.json') or {}
            if pointer.get('queue'):
                target=Path(pointer['queue']).resolve()
                if target.is_relative_to(queue_root.resolve()):
                    record=read(target) or {}
                    queue={k:record.get(k) for k in ['queue_id','status','counts','updated_at']}
                    queue['total']=len(record.get('items',[]))
                    queue['review']='/queue/'+str(record.get('queue_id'))+'/evaluation.html' if (target.parent/'evaluation.html').is_file() else None
            return self.json({'jobs':jobs,'resources':resources,'queue':queue,'server_time':datetime.now(timezone.utc).isoformat()},head=head)
        if path.startswith('/queue/'):
            parts=path.split('/')
            if len(parts)!=4 or not JOB.fullmatch(parts[2]) or parts[3] not in {'evaluation.html','evaluation.json'}:
                return self.json({'error':'Queue report not allowed'},403,head)
            root=(self.root.parent/'pdf-queues').resolve();target=(root/parts[2]/parts[3]).resolve()
            if not target.is_relative_to(root) or not target.is_file():return self.json({'error':'Queue report not found'},404,head)
            return self.send(target.read_bytes(),'text/html; charset=utf-8' if target.suffix=='.html' else 'application/json; charset=utf-8',head=head)
        if path.startswith('/artifacts/'):
            parts=path[len('/artifacts/'):].split('/')
            if len(parts)<2 or not JOB.fullmatch(parts[0]) or any(p.startswith('.') or p in {'jobs','runs'} for p in parts[1:]):
                return self.json({'error':'Artifact not allowed'},403,head)
            job=(self.root/parts[0]).resolve();target=(job/('/'.join(parts[1:]))).resolve()
            allowed={'.html','.json','.jsonl','.png','.jpg','.jpeg','.pdf','.css','.js','.woff','.woff2','.ttf'}
            if not job.is_relative_to(self.root) or not target.is_relative_to(job) or target.suffix.lower() not in allowed or not target.is_file():
                return self.json({'error':'Artifact not found'},404,head)
            kind=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
            self.send_response(200);self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(target.stat().st_size))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer');self.end_headers()
            if not head:
                try:
                    with target.open('rb') as stream:
                        while chunk:=stream.read(65536):self.wfile.write(chunk)
                except (BrokenPipeError,ConnectionResetError):pass
            return
        return self.json({'error':'Not found'},404,head)
    def do_GET(self):self.route()
    def do_HEAD(self):self.route(head=True)
    def do_POST(self):self.json({'error':'Read-only monitor'},405)


def create_server(root,runtime,port):
    root,runtime=Path(root).resolve(),Path(runtime).resolve();root.mkdir(parents=True,exist_ok=True)
    return ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,root=root,runtime=runtime,sampler=Resources()))
