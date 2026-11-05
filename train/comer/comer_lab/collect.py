"""Loopback-only paired-ink collector using the app's exact frozen preprocessor."""
from __future__ import annotations
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler,HTTPServer
from io import BytesIO
import json
from pathlib import Path
import re
import secrets
import uuid
from PIL import Image
from .data import safe_path,tokenize

ROOT=Path(__file__).resolve().parents[3]

def store_sample(folder,payload,vocab):
    writer=payload.get('writer_id','')
    if not re.fullmatch(r'writer_[a-z0-9_-]{1,32}',writer): raise ValueError('Use anonymous writer_id, e.g. writer_001')
    split=payload.get('split')
    if split not in ('train','val','test'): raise ValueError('Invalid split')
    label=payload.get('latex_verbatim','')
    tokenize(label,vocab['word2idx'])
    if payload.get('reviewed') is not True or payload.get('training_permission') is not True:
        raise ValueError('Confirm the label and permission before saving')
    data=base64.b64decode(payload['png_base64'],validate=True)
    with Image.open(BytesIO(data)) as im:
        w,h=im.size
        if h!=256 or not 128<=w<=1024 or w%64: raise ValueError('Invalid frozen tensor shape')
        im.load()
        im=im.convert('L');buf=BytesIO();im.save(buf,format='PNG');data=buf.getvalue()
    ch,cw=payload.get('content_height'),payload.get('content_width')
    if type(ch) is not int or type(cw) is not int or not (1<=ch<=128 and 1<=cw<=w): raise ValueError('Invalid mask')
    strokes=payload.get('model_strokes')
    if not isinstance(strokes,list) or not strokes: raise ValueError('Missing source strokes')
    manifest=folder/'manifest.jsonl'
    old=manifest.read_text(encoding='utf-8') if manifest.exists() else ''
    digest=hashlib.sha256(data).hexdigest()
    for row in [json.loads(line) for line in old.splitlines() if line.strip()]:
        if row['writer_id']==writer and row['split']!=split: raise ValueError('WRITER_SPLIT_LEAKAGE: this writer belongs to '+row['split'])
        if row['image_sha256']==digest: raise ValueError('Duplicate ink image')
    sid='ink_'+uuid.uuid4().hex
    folder.mkdir(parents=True,exist_ok=True);(folder/'images').mkdir(exist_ok=True);(folder/'strokes').mkdir(exist_ok=True)
    (folder/'images'/f'{sid}.png').write_bytes(data)
    (folder/'strokes'/f'{sid}.json').write_text(json.dumps(strokes)+'\n',encoding='utf-8')
    row={'sample_id':sid,'writer_id':writer,'image_path':f'images/{sid}.png','image_sha256':digest,
         'strokes_path':f'strokes/{sid}.json','latex_verbatim':label,'split':split,
         'source':'coach_canvas_collector','review_status':'APPROVED','usage_permission':'GRANTED',
         'media_permission':'GRANTED' if payload.get('media_permission') is True else 'NOT_GRANTED',
         'content_height':ch,'content_width':cw,'preprocess_version':'ink-on-0.1.0-frozen-v1',
         'expression_family_id':payload.get('expression_family_id','')}
    tmp=manifest.with_suffix('.tmp');tmp.write_text(old+json.dumps(row,ensure_ascii=False)+'\n',encoding='utf-8');tmp.replace(manifest)
    return {'saved':sid,'total':len(old.splitlines())+1}

def serve(folder:Path,port:int,ocr_assets:Path):
    folder=folder.resolve();ocr_assets=ocr_assets.resolve()
    expected='4d590a0f30cd0f4840c5cfe1a57dfb32e462e3dfdda0b37d438ede2d6420675f'
    # Git may check JS out with CRLF on Windows and LF on Kaggle/Linux.
    content=(ocr_assets/'ink-on/chunks/inference-4T2UM6yg.js').read_bytes().replace(b'\r\n',b'\n')
    actual=hashlib.sha256(content).hexdigest()
    if actual!=expected: raise ValueError('Preprocessor changed: define and validate a new preprocessing version before collecting')
    vocab=json.loads((ocr_assets/'comer/v0_1/vocab.json').read_text(encoding='utf-8'))
    token=secrets.token_urlsafe(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def send(self,status,body,mime):
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
            self.end_headers();self.wfile.write(body)
        def do_GET(self):
            try:
                if self.path=='/': return self.send(200,Path(__file__).with_name('collector.html').read_bytes(),'text/html; charset=utf-8')
                if self.path=='/api/config': return self.send(200,json.dumps({'token':token}).encode(),'application/json')
                if self.path.startswith('/ocr/'):
                    p=safe_path(ocr_assets,self.path[len('/ocr/'):])
                    if not p.is_file(): raise FileNotFoundError()
                    mime='text/javascript' if p.suffix in ('.js','.mjs') else 'application/wasm' if p.suffix=='.wasm' else 'application/json'
                    return self.send(200,p.read_bytes(),mime)
                raise FileNotFoundError()
            except (ValueError,FileNotFoundError): self.send(404,b'Not found','text/plain')
        def do_POST(self):
            try:
                if self.path!='/api/sample' or self.headers.get('X-Collector-Token')!=token:
                    return self.send(403,b'Forbidden','text/plain')
                n=int(self.headers.get('Content-Length',0))
                if not 0<n<=2_000_000: raise ValueError('Payload too large')
                result=store_sample(folder,json.loads(self.rfile.read(n)),vocab)
                self.send(200,json.dumps(result).encode(),'application/json')
            except (ValueError,KeyError,OSError) as e: self.send(400,json.dumps({'error':str(e)}).encode(),'application/json')
    print(f'Collector: http://127.0.0.1:{port} | local data: {folder}',flush=True)
    HTTPServer(('127.0.0.1',port),Handler).serve_forever()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=Path('data/collection'))
    p.add_argument('--port',type=int,default=8778);p.add_argument('--ocr-assets',type=Path,default=ROOT/'frontend/public/ocr')
    a=p.parse_args();serve(a.output,a.port,a.ocr_assets)
