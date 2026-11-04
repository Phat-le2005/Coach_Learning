from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import build_opener,ProxyHandler

from . import preparing_model
from .server import create_server,root_id


def health(port):
    try:
        with build_opener(ProxyHandler({})).open(f'http://127.0.0.1:{port}/api/health',timeout=.5) as response:
            return json.load(response)
    except (URLError,OSError,ValueError):return None


def ensure(root,runtime,port):
    root,runtime=Path(root).resolve(),Path(runtime).resolve();runtime.mkdir(parents=True,exist_ok=True)
    identity=root_id(root)
    for choice in range(port,port+10):
        if choice==8790:continue  # Reserved for the model server.
        state=health(choice)
        if state and state.get('service')=='pdf-progress/v1' and state.get('root_id')==identity:
            if state.get('pid'):
                (runtime/'progress-server.json').write_text(json.dumps({'pid':state['pid'],'port':choice,'root_id':identity}),encoding='utf-8')
            return f'http://127.0.0.1:{choice}/'
        import socket
        with socket.socket() as probe:
            try:probe.bind(('127.0.0.1',choice))
            except OSError:continue
        command=[sys.executable,'-B','-u','-m','pdfmeta.progress','serve','--root',str(root),'--runtime',str(runtime),'--port',str(choice)]
        with (runtime/'progress-server.log').open('ab') as log:
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                start_new_session=os.name!='nt')
        for _ in range(30):
            state=health(choice)
            if state and state.get('root_id')==identity:
                (runtime/'progress-server.json').write_text(json.dumps({'pid':state.get('pid',process.pid),'port':choice,'root_id':identity}),encoding='utf-8')
                return f'http://127.0.0.1:{choice}/'
            if process.poll() is not None:break
            time.sleep(.1)
    raise ValueError('PROGRESS_SERVER_PORTS_UNAVAILABLE')


def main():
    parser=argparse.ArgumentParser(description='Local PDF progress dashboard')
    parser.add_argument('action',choices=['serve','ensure','model-loading'])
    parser.add_argument('--root',type=Path);parser.add_argument('--runtime',type=Path)
    parser.add_argument('--port',type=int,default=8789);parser.add_argument('--job',type=Path)
    args=parser.parse_args()
    if args.action=='model-loading':preparing_model(args.job);return
    if not args.root or not args.runtime:parser.error('--root and --runtime are required')
    if args.action=='ensure':print(ensure(args.root,args.runtime,args.port));return
    with create_server(args.root,args.runtime,args.port) as server:
        print(f'PDF progress: http://127.0.0.1:{server.server_port}/',flush=True);server.serve_forever()


if __name__=='__main__':main()
