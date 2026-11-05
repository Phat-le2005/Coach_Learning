"""Evaluate a selected checkpoint on test without changing the training run."""
import argparse
import json
from pathlib import Path
import torch
from .model import load_model,UPSTREAM
from .data import read_manifest
from .train import evaluate,fingerprint,json_write,METRIC_CONTRACT

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--upstream',type=Path,default=UPSTREAM)
    p.add_argument('--device',default='cuda');p.add_argument('--max-decode-tokens',type=int,default=192)
    p.add_argument('--smoke',action='store_true');a=p.parse_args()
    if a.output.exists(): raise ValueError('Evaluation output exists; keep previous test records')
    torch.set_num_threads(4)
    model,vocab,_=load_model(a.checkpoint,a.upstream);vocabulary={'word2idx':vocab.word2idx}
    rows=read_manifest(a.manifest,vocabulary,allow_smoke=a.smoke)
    state=torch.load(a.checkpoint,map_location='cpu',weights_only=True)
    if state.get('dataset_fingerprint')!=fingerprint(rows): raise ValueError('Checkpoint/dataset fingerprint mismatch')
    tests=sorted([r for r in rows if r['split']=='test'],key=lambda r:r['sample_id'])
    model.to(a.device)
    metrics,predictions=evaluate(model,tests,vocabulary,torch.device(a.device),a.max_decode_tokens)
    result={'split':'test','metrics':metrics,'predictions':predictions,'metric_contract':METRIC_CONTRACT,
            'checkpoint':a.checkpoint.name,'epoch':state['epoch'],'smoke_only':a.smoke}
    a.output.parent.mkdir(parents=True,exist_ok=True);json_write(a.output,result);print(json.dumps(metrics))

if __name__=='__main__': main()
