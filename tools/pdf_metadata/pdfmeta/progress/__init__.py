"""Small, best-effort progress records. No inference imports or pipeline decisions."""
from __future__ import annotations

from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import uuid


STAGES=[('read','Đọc tài liệu','trang'),('questions','Tách câu hỏi','câu'),
        ('formula','Nhận dạng công thức','trang'),('math','Kiểm tra bước giải','câu'),
        ('tables','Đọc bảng và miền','câu'),('latex','Chuẩn hóa LaTeX','câu'),
        ('review','Qwen rà soát','câu'),('export','Xuất kết quả','tệp')]
EXTRACTION={'native-extraction':'read','page-routing':'read','question-assembly':'questions',
            'formula-evidence':'formula','steps-and-math':'math','tables':'tables'}


def now():return datetime.now(timezone.utc).isoformat()


def read(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None


def owner(pid=None):
    pid=pid or os.getpid()
    try:
        import psutil
        return {'pid':pid,'created':psutil.Process(pid).create_time()}
    except Exception:return {'pid':pid,'created':None}


def controller():
    """Windows venv redirectors create a fresh Python parent for each command."""
    try:
        import psutil
        for process in psutil.Process().parents():
            if not process.name().lower().startswith(('python','py.exe')):
                return owner(process.pid)
    except Exception:pass
    return owner(os.getppid())


class Progress:
    def __init__(self,job):
        self.job=Path(job);self.path=self.job/'progress.json';self.state=read(self.path) or {}

    def _save(self,event=None):
        """Observability must never make an otherwise valid PDF run fail."""
        try:
            self.job.mkdir(parents=True,exist_ok=True);self.state['updated_at']=now()
            path=self.path.with_suffix('.json.pending')
            path.write_text(json.dumps(self.state,ensure_ascii=False,indent=2),encoding='utf-8');path.replace(self.path)
            if event:
                line={'run_id':self.state.get('run_id'),'at':self.state['updated_at'],
                      'stage':self.state.get('active_stage'),'message':str(event)[:220]}
                with (self.job/'progress-events.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(line,ensure_ascii=False)+'\n')
        except (OSError,ValueError):pass

    def begin(self,name):
        self.state={'schema_version':'pdf-progress/v1','job_id':self.job.name,'run_id':uuid.uuid4().hex,
            'source_name':Path(name).name,'status':'RUNNING','started_at':now(),'finished_at':None,
            'owner':owner(),'controller':controller(),'active_stage':'read','detail':'Đang chuẩn bị tài liệu',
            'counters':{},'stages':[{'id':key,'label':label,'unit':unit,'status':'pending','done':None,'total':None,
                                   'detail':''} for key,label,unit in STAGES]}
        self._save('Bắt đầu lượt xử lý mới')

    def stage(self,key,status='running',*,done=None,total=None,detail=None,log=False):
        if not self.state:return
        item=next((s for s in self.state['stages'] if s['id']==key),None)
        if item is None:return
        item['status']=status
        if done is not None:item['done']=max(0,int(done))
        if total is not None:item['total']=max(0,int(total))
        if detail is not None:item['detail']=detail
        if status=='running':
            self.state.update(active_stage=key,status='RUNNING',detail=detail or item['label'],owner=owner())
        self._save((detail or item['label']) if log else None)

    def extract_event(self,kind,value):
        if kind=='stage' and value in EXTRACTION:self.stage(EXTRACTION[value],detail=dict((k,l) for k,l,_ in STAGES)[EXTRACTION[value]],log=True)
        elif kind in {'done','cache'} and isinstance(value,str) and value in EXTRACTION:
            key=EXTRACTION[value]
            self.stage(key,'cached' if kind=='cache' else 'completed',detail='Dùng lại checkpoint hợp lệ' if kind=='cache' else 'Đã xử lý xong',log=True)
        elif kind in {'page','native_page'}:
            if isinstance(value,dict):done,total=value['done'],value['total']
            else:
                match=re.match(r'(\d+)/(\d+)',str(value))
                if not match:return
                done,total=map(int,match.groups())
            self.stage('read',done=done,total=total,detail=f'Đang đọc trang {done}/{total}')
            self.state['counters']['pages']=int(total);self._save()
        elif kind=='counts':
            self.state['counters'].update(value);self._save()
            for key,count in [('read',value.get('pages')),('questions',value.get('questions'))]:
                item=next(s for s in self.state['stages'] if s['id']==key)
                if count is not None:self.stage(key,item['status'],done=count,total=count)
        elif kind=='formula_progress':
            self.stage('formula',done=value['done'],total=value['total'],detail=f"Đã xử lý {value['done']}/{value['total']} trang có công thức")
        elif kind=='table_progress':
            self.stage('tables',done=value['done'],total=value['total'],detail=f"Đã khảo sát {value['done']}/{value['total']} câu")
        elif kind=='model':
            self.state['current_model']=str(value);self._save('Nạp model local: '+str(value))
        elif kind=='cache' and value=='native-pages':
            self.stage('read',detail='Đã có cache trang PDF')

    def extracted(self,report):
        self.state['counters'].update(pages=report['page_count'],questions=report['question_count'],
            table_regions=report['tables']['count'],ocr_cache_hits=report['ocr_cache_hits'],
            extraction_cache_hits=report['stage_cache_hits'])
        self.state.update(status='AWAITING_NEXT',detail='Đã trích xuất · chờ chuẩn hóa và Qwen',metadata_version=report['workflow_fingerprint'])
        self._save('Hoàn tất trích xuất tài liệu')

    def begin_document(self,latest,limit,rules_only):
        previous=self.state
        parent=controller()
        handoff=(previous.get('status') in {'AWAITING_NEXT','PREPARING_MODEL'}
                 and previous.get('metadata_version')==latest.get('version')
                 and previous.get('controller')==parent)
        report=latest['report']
        if not handoff:
            self.begin(report.get('source_path',self.job.name))
            for key,_,_ in STAGES[:5]:self.stage(key,'cached',detail='Dùng dữ liệu trích xuất đã có')
        self.state.update(owner=owner(),controller=parent,status='RUNNING',rules_only=rules_only,
                          document_questions=report.get('question_count',0),review_limit=limit)
        self.state['counters'].update(pages=report.get('page_count'),questions=report.get('question_count'),
            table_regions=report.get('tables',{}).get('count'))
        self.stage('latex',done=0,total=report.get('question_count',0),detail='Đang chuẩn hóa biểu thức',log=True)

    def document_event(self,message):
        if message=='[pipeline] text-to-latex':self.stage('latex',detail='Chuẩn hóa text và kiểm cấu trúc nguồn',log=True)
        elif message=='[pipeline] qwen-review':
            total=self.state.get('document_questions',0);scope=min(self.state.get('review_limit') or total,total)
            self.stage('review',done=0,total=scope,detail='Qwen đang rà soát metadata',log=True)
        elif message=='[pipeline] export':self.stage('export',done=0,total=3,detail='Đang ghi file và dựng trang kết quả',log=True)
        else:
            match=re.match(r'\[(latex|review)/done\] (\d+)/(\d+)',message)
            if match:self.stage(match[1],done=int(match[2]),total=int(match[3]),detail='Đã quét qua metadata câu' if match[1]=='latex' else 'Đã phân loại câu trong lượt')
            elif message.startswith(('[latex/qwen]','[qwen]')):
                position=re.match(r'\[latex/qwen\] (\d+)/(\d+)',message)
                if position:
                    # Reaching item N proves items before N have finished; N is
                    # still in inference and must not be counted as complete.
                    self.stage('latex',done=max(0,int(position[1])-1),total=int(position[2]))
                if message.startswith('[qwen]'):
                    total=self.state.get('document_questions',0)
                    scope=min(self.state.get('review_limit') or total,total)
                    message=re.sub(r'(\d+)/\d+',lambda m:f'{m[1]}/{scope} trong lượt',message,count=1)
                self.state.update(current_model='Qwen3-VL-2B · local',detail=message.replace('[latex/qwen]','LaTeX ·').replace('[qwen]','Rà soát ·'))
                self._save(self.state['detail'])

    def latex_done(self,report):
        self.state['counters'].update(formula_candidates=report['formula_count'],
            normalized=report['status_counts'].get('NORMALIZED',0),latex_cache_hits=report['cache_hits'])
        self.stage('latex','completed',done=report['question_count'],total=report['question_count'],
                   detail=f"{report['status_counts'].get('NORMALIZED',0)} ứng viên được chuẩn hóa",log=True)

    def review_done(self,report):
        if report.get('status')=='SKIPPED':self.stage('review','skipped',detail='Không chạy Qwen trong lượt này',log=True);return
        selected=report['selected_count'];total=report['question_count']
        self.state['counters'].update(review_completed=report['completed_count'],review_selected=selected,
            review_deferred=report['status_counts'].get('DEFERRED',0),review_cache_hits=report['cache_hits'])
        self.stage('review','partial' if report['status']=='PARTIAL' else 'completed',done=selected,total=selected,
            detail=f"{report['completed_count']}/{selected} phản hồi hợp lệ · {max(0,total-selected)} câu ngoài lượt",log=True)

    def finish(self,report):
        self.stage('export','completed',done=3,total=3,detail='File cuối và trang xem đã sẵn sàng',log=True)
        self.state.update(status='COMPLETED_PARTIAL' if report['status']!='DRAFT_READY' else 'COMPLETED',
            detail='Đã xuất bản nháp · còn phần cần xử lý' if report['status']!='DRAFT_READY' else 'Đã xuất bản nháp',
            finished_at=now(),result=str(self.job/'final.json'),current_model=None)
        self._save(self.state['detail'])

    def fail(self,error):
        if not self.state or self.state.get('owner',{}).get('pid')!=os.getpid():return
        self.state.update(status='INTERRUPTED' if isinstance(error,KeyboardInterrupt) else 'FAILED',
            detail='Lượt xử lý đã dừng · dữ liệu và checkpoint được giữ',error_type=type(error).__name__,finished_at=now())
        active=next((s for s in self.state['stages'] if s['id']==self.state.get('active_stage')),None)
        if active:active['status']='failed'
        self._save(self.state['detail'])


def preparing_model(job):
    progress=Progress(job)
    if not progress.state:return
    progress.state.update(status='PREPARING_MODEL',detail='Đang nạp Qwen local',owner=controller())
    progress._save('Chuẩn bị model Qwen local')
