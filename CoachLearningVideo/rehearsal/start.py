import json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).parent;REPO=Path('D:/SGU/DuAn/Coach_Learning')
p=json.loads((ROOT/'private.json').read_text(encoding='utf-8'))
base=os.environ.copy();base.update(json.loads((ROOT/'environment.json').read_text(encoding='utf-8')))
base.update({'COACH_LAN_MODE':'0','LIVE_INK_ORIGINS':'http://127.0.0.1:3150,http://localhost:3150'})
def start(name,args,cwd,env):
 out=(ROOT/(name+'.log')).open('wb');err=(ROOT/(name+'-errors.log')).open('wb')
 proc=subprocess.Popen(args,cwd=cwd,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
 (ROOT/(name+'.pid')).write_text(str(proc.pid));return proc.pid
backend=start('backend',[str(REPO/'backend/.venv/Scripts/python.exe'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8050','--workers','1','--ws-max-size','300000'],REPO/'backend',base)
front=base.copy();front.update({'API_BASE_URL':'http://127.0.0.1:8050','AUTH_SESSION_SECRET':p['session_secret'],'NEXT_DIST_DIR':'.next-video-rehearsal','OCR_V2_EXPERIMENTAL':'0','SESSION_COOKIE_SECURE':'false','SELF_STUDY_PUBLISHED_SUBJECT_CODES':'MATH_G12'})
ts=REPO/'frontend/tsconfig.json';(ROOT/'tsconfig-before.json').write_bytes(ts.read_bytes())
frontend=start('frontend',['node',str(REPO/'frontend/node_modules/next/dist/bin/next'),'dev','--hostname','127.0.0.1','--port','3150'],REPO/'frontend',front)
print('Rehearsal services started on frontend 3150 / backend 8050; private settings omitted.')
