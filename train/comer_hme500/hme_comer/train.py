"""Fine-tune the pinned pretrained CoMER on real JPGs; test stays held out."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time

import numpy as np
import torch
from torch.utils.data import DataLoader
from .data import audit, fit_vocabulary, resolve_metadata, PREPROCESS
from .metrics import InkDataset, collate, teacher_loss, evaluate, CONTRACT
from .model import UPSTREAM, load_model, expand_vocabulary
from .tracking import write_json, init_run, log_predictions, append_history, log_model, bundle

ROOT=Path(__file__).resolve().parents[1]
DEFAULTS=json.loads((ROOT/'config.example.json').read_text())


def read_config(path):
    raw=json.loads(Path(path).read_text(encoding='utf-8'))
    if set(raw)-set(DEFAULTS)-{'upstream'}: raise ValueError('UNKNOWN_CONFIG_KEYS')
    cfg={**DEFAULTS,**raw}
    cfg['wandb']={**DEFAULTS['wandb'],**raw.get('wandb',{})}
    if set(cfg['wandb'])-set(DEFAULTS['wandb']): raise ValueError('UNKNOWN_WANDB_KEYS: use Secrets for credentials')
    for k in ('epochs','batch_size','accumulate','lr_patience','early_stopping_patience','max_decode_tokens','media_samples'):
        if type(cfg[k]) is not int or cfg[k]<1: raise ValueError('INVALID_'+k)
    if type(cfg['freeze_encoder_epochs']) is not int or cfg['freeze_encoder_epochs']<0: raise ValueError('INVALID_FREEZE_EPOCHS')
    if type(cfg['seed']) is not int or not 0<=cfg['seed']<2**32: raise ValueError('INVALID_SEED')
    for k in ('decoder_lr','encoder_lr','clip_grad_norm','weight_decay'):
        if type(cfg[k]) not in (int,float) or not math.isfinite(cfg[k]) or cfg[k]<0 or (k!='weight_decay' and cfg[k]==0):
            raise ValueError('INVALID_'+k)
    for k in ('data','output','device'):
        if not isinstance(cfg[k],str) or not cfg[k]: raise ValueError('INVALID_'+k)
    if type(cfg['amp']) is not bool: raise ValueError('INVALID_AMP')
    if cfg['wandb']['mode'] not in ('online','offline','disabled'): raise ValueError('INVALID_WANDB_MODE')
    for k in ('log_images','log_checkpoints'):
        if type(cfg['wandb'][k]) is not bool: raise ValueError('INVALID_WANDB_'+k)
    if cfg['max_decode_tokens']>256: raise ValueError('DECODE_LIMIT_TOO_LARGE')
    out=Path(cfg['output']).resolve()
    if out.is_relative_to(Path('/kaggle/input').resolve()): raise ValueError('KAGGLE_INPUT_IS_READ_ONLY: use /kaggle/working')
    return cfg


def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark=False
    torch.use_deterministic_algorithms(True,warn_only=True)


def signature(cfg):
    return {k:cfg[k] for k in DEFAULTS if k not in ('data','output','wandb','epochs','media_samples')}


def save_checkpoint(path,model,hparams,vocab,optimizer,scheduler,scaler,epoch,step,best,stale,cfg,digest,run_id,qa):
    rng=np.random.get_state()
    value=dict(format='coach-hme500-v1',state_dict=model.state_dict(),hyper_parameters=hparams,
        vocabulary=vocab,optimizer=optimizer.state_dict(),scheduler=scheduler.state_dict(),scaler=scaler.state_dict(),
        epoch=epoch,global_step=step,best=best,stale=stale,dataset_fingerprint=digest,
        training_signature=signature(cfg),wandb_id=run_id,qa_only=qa,
        torch_rng=torch.get_rng_state(),python_rng=random.getstate(),
        numpy_rng=(rng[0],rng[1].tolist(),rng[2],rng[3],rng[4]),
        cuda_rng=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [])
    tmp=path.with_suffix('.tmp');torch.save(value,tmp);tmp.replace(path)


def runtime_info(upstream,device,model):
    env={}
    for p in ('torch','torchvision','einops','pytorch-lightning','torchmetrics','numpy','Pillow','wandb','matplotlib'):
        try: env[p]=importlib.metadata.version(p)
        except importlib.metadata.PackageNotFoundError: env[p]='not-installed'
    env.update(python=sys.version,device=str(device),cuda=torch.version.cuda,
        gpu=torch.cuda.get_device_name(device) if device.type=='cuda' else None,
        parameters=sum(p.numel() for p in model.parameters()),preprocess=PREPROCESS)
    lock=json.loads((ROOT/'hme_comer/upstream.lock.json').read_text())
    cp=next(r['path'] for r in lock['files'] if r['path'].endswith('.ckpt'))
    env['upstream_commit']=lock['commit']
    env['pretrained_checkpoint_sha256']=hashlib.sha256((upstream/cp).read_bytes()).hexdigest()
    source_files=[*sorted((ROOT/'hme_comer').glob('*')), *sorted((ROOT/'scripts').glob('*.sh')),
                  ROOT/'kaggle_bootstrap.py', ROOT/'build_notebook.py']
    env['sources_sha256']={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source_files if p.is_file()}
    try: env['code_git_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError): env['code_git_revision']=None
    return env


def train(cfg,resume=None,qa=False):
    seed_all(cfg['seed']);torch.set_num_threads(min(4,os.cpu_count() or 1))
    device=torch.device(cfg['device'])
    if device.type=='cuda' and not torch.cuda.is_available(): raise RuntimeError('Enable a Kaggle GPU, or set device=cpu for local QA.')
    metadata=resolve_metadata(cfg['data']);rows,report=audit(metadata)
    upstream=Path(cfg.get('upstream',UPSTREAM))
    model,base,hparams=load_model(upstream=upstream)
    vocabulary,added=fit_vocabulary(rows,base.word2idx)
    expand_vocabulary(model,base,vocabulary)
    report.update(base_vocabulary_size=len(base.word2idx),vocabulary_size=len(vocabulary),
                  added_train_tokens=added,vocabulary_fit_split='train only',qa_only=qa)
    trains=sorted([r for r in rows if r['split']=='train'],key=lambda r:r['id'])
    vals=sorted([r for r in rows if r['split']=='validation'],key=lambda r:r['id'])
    if qa: trains=trains[:4];vals=vals[:2]
    report['executed_splits']={'train':len(trains),'validation':len(vals),'test':0}
    if cfg['max_decode_tokens']<=max(len(r['_tokens']) for r in trains+vals) and not qa:
        raise ValueError('DECODE_LIMIT_SHORTER_THAN_LABELS')
    out=Path(cfg['output']).resolve()
    if out==metadata.parent or out.is_relative_to(metadata.parent): raise ValueError('OUTPUT_MUST_NOT_MODIFY_INPUT_DATASET')
    if out.exists() and any(out.iterdir()) and not resume: raise ValueError('OUTPUT_EXISTS: choose a new output or --resume last.pt')
    out.mkdir(parents=True,exist_ok=True)
    model.to(device)
    optimizer=torch.optim.AdamW([{'params':model.encoder.parameters(),'lr':cfg['encoder_lr']},
        {'params':model.decoder.parameters(),'lr':cfg['decoder_lr']}],weight_decay=cfg['weight_decay'])
    scheduler=torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer,mode='min',factor=.5,patience=cfg['lr_patience'])
    scaler=torch.amp.GradScaler('cuda',enabled=cfg['amp'] and device.type=='cuda')
    start=step=stale=0;best={'exp_rate':-1.,'loss':None,'epoch':0};run_id=None
    if resume:
        resume=Path(resume)
        state=torch.load(resume,map_location='cpu',weights_only=True)
        if state.get('format')!='coach-hme500-v1' or state['qa_only']!=qa: raise ValueError('INVALID_RESUME_CHECKPOINT')
        if state['dataset_fingerprint']!=report['fingerprint']: raise ValueError('RESUME_DATASET_CHANGED')
        if state['training_signature']!=signature(cfg) or state['vocabulary']!=vocabulary: raise ValueError('RESUME_CONFIG_CHANGED')
        if out.exists() and any(out.iterdir()):
            previous=json.loads((out/'run.json').read_text())
            if previous['id']!=state['wandb_id']: raise ValueError('RESUME_OUTPUT_BELONGS_TO_OTHER_RUN')
        for n in ('best.pt','history.csv','metrics.jsonl','baseline-validation.json','baseline.json','run.json'):
            src=resume.parent/n
            if src.exists() and src.resolve()!=(out/n).resolve(): shutil.copy2(src,out/n)
        if not (out/'best.pt').exists(): raise ValueError('RESUME_REQUIRES_BEST_PT_NEXT_TO_LAST_PT')
        selected=torch.load(out/'best.pt',map_location='cpu',weights_only=True)
        if selected['dataset_fingerprint']!=report['fingerprint'] or selected['best']!=state['best']:
            raise ValueError('RESUME_BEST_CHECKPOINT_MISMATCH')
        model.load_state_dict(state['state_dict'],strict=True);optimizer.load_state_dict(state['optimizer'])
        scheduler.load_state_dict(state['scheduler']);scaler.load_state_dict(state['scaler'])
        start=state['epoch'];step=state['global_step'];best=state['best'];stale=state['stale'];run_id=state['wandb_id']
        torch.set_rng_state(state['torch_rng']);random.setstate(state['python_rng'])
        nr=state['numpy_rng'];np.random.set_state((nr[0],np.array(nr[1],dtype=np.uint32),*nr[2:]))
        if device.type=='cuda' and state['cuda_rng']: torch.cuda.set_rng_state_all(state['cuda_rng'])
    if cfg['epochs']<=start: raise ValueError('TOTAL_EPOCHS_MUST_EXCEED_RESUME_EPOCH')
    if not cfg['wandb']['name']:
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        cfg['wandb']['name']=f"comer-hme500-{'real-jpeg-qa' if qa else 'finetune'}-seed{cfg['seed']}-{stamp}"
    if resume and (out/'run.json').exists(): cfg['wandb']['name']=json.loads((out/'run.json').read_text())['name']
    write_json(out/'config.json',cfg);write_json(out/'dataset-audit.json',report)
    write_json(out/'dataset-manifest.json',[{k:r[k] for k in r if not k.startswith('_')} for r in rows])
    write_json(out/'vocabulary.json',{'word2idx':vocabulary,'added_train_tokens':added})
    write_json(out/'metric-contract.json',CONTRACT);write_json(out/'runtime.json',runtime_info(upstream,device,model))
    run=init_run(cfg,out,report,run_id,qa)
    write_json(out/'run.json',{'id':run.id,'name':cfg['wandb']['name'],'project':cfg['wandb']['project'],
        'entity':run.entity,'url':run.url if cfg['wandb']['mode']=='online' else None,'mode':cfg['wandb']['mode']})
    success=False
    def history(epoch,train_loss,metrics,elapsed):
        append_history(out,dict(epoch=epoch,train_loss=train_loss,val_loss=metrics['loss'],
            val_exp_rate=metrics['exp_rate'],val_cer=metrics['cer'],val_token_error_rate=metrics['token_error_rate'],
            encoder_lr=optimizer.param_groups[0]['lr'],decoder_lr=optimizer.param_groups[1]['lr'],seconds=elapsed))
    try:
        if not resume:
            metrics,preds,groups=evaluate(model,vals,vocabulary,device,cfg['max_decode_tokens'])
            write_json(out/'baseline-validation.json',{'metrics':metrics,'predictions':preds,'groups':groups})
            write_json(out/'baseline.json',metrics)
            history(0,None,metrics,0)
            log_predictions(run,cfg,metrics,preds,groups,vals,0)
            for k,v in metrics.items(): run.summary['baseline/val_'+k]=v
            print('Pretrained validation:',json.dumps(metrics),flush=True)
        for epoch in range(start+1,cfg['epochs']+1):
            began=time.monotonic();model.train();frozen=epoch<=cfg['freeze_encoder_epochs']
            for p in model.encoder.parameters(): p.requires_grad_(not frozen)
            if frozen: model.encoder.eval()
            generator=torch.Generator().manual_seed(cfg['seed']+epoch)
            loader=DataLoader(InkDataset(trains),batch_size=cfg['batch_size'],shuffle=True,
                collate_fn=collate,num_workers=0,generator=generator)
            optimizer.zero_grad(set_to_none=True)
            denom=total_tokens=0;group_loss=total_loss=0.
            for batch_no,(x,mask,ts) in enumerate(loader,1):
                x=x.to(device);mask=mask.to(device)
                with torch.amp.autocast(device_type=device.type,enabled=scaler.is_enabled()):
                    loss,n=teacher_loss(model,x,mask,ts)
                if not torch.isfinite(loss): raise FloatingPointError('NONFINITE_TRAINING_LOSS')
                scaler.scale(loss).backward()
                value=float(loss.detach());denom+=n;total_tokens+=n;group_loss+=value;total_loss+=value
                if batch_no%cfg['accumulate']==0 or batch_no==len(loader):
                    scaler.unscale_(optimizer)
                    for p in model.parameters():
                        if p.grad is not None: p.grad.div_(denom)
                    grad=torch.nn.utils.clip_grad_norm_(model.parameters(),cfg['clip_grad_norm'])
                    old=scaler.get_scale();scaler.step(optimizer);scaler.update();skipped=scaler.get_scale()<old
                    if not skipped: step+=1
                    if not scaler.is_enabled() and not math.isfinite(float(grad)): raise FloatingPointError('NONFINITE_GRADIENT')
                    log={'train/optimizer_step':step,'train/loss':group_loss/denom,
                        'train/grad_norm':float(grad) if math.isfinite(float(grad)) else None,
                        'train/amp_skipped':int(skipped),'train/encoder_frozen':int(frozen)}
                    run.log(log)
                    with (out/'metrics.jsonl').open('a',encoding='utf-8') as f:
                        f.write(json.dumps({'epoch':epoch,**log},allow_nan=False)+'\n')
                    optimizer.zero_grad(set_to_none=True);denom=0;group_loss=0.
            metrics,preds,groups=evaluate(model,vals,vocabulary,device,cfg['max_decode_tokens'])
            write_json(out/f'validation-{epoch:03}.json',{'metrics':metrics,'predictions':preds,'groups':groups})
            log_predictions(run,cfg,metrics,preds,groups,vals,epoch)
            improved=best['loss'] is None or (metrics['exp_rate'],-metrics['loss'])>(best['exp_rate'],-best['loss'])
            if improved: best={'exp_rate':metrics['exp_rate'],'loss':metrics['loss'],'epoch':epoch};stale=0
            else: stale+=1
            elapsed=time.monotonic()-began
            history(epoch,total_loss/total_tokens,metrics,elapsed)
            run.log({'epoch':epoch,'epoch_train/loss':total_loss/total_tokens,
                'lr/encoder':optimizer.param_groups[0]['lr'],'lr/decoder':optimizer.param_groups[1]['lr'],
                'runtime/epoch_seconds':elapsed,'runtime/gpu_peak_gib':
                torch.cuda.max_memory_allocated(device)/1024**3 if device.type=='cuda' else 0})
            scheduler.step(metrics['loss'])
            save_checkpoint(out/'last.pt',model,hparams,vocabulary,optimizer,scheduler,scaler,epoch,step,best,stale,cfg,report['fingerprint'],run.id,qa)
            if improved:
                shutil.copy2(out/'last.pt',out/'best.pt')
            # Both files each completed epoch: recovery does not depend on finishing all epochs.
            log_model(run,out,cfg,['latest']+(['best',f'epoch-{epoch}'] if improved else [f'epoch-{epoch}']),
                {'epoch':epoch,'best_epoch':best['epoch'],'fingerprint':report['fingerprint'],'qa_only':qa})
            run.log({'epoch':epoch,'evidence/curves':__import__('wandb').Image(str(out/'curves.png'))})
            print(f'Epoch {epoch}: train_loss={total_loss/total_tokens:.5f} '+json.dumps(metrics),flush=True)
            if stale>=cfg['early_stopping_patience']:
                print('Early stopping; selected best.pt from validation.',flush=True);break
        baseline=json.loads((out/'baseline.json').read_text()) if (out/'baseline.json').exists() else None
        summary={'status':'completed','qa_only':qa,'selected_best':best,'last_epoch':epoch,
                 'optimizer_steps':step,'baseline_validation':baseline,'dataset_fingerprint':report['fingerprint'],
                 'test_evaluated':False,'wandb_url':run.url if cfg['wandb']['mode']=='online' else None}
        write_json(out/'summary.json',summary)
        run.summary.update({'best/epoch':best['epoch'],'best/val_exp_rate':best['exp_rate'],
            'best/val_loss':best['loss'],'epochs_completed':epoch,'qa_only':qa})
        if baseline: run.summary['best/exp_rate_delta_from_baseline']=best['exp_rate']-baseline['exp_rate']
        (out/'evidence.md').write_text('# CoMER HME500 experiment\n\n'+
            ('Local real-JPEG QA only; not a full training accuracy result.\n\n' if qa else '')+
            f"Dataset SHA256 fingerprint: {report['fingerprint']}\n\n"+
            f"Best epoch: {best['epoch']}; validation exact match: {best['exp_rate']:.4f}.\n\n"+
            'Metrics: greedy L2R; see metric-contract.json. Test not used during training.\n'+
            'history.csv / metrics.jsonl contain epoch / optimizer-step history; curves.png is derived from CSV.\n'+
            'Original JPGs were read without rewriting. Writer identity is unavailable.\n',encoding='utf-8')
        if cfg['wandb']['mode']!='disabled':
            import wandb
            artifact=wandb.Artifact('hme500-evidence-'+run.id,type='experiment-evidence')
            for p in sorted(out.iterdir()):
                if p.is_file() and p.suffix in ('.json','.jsonl','.csv','.png','.md'): artifact.add_file(str(p),name=p.name)
            run.log_artifact(artifact,aliases=['completed'])
        archive=bundle(out);print('Evidence ZIP:',archive,flush=True)
        success=True
        return summary
    except BaseException as exc:
        # Exception text can contain third-party authentication details; save class only.
        write_json(out/'failure.json',{'error_type':type(exc).__name__,'resume_from':'last.pt if present'})
        raise
    finally: run.finish(exit_code=0 if success else 1)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True,type=Path);p.add_argument('--resume',type=Path)
    p.add_argument('--qa',action='store_true',help='4 real train + 2 val samples; marks all outputs as QA, not experiment results')
    a=p.parse_args();train(read_config(a.config),a.resume,a.qa)


if __name__=='__main__': main()
