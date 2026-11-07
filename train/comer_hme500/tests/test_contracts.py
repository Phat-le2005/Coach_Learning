"""Unit fixtures are mechanical checks; actual training QA uses the user's real JPEGs."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image
import torch
from hme_comer.data import tokens, safe_path, resolve_metadata, fit_vocabulary, input_array, configure_preprocess, PREPROCESS, OTSU_PREPROCESS
from hme_comer.metrics import collate, edit_distance
from hme_comer.tracking import bundle, write_json, log_model, log_final_model
from hme_comer.train import read_config, DEFAULTS, signature


class Contracts(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def test_kaggle_nested_path_and_ambiguous_dataset(self):
        p=self.root/'data-finetune-comer/CoachLearning_500_HME100K/metadata.json'
        p.parent.mkdir(parents=True);p.write_text('[]')
        self.assertEqual(resolve_metadata(self.root),p.resolve())
        q=self.root/'copy/metadata.json';q.parent.mkdir();q.write_text('[]')
        with self.assertRaisesRegex(ValueError,'Expected one'): resolve_metadata(self.root)
    def test_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError,'ESCAPE'): safe_path(self.root,'../secret.jpg')
    def test_vocabulary_never_fits_heldout(self):
        rows=[{'split':'train','_words':['x',r'\cot']},{'split':'test','_words':[r'\ln']}]
        with self.assertRaisesRegex(ValueError,'HELDOUT_UNKNOWN'):fit_vocabulary(rows,{'x':0})
    def test_new_tokens_preserve_original_ids(self):
        rows=[{'split':'train','_words':['x',r'\cot']},{'split':'validation','_words':['x']}]
        v,added=fit_vocabulary(rows,{'<pad>':0,'x':1})
        self.assertEqual(v['x'],1);self.assertEqual(v[r'\cot'],2)
        self.assertEqual(added,[r'\cot'])
    def test_tokenization_preserves_latex_commands(self):
        self.assertEqual(tokens(r'\frac { x } { 1 0 }'),[r'\frac','{','x','}','{','1','0','}'])
        self.assertEqual(tokens("x'"),['x',r'\prime'])
    def test_preprocess_read_only_and_padding_mask(self):
        p=self.root/'unit.jpg';Image.new('RGB',(180,45),(245,240,230)).save(p)
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        a=input_array({'_image':p})
        x,m,t=collate([(torch.from_numpy(a)[None],[3])])
        self.assertEqual(x.shape,(1,1,64,192));self.assertFalse(m[0,44,179]);self.assertTrue(m[0,45,179])
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),digest)
    def test_evidence_archive_checksums_and_no_wandb_cache(self):
        write_json(self.root/'summary.json',{'completed':True});bundle(self.root);bundle(self.root)
        with zipfile.ZipFile(self.root/'experiment_evidence.zip') as z:
            prefix=self.root.name+'/'
            checks=json.loads(z.read(prefix+'checksums.json'))
            self.assertNotIn('checksums.json',checks)
            for n,h in checks.items(): self.assertEqual(hashlib.sha256(z.read(prefix+n)).hexdigest(),h)
    def test_otsu_removes_paper_background_without_rewriting_jpeg(self):
        import numpy as np
        pixels=np.tile(np.linspace(190,225,180,dtype=np.uint8),(45,1))
        pixels[12:32,25:155]=25
        path=self.root/'paper.jpg';Image.fromarray(pixels).save(path,quality=95)
        before=path.read_bytes();row={'_image':path}
        legacy=input_array(row)
        configure_preprocess([row],{'preprocess':OTSU_PREPROCESS})
        clean=input_array(row)
        self.assertEqual(clean.shape,legacy.shape)
        self.assertEqual(set(np.unique(clean)),{0.,1.})
        self.assertTrue(np.all(clean[:8]==0));self.assertGreater(float(legacy[:8].mean()),.05)
        self.assertEqual(path.read_bytes(),before)
    def test_preprocess_contract_applies_to_every_split_and_rejects_unknown_method(self):
        rows=[{'split':s} for s in ('train','validation','test')];report={}
        configure_preprocess(rows,{'preprocess':OTSU_PREPROCESS},report)
        self.assertEqual({r['_preprocess'] for r in rows},{OTSU_PREPROCESS})
        self.assertEqual(report['preprocess'],OTSU_PREPROCESS)
        configure_preprocess(rows,{})
        self.assertEqual({r['_preprocess'] for r in rows},{PREPROCESS})
        with self.assertRaisesRegex(ValueError,'INVALID_PREPROCESS'):configure_preprocess(rows,{'preprocess':'other'})
    def test_secrets_cannot_enter_config(self):
        p=self.root/'config.json';write_json(p,{'wandb':{'api_key':'unit-test-not-a-key'}})
        with self.assertRaisesRegex(ValueError,'UNKNOWN_WANDB'):read_config(p)
    def test_compact_model_export_preserves_fp32_weights_and_local_resume_checkpoint(self):
        full=dict(state_dict={'weight':torch.tensor([[1.,2.]])},hyper_parameters={'fixture':True},
            vocabulary={'x':0},epoch=5,dataset_fingerprint='fixture',qa_only=True,
            optimizer={'large':'fixture-only'},torch_rng=torch.get_rng_state())
        path=self.root/'best.pt';torch.save(full,path);before=path.read_bytes()
        cfg={'checkpoint_upload':'final_inference','preprocess':OTSU_PREPROCESS,'wandb':{'mode':'disabled'}}
        exported=log_final_model(None,self.root,cfg)
        value=torch.load(exported,map_location='cpu',weights_only=True)
        self.assertTrue(torch.equal(value['state_dict']['weight'],full['state_dict']['weight']))
        self.assertEqual(value['state_dict']['weight'].dtype,torch.float32)
        self.assertNotIn('optimizer',value);self.assertNotIn('torch_rng',value)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(value['source_full_checkpoint_sha256'],hashlib.sha256(before).hexdigest())
    def test_compact_policy_does_not_upload_per_epoch_checkpoints(self):
        cfg={'checkpoint_upload':'final_inference','wandb':{'mode':'online','log_checkpoints':True}}
        log_model(None,self.root,cfg,[],{})
        self.assertFalse(list(self.root.iterdir()))
    def test_resume_signature_allows_only_epoch_extension(self):
        a=dict(DEFAULTS);b={**a,'epochs':100,'decoder_lr':2e-4}
        self.assertNotEqual(signature(a),signature(b))
        b['decoder_lr']=a['decoder_lr'];self.assertEqual(signature(a),signature(b))
        b['preprocess']=OTSU_PREPROCESS;self.assertNotEqual(signature(a),signature(b))
    def test_edit_distance(self):
        self.assertEqual(edit_distance('abc','adc'),1)
        self.assertEqual(edit_distance([1,2,3],[1,3]),1)


if __name__=='__main__': unittest.main()
