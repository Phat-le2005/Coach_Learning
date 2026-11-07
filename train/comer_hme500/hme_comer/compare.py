"""Paired before/after evaluation: frozen initial weights and validation-selected best.pt."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import torch
from PIL import Image
from .data import audit,resolve_metadata,PREPROCESS,configure_preprocess
from .metrics import evaluate,CONTRACT
from .model import load_model,UPSTREAM
from .tracking import write_json,bundle,log_predictions,prepare_wandb


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs(output,qa):
    output=Path(output);cfg=json.loads((output/'config.json').read_text())
    rows,report=audit(resolve_metadata(cfg['data']))
    method=configure_preprocess(rows,cfg,report)
    initial=torch.load(output/'initial.pt',map_location='cpu',weights_only=True)
    best=torch.load(output/'best.pt',map_location='cpu',weights_only=True)
    if initial.get('format')!='coach-hme500-initial-v1' or best.get('format')!='coach-hme500-v1':raise ValueError('COMPARISON_CHECKPOINT_FORMAT')
    if initial['qa_only']!=qa or best['qa_only']!=qa:raise ValueError('COMPARISON_QA_MISMATCH')
    if any(s['dataset_fingerprint']!=report['fingerprint'] for s in (initial,best)):raise ValueError('COMPARISON_DATASET_CHANGED')
    if sha(output/'initial.pt')!=best.get('initial_checkpoint_sha256'):raise ValueError('COMPARISON_INITIAL_SNAPSHOT_MISMATCH')
    if initial['vocabulary']!=best['vocabulary']:raise ValueError('COMPARISON_VOCABULARY_CHANGED')
    if initial.get('preprocess',PREPROCESS)!=method or best['training_signature'].get('preprocess',PREPROCESS)!=method:
        raise ValueError('COMPARISON_PREPROCESS_CHANGED')
    selected=sorted([r for r in rows if r['split']==('validation' if qa else 'test')],key=lambda r:r['id'])
    if qa:selected=selected[:2]
    for r in selected:r['_tokens']=[initial['vocabulary'][t] for t in r['_words']]
    return cfg,selected,report,best


def worker(output,stage,device,qa=False):
    output=Path(output);cfg,rows,report,best=inputs(output,qa)
    checkpoint=output/('initial.pt' if stage=='before' else 'best.pt')
    path=output/f'comparison-{stage}.json'
    contract=dict(checkpoint_sha256=sha(checkpoint),dataset_fingerprint=report['fingerprint'],
                  ids=[r['id'] for r in rows],qa_only=qa,max_decode_tokens=cfg['max_decode_tokens'])
    # Old v1/v2/v3 saved records omitted this key; their original method is fixed.
    if cfg.get('preprocess',PREPROCESS)!=PREPROCESS:contract['preprocess']=cfg['preprocess']
    if path.exists():
        old=json.loads(path.read_text())
        if any(old.get(k)!=v for k,v in contract.items()):raise ValueError('SAVED_COMPARISON_PART_CHANGED')
        return
    torch.set_num_threads(2)
    if str(device).startswith('cuda'):torch.cuda.set_device(torch.device(device))
    model,vocab,_=load_model(checkpoint,Path(cfg.get('upstream',UPSTREAM)))
    model.to(device)
    metrics,predictions,groups=evaluate(model,rows,vocab.word2idx,torch.device(device),cfg['max_decode_tokens'])
    write_json(path,{**contract,'stage':stage,'split':'validation-qa' if qa else 'test','device':device,
        'metrics':metrics,'predictions':predictions,'groups':groups,'epoch':0 if stage=='before' else best['epoch']})
    print(f'{stage} evaluation: '+json.dumps(metrics),flush=True)


def paired(before,after):
    if before['ids']!=after['ids'] or before['dataset_fingerprint']!=after['dataset_fingerprint']:
        raise ValueError('COMPARISON_SAMPLES_NOT_PAIRED')
    result=[]
    for b,a in zip(before['predictions'],after['predictions']):
        if b['id']!=a['id'] or b['latex']!=a['latex'] or b['target']!=a['target']:raise ValueError('COMPARISON_LABEL_CHANGED')
        outcome=('improved' if a['exact'] else 'regressed') if a['exact']!=b['exact'] else ('both_correct' if a['exact'] else 'both_wrong')
        result.append(dict(id=b['id'],group=b['group'],latex=b['latex'],before=b['prediction'],after=a['prediction'],
            before_exact=b['exact'],after_exact=a['exact'],before_cer=b['cer'],after_cer=a['cer'],outcome=outcome))
    delta={k:after['metrics'][k]-before['metrics'][k] for k in ('loss','exp_rate','cer','token_error_rate')}
    return result,delta


def plots(output,before,after):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(12,4))
    for ax,key,title in zip(axes,('exp_rate','cer','token_error_rate'),('Exact match (higher is better)','CER (lower is better)','Token error (lower is better)')):
        vals=[before['metrics'][key],after['metrics'][key]]
        ax.bar(['Before fine-tune','After fine-tune'],vals,color=['#72849a','#288f74'])
        for i,v in enumerate(vals):ax.text(i,v,f'{v:.4f}',ha='center',va='bottom')
        ax.set_title(title);ax.grid(axis='y',alpha=.2)
    fig.suptitle('CoMER HME500 | paired samples, same vocabulary / preprocessing / decoder')
    fig.tight_layout();fig.savefig(output/'comparison.png',dpi=160);plt.close(fig)


def compare(output,device='cuda:0',qa=False):
    output=Path(output).resolve()
    if (output/'comparison.json').exists():raise ValueError('COMPARISON_ALREADY_SAVED: use --sync-only to upload it')
    cfg,rows,report,best=inputs(output,qa)
    # The two fixed model evaluations are independent and can use one GPU each.
    devices=['cuda:0','cuda:1'] if str(device).startswith('cuda') and cfg['devices']==2 else [device,device]
    if devices==['cuda:0','cuda:1']:
        if torch.cuda.device_count()<2:raise RuntimeError('The two-GPU comparison requires two visible CUDA devices.')
        processes=[]
        try:
            for stage,d in zip(('before','after'),devices):
                args=[sys.executable,'-m','hme_comer.compare','--output',str(output),'--worker',stage,'--device',d]
                if qa:args+=['--qa']
                processes.append(subprocess.Popen(args))
            codes=[p.wait() for p in processes]
            if any(codes):raise RuntimeError('A comparison worker failed; saved successful parts are retained.')
        finally:
            for p in processes:
                if p.poll() is None:p.terminate()
    else:
        for stage,d in zip(('before','after'),devices):worker(output,stage,d,qa)
    before=json.loads((output/'comparison-before.json').read_text());after=json.loads((output/'comparison-after.json').read_text())
    pairs,delta=paired(before,after)
    result=dict(qa_only=qa,split=before['split'],samples=len(rows),dataset_fingerprint=report['fingerprint'],
        before=before['metrics'],after=after['metrics'],delta_after_minus_before=delta,
        checkpoint_sha256={'before':before['checkpoint_sha256'],'after':after['checkpoint_sha256']},
        transitions={k:sum(p['outcome']==k for p in pairs) for k in ('improved','regressed','both_correct','both_wrong')},
        pairs=pairs,metric_contract={**CONTRACT,'preprocess':cfg.get('preprocess',PREPROCESS)},
        baseline='Exact initial snapshot before any optimizer step; same train-fitted vocabulary, including new initialized tokens.')
    write_json(output/'comparison.json',result)
    with (output/'comparison.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(pairs[0]));w.writeheader();w.writerows(pairs)
    with (output/'comparison-summary.csv').open('w',newline='',encoding='utf-8') as f:
        fields=['stage','samples','loss','exp_rate','cer','token_error_rate']
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader()
        for stage,p in (('before',before),('after',after)):w.writerow({'stage':stage,**p['metrics']})
    plots(output,before,after)
    summary=json.loads((output/'summary.json').read_text())
    summary.update(test_evaluated=not qa,comparison=result if qa else {k:v for k,v in result.items() if k!='pairs'})
    write_json(output/'summary.json',summary);bundle(output)
    sync(output)
    print('Before/after evidence:',output/'comparison.png',flush=True)


def sync(output):
    output=Path(output);cfg=json.loads((output/'config.json').read_text())
    result=json.loads((output/'comparison.json').read_text())
    if cfg['wandb']['mode']=='disabled':return
    if cfg['wandb']['mode']=='online' and not os.environ.get('WANDB_API_KEY'):
        try:
            from kaggle_secrets import UserSecretsClient
            os.environ['WANDB_API_KEY']=UserSecretsClient().get_secret('WANDB_API_KEY')
        except Exception:raise RuntimeError('Enable WANDB_API_KEY to upload the saved comparison.') from None
    prepare_wandb(output)
    import wandb
    _,rows,_,_=inputs(output,result['qa_only'])
    info=json.loads((output/'run.json').read_text());links={}
    for stage in ('before','after'):
        part=json.loads((output/f'comparison-{stage}.json').read_text())
        run_id=hashlib.sha256((info['id']+stage).encode()).hexdigest()[:16]
        run=wandb.init(project=cfg['wandb']['project'],entity=info['entity'],name=info['name']+'-'+stage,
            id=run_id,group=cfg['wandb']['group'],mode=cfg['wandb']['mode'],dir=str(output),
            resume='allow' if cfg['wandb']['mode']=='online' else None,
            job_type='qa-prepost' if result['qa_only'] else 'prepost-evaluation',
            config={**cfg,'evaluation_stage':stage,'parent_run_id':info['id'],'checkpoint_sha256':part['checkpoint_sha256'],
                    'qa_only':result['qa_only'],'dataset_fingerprint':result['dataset_fingerprint'],
                    'baseline_definition':result['baseline'],'metric_contract':CONTRACT},
            settings=wandb.Settings(disable_code=True,disable_git=True,console='off'))
        ok=False
        try:
            log_predictions(run,cfg,part['metrics'],part['predictions'],part['groups'],rows,part['epoch'],
                            split='validation' if result['qa_only'] else 'test')
            run.log({'evaluation/'+k:v for k,v in part['metrics'].items()})
            run.summary.update({'evaluation/'+k:v for k,v in part['metrics'].items()})
            if stage=='after':
                table=wandb.Table(columns=['id','original_image','latex','before','after','before_exact','after_exact','outcome'])
                images={r['id']:r['_image'] for r in rows}
                for p in result['pairs']:
                    picture=None
                    if cfg['wandb']['log_images']:
                        with Image.open(images[p['id']]) as im:picture=wandb.Image(im.copy())
                    table.add_data(p['id'],picture,p['latex'],p['before'],p['after'],p['before_exact'],p['after_exact'],p['outcome'])
                run.log({'comparison/paired_predictions':table,'comparison/chart':wandb.Image(str(output/'comparison.png')),
                         **{'comparison/delta_'+k:v for k,v in result['delta_after_minus_before'].items()}})
                artifact=wandb.Artifact('hme500-prepost-'+info['id'],type='evaluation',metadata={'qa_only':result['qa_only']})
                for n in ('comparison.json','comparison-before.json','comparison-after.json','comparison.csv','comparison-summary.csv','comparison.png'):
                    artifact.add_file(str(output/n),name=n)
                run.log_artifact(artifact,aliases=['paired'])
            links[stage]={'id':run_id,'url':run.url if cfg['wandb']['mode']=='online' else None}
            ok=True
        finally:run.finish(exit_code=0 if ok else 1)
    write_json(output/'comparison-wandb.json',links);bundle(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--device',default='cuda:0');p.add_argument('--qa',action='store_true');p.add_argument('--sync-only',action='store_true')
    p.add_argument('--worker',choices=('before','after'));a=p.parse_args()
    if a.worker:worker(a.output,a.worker,a.device,a.qa)
    elif a.sync_only:sync(a.output)
    else:compare(a.output,a.device,a.qa)
