"""Generate explicitly synthetic ink for mechanical QA, never accuracy evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image,ImageDraw
from .model import UPSTREAM

def make(destination:Path,upstream:Path=UPSTREAM):
    if destination.exists() and any(destination.iterdir()): raise ValueError('Smoke destination must be empty')
    destination.mkdir(parents=True,exist_ok=True);rows=[]
    for i,split in enumerate(('train','train','val','test')):
        image=Image.new('L',(128,256));d=ImageDraw.Draw(image);offset=i*2
        d.line([(20+offset,24),(70+offset,100)],fill=255,width=5)
        d.line([(70+offset,24),(20+offset,100)],fill=255,width=5)
        p=destination/f'smoke-{i}.png';image.save(p)
        rows.append({'sample_id':f'smoke-{i}','writer_id':f'writer_synthetic_{i}',
                     'image_path':p.name,'image_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                     'latex_verbatim':'x','split':split,'source':'synthetic_smoke',
                     'review_status':'APPROVED','usage_permission':'GRANTED','media_permission':'GRANTED',
                     'preprocess_version':'ink-on-0.1.0-frozen-v1','content_height':128,'content_width':120})
    (destination/'manifest.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    config={'manifest':str((destination/'manifest.jsonl').resolve()),'output':str((destination/'run').resolve()),
            'upstream':str(upstream.resolve()),'epochs':1,'batch_size':2,'accumulate':2,'max_decode_tokens':8,
            'freeze_encoder_epochs':1,'device':'cpu','amp':False,'media_samples':1,
            'wandb':{'mode':'offline','project':'coach-learning-comer-qa','name':'synthetic-smoke-only'}}
    (destination/'config.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    print('Synthetic smoke only:',destination)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--upstream',type=Path,default=UPSTREAM);a=p.parse_args();make(a.output,a.upstream)
