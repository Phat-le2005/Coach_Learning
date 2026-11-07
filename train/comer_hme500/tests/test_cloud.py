import ast
import hashlib
import json
import io
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile
from hme_comer.cloud import ROOT,RESULT_PATTERN,prepare,read_config,verify_download,submit,extract_verified,expand_trials,package_suite


class CloudConfig(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.cfg=json.loads((ROOT/'kaggle.v5.json').read_text())
        self.path=self.root/'config.json'
    def tearDown(self):self.temp.cleanup()
    def write(self):self.path.write_text(json.dumps(self.cfg),encoding='utf-8')
    def test_prepared_notebook_is_private_two_gpu_and_reads_secret_at_runtime(self):
        self.write();folder,_=prepare(self.path,self.root/'submission')
        meta=json.loads((folder/'kernel-metadata.json').read_text())
        self.assertTrue(meta['is_private']);self.assertTrue(meta['enable_gpu'])
        self.assertEqual(meta['machine_shape'],'NvidiaTeslaT4')
        notebook=json.loads((folder/'run.ipynb').read_text())
        code=notebook['cells'][1]['source'][0];ast.parse(code)
        self.assertIn('UserSecretsClient().get_secret',code)
        self.assertIn('torch.cuda.device_count()!=2',code)
        self.assertNotIn('KGAT_',code);self.assertNotIn('wandb_v1_',code)
        self.assertEqual(notebook['cells'][1]['outputs'],[])
    def test_credentials_cannot_enter_config(self):
        self.cfg['wandb']['api_key']='unit-test-not-a-real-key';self.write()
        with self.assertRaisesRegex(ValueError,'MUST_NOT_CONTAIN_A_KEY'):read_config(self.path)
    def test_unavailable_secret_records_offline_without_blocking_training(self):
        self.write();folder,_=prepare(self.path,self.root/'submission')
        code=json.loads((folder/'run.ipynb').read_text())['cells'][1]['source'][0]
        class Unavailable:
            def get_secret(self,label):raise RuntimeError('permission denied')
        state={}
        with patch.dict('sys.modules',{'kaggle_secrets':SimpleNamespace(UserSecretsClient=Unavailable)}),patch('sys.stdout',io.StringIO()):
            exec(code.split('import torch')[0],state)
        self.assertEqual(state['wandb_mode'],'offline');self.assertEqual(state['secret'],'')
    def test_result_filter_matches_only_expected_outputs(self):
        for name in ('CoachLearning_CoMER_v5_Kaggle_DDP2_Results.zip','result-index.json'):
            self.assertIsNotNone(re.fullmatch(RESULT_PATTERN,'/kaggle/working/'+name))
        self.assertIsNone(re.fullmatch(RESULT_PATTERN,'unrelated-checkpoint.pt'))
    def test_replay_extraction_rejects_escape_and_altered_payloads(self):
        archive=self.root/'payload.zip';raw=b'measured result'
        for name,digest,error in (('../escape.json',hashlib.sha256(raw).hexdigest(),'PATH_ESCAPE'),
                                  ('metrics.json','0'*64,'PAYLOAD_CHANGED')):
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr(name,raw);z.writestr('checksums.json',json.dumps({name:digest}))
            with self.assertRaisesRegex(ValueError,error):extract_verified(archive,self.root/'extracted')
        self.assertFalse((self.root/'escape.json').exists())
    def test_wrong_gpu_count_or_large_upload_policy_is_rejected(self):
        self.cfg['training']['devices']=1;self.write()
        with self.assertRaisesRegex(ValueError,'DDP2'):read_config(self.path)
        self.cfg['training']['devices']=2;self.cfg['training']['checkpoint_upload']='every_epoch';self.write()
        with self.assertRaisesRegex(ValueError,'COMPACT'):read_config(self.path)
    def test_download_checksums_and_ddp_result_are_verified(self):
        path=self.root/'CoachLearning_CoMER_v5_Kaggle_DDP2_Results.zip'
        raw=json.dumps({'status':'completed','world_size':2}).encode()
        with zipfile.ZipFile(path,'w') as archive:
            archive.writestr('result-index.json',raw)
            archive.writestr('checksums.json',json.dumps({'result-index.json':hashlib.sha256(raw).hexdigest()}))
        result,index=verify_download(self.root)
        self.assertEqual(result,path);self.assertEqual(index['world_size'],2)
    def test_download_refuses_missing_archive(self):
        with self.assertRaisesRegex(RuntimeError,'ONE_RESULT_ZIP'):verify_download(self.root)
    def test_submission_requests_run_all_with_t4_and_normalized_notebook(self):
        self.write();folder,_=prepare(self.path,self.root/'submission')
        captured=[]
        class Client:
            def __enter__(self):
                self.kernels=SimpleNamespace(kernels_api_client=SimpleNamespace(save_kernel=lambda request:captured.append(request) or 'accepted'))
                return self
            def __exit__(self,*args):pass
        api=SimpleNamespace(build_kaggle_client=Client)
        modules={
            'kagglesdk.kernels.types.kernels_api_service':SimpleNamespace(ApiSaveKernelRequest=SimpleNamespace),
            'kagglesdk.kernels.types.kernels_enums':SimpleNamespace(KernelExecutionType=SimpleNamespace(SAVE_AND_RUN_ALL=1))}
        with patch.dict('sys.modules',modules):self.assertEqual(submit(api,folder),'accepted')
        request=captured[0]
        self.assertEqual(request.kernel_execution_type,1)
        self.assertEqual(request.machine_shape,'NvidiaTeslaT4')
        self.assertEqual(request.session_timeout_seconds,3600)
        self.assertTrue(request.is_private)
        self.assertIsInstance(json.loads(request.text)['cells'][1]['source'],str)
    def test_suite_expansion_preserves_common_conditions_and_only_changes_declared_factors(self):
        self.cfg['training'].update(epochs=50,early_stopping_patience=50,train_scale_min=1.,train_scale_max=1.)
        self.cfg['trials']=[{'version':'v4-e50-ddp2','training':{'decoder_lr':1e-4}},
            {'version':'v5-e50-ddp2','training':{'decoder_lr':5e-5}},
            {'version':'v6-e50-scale-ddp2','training':{'decoder_lr':5e-5,'train_scale_min':.9,'train_scale_max':1.1}}]
        self.write();trials=expand_trials(read_config(self.path))
        self.assertEqual(len(trials),3)
        for i,trial in enumerate(trials):
            self.assertNotIn('trials',trial);self.assertEqual(trial['training']['devices'],2)
            self.assertEqual(trial['training']['epochs'],50);self.assertEqual(trial['training']['early_stopping_patience'],50)
            folder,_=prepare(trial,self.root/f'trial-{i}')
            code=json.loads((folder/'run.ipynb').read_text())['cells'][1]['source'][0]
            ast.parse(code);self.assertIn('REQUESTED_FULL_EPOCH_COUNT_NOT_REACHED',code)
        self.assertEqual(trials[0]['training']['decoder_lr'],1e-4)
        self.assertEqual(trials[1]['training']['train_scale_min'],1.)
        self.assertEqual(trials[2]['training']['train_scale_min'],.9)
        self.cfg['trials'][2]['version']=self.cfg['trials'][1]['version'];self.write()
        with self.assertRaisesRegex(ValueError,'DUPLICATE_TRIAL'):read_config(self.path)
    def test_suite_archive_keeps_trial_zips_and_checks_every_payload(self):
        (self.root/'cloud-config.json').write_text('{}')
        results=[]
        for version in ('v4','v5','v6'):
            archive=self.root/(version+'.zip')
            with zipfile.ZipFile(archive,'w') as z:z.writestr('measured.json','{}')
            results.append({'version':version,'archive':str(archive),'wandb':{},
                'result':{'last_epoch':50,'best':{'epoch':25,'exp_rate':.5},'before':{'exp_rate':.38},
                    'after':{'exp_rate':.62,'cer':.08,'token_error_rate':.07}}})
        target=package_suite(self.root,{'version':'suite-unit','source_revision':'a'*40},results)
        with zipfile.ZipFile(target) as z:
            checks=json.loads(z.read('checksums.json'))
            self.assertEqual(set(checks),set(z.namelist())-{'checksums.json'})
            for name,digest in checks.items():self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(),digest)
            for result in results:self.assertEqual(z.read(Path(result['archive']).name),Path(result['archive']).read_bytes())


if __name__=='__main__':unittest.main()
