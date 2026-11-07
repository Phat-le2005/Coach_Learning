import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile
from hme_comer.cloud import ROOT,prepare,read_config,verify_download,submit


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


if __name__=='__main__':unittest.main()
