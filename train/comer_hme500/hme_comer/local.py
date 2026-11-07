"""Run v4 on one local CUDA GPU: smoke check, full fine-tune, paired evaluation."""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
from .experiments import create, ROOT


def child(module, arguments, log, env):
    """Keep credentials in the child environment; redact any accidental console echo."""
    secret=env.get('WANDB_API_KEY','')
    with Path(log).open('w',encoding='utf-8') as stream:
        with subprocess.Popen([sys.executable,'-u','-m',module,*map(str,arguments)],cwd=ROOT,
                env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                text=True,encoding='utf-8',errors='replace') as process:
            for line in process.stdout:
                safe=line.replace(secret,'[REDACTED]') if secret else line
                stream.write(safe);stream.flush();print(safe,end='',flush=True)
            if process.wait():raise RuntimeError('LOCAL_CHILD_FAILED: '+module)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',required=True,type=Path)
    parser.add_argument('--upstream',required=True,type=Path)
    parser.add_argument('--root',type=Path,default=ROOT.parents[1]/'.tmp/comer-local-experiments')
    parser.add_argument('--epochs',type=int,default=30)
    parser.add_argument('--entity')
    parser.add_argument('--wandb-mode',choices=('online','offline','disabled'),default='online')
    parser.add_argument('--smoke-only',action='store_true')
    args=parser.parse_args()
    if args.epochs<1:parser.error('--epochs must be positive')
    if args.wandb_mode=='online' and not os.environ.get('WANDB_API_KEY'):
        os.environ['WANDB_API_KEY']=getpass.getpass('W&B API key (hidden; process memory only): ').strip()
    env=os.environ.copy()
    env.update(PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',CUBLAS_WORKSPACE_CONFIG=':4096:8')
    root=args.root.resolve();root.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    session=root/('session-'+stamp+'.json')
    state=dict(status='starting',project='coachlearning-handwritten-math',execution='local-cuda1',
        credential_storage='process environment only; never config/argv/source')
    def record():session.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    record()
    try:
        entity=args.entity
        if args.wandb_mode=='online':
            import wandb
            api=wandb.Api(timeout=30)
            viewer=api.viewer
            entity=entity or api.default_entity
            print('W&B authenticated; target:',entity+'/'+state['project'],flush=True)
        common=dict(data=str(args.data.resolve()),upstream=str(args.upstream.resolve()),
            wandb_mode=args.wandb_mode,entity=entity)
        qa_path,qa_cfg=create('v4',root=root/'qa',epochs=2,freeze_encoder_epochs=1,accumulate=1,media_samples=2,**common)
        qa_cfg['wandb']['name']+='-qa-only';qa_cfg['wandb']['group']=qa_cfg['wandb']['name']
        qa_path.write_text(json.dumps(qa_cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        state.update(status='smoke-running',qa_output=qa_cfg['output']);record()
        print('GPU SMOKE CHECK: 4 train / 2 validation, 2 epochs, 8 update attempts, freeze/unfreeze; QA only.',flush=True)
        child('hme_comer.train',['--config',qa_path,'--qa'],root/(stamp+'-qa.log'),env)
        qa_out=Path(qa_cfg['output'])
        qa_summary=json.loads((qa_out/'summary.json').read_text())
        qa_runtime=json.loads((qa_out/'runtime.json').read_text())
        if not qa_summary['qa_only'] or qa_summary['optimizer_steps']<1 or not qa_runtime['device'].startswith('cuda'):
            raise RuntimeError('CUDA_SMOKE_NOT_VERIFIED')
        if args.smoke_only:
            state.update(status='smoke-completed',qa_summary=qa_summary);record();return
        path,cfg=create('v4',root=root,epochs=args.epochs,**common)
        state.update(status='training',config=str(path),output=cfg['output']);record()
        print('FULL LOCAL RUN:',cfg['wandb']['name'],flush=True)
        child('hme_comer.train',['--config',path],root/(stamp+'-train.log'),env)
        state.update(status='paired-evaluation');record()
        child('hme_comer.compare',['--output',cfg['output'],'--device','cuda:0'],root/(stamp+'-comparison.log'),env)
        child('hme_comer.review',['--output',cfg['output']],root/(stamp+'-review.log'),env)
        state.update(status='completed',summary=json.loads((Path(cfg['output'])/'summary.json').read_text()))
        record();print('LOCAL SESSION COMPLETE:',session,flush=True)
    except BaseException as exc:
        state.update(status='failed',error_type=type(exc).__name__);record()
        # Authentication libraries can include credentials in exception strings.
        print('Local run stopped:',type(exc).__name__,'See the saved session and redacted stage logs.',flush=True)
        raise SystemExit(1) from None
    finally:
        env.pop('WANDB_API_KEY',None)
        os.environ.pop('WANDB_API_KEY',None)


if __name__=='__main__':main()
