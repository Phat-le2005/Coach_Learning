"""W&B evidence plus independent CSV/JSON/PNG/ZIP outputs; no credentials in config."""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import zipfile
from PIL import Image


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    tmp.replace(path)


def prepare_wandb(output):
    """Keep offline media/artifact staging with downloadable experiment outputs."""
    output=Path(output)
    os.environ['WANDB_DISABLE_CODE']='true'
    for env,folder in (('WANDB_DATA_DIR','wandb-data'),('WANDB_CACHE_DIR','wandb-cache')):
        path=(output/folder).resolve();path.mkdir(parents=True,exist_ok=True)
        os.environ[env]=str(path)


def init_run(cfg, output, audit, resume_id=None, qa=False):
    wb = cfg['wandb']
    if wb['mode'] == 'online' and not os.environ.get('WANDB_API_KEY'):
        try:
            from kaggle_secrets import UserSecretsClient
            os.environ['WANDB_API_KEY'] = UserSecretsClient().get_secret('WANDB_API_KEY')
        except Exception:
            raise RuntimeError('Enable notebook access to Kaggle Secret WANDB_API_KEY '
                               '(Add-ons > Secrets), or set WANDB_API_KEY in your local environment. '
                               'No key belongs in the notebook/config.') from None
    prepare_wandb(output)
    import wandb
    run = wandb.init(project=wb['project'], entity=wb['entity'], name=wb['name'], group=wb['group'],
        job_type='real-jpeg-qa' if qa else 'fine-tune', tags=['CoMER','HME100K','paper-handwriting',
        'qa-not-quality-evidence' if qa else 'hme500-fixed-splits',cfg.get('experiment_version','v1'),
        f"workers-{cfg.get('devices',1)}"], mode=wb['mode'], dir=str(output),
        id=resume_id, resume='must' if resume_id and wb['mode']=='online' else None,
        config={**cfg, 'dataset':audit, 'qa_only':qa},
        settings=wandb.Settings(disable_code=True, disable_git=True, console='off'))
    run.define_metric('train/optimizer_step')
    run.define_metric('train/*', step_metric='train/optimizer_step')
    run.define_metric('epoch')
    for prefix in ('val','epoch_train','runtime','lr'):
        run.define_metric(prefix+'/*', step_metric='epoch')
    run.define_metric('val/exp_rate', summary='max')
    run.define_metric('val/cer', summary='min')
    if wb['mode'] != 'disabled':
        a = wandb.Artifact('hme500-'+audit['fingerprint'][:12], type='dataset-manifest',
                           metadata={'fingerprint':audit['fingerprint']})
        for name in ('dataset-audit.json','dataset-manifest.json','vocabulary.json','metric-contract.json'):
            a.add_file(str(output/name), name=name)
        # SDK commits/waits for a draft passed to use_artifact; offline only stages it.
        if wb['mode'] == 'online': run.use_artifact(a)
        else: run.log_artifact(a)
        source = wandb.Artifact('hme500-training-code-'+run.id, type='source-code')
        root = Path(__file__).resolve().parents[1]
        # Explicit whitelist; no automatic repository/diff/environment capture.
        for p in sorted([*root.rglob('*.py'), *root.rglob('*.sh')]):
            if '.cache' not in p.parts and '__pycache__' not in p.parts:
                source.add_file(str(p), name=p.relative_to(root).as_posix())
        for name in ('requirements.txt','config.example.json','hme_comer/upstream.lock.json'):
            source.add_file(str(root/name), name=name)
        run.log_artifact(source)
    return run


def log_predictions(run, cfg, metrics, predictions, groups, rows, epoch, split='validation'):
    import wandb
    mapping = {r['id']:r for r in rows}
    def table(ps):
        t = wandb.Table(columns=['id','group','original_jpeg','latex_ground_truth',
                                'prediction','exact','CER','ended'])
        for p in ps:
            picture = None
            if cfg['wandb']['log_images']:
                with Image.open(mapping[p['id']]['_image']) as im:
                    picture = wandb.Image(im.copy(), caption=p['id']+' | '+p['group'])
            t.add_data(p['id'],p['group'],picture,p['latex'],p['prediction'],p['exact'],p['cer'],p['ended'])
        return t
    prefix = 'val' if split == 'validation' else 'test'
    values = {'epoch':epoch, **{prefix+'/'+k:v for k,v in metrics.items()},
              split+'/fixed_examples':table(predictions[:cfg['media_samples']]),
              split+'/largest_errors':table(sorted(predictions,key=lambda p:p['cer'],reverse=True)[:cfg['media_samples']])}
    for g, values_g in groups.items():
        for k, v in values_g.items(): values[prefix+'/groups/'+g+'/'+k] = v
    run.log(values)


def append_history(output, row):
    path = output/'history.csv'
    existed = path.exists()
    with path.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if not existed: w.writeheader()
        w.writerow(row)
    plot_curves(output)


def plot_curves(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    with (output/'history.csv').open(encoding='utf-8') as f: rows=list(csv.DictReader(f))
    epochs=[int(r['epoch']) for r in rows]
    fig, axes=plt.subplots(2,2,figsize=(11,7))
    for field, label in (('train_loss','Train'),('val_loss','Validation')):
        axes[0,0].plot(epochs,[float(r[field]) if r[field] else float('nan') for r in rows],label=label)
    axes[0,0].legend(); axes[0,0].set_title('Bidirectional token cross entropy')
    axes[0,1].plot(epochs,[100*float(r['val_exp_rate']) for r in rows]);axes[0,1].set_title('Validation exact match (%)')
    axes[1,0].plot(epochs,[float(r['val_cer']) for r in rows],label='CER')
    axes[1,0].plot(epochs,[float(r['val_token_error_rate']) for r in rows],label='Token error');axes[1,0].legend()
    axes[1,0].set_title('Validation error rates (may exceed 1)')
    for k in ('encoder_lr','decoder_lr'): axes[1,1].plot(epochs,[float(r[k]) for r in rows],label=k)
    axes[1,1].set_yscale('log');axes[1,1].legend();axes[1,1].set_title('Learning rates')
    for ax in axes.flat: ax.set_xlabel('Epoch (0 = pretrained baseline)');ax.grid(alpha=.25)
    fig.suptitle('Coach Learning | CoMER | HME500',fontsize=14)
    fig.tight_layout();fig.savefig(output/'curves.png',dpi=160);plt.close(fig)


def log_model(run, output, cfg, aliases, metadata):
    if cfg.get('checkpoint_upload','every_epoch')=='final_inference':return
    if cfg['wandb']['mode']=='disabled' or not cfg['wandb']['log_checkpoints']: return
    import wandb
    artifact=wandb.Artifact('comer-hme500-'+run.id,type='model',metadata=metadata)
    for n in ('best.pt','last.pt','initial.pt','config.json','vocabulary.json','dataset-audit.json','runtime.json'):
        if (output/n).exists(): artifact.add_file(str(output/n),name=n)
    run.log_artifact(artifact,aliases=aliases)


def log_final_model(run, output, cfg):
    """Export identical best FP32 tensors once; retain resume checkpoints locally."""
    if cfg.get('checkpoint_upload','every_epoch')!='final_inference':return
    import torch
    full=torch.load(output/'best.pt',map_location='cpu',weights_only=True)
    exported={k:full[k] for k in ('state_dict','hyper_parameters','vocabulary','epoch','dataset_fingerprint','qa_only')}
    exported.update(format='coach-hme500-inference-v1',preprocess=cfg['preprocess'],
        source_full_checkpoint_sha256=hashlib.sha256((output/'best.pt').read_bytes()).hexdigest(),
        note='Identical FP32 tensors; optimizer/RNG omitted; full best.pt/last.pt retained locally.')
    path=output/'best-inference.pt';torch.save(exported,path)
    write_json(output/'inference-export.json',dict(
        source_full_checkpoint_sha256=exported['source_full_checkpoint_sha256'],
        inference_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),epoch=full['epoch'],
        inference_bytes=path.stat().st_size,same_model_tensors=True))
    if cfg['wandb']['mode']=='disabled' or not cfg['wandb']['log_checkpoints']:return path
    import wandb
    artifact=wandb.Artifact('comer-hme500-inference-'+run.id,type='model',
        metadata={'epoch':full['epoch'],'qa_only':full['qa_only'],'source_full_checkpoint_sha256':exported['source_full_checkpoint_sha256']})
    for name in ('best-inference.pt','inference-export.json','config.json','vocabulary.json','runtime.json'):
        artifact.add_file(str(output/name),name=name)
    run.log_artifact(artifact,aliases=['best','final'])
    return path


def bundle(output):
    """Portable independent evidence, excluding W&B caches and authentication files."""
    files=[p for p in sorted(output.iterdir()) if p.is_file() and p.name!='checksums.json'
           and p.suffix in ('.json','.jsonl','.csv','.png','.md','.pt')]
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    write_json(output/'checksums.json',manifest)
    target=output/'experiment_evidence.zip'
    tmp=target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for p in files:
            z.write(p,arcname=output.name+'/'+p.name)
        if output/'checksums.json' not in files:
            z.write(output/'checksums.json',arcname=output.name+'/checksums.json')
    tmp.replace(target)
    return target
