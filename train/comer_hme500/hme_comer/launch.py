"""Start one process per GPU; finalize with either test or a paired comparison."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def command(cfg,path,args,executable=sys.executable):
    devices=cfg.get('devices',1)
    if type(devices) is not int or devices not in (1,2):raise ValueError('devices must be 1 or 2')
    prefix=[executable,'-m','hme_comer.train']
    if devices==2:
        prefix=[executable,'-m','torch.distributed.run','--standalone','--nnodes=1','--nproc_per_node=2','-m','hme_comer.train']
    return [*prefix,'--config',str(path),*args]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path)
    p.add_argument('--finish',action='store_true');a,extra=p.parse_known_args()
    cfg=json.loads(a.config.read_text(encoding='utf-8'))
    if a.finish:
        target='hme_comer.compare' if cfg.get('compare_before_after') else 'hme_comer.final_test'
        subprocess.run([sys.executable,'-m',target,'--output',cfg['output'],'--device',cfg['device']],check=True)
    else:
        if cfg.get('devices',1)==2 and not ('--qa' in extra and cfg['device']=='cpu'):
            import torch
            if torch.cuda.device_count()<2:raise RuntimeError('Two GPUs required. Select Kaggle GPU T4 x2, then start a new run.')
        subprocess.run(command(cfg,a.config,extra),check=True)


if __name__=='__main__':main()
