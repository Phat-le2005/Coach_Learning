import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import torch
from torch import nn
from torch.utils.data.distributed import DistributedSampler
from hme_comer.experiments import create
from hme_comer.launch import command
from hme_comer.distributed import Context,TrainingModel,rng_state,restore_rng
from hme_comer.compare import paired
from hme_comer.train import read_config


class Versions(unittest.TestCase):
    def test_new_trials_are_unique_and_configs_are_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            p1,c1=create('v3',root=folder,wandb_mode='disabled')
            p2,c2=create('v3',root=folder,wandb_mode='disabled')
            self.assertIn('-r001-',c1['wandb']['name']);self.assertIn('-r002-',c2['wandb']['name'])
            self.assertNotEqual(c1['output'],c2['output'])
            self.assertEqual(c1['batch_size']*c1['devices']*c1['accumulate'],16)
            self.assertEqual(c1['devices'],2);self.assertTrue(c1['compare_before_after'])
            self.assertEqual(read_config(p1)['output'],c1['output'])
    def test_parallel_name_reservations_do_not_collide(self):
        with tempfile.TemporaryDirectory() as folder:
            with ThreadPoolExecutor(max_workers=4) as pool:
                configs=list(pool.map(lambda _:create('v2',root=folder)[1],range(4)))
            self.assertEqual(len({c['wandb']['name'] for c in configs}),4)
            self.assertEqual(json.loads((Path(folder)/'.v2-sequence.json').read_text())['last'],4)
    def test_v1_is_available_and_v2_does_not_enable_comparison(self):
        with tempfile.TemporaryDirectory() as folder:
            _,a=create('v1',root=folder);_,b=create('v2',root=folder)
            self.assertEqual(a['devices'],1);self.assertEqual(a['accumulate'],4)
            self.assertEqual(b['devices'],2);self.assertFalse(b['compare_before_after'])
    def test_v4_is_local_single_gpu_with_otsu_and_paired_comparison(self):
        from hme_comer.data import OTSU_PREPROCESS
        with tempfile.TemporaryDirectory() as folder:
            path,cfg=create('v4',root=folder,wandb_mode='disabled')
            self.assertEqual(cfg['devices'],1);self.assertEqual(cfg['batch_size'],1)
            self.assertEqual(cfg['accumulate'],16);self.assertTrue(cfg['compare_before_after'])
            self.assertEqual(cfg['preprocess'],OTSU_PREPROCESS)
            self.assertIn('otsu-local-cuda1',cfg['wandb']['name'])
            self.assertEqual(read_config(path)['preprocess'],OTSU_PREPROCESS)


class DistributedContract(unittest.TestCase):
    def test_launcher_starts_exactly_two_workers(self):
        cmd=command({'devices':2},'config with spaces.json',['--resume','last.pt'],'python')
        self.assertIn('torch.distributed.run',cmd);self.assertIn('--nproc_per_node=2',cmd)
        self.assertEqual(cmd[-4:],['--config','config with spaces.json','--resume','last.pt'])
    def test_sampler_is_disjoint_and_complete(self):
        samplers=[DistributedSampler(range(400),num_replicas=2,rank=i,seed=42) for i in range(2)]
        for s in samplers:s.set_epoch(3)
        ids=[set(s) for s in samplers]
        self.assertFalse(ids[0]&ids[1]);self.assertEqual(ids[0]|ids[1],set(range(400)))
    def test_token_normalization_matches_global_objective(self):
        model=nn.Linear(1,1,bias=False)
        # DDP has averaged summed gradients from ranks with different token counts.
        model.weight.grad=torch.tensor([[5.]])
        ctx=object.__new__(Context);ctx.world=2
        with patch.object(ctx,'reduce',return_value=[12.,8.]):
            loss=ctx.normalize_gradients(model,5.,2)
        self.assertAlmostEqual(float(model.weight.grad),10/8)
        self.assertEqual(loss,12/8)
    def test_rank_rng_roundtrip(self):
        device=torch.device('cpu');state=rng_state(device);expected=torch.rand(4)
        restore_rng(state,device);self.assertTrue(torch.equal(expected,torch.rand(4)))
    def test_freezing_keeps_registered_parameters_fixed(self):
        class Core(nn.Module):
            def __init__(self):
                super().__init__();self.encoder_layer=nn.Linear(2,2);self.decoder_layer=nn.Linear(2,1)
            def encoder(self,x,m):return self.encoder_layer(x),m
            def decoder(self,x,m,t):return self.decoder_layer(x)
            def forward(self,x,m,t):return self.decoder(torch.cat((self.encoder(x,m)[0],)*2),m,t)
        core=Core();wrapper=TrainingModel(core);params=[id(p) for p in wrapper.parameters()]
        wrapper.frozen=True;wrapper(torch.ones(1,2),torch.zeros(1),None).sum().backward()
        self.assertIsNone(core.encoder_layer.weight.grad)
        core.zero_grad(set_to_none=True);wrapper.frozen=False
        wrapper(torch.ones(1,2),torch.zeros(1),None).sum().backward()
        self.assertIsNotNone(core.encoder_layer.weight.grad)
        self.assertEqual(params,[id(p) for p in wrapper.parameters()])


class PairedComparison(unittest.TestCase):
    def parts(self):
        b={'ids':['a'],'dataset_fingerprint':'same','metrics':{'loss':2.,'exp_rate':0.,'cer':1.,'token_error_rate':1.},
           'predictions':[dict(id='a',latex='x',target='x',prediction='y',group='Cơ bản',exact=False,cer=1.)]}
        a={'ids':['a'],'dataset_fingerprint':'same','metrics':{'loss':1.,'exp_rate':1.,'cer':0.,'token_error_rate':0.},
           'predictions':[dict(id='a',latex='x',target='x',prediction='x',group='Cơ bản',exact=True,cer=0.)]}
        return b,a
    def test_deltas_and_improved_example(self):
        rows,delta=paired(*self.parts())
        self.assertEqual(rows[0]['outcome'],'improved');self.assertEqual(delta['exp_rate'],1)
        self.assertEqual(delta['cer'],-1)
    def test_mismatched_samples_and_labels_rejected(self):
        b,a=self.parts();a['ids']=['other']
        with self.assertRaisesRegex(ValueError,'NOT_PAIRED'):paired(b,a)
        b,a=self.parts();a['predictions'][0]['latex']='z'
        with self.assertRaisesRegex(ValueError,'LABEL_CHANGED'):paired(b,a)


if __name__=='__main__':unittest.main()
