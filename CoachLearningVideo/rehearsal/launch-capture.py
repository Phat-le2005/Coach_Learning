"""Restart only missing private rehearsal services; never alter the main app."""
import json,os,subprocess
from pathlib import Path
import socket
R=Path(__file__).parent
REPO=Path('D:/SGU/DuAn/Coach_Learning')
def listening(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(('127.0.0.1',port))==0
def launch(name,args,cwd,env):
    proc=subprocess.Popen(args,cwd=cwd,env=env,stdout=(R/(name+'.log')).open('wb'),stderr=(R/(name+'-errors.log')).open('wb'),creationflags=subprocess.CREATE_NO_WINDOW)
    (R/(name+'.pid')).write_text(str(proc.pid))
    print(name,'started')
if not listening(8050):
    env=os.environ.copy();env.update(json.loads((R/'environment.json').read_text()))
    env.update(COACH_LAN_MODE='0',LIVE_INK_ORIGINS='http://127.0.0.1:3150,http://localhost:3150')
    launch('backend',[str(REPO/'backend/.venv/Scripts/python.exe'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8050','--workers','1','--ws-max-size','300000'],REPO/'backend',env)
if not listening(3150):
    dest=REPO/'.tmp/video-capture-frontend'
    if not (dest/'.env.local').exists():raise SystemExit('Capture snapshot missing. Preserve private environment; do not use the main frontend.')
    env=os.environ.copy();env.pop('NEXT_DIST_DIR',None);env['API_BASE_URL']='http://127.0.0.1:8050'
    launch('frontend-d',['node',str(dest/'node_modules/next/dist/bin/next'),'dev','--webpack','--hostname','127.0.0.1','--port','3150'],dest,env)
print('Capture endpoints: frontend 3150, backend 8050; existing listeners preserved.')
