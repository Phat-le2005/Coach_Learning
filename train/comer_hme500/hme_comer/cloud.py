"""Submit a two-GPU Kaggle experiment from one JSON config; no credential files."""
import argparse
import ast
from collections import defaultdict
import csv
from datetime import datetime,timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RESULT_PATTERN=r'.*(CoachLearning_CoMER_v5_Kaggle_DDP2_Results\.zip|result-index\.json)$'

REMOTE=r'''
import hashlib,json,os,subprocess,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path

TASK=json.loads(__TASK_JSON__)
WORK=Path('/kaggle/working')
from kaggle_secrets import UserSecretsClient
try:
    secret=UserSecretsClient().get_secret(TASK['wandb']['secret_label'])
    if not secret:raise ValueError('empty')
    wandb_mode='online'
except Exception:
    secret='';wandb_mode='offline'
    print('Kaggle Secret unavailable: recording full W&B evidence offline for authenticated local sync after download.',flush=True)
import torch
if torch.cuda.device_count()!=2:raise RuntimeError('EXACTLY_TWO_CUDA_GPUS_REQUIRED; request NvidiaTeslaT4.')
print('Allocated GPUs:',[torch.cuda.get_device_name(i) for i in range(2)],flush=True)
repo=WORK/'Coach_Learning'
if repo.exists():raise RuntimeError('FRESH_KAGGLE_WORKSPACE_REQUIRED')
repo.mkdir()
git_env=os.environ.copy()
git_env.pop('WANDB_API_KEY',None);git_env['GIT_TERMINAL_PROMPT']='0'
for args in (['init','-q'],['remote','add','origin','https://github.com/Phat-le2005/Coach_Learning.git'],
             ['sparse-checkout','init','--cone'],['sparse-checkout','set','train/comer_hme500'],
             ['fetch','--depth=1','--filter=blob:none','origin',TASK['source_revision']],
             ['checkout','--detach','FETCH_HEAD']):
    subprocess.run(['git','-C',str(repo),*args],env=git_env,check=True)
lab=repo/'train/comer_hme500'
cfg=json.loads((lab/'config.example.json').read_text())
cfg.update(TASK['training'])
cfg.update(data='/kaggle/input/datasets/'+TASK['dataset_source'],experiment_version=TASK['version'])
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
lr=format(cfg['decoder_lr'],'.0e').replace('e-0','e-').replace('e+0','e+')
effective=cfg['batch_size']*cfg['devices']*cfg['accumulate']
name=f"comer-hme500-{TASK['version']}-otsu-ddp2-lrdec{lr}-s{cfg['seed']}-eb{effective}-{stamp}"
cfg['output']=str(WORK/'comer_experiments'/name)
cfg['wandb'].update(mode=wandb_mode,entity=TASK['wandb']['entity'],project=TASK['wandb']['project'],name=name,group=name)
path=WORK/'comer.config.json';path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
env=os.environ.copy()
env.update(RUN_FINAL_TEST='1',PYTHONUNBUFFERED='1',CUBLAS_WORKSPACE_CONFIG=':4096:8',WANDB_MODE=wandb_mode)
if secret:env['WANDB_API_KEY']=secret
else:env.pop('WANDB_API_KEY',None)
log=WORK/'comer-run.log'
def command(args):
    with log.open('a',encoding='utf-8') as stream:
        process=subprocess.Popen(args,cwd=lab,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in process.stdout:
            safe=line.replace(secret,'[REDACTED]') if secret else line
            print(safe,end='',flush=True);stream.write(safe);stream.flush()
        if process.wait():raise RuntimeError('EXPERIMENT_STAGE_FAILED; inspect the saved stage log.')
command(['bash','scripts/run_kaggle.sh','all',str(path)])
out=Path(cfg['output'])
command([sys.executable,'-m','hme_comer.review','--output',str(out)])
summary=json.loads((out/'summary.json').read_text())
comparison=json.loads((out/'comparison.json').read_text())
if summary['world_size']!=2 or summary['qa_only'] or not summary['test_evaluated']:
    raise RuntimeError('FULL_DDP_EXPERIMENT_NOT_VERIFIED')
index=dict(status='completed',kernel=TASK['kernel_ref'],output=str(out),
    source_revision=TASK['source_revision'],world_size=2,
    best=summary['selected_best'],last_epoch=summary['last_epoch'],wandb_url=summary['wandb_url'],
    wandb_mode=wandb_mode,wandb_run_id=json.loads((out/'run.json').read_text())['id'],
    before=comparison['before'],after=comparison['after'],
    note='Fresh DDP2 trial. Per-GPU batch 4 differs from the interrupted local batch-1 trial; this is not an exact continuation.')
(WORK/'result-index.json').write_text(json.dumps(index,indent=2)+'\n')
archive=WORK/'CoachLearning_CoMER_v5_Kaggle_DDP2_Results.zip'
files=[p for p in out.iterdir() if p.is_file() and p.name!='checksums.json' and p.suffix in ('.json','.jsonl','.csv','.png','.md','.pt','.html')]
files+=[log,WORK/'result-index.json',path]
checks={}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:
        raw=p.read_bytes()
        if secret and secret.encode() in raw:raise RuntimeError('CREDENTIAL_IN_OUTPUT; refusing to package')
        z.writestr(p.name,raw);checks[p.name]=hashlib.sha256(raw).hexdigest()
    for p in sorted((lab/'hme_comer').glob('*.py')):
        raw=p.read_bytes();entry='source/hme_comer/'+p.name
        z.writestr(entry,raw);checks[entry]=hashlib.sha256(raw).hexdigest()
    for rel in ('requirements.txt','config.example.json','hme_comer/upstream.lock.json'):
        raw=(lab/rel).read_bytes();entry='source/'+rel
        z.writestr(entry,raw);checks[entry]=hashlib.sha256(raw).hexdigest()
    # Self-contained original JPEGs for post-run W&B galleries without cloud credentials.
    sys.path.insert(0,str(lab))
    from hme_comer.data import audit,resolve_metadata
    all_rows,after_audit=audit(resolve_metadata(cfg['data']))
    if after_audit['fingerprint']!=summary['dataset_fingerprint']:raise RuntimeError('INPUT_DATA_CHANGED')
    for row in all_rows:
        if row['split'] not in ('validation','test'):continue
        raw=row['_image'].read_bytes();entry='preview-images/'+row['id']+'.jpg'
        if hashlib.sha256(raw).hexdigest()!=row['image_sha256']:raise RuntimeError('PREVIEW_IMAGE_CHANGED')
        z.writestr(entry,raw);checks[entry]=hashlib.sha256(raw).hexdigest()
    z.writestr('checksums.json',json.dumps(checks,indent=2))
with zipfile.ZipFile(archive) as z:
    if z.testzip() is not None:raise RuntimeError('RESULT_ZIP_CORRUPT')
    for entry,digest in checks.items():
        if hashlib.sha256(z.read(entry)).hexdigest()!=digest:raise RuntimeError('RESULT_ZIP_CHECKSUM_FAILED')
env.pop('WANDB_API_KEY',None);secret=None
print('RESULT INDEX:',json.dumps(index),flush=True)
print('VERIFIED RESULT ZIP:',archive,flush=True)
'''


def read_config(path):
    cfg=json.loads(Path(path).read_text(encoding='utf-8'))
    expected={'kernel_ref','title','is_private','source_revision','dataset_source','version','training','wandb'}
    if set(cfg)!=expected:raise ValueError('CLOUD_CONFIG_FIELDS_INVALID; credentials belong only in environment/Secrets')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+',cfg['kernel_ref']):raise ValueError('INVALID_KERNEL_REF')
    if not re.fullmatch(r'[0-9a-f]{40}',cfg['source_revision']):raise ValueError('PIN_FULL_SOURCE_REVISION')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+',cfg['dataset_source']):raise ValueError('INVALID_DATASET_REF')
    if type(cfg['is_private']) is not bool:raise ValueError('PRIVATE_FLAG_MUST_BE_BOOL')
    if set(cfg['wandb'])!={'entity','project','secret_label'}:raise ValueError('WANDB_CONFIG_MUST_NOT_CONTAIN_A_KEY')
    if not cfg['wandb']['secret_label']:raise ValueError('WANDB_SECRET_LABEL_REQUIRED')
    default=json.loads((ROOT/'config.example.json').read_text())
    if set(cfg['training'])-set(default):raise ValueError('UNKNOWN_TRAINING_FIELDS')
    if {'data','output','wandb'}&set(cfg['training']):raise ValueError('CLOUD_OWNS_PATHS_AND_WANDB')
    train={**default,**cfg['training']}
    if train['devices']!=2 or train['device']!='cuda:0':raise ValueError('CLOUD_REQUIRES_DDP2')
    if train['batch_size']*train['accumulate']*train['devices']!=16:raise ValueError('EFFECTIVE_BATCH_MUST_BE_16')
    if train['checkpoint_upload']!='final_inference':raise ValueError('COMPACT_CHECKPOINT_UPLOAD_REQUIRED')
    if not train['compare_before_after']:raise ValueError('PAIRED_COMPARISON_REQUIRED')
    return cfg


def prepare(path,destination=None):
    cfg=read_config(path)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=Path(destination or ROOT.parents[1]/'.tmp/comer-kaggle-submit'/stamp).resolve()
    folder.mkdir(parents=True,exist_ok=False)
    remote=REMOTE.replace('__TASK_JSON__',repr(json.dumps(cfg)))
    ast.parse(remote)
    notebook=dict(nbformat=4,nbformat_minor=5,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},
        cells=[dict(cell_type='markdown',metadata={},source=['# CoMER '+cfg['version']+' · T4 x2\nOne config; runtime secrets; fixed source revision.']),
               dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=[remote])])
    (folder/'run.ipynb').write_text(json.dumps(notebook,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    metadata=dict(id=cfg['kernel_ref'],title=cfg['title'],code_file='run.ipynb',language='python',kernel_type='notebook',
        is_private=cfg['is_private'],enable_gpu=True,enable_internet=True,machine_shape='NvidiaTeslaT4',
        dataset_sources=[cfg['dataset_source']],competition_sources=[],kernel_sources=[],model_sources=[])
    (folder/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    return folder,cfg


def verify_download(folder):
    archives=list(Path(folder).rglob('CoachLearning_CoMER_v5_Kaggle_DDP2_Results.zip'))
    if len(archives)!=1:raise RuntimeError('EXPECTED_ONE_RESULT_ZIP')
    with zipfile.ZipFile(archives[0]) as archive:
        if archive.testzip() is not None:raise RuntimeError('DOWNLOADED_ZIP_CORRUPT')
        checks=json.loads(archive.read('checksums.json'))
        for name,digest in checks.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=digest:raise RuntimeError('DOWNLOADED_CHECKSUM_MISMATCH')
        index=json.loads(archive.read('result-index.json'))
        if index['status']!='completed' or index['world_size']!=2:raise RuntimeError('DDP2_RESULT_NOT_VERIFIED')
    return archives[0],index


def submit(api,folder):
    """Explicit Save & Run All; do not rely on an unspecified execution type."""
    from kagglesdk.kernels.types.kernels_api_service import ApiSaveKernelRequest
    from kagglesdk.kernels.types.kernels_enums import KernelExecutionType
    folder=Path(folder)
    metadata=json.loads((folder/'kernel-metadata.json').read_text())
    request=ApiSaveKernelRequest()
    request.slug=metadata['id'];request.new_title=metadata['title']
    notebook=json.loads((folder/metadata['code_file']).read_text(encoding='utf-8'))
    for cell in notebook['cells']:
        if isinstance(cell.get('source'),list):cell['source']=''.join(cell['source'])
        if cell['cell_type']=='code':cell['outputs']=[];cell['execution_count']=None
    request.text=json.dumps(notebook)
    request.language='python';request.kernel_type='notebook';request.is_private=True
    request.enable_gpu=True;request.enable_tpu=False;request.enable_internet=True
    request.machine_shape='NvidiaTeslaT4';request.session_timeout_seconds=3600
    request.dataset_data_sources=metadata['dataset_sources']
    request.competition_data_sources=[];request.kernel_data_sources=[];request.model_data_sources=[]
    request.kernel_execution_type=KernelExecutionType.SAVE_AND_RUN_ALL
    with api.build_kaggle_client() as client:
        return client.kernels.kernels_api_client.save_kernel(request)


def extract_verified(archive,destination):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        checks=json.loads(source.read('checksums.json'))
        for name,digest in checks.items():
            path=(destination/name).resolve()
            if Path(name).is_absolute() or not path.is_relative_to(destination):raise ValueError('ZIP_PATH_ESCAPE')
            raw=source.read(name)
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('ZIP_PAYLOAD_CHANGED')
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    return destination


def replay_offline(archive,index):
    """Upload measured cloud records after training; never rerun model inference."""
    if index.get('wandb_mode')!='offline':return index
    output=extract_verified(archive,Path(archive).parent/'wandb-replay')
    marker=output/'local-cloud-sync.json'
    if marker.exists():
        previous=json.loads(marker.read_text())
        if previous.get('status')=='PASS':return previous
    if not os.environ.get('WANDB_API_KEY'):
        os.environ['WANDB_API_KEY']=getpass.getpass('W&B API key for syncing measured Kaggle results (hidden): ').strip()
    try:
        import wandb
        try:from .tracking import log_predictions,prepare_wandb
        except ImportError:
            import sys
            sys.path.insert(0,str(ROOT));from hme_comer.tracking import log_predictions,prepare_wandb
        api=wandb.Api(timeout=30);api.viewer
        def read(name):return json.loads((output/name).read_text(encoding='utf-8'))
        original=read('config.json');info=read('run.json');summary=read('summary.json')
        cfg={**original,'wandb':{**original['wandb'],'mode':'online'}}
        rows=[{**row,'_image':output/'preview-images'/(row['id']+'.jpg')}
            for row in read('dataset-manifest.json') if row['split'] in ('validation','test')]
        if len(rows)!=100 or any(not row['_image'].is_file() for row in rows):raise RuntimeError('GALLERY_IMAGES_MISSING')
        for row in rows:
            if hashlib.sha256(row['_image'].read_bytes()).hexdigest()!=row['image_sha256']:raise RuntimeError('GALLERY_IMAGE_CHANGED')
        prepare_wandb(output)
        run=wandb.init(project=info['project'],entity=info['entity'],name=info['name'],group=info['group'],
            id=info['id'],resume='allow',mode='online',dir=str(output),job_type='fine-tune',
            tags=['CoMER','HME100K','kaggle-ddp2','measured-offline-synced-later'],
            config={**cfg,'original_logging_mode':'offline','history_replayed_from_saved_cloud_records':True},
            settings=wandb.Settings(disable_code=True,disable_git=True,console='off'))
        run.define_metric('epoch');run.define_metric('train/optimizer_step')
        run.define_metric('train/*',step_metric='train/optimizer_step')
        for prefix in ('val','epoch_train','lr','runtime'):run.define_metric(prefix+'/*',step_metric='epoch')
        run.define_metric('val/exp_rate',summary='max');run.define_metric('val/cer',summary='min')
        steps=defaultdict(list)
        for line in (output/'metrics.jsonl').read_text().splitlines():
            item=json.loads(line);steps[item['epoch']].append(item)
        with (output/'history.csv').open(encoding='utf-8',newline='') as stream:history=list(csv.DictReader(stream))
        try:
            for epoch_row in history:
                epoch=int(epoch_row['epoch'])
                for item in steps[epoch]:run.log({k:v for k,v in item.items() if k!='epoch'})
                part=read('baseline-validation.json' if epoch==0 else f'validation-{epoch:03}.json')
                log_predictions(run,cfg,part['metrics'],part['predictions'],part['groups'],rows,epoch)
                values={'epoch':epoch,'runtime/world_size':2,'runtime/epoch_seconds':float(epoch_row['seconds']),
                    'lr/encoder':float(epoch_row['encoder_lr']),'lr/decoder':float(epoch_row['decoder_lr'])}
                if epoch_row['train_loss']:values['epoch_train/loss']=float(epoch_row['train_loss'])
                run.log(values)
            run.log({'epoch':summary['last_epoch'],'evidence/curves':wandb.Image(str(output/'curves.png'))})
            run.summary.update({'best/epoch':summary['selected_best']['epoch'],
                'best/val_exp_rate':summary['selected_best']['exp_rate'],'best/val_loss':summary['selected_best']['loss'],
                'epochs_completed':summary['last_epoch'],'qa_only':False,'logging/replayed_offline_cloud_records':True})
            for key,value in read('baseline.json').items():run.summary['baseline/val_'+key]=value
            artifact=wandb.Artifact('hme500-final-cloud-'+info['id'],type='experiment-evidence',
                metadata={'measured_on':'Kaggle T4 x2','logging_mode':'offline replay; no training or inference repeated'})
            for path in sorted(output.iterdir()):
                if path.is_file() and (path.suffix in ('.json','.jsonl','.csv','.png','.md','.html') or path.name=='best-inference.pt'):
                    artifact.add_file(str(path),name=path.name)
            for path in sorted((output/'source').rglob('*')):
                if path.is_file():artifact.add_file(str(path),name=path.relative_to(output).as_posix())
            run.log_artifact(artifact,aliases=['completed','best'])
        finally:run.finish()
        links={'train':{'id':info['id'],'url':run.url}}
        for stage in ('before','after'):
            part=read('comparison-'+stage+'.json')
            run_id=hashlib.sha256((info['id']+stage).encode()).hexdigest()[:16]
            evaluation=wandb.init(project=info['project'],entity=info['entity'],name=info['name']+'-'+stage,
                group=info['group'],id=run_id,resume='allow',mode='online',dir=str(output),job_type='prepost-evaluation',
                config={**cfg,'evaluation_stage':stage,'checkpoint_sha256':part['checkpoint_sha256'],
                    'original_logging_mode':'offline','parent_run_id':info['id']},
                settings=wandb.Settings(disable_code=True,disable_git=True,console='off'))
            try:
                log_predictions(evaluation,cfg,part['metrics'],part['predictions'],part['groups'],rows,part['epoch'],split='test')
                evaluation.log({'evaluation/'+key:value for key,value in part['metrics'].items()})
                evaluation.summary.update({'evaluation/'+key:value for key,value in part['metrics'].items()})
                if stage=='after':
                    comparison=read('comparison.json')
                    evaluation.log({'comparison/chart':wandb.Image(str(output/'comparison.png')),
                        **{'comparison/delta_'+key:value for key,value in comparison['delta_after_minus_before'].items()}})
                    pairs=wandb.Table(columns=['id','original_jpeg','latex','before','after','before_exact','after_exact'])
                    images={row['id']:row['_image'] for row in rows}
                    for pair in comparison['pairs']:
                        pairs.add_data(pair['id'],wandb.Image(str(images[pair['id']])),pair['latex'],pair['before'],pair['after'],pair['before_exact'],pair['after_exact'])
                    evaluation.log({'comparison/paired_predictions':pairs})
            finally:evaluation.finish()
            links[stage]={'id':run_id,'url':evaluation.url}
        remote=api.run(info['entity']+'/'+info['project']+'/'+info['id'])
        records={int(row['epoch']):row for row in remote.scan_history(keys=['epoch','val/exp_rate','val/loss'])}
        for expected in history:
            actual=records[int(expected['epoch'])]
            if abs(actual['val/exp_rate']-float(expected['val_exp_rate']))>1e-7 or abs(actual['val/loss']-float(expected['val_loss']))>1e-6:
                raise RuntimeError('REPLAY_HISTORY_MISMATCH')
        report={'status':'PASS','links':links,'cloud_validation_history_matches_saved_csv':True,
            'retrained':False,'inference_repeated':False,'original_images_preserved':True,
            'note':'Metrics and galleries were measured on Kaggle and uploaded locally after completion.'}
        marker.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        return report
    finally:os.environ.pop('WANDB_API_KEY',None)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path)
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--no-wait',action='store_true')
    p.add_argument('--sync-only',type=Path,help='Upload measured offline results from a previously downloaded ZIP')
    a=p.parse_args()
    if a.sync_only:
        read_config(a.config)
        archive,index=verify_download(a.sync_only.parent)
        print(json.dumps(replay_offline(archive,index),indent=2),flush=True);return
    folder,cfg=prepare(a.config)
    print('Generated submission:',folder,flush=True)
    if a.prepare_only:return
    if not os.environ.get('KAGGLE_API_TOKEN'):
        os.environ['KAGGLE_API_TOKEN']=getpass.getpass('Kaggle API token (hidden; process memory only): ').strip()
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api=KaggleApi();api.authenticate()
        result=submit(api,folder)
        if getattr(result,'error',''):raise RuntimeError('KAGGLE_SUBMISSION_REJECTED')
        url=getattr(result,'url',None) or 'https://www.kaggle.com/code/'+cfg['kernel_ref']
        ref=cfg['kernel_ref']+'/'+str(result.version_number)
        (folder/'submission.json').write_text(json.dumps({'url':url,'version':result.version_number,'ref':ref},indent=2)+'\n',encoding='utf-8')
        print('Submitted:',url,flush=True)
        if a.no_wait:return
        while True:
            status=api.kernels_status(ref)
            value=str(getattr(status,'status',status)).lower()
            print('Kaggle status:',value,flush=True)
            if 'complete' in value:
                api.kernels_output(ref,path=str(folder/'outputs'),force=True,quiet=True,
                    file_pattern=RESULT_PATTERN)
                archive,index=verify_download(folder/'outputs')
                print('Verified downloaded ZIP:',archive,flush=True)
                print('Result:',json.dumps(index),flush=True)
                if index.get('wandb_mode')=='offline':print('W&B synchronization:',json.dumps(replay_offline(archive,index)),flush=True)
                return
            if any(word in value for word in ('error','fail','cancel')):raise RuntimeError('KAGGLE_RUN_FAILED; inspect notebook output')
            time.sleep(30)
    finally:os.environ.pop('KAGGLE_API_TOKEN',None)


if __name__=='__main__':main()
