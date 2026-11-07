"""Endpoint safety tests, not detector/handwriting accuracy evidence."""
import importlib.util, os, pathlib, unittest
os.environ['OCR_V2_SIDECAR_TOKEN']='isolated-test-token-with-at-least-32-characters'
spec=importlib.util.spec_from_file_location('ocr_lab_service',pathlib.Path(__file__).with_name('service.py'))
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
from fastapi.testclient import TestClient
class Safety(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(service.app);self.auth={'Authorization':'Bearer '+os.environ['OCR_V2_SIDECAR_TOKEN']}
    def test_auth_and_browser_origin(self):
        self.assertEqual(self.client.get('/health').status_code,401)
        self.assertEqual(self.client.get('/health',headers={**self.auth,'Origin':'https://attacker.invalid'}).status_code,403)
        self.assertEqual(self.client.get('/health',headers=self.auth).status_code,200)
    def test_no_path_or_url_inference_and_size_limit(self):
        for value in ({'model':'LAYOUT_M','path':'C:/secret'},{'model':'LAYOUT_M','png':'https://attacker.invalid/ink.png'},{'model':'OTHER','png':''}):
            self.assertEqual(self.client.post('/infer',json=value,headers=self.auth).status_code,400)
        self.assertEqual(self.client.post('/infer',content=b'x'*4_000_001,headers=self.auth).status_code,413)
if __name__=='__main__': unittest.main()
