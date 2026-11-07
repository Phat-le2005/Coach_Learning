"""Submit a two-GPU Kaggle experiment from one JSON config; no credential files."""
import argparse
import ast
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
except Exception:
    raise RuntimeError('WANDB_SECRET_UNAVAILABLE: enable this notebook access to WANDB_API_KEY in Kaggle Secrets.') from None
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
cfg['wandb'].update(mode='online',entity=TASK['wandb']['entity'],project=TASK['wandb']['project'],name=name,group=name)
path=WORK/'comer.config.json';path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
env=os.environ.copy()
env.update(WANDB_API_KEY=secret,RUN_FINAL_TEST='1',PYTHONUNBUFFERED='1',CUBLAS_WORKSPACE_CONFIG=':4096:8')
log=WORK/'comer-run.log'
def command(args):
    with log.open('a',encoding='utf-8') as stream:
        process=subprocess.Popen(args,cwd=lab,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in process.stdout:
            safe=line.replace(secret,'[REDACTED]');print(safe,end='',flush=True);stream.write(safe);stream.flush()
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
        if secret.encode() in raw:raise RuntimeError('CREDENTIAL_IN_OUTPUT; refusing to package')
        z.writestr(p.name,raw);checks[p.name]=hashlib.sha256(raw).hexdigest()
    for p in sorted((lab/'hme_comer').glob('*.py')):
        raw=p.read_bytes();entry='source/hme_comer/'+p.name
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


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path)
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--no-wait',action='store_true')
    a=p.parse_args();folder,cfg=prepare(a.config)
    print('Generated submission:',folder,flush=True)
    if a.prepare_only:return
    if not os.environ.get('KAGGLE_API_TOKEN'):
        os.environ['KAGGLE_API_TOKEN']=getpass.getpass('Kaggle API token (hidden; process memory only): ').strip()
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api=KaggleApi();api.authenticate()
        result=api.kernels_push(str(folder),timeout='10800',acc='NvidiaTeslaT4')
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
                    file_pattern=r'.*(CoachLearning_CoMER_v5_Kaggle_DDP2_Results\.zip|result-index\.json)$')
                archive,index=verify_download(folder/'outputs')
                print('Verified downloaded ZIP:',archive,flush=True)
                print('Result:',json.dumps(index),flush=True);return
            if any(word in value for word in ('error','fail','cancel')):raise RuntimeError('KAGGLE_RUN_FAILED; inspect notebook output')
            time.sleep(30)
    finally:os.environ.pop('KAGGLE_API_TOKEN',None)


if __name__=='__main__':main()
