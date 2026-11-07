"""DDP context; token-weighted gradients and rank-local RNG checkpoints."""
from contextlib import nullcontext
from datetime import timedelta
import os
import random
import numpy as np
import torch
import torch.distributed as dist
from torch import nn
from torch.nn.parallel import DistributedDataParallel


class TrainingModel(nn.Module):
    """Keep DDP's parameter set fixed while freezing the encoder's autograd graph."""
    def __init__(self, core):
        super().__init__();self.core=core;self.frozen=False

    def forward(self, images, masks, targets):
        if not self.frozen: return self.core(images,masks,targets)
        with torch.no_grad(): features,mask=self.core.encoder(images,masks)
        return self.core.decoder(torch.cat((features,features)),torch.cat((mask,mask)),targets)


def rng_state(device):
    state=np.random.get_state()
    return dict(torch_rng=torch.get_rng_state(),python_rng=random.getstate(),
        numpy_rng=(state[0],state[1].tolist(),*state[2:]),
        cuda_rng=torch.cuda.get_rng_state(device) if device.type=='cuda' else None)


def restore_rng(state,device):
    torch.set_rng_state(state['torch_rng']);random.setstate(state['python_rng'])
    n=state['numpy_rng'];np.random.set_state((n[0],np.array(n[1],dtype=np.uint32),*n[2:]))
    if device.type=='cuda' and state['cuda_rng'] is not None: torch.cuda.set_rng_state(state['cuda_rng'],device)


class Context:
    def __init__(self,cfg,qa=False):
        self.world=int(os.environ.get('WORLD_SIZE','1'))
        self.rank=int(os.environ.get('RANK','0'));self.local_rank=int(os.environ.get('LOCAL_RANK','0'))
        if self.world!=cfg['devices']: raise RuntimeError('GPU count/config mismatch. Use hme_comer.launch or the .sh runner.')
        self.lead=self.rank==0
        device=torch.device(cfg['device'])
        if device.type=='cuda':
            if torch.cuda.device_count()<self.world: raise RuntimeError(f'Requires {self.world} GPUs. Select Kaggle GPU T4 x2 for v2/v3.')
            self.device=torch.device('cuda',self.local_rank if self.world>1 else (device.index or 0))
            torch.cuda.set_device(self.device)
        else:
            if self.world>1 and not qa: raise RuntimeError('Multi-process CPU is QA only; v2/v3 training requires two CUDA GPUs.')
            self.device=device
        self.backend='nccl' if self.device.type=='cuda' else 'gloo'
        if self.world>1:
            kwargs={}
            if self.device.type=='cuda':kwargs['device_id']=self.device
            if qa and os.environ.get('COMER_QA_INIT_METHOD'):
                kwargs['init_method']=os.environ['COMER_QA_INIT_METHOD']
            dist.init_process_group(self.backend,rank=self.rank,world_size=self.world,
                                    timeout=timedelta(minutes=5),**kwargs)

    def barrier(self):
        if self.world>1: dist.barrier()

    def broadcast(self,value):
        if self.world==1:return value
        data=[value if self.lead else None];dist.broadcast_object_list(data,src=0)
        return data[0]

    def reduce(self,values,maximum=False):
        t=torch.tensor(values,dtype=torch.float64,device=self.device)
        if self.world>1:dist.all_reduce(t,op=dist.ReduceOp.MAX if maximum else dist.ReduceOp.SUM)
        return t.tolist()

    def gather_rng(self):
        return self.gather(rng_state(self.device))

    def gather(self,value):
        if self.world==1:return [value]
        values=[None]*self.world;dist.all_gather_object(values,value);return values

    def wrap(self,wrapper):
        if self.world==1:return wrapper
        # Encoder is unused during warmup, then participates without changing parameter registration.
        return DistributedDataParallel(wrapper,device_ids=[self.local_rank] if self.device.type=='cuda' else None,
                                       find_unused_parameters=True)

    def sync_context(self,wrapped,update):
        return wrapped.no_sync() if self.world>1 and not update else nullcontext()

    def normalize_gradients(self,model,local_loss,local_tokens):
        loss,tokens=self.reduce([local_loss,local_tokens])
        # DDP averages rank gradients; restore the global summed-loss / global-token objective.
        for p in model.parameters():
            if p.grad is not None:p.grad.mul_(self.world/tokens)
        return loss/tokens

    def close(self):
        if self.world>1 and dist.is_initialized():dist.destroy_process_group()
