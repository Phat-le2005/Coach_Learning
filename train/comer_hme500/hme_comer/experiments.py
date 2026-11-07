"""Create versioned experiment configs using only stdlib, before importing torch/W&B."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timezone
import errno
import json
import os
from pathlib import Path
import time
import threading

ROOT=Path(__file__).resolve().parents[1]
PROFILES={
    'v1':dict(label='finetune-single',devices=1,accumulate=4,compare_before_after=False),
    'v2':dict(label='finetune-ddp2',devices=2,accumulate=2,compare_before_after=False),
    'v3':dict(label='prepost-ddp2',devices=2,accumulate=2,compare_before_after=True),
}
_THREAD_LOCK=threading.Lock()


@contextmanager
def registry_lock(path):
    """OS lock survives process interruption; keep the file to avoid unlink/open races."""
    with _THREAD_LOCK, Path(path).open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        deadline=time.monotonic()+10
        while True:
            handle.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES,errno.EAGAIN,errno.EDEADLK):raise
                if time.monotonic()>deadline:raise RuntimeError('Experiment registry is busy; retry shortly.') from exc
                time.sleep(.05)
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_UN)


def next_trial(root,variant):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with registry_lock(root/f'.{variant}-sequence.lock'):
        path=root/f'.{variant}-sequence.json'
        number=(json.loads(path.read_text())['last'] if path.exists() else 0)+1
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps({'last':number}));temp.replace(path)
        return number


def create(variant='v3',root='/kaggle/working/comer_experiments',**overrides):
    profile=PROFILES[variant];trial=next_trial(root,variant)
    cfg=json.loads((ROOT/'config.example.json').read_text())
    cfg.update({k:v for k,v in profile.items() if k!='label'})
    cfg.update({k:v for k,v in overrides.items() if v is not None and k not in ('wandb_mode','entity','project')})
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    effective=cfg['batch_size']*cfg['accumulate']*cfg['devices']
    name=f"comer-hme500-{variant}-{profile['label']}-r{trial:03d}-s{cfg['seed']}-eb{effective}-{stamp}"
    cfg.update(output=str(Path(root).resolve()/name),experiment_version=variant)
    cfg['wandb'].update(name=name,group=name)
    for key,target in (('wandb_mode','mode'),('entity','entity'),('project','project')):
        if overrides.get(key) is not None:cfg['wandb'][target]=overrides[key]
    path=Path(root).resolve()/(name+'.config.json')
    path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return path,cfg


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variant',choices=PROFILES,default='v3');p.add_argument('--root',default='/kaggle/working/comer_experiments')
    p.add_argument('--data');p.add_argument('--epochs',type=int);p.add_argument('--seed',type=int)
    p.add_argument('--wandb-mode',choices=('online','offline','disabled'));p.add_argument('--entity');p.add_argument('--project')
    a=vars(p.parse_args());path,_=create(**a);print(path)


if __name__=='__main__':main()
