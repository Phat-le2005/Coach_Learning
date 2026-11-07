"""Evaluate best.pt once after freezing the experiment; log test evidence separately."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import torch
from .data import audit, resolve_metadata
from .metrics import evaluate, CONTRACT
from .model import load_model, UPSTREAM
from .tracking import write_json, log_predictions, bundle, prepare_wandb


def final_test(output,upstream=UPSTREAM,device='cuda:0'):
    output=Path(output).resolve()
    marker=output/'final-test.json'
    if marker.exists(): raise ValueError('FINAL_TEST_ALREADY_RECORDED: do not overwrite the held-out record')
    cfg=json.loads((output/'config.json').read_text())
    rows,report=audit(resolve_metadata(cfg['data']))
    checkpoint=output/'best.pt'
    state=torch.load(checkpoint,map_location='cpu',weights_only=True)
    if state.get('format')!='coach-hme500-v1' or state.get('qa_only'): raise ValueError('FINAL_TEST_REQUIRES_FULL_TRAINING_CHECKPOINT')
    if state['dataset_fingerprint']!=report['fingerprint']: raise ValueError('TEST_DATASET_CHANGED')
    model,vocab,_=load_model(checkpoint,Path(upstream))
    tests=sorted([r for r in rows if r['split']=='test'],key=lambda r:r['id'])
    for r in tests:
        if set(r['_words'])-set(vocab.word2idx): raise ValueError('UNKNOWN_TEST_TOKEN')
        r['_tokens']=[vocab.word2idx[t] for t in r['_words']]
    torch.set_num_threads(min(4,os.cpu_count() or 1));model.to(device)
    metrics,predictions,groups=evaluate(model,tests,vocab.word2idx,torch.device(device),cfg['max_decode_tokens'])
    result={'split':'test','metrics':metrics,'groups':groups,'predictions':predictions,'epoch':state['epoch'],
            'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            'dataset_fingerprint':report['fingerprint'],'metric_contract':CONTRACT}
    # Save the held-out result before trying a network sync, so a network error never reruns inference.
    write_json(marker,result)
    summary=json.loads((output/'summary.json').read_text());summary.update(test_evaluated=True,test=metrics)
    write_json(output/'summary.json',summary);bundle(output)
    sync_test(output)
    print(json.dumps(metrics,indent=2))


def sync_test(output):
    """Retry a failed W&B upload without recomputing/overwriting held-out predictions."""
    output=Path(output)
    cfg=json.loads((output/'config.json').read_text())
    result=json.loads((output/'final-test.json').read_text())
    if cfg['wandb']['mode']=='disabled': return
    if cfg['wandb']['mode']=='online' and not os.environ.get('WANDB_API_KEY'):
        try:
            from kaggle_secrets import UserSecretsClient
            os.environ['WANDB_API_KEY']=UserSecretsClient().get_secret('WANDB_API_KEY')
        except Exception: raise RuntimeError('Enable Kaggle Secret WANDB_API_KEY to sync the saved test result.') from None
    prepare_wandb(output)
    import wandb
    info=json.loads((output/'run.json').read_text())
    if info['mode']!=cfg['wandb']['mode']: raise ValueError('WANDB_MODE_CHANGED')
    kwargs={'id':info['id'],'resume':'must'} if info['mode']=='online' else {'name':info['name']+'-heldout-test'}
    run=wandb.init(project=cfg['wandb']['project'],entity=info['entity'],mode=info['mode'],dir=str(output),
        job_type='heldout-evaluation',settings=wandb.Settings(disable_code=True,disable_git=True,console='off'),**kwargs)
    ok=False
    try:
        rows,_=audit(resolve_metadata(cfg['data']))
        log_predictions(run,cfg,result['metrics'],result['predictions'],result['groups'],rows,result['epoch'],split='test')
        run.summary.update({'test/'+k:v for k,v in result['metrics'].items()})
        artifact=wandb.Artifact('hme500-final-test-'+info['id'],type='evaluation',
            metadata={'checkpoint_sha256':result['checkpoint_sha256']})
        for name in ('final-test.json','summary.json','checksums.json'): artifact.add_file(str(output/name),name=name)
        run.log_artifact(artifact,aliases=['final']);ok=True
    finally: run.finish(exit_code=0 if ok else 1)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--upstream',type=Path,default=UPSTREAM);p.add_argument('--device',default='cuda:0')
    p.add_argument('--sync-only',action='store_true')
    a=p.parse_args()
    if a.sync_only: sync_test(a.output)
    else: final_test(a.output,a.upstream,a.device)
