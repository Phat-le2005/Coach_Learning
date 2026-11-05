"""Single-GPU CoMER fine-tuning with writer-disjoint evaluation and W&B media.

Run from train/comer: python -m comer_lab.train --config config.json
Only epoch-boundary checkpoints are resumed; the test split is never evaluated here.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import random
import time
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from .data import read_manifest, input_array, edit_distance, manifest_summary
from .model import load_model, UPSTREAM

DEFAULTS = dict(epochs=20, batch_size=4, accumulate=4, decoder_lr=1e-4,
                encoder_lr=1e-5, weight_decay=.01, freeze_encoder_epochs=2,
                clip_grad_norm=1., max_decode_tokens=192, seed=42, amp=True,
                device='cuda', media_samples=16)
WB_DEFAULTS = dict(mode='disabled', project='coach-learning-comer', entity=None,
                   name=None, group=None, log_images=True, log_checkpoints=True)
METRIC_CONTRACT = {
    'decoder': 'left-to-right greedy; SOS=1, EOS=2; PAD/SOS suppressed',
    'exp_rate': 'fraction of exact token sequences, requiring an EOS',
    'cer': 'sum character edit distances / sum reference characters; concatenated LaTeX tokens',
    'token_error_rate': 'sum token edit distances / sum reference tokens',
    'loss': 'bidirectional teacher-forced cross entropy, averaged over non-PAD tokens',
    'selection': 'highest validation exp_rate, then lowest validation loss',
    'test_policy': 'train command never evaluates test; use separate evaluate command once selected',
    'limits': 'Not the paper bidirectional beam search or browser beam=3. No semantic equivalence claim.'
}

def json_write(path, value):
    path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(path)

def read_config(path: Path):
    raw=json.loads(path.read_text(encoding='utf-8'))
    allowed=set(DEFAULTS)|{'manifest','output','upstream','checkpoint','wandb'}
    if set(raw)-allowed: raise ValueError('Unknown config keys: '+str(sorted(set(raw)-allowed)))
    cfg={**DEFAULTS,**raw}
    wb={**WB_DEFAULTS,**cfg.get('wandb',{})}
    if set(wb)-set(WB_DEFAULTS): raise ValueError('Unknown W&B keys')
    if wb['mode'] not in ('online','offline','disabled'): raise ValueError('Invalid W&B mode')
    cfg['wandb']=wb
    for k in ('epochs','batch_size','accumulate','max_decode_tokens','media_samples'):
        if type(cfg[k]) is not int or cfg[k]<1: raise ValueError('Expected positive integer: '+k)
    if type(cfg['freeze_encoder_epochs']) is not int or cfg['freeze_encoder_epochs']<0:
        raise ValueError('Invalid freeze_encoder_epochs')
    if type(cfg['seed']) is not int or not 0<=cfg['seed']<2**32: raise ValueError('Invalid seed')
    for k in ('encoder_lr','decoder_lr','clip_grad_norm'):
        if not isinstance(cfg[k],(float,int)) or not math.isfinite(cfg[k]) or cfg[k]<=0:
            raise ValueError('Invalid '+k)
    if not 0<=cfg['weight_decay']<1: raise ValueError('Invalid weight_decay')
    for k in ('amp',):
        if type(cfg[k]) is not bool: raise ValueError('Expected bool: '+k)
    for k in ('log_images','log_checkpoints'):
        if type(wb[k]) is not bool: raise ValueError('Expected bool: wandb.'+k)
    for k in ('manifest','output'):
        if not isinstance(cfg.get(k),str) or not cfg[k]: raise ValueError('Missing '+k)
    return cfg

class InkDataset(Dataset):
    def __init__(self,rows): self.rows=rows
    def __len__(self): return len(self.rows)
    def __getitem__(self,i):
        a,m=input_array(self.rows[i])
        return torch.from_numpy(a[None]),torch.from_numpy(m),self.rows[i]['_tokens']

def collate(items):
    width=max(x.shape[-1] for x,m,t in items)
    images=torch.zeros(len(items),1,256,width)
    masks=torch.ones(len(items),256,width,dtype=torch.bool)
    for i,(x,m,t) in enumerate(items):
        images[i,:,:,:x.shape[-1]]=x
        masks[i,:,:x.shape[-1]]=m
    return images,masks,[t for x,m,t in items]

def fingerprint(rows):
    # Includes paired labels, split ownership, source provenance and mask geometry.
    keys=('sample_id','writer_id','image_sha256','latex_verbatim','split','source',
          'preprocess_version','content_height','content_width','review_status','usage_permission')
    clean=[{k:r[k] for k in keys} for r in sorted(rows,key=lambda r:r['sample_id'])]
    return hashlib.sha256(json.dumps(clean,sort_keys=True).encode()).hexdigest()

def training_signature(cfg):
    return {k:cfg[k] for k in DEFAULTS if k not in ('epochs','media_samples')}

def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark=False
    torch.use_deterministic_algorithms(True,warn_only=True)

def teacher_loss(model,x,mask,tokens):
    from comer.utils.utils import to_bi_tgt_out
    tgt,out=to_bi_tgt_out(tokens,x.device)
    logits=model(x,mask,tgt)
    total=F.cross_entropy(logits.reshape(-1,logits.shape[-1]),out.reshape(-1),ignore_index=0,reduction='sum')
    return total,int(out.ne(0).sum().item())

@torch.inference_mode()
def greedy(model,x,mask,max_tokens):
    features,m=model.encoder(x,mask)
    ids=torch.ones((1,1),dtype=torch.long,device=x.device)
    seq=[];ended=False
    for _ in range(max_tokens):
        logits=model.decoder(features,m,ids)[:,-1,:].clone()
        logits[:,0:2]=-torch.inf
        token=int(logits.argmax(-1).item())
        if token==2: ended=True;break
        seq.append(token)
        ids=torch.cat([ids,torch.tensor([[token]],device=x.device)],dim=1)
    return seq,ended

@torch.inference_mode()
def evaluate(model,rows,vocab,device,max_tokens):
    if not rows: raise ValueError('Evaluation split is empty')
    model.eval();loss_sum=0.;n_tokens=0;correct=0;empty=0;truncated=0
    char_ed=0;char_n=0;token_ed=0;token_n=0;predictions=[]
    idx={int(v):k for k,v in vocab['word2idx'].items()}
    for row in rows:
        x,m,_=collate([InkDataset([row])[0]])
        x=x.to(device);m=m.to(device)
        loss,n=teacher_loss(model,x,m,[row['_tokens']]);loss_sum+=float(loss);n_tokens+=n
        seq,ended=greedy(model,x,m,max_tokens)
        truth=row['_tokens'];pred_text=''.join(idx[t] for t in seq);true_text=''.join(idx[t] for t in truth)
        exact=seq==truth and ended
        correct+=int(exact);empty+=int(not seq);truncated+=int(not ended)
        te=edit_distance(seq,truth);ce=edit_distance(pred_text,true_text)
        token_ed+=te;token_n+=len(truth);char_ed+=ce;char_n+=len(true_text)
        predictions.append({'sample_id':row['sample_id'],'truth':true_text,'prediction':pred_text,
                            'exact':exact,'ended':ended,'token_edits':te,'character_edits':ce})
    return {'samples':len(rows),'loss':loss_sum/n_tokens,'exp_rate':correct/len(rows),
            'cer':char_ed/max(1,char_n),'token_error_rate':token_ed/max(1,token_n),
            'empty_rate':empty/len(rows),'truncation_rate':truncated/len(rows)},predictions

def init_wandb(cfg,out,summary,resume_id=None,smoke=False):
    # Keep offline artifact/media staging with Kaggle outputs, not an ephemeral home cache.
    os.environ['WANDB_DATA_DIR']=str((out/'wandb-data').resolve())
    os.environ['WANDB_CACHE_DIR']=str((out/'wandb-cache').resolve())
    import wandb
    wb=cfg['wandb'];os.environ['WANDB_DISABLE_CODE']='true'
    run=wandb.init(project=wb['project'],entity=wb['entity'],name=wb['name'],group=wb['group'],
        mode=wb['mode'],dir=str(out),id=resume_id,
        resume='must' if resume_id and wb['mode']=='online' else None,
        config={**cfg,'dataset':summary,'smoke_only':smoke,'metric_contract':METRIC_CONTRACT},
        tags=['CoMER','synthetic-smoke' if smoke else 'writer-disjoint'],
        settings=wandb.Settings(disable_code=True,disable_git=True,console='off'))
    run.define_metric('train/*',step_metric='train/global_step')
    run.define_metric('val/*',step_metric='epoch')
    run.define_metric('val/exp_rate',summary='max')
    run.define_metric('val/cer',summary='min')
    if wb['mode']!='disabled':
        artifact=wandb.Artifact('comer-dataset-summary',type='dataset-metadata',metadata={'fingerprint':summary['fingerprint']})
        artifact.add_file(str(out/'dataset-summary.json'))
        artifact.add_file(str(out/'metric-contract.json'))
        run.log_artifact(artifact)
    return run

def log_validation(run,cfg,metrics,predictions,rows,epoch):
    import wandb
    log={'epoch':epoch,**{'val/'+k:v for k,v in metrics.items()}}
    table=wandb.Table(columns=['sample_id','image','label','prediction','exact','token_edits','ended']);gallery=[]
    # The fixed first N validation samples make successive epochs comparable.
    for pred,row in zip(predictions[:cfg['media_samples']],rows):
        picture=None
        if cfg['wandb']['log_images'] and row.get('media_permission')=='GRANTED':
            with Image.open(row['_image']) as img:
                picture=wandb.Image(img.crop((0,0,row['content_width'],row['content_height'])).copy(),
                                    caption=pred['sample_id']+' | GT: '+pred['truth']+' | Pred: '+pred['prediction'])
                gallery.append(picture)
        table.add_data(pred['sample_id'],picture,pred['truth'],pred['prediction'],
                       pred['exact'],pred['token_edits'],pred['ended'])
    log['validation/predictions']=table
    if gallery: log['validation/ink']=gallery
    run.log(log)

def save_checkpoint(path,model,hparams,optimizer,scaler,epoch,global_step,best,cfg,digest,run_id):
    value={'format':'coach-comer-epoch-v1','state_dict':model.state_dict(),'hyper_parameters':hparams,
           'optimizer':optimizer.state_dict(),'scaler':scaler.state_dict(),'epoch':epoch,
           'global_step':global_step,'best':best,'training_signature':training_signature(cfg),
           'dataset_fingerprint':digest,'wandb_id':run_id,'torch_rng':torch.get_rng_state(),
           'python_rng':random.getstate(),
           'cuda_rng':torch.cuda.get_rng_state_all() if torch.cuda.is_available() else []}
    tmp=path.with_suffix('.tmp');torch.save(value,tmp);tmp.replace(path)

def train(cfg,*,resume:Path|None=None,smoke=False):
    seed_all(cfg['seed']);torch.set_num_threads(min(4,os.cpu_count() or 1))
    device=torch.device(cfg['device'])
    if device.type=='cuda' and not torch.cuda.is_available():
        raise RuntimeError('CUDA unavailable: enable a Kaggle GPU, or explicitly set device=cpu for smoke QA')
    upstream=Path(cfg.get('upstream',UPSTREAM))
    model,vocab,hparams=load_model(Path(cfg['checkpoint']) if cfg.get('checkpoint') else None,upstream)
    vocabulary={'word2idx':vocab.word2idx}
    rows=read_manifest(Path(cfg['manifest']),vocabulary,allow_smoke=smoke)
    if not smoke and any(r['source']=='synthetic_smoke' for r in rows): raise ValueError('Smoke data rejected')
    trains=sorted([r for r in rows if r['split']=='train'],key=lambda r:r['sample_id'])
    vals=sorted([r for r in rows if r['split']=='val'],key=lambda r:r['sample_id'])
    if not trains or not vals: raise ValueError('Both train and val splits must be nonempty')
    digest=fingerprint(rows);out=Path(cfg['output']);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()) and not resume: raise ValueError('Output is not empty; choose a new folder or --resume latest.pt')
    model.to(device)
    optimizer=torch.optim.AdamW([{'params':model.encoder.parameters(),'lr':cfg['encoder_lr']},
                                {'params':model.decoder.parameters(),'lr':cfg['decoder_lr']}],weight_decay=cfg['weight_decay'])
    scaler=torch.amp.GradScaler('cuda',enabled=cfg['amp'] and device.type=='cuda')
    start=0;global_step=0;best={'exp_rate':-1.,'loss':float('inf'),'epoch':0};resume_id=None
    if resume:
        state=torch.load(resume,map_location='cpu',weights_only=True)
        if state.get('format')!='coach-comer-epoch-v1': raise ValueError('Not a resumable Coach checkpoint')
        if state['dataset_fingerprint']!=digest: raise ValueError('RESUME_DATASET_CHANGED')
        if state['training_signature']!=training_signature(cfg): raise ValueError('RESUME_TRAINING_CONFIG_CHANGED')
        if any(out.iterdir()):
            old_summary=out/'dataset-summary.json';old_run=out/'run.json'
            if not old_summary.is_file() or not old_run.is_file():
                raise ValueError('Resume output contains files from an unknown run')
            if json.loads(old_summary.read_text())['fingerprint']!=digest or json.loads(old_run.read_text())['id']!=state['wandb_id']:
                raise ValueError('Resume output belongs to another run')
        model.load_state_dict(state['state_dict']);optimizer.load_state_dict(state['optimizer']);scaler.load_state_dict(state['scaler'])
        start=state['epoch'];global_step=state['global_step'];best=state['best'];resume_id=state['wandb_id']
        torch.set_rng_state(state['torch_rng']);random.setstate(state['python_rng'])
        if device.type=='cuda' and state['cuda_rng']: torch.cuda.set_rng_state_all(state['cuda_rng'])
        previous_best=resume if best.get('epoch')==start else resume.parent/'best.pt'
        if not previous_best.is_file(): raise ValueError('RESUME_BEST_CHECKPOINT_MISSING: restore both latest.pt and best.pt')
        selected=torch.load(previous_best,map_location='cpu',weights_only=True)
        if selected.get('dataset_fingerprint')!=digest or selected.get('best')!=best:
            raise ValueError('RESUME_BEST_CHECKPOINT_MISMATCH')
        if previous_best.resolve()!=(out/'best.pt').resolve():
            import shutil
            shutil.copy2(previous_best,out/'best.pt')
    if cfg['epochs']<=start: raise ValueError('epochs must exceed the checkpoint epoch')
    summary={**manifest_summary(rows),'fingerprint':digest,'smoke_only':smoke}
    json_write(out/'dataset-summary.json',summary);json_write(out/'metric-contract.json',METRIC_CONTRACT)
    json_write(out/'config.json',cfg)
    env={p:importlib.metadata.version(p) for p in ('torch','torchvision','numpy','wandb','onnx','onnxruntime')}
    env.update(device=str(device),gpu=torch.cuda.get_device_name(0) if device.type=='cuda' else None)
    env['lab_sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')}
    env['upstream_commit']=json.loads(Path(__file__).with_name('upstream.lock.json').read_text())['commit']
    json_write(out/'environment.json',env)
    run=init_wandb(cfg,out,summary,resume_id,smoke)
    json_write(out/'run.json',{'id':run.id,'url':run.url if cfg['wandb']['mode']=='online' else None,'mode':cfg['wandb']['mode']})
    success=False
    try:
        if not resume:
            metrics,preds=evaluate(model,vals,vocabulary,device,cfg['max_decode_tokens'])
            json_write(out/'baseline-val.json',{'metrics':metrics,'predictions':preds})
            log_validation(run,cfg,metrics,preds,vals,0)
            print('Baseline validation:',json.dumps(metrics),flush=True)
        for epoch in range(start+1,cfg['epochs']+1):
            began=time.monotonic();model.train();frozen=epoch<=cfg['freeze_encoder_epochs']
            for p in model.encoder.parameters(): p.requires_grad_(not frozen)
            if frozen: model.encoder.eval()
            generator=torch.Generator().manual_seed(cfg['seed']+epoch)
            loader=DataLoader(InkDataset(trains),batch_size=cfg['batch_size'],shuffle=True,
                              collate_fn=collate,num_workers=0,generator=generator)
            optimizer.zero_grad(set_to_none=True);denom=0;group_loss=0.;epoch_loss=0.;epoch_tokens=0
            for i,(x,mask,tokens) in enumerate(loader,1):
                x=x.to(device);mask=mask.to(device)
                with torch.amp.autocast(device_type=device.type,enabled=scaler.is_enabled()):
                    loss,n=teacher_loss(model,x,mask,tokens)
                if not torch.isfinite(loss): raise FloatingPointError('Non-finite training loss')
                scaler.scale(loss).backward();denom+=n;value=float(loss.detach())
                group_loss+=value;epoch_loss+=value;epoch_tokens+=n
                if i%cfg['accumulate']==0 or i==len(loader):
                    scaler.unscale_(optimizer)
                    for p in model.parameters():
                        if p.grad is not None: p.grad.div_(denom)
                    grad=torch.nn.utils.clip_grad_norm_(model.parameters(),cfg['clip_grad_norm'])
                    old_scale=scaler.get_scale();scaler.step(optimizer);scaler.update()
                    skipped=scaler.get_scale()<old_scale
                    if not skipped: global_step+=1
                    run.log({'train/global_step':global_step,'train/loss':group_loss/denom,
                             'train/epoch_running_loss':epoch_loss/epoch_tokens,
                             'train/grad_norm':float(grad),'train/amp_skipped':int(skipped),
                             'train/encoder_frozen':int(frozen),'train/decoder_lr':cfg['decoder_lr'],
                             'train/encoder_lr':0. if frozen else cfg['encoder_lr']})
                    optimizer.zero_grad(set_to_none=True);denom=0;group_loss=0.
            metrics,preds=evaluate(model,vals,vocabulary,device,cfg['max_decode_tokens'])
            json_write(out/f'validation-{epoch:03}.json',{'metrics':metrics,'predictions':preds})
            log_validation(run,cfg,metrics,preds,vals,epoch)
            improved=(metrics['exp_rate'],-metrics['loss'])>(best['exp_rate'],-best['loss'])
            if improved: best={'exp_rate':metrics['exp_rate'],'loss':metrics['loss'],'epoch':epoch}
            save_checkpoint(out/'latest.pt',model,hparams,optimizer,scaler,epoch,global_step,best,cfg,digest,run.id)
            if improved:
                save_checkpoint(out/'best.pt',model,hparams,optimizer,scaler,epoch,global_step,best,cfg,digest,run.id)
                if cfg['wandb']['log_checkpoints'] and cfg['wandb']['mode']!='disabled':
                    import wandb
                    artifact=wandb.Artifact('comer-'+run.id,type='model',metadata={'epoch':epoch,'dataset_fingerprint':digest,'smoke_only':smoke,**metrics})
                    artifact.add_file(str(out/'best.pt'),name='best.pt');run.log_artifact(artifact,aliases=['best',f'epoch-{epoch}'])
            run.log({'epoch':epoch,'time/epoch_seconds':time.monotonic()-began})
            print(f'Epoch {epoch}: '+json.dumps(metrics),flush=True)
        if cfg['wandb']['log_checkpoints'] and cfg['wandb']['mode']!='disabled':
            import wandb
            artifact=wandb.Artifact('comer-'+run.id,type='model',metadata={'epoch':cfg['epochs'],'smoke_only':smoke,'best_epoch':best['epoch']})
            for name in ('latest.pt','best.pt','environment.json','metric-contract.json'):
                artifact.add_file(str(out/name),name=name)
            run.log_artifact(artifact,aliases=['latest'])
        run.summary['best_val_exp_rate']=best['exp_rate'];run.summary['smoke_only']=smoke
        success=True
        return {'output':str(out),'best_val':best,'epochs':cfg['epochs'],'smoke_only':smoke}
    finally:
        run.finish(exit_code=0 if success else 1)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path)
    p.add_argument('--resume',type=Path);p.add_argument('--smoke',action='store_true',help='Mechanical QA only, not a handwriting result')
    a=p.parse_args();print(json.dumps(train(read_config(a.config),resume=a.resume,smoke=a.smoke)))
