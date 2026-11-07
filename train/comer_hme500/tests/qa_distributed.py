"""Opt-in Linux CPU two-rank integration on four real train JPEGs, never on held-out test."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import torch


def execute(config,root,resume=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    config_path=root/'config.json';config_path.write_text(json.dumps(config))
    processes=[]
    for rank in range(2):
        env={**os.environ,'RANK':str(rank),'LOCAL_RANK':str(rank),'WORLD_SIZE':'2',
             'COMER_QA_INIT_METHOD':(root/'gloo-store').resolve().as_uri()}
        args=[sys.executable,'-m','hme_comer.train','--config',str(config_path),'--qa']
        if resume:args+=['--resume',str(resume)]
        log=(root/f'rank-{rank}.log').open('w')
        processes.append((subprocess.Popen(args,env=env,stdout=log,stderr=subprocess.STDOUT),log))
    codes=[p.wait() for p,f in processes]
    for p,f in processes:f.close()
    if any(codes):
        for rank in range(2):print((root/f'rank-{rank}.log').read_text()[-6000:])
        raise RuntimeError(f'DDP QA failed: {codes}')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--upstream',required=True)
    p.add_argument('--root',required=True,type=Path);a=p.parse_args()
    if sys.platform=='win32':raise RuntimeError('Use a Linux Python/Gloo build for this CPU integration QA.')
    base=json.loads(Path('config.example.json').read_text())
    base.update(data=a.data,upstream=a.upstream,epochs=2,batch_size=1,accumulate=1,freeze_encoder_epochs=1,
        max_decode_tokens=12,device='cpu',devices=2,amp=False,media_samples=2,experiment_version='v3',compare_before_after=True)
    base['wandb'].update(mode='offline',name='v3-ddp-two-cpu-real-jpeg-qa',group='mechanical-qa-not-gpu-results')
    full={**base,'output':str((a.root/'full-run').resolve())}
    execute(full,a.root/'full-job')
    part={**base,'epochs':1,'output':str((a.root/'resumed-run').resolve())}
    execute(part,a.root/'first-job')
    part['epochs']=2;execute(part,a.root/'resume-job',Path(part['output'])/'last.pt')
    x=torch.load(Path(full['output'])/'last.pt',map_location='cpu',weights_only=True)
    y=torch.load(Path(part['output'])/'last.pt',map_location='cpu',weights_only=True)
    assert x['world_size']==2 and len(x['rank_rng'])==2
    assert all(torch.equal(v,y['state_dict'][k]) for k,v in x['state_dict'].items()),'Resumed model differs from uninterrupted model'
    for epoch in (1,2):
        ranks=json.loads((Path(full['output'])/f'rank-samples-{epoch:03}.json').read_text())['rank_samples']
        assert len(set(ranks[0])|set(ranks[1]))==4 and not set(ranks[0])&set(ranks[1])
    dirs=list((Path(full['output'])/'wandb').glob('offline-run-*'))
    assert len(dirs)==1,'More than one rank initialized a training W&B run'
    subprocess.run([sys.executable,'-m','hme_comer.compare','--output',full['output'],'--device','cpu','--qa'],check=True)
    report={'two_rank_training':True,'disjoint_samples':True,'single_training_wandb_run':True,
            'resume_tensor_equality':True,'paired_before_after_validation_qa':True,'qa_only':True,'cuda_tested':False}
    (a.root/'qa-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
