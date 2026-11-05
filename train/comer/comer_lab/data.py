"""Strict local handwriting manifests, tokenization and writer-disjoint checks."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import numpy as np
from PIL import Image

TOKEN = re.compile(r'\\[A-Za-z]+|\\.|[^\s]')

def tokenize(latex: str, word2idx: dict[str,int]) -> list[int]:
    # Apostrophe is only a spelling alias for the same visible prime symbol.
    text=latex.replace("'",r'\prime')
    tokens=TOKEN.findall(text)
    if not tokens or len(tokens)>180:
        raise ValueError('Expected 1–180 formula tokens')
    unknown=sorted(set(tokens)-set(word2idx))
    if unknown:
        raise ValueError('Unsupported vocabulary tokens: '+', '.join(unknown))
    return [word2idx[t] for t in tokens]

def safe_path(root: Path, relative: str) -> Path:
    root=root.resolve();p=(root/relative).resolve()
    if Path(relative).is_absolute() or not p.is_relative_to(root):
        raise ValueError('DATA_PATH_ESCAPE')
    return p

def read_manifest(path: Path, vocab: dict, *, allow_smoke: bool=False) -> list[dict]:
    root=path.resolve().parent
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not rows: raise ValueError('Empty handwriting manifest')
    ids=set();hashes={};writers={}
    for row in rows:
        for field in ('sample_id','writer_id','image_path','image_sha256','latex_verbatim','split','source'):
            if not isinstance(row.get(field),str) or not row[field].strip():
                raise ValueError('Missing field: '+field)
        if row['sample_id'] in ids: raise ValueError('DUPLICATE_SAMPLE_ID')
        ids.add(row['sample_id'])
        if row['split'] not in ('train','val','test'): raise ValueError('INVALID_SPLIT')
        if row.get('review_status')!='APPROVED': raise ValueError('UNREVIEWED_LABEL')
        if row.get('usage_permission')!='GRANTED': raise ValueError('TRAINING_PERMISSION_MISSING')
        if row['source']=='synthetic_smoke' and not allow_smoke: raise ValueError('SMOKE_DATA_NOT_TRAINING_EVIDENCE')
        image=safe_path(root,row['image_path'])
        data=image.read_bytes();digest=hashlib.sha256(data).hexdigest()
        if digest!=row['image_sha256']: raise ValueError('IMAGE_HASH_MISMATCH')
        with Image.open(image) as im:
            w,h=im.size
            if h!=256 or w<128 or w>1024 or w%64: raise ValueError('PREPROCESS_SHAPE_MISMATCH')
            if im.mode!='L' or im.format!='PNG': raise ValueError('EXPECTED_GRAYSCALE_PNG_MODEL_INPUT')
            pixels=np.asarray(im)
        ch,cw=row.get('content_height'),row.get('content_width')
        if type(ch) is not int or type(cw) is not int or not (1<=ch<=128 and 1<=cw<=w):
            raise ValueError('INVALID_PADDING_MASK')
        if not np.any(pixels[:ch,:cw]): raise ValueError('EMPTY_INK_IMAGE')
        if np.any(pixels[ch:,:]) or np.any(pixels[:ch,cw:]): raise ValueError('NONZERO_PADDING_PIXELS')
        if row.get('preprocess_version')!='ink-on-0.1.0-frozen-v1': raise ValueError('PREPROCESS_VERSION_MISMATCH')
        row['_tokens']=tokenize(row['latex_verbatim'],vocab['word2idx'])
        row['_image']=image
        if digest in hashes:
            raise ValueError('IMAGE_SPLIT_LEAKAGE' if hashes[digest]!=row['split'] else 'DUPLICATE_IMAGE')
        hashes[digest]=row['split']
        writer=row['writer_id']
        if writer in writers and writers[writer]!=row['split']: raise ValueError('WRITER_SPLIT_LEAKAGE')
        writers[writer]=row['split']
    return rows

def input_array(row: dict):
    with Image.open(row['_image']) as image:
        arr=np.asarray(image,dtype=np.float32)/255.0
    mask=np.ones(arr.shape,dtype=bool)
    mask[:row['content_height'],:row['content_width']]=False
    return arr,mask

def edit_distance(a,b):
    previous=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        current=[i]
        for j,y in enumerate(b,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(x!=y)))
        previous=current
    return previous[-1]

def manifest_summary(rows):
    def count(split):
        r=[v for v in rows if v['split']==split]
        return {'samples':len(r),'writers':len({v['writer_id'] for v in r}),
                'families':len({v['expression_family_id'] for v in r if v.get('expression_family_id')})}
    family_sets={s:{r.get('expression_family_id') for r in rows if r['split']==s and r.get('expression_family_id')} for s in ('train','val','test')}
    return {'splits':{s:count(s) for s in ('train','val','test')},
            'family_overlap':{a+'_'+b:len(family_sets[a]&family_sets[b]) for a,b in [('train','val'),('train','test'),('val','test')]},
            'claim':'writer-disjoint; expression-family overlap is separately reported'}
