"""Test Git credentials and the Bash workflow without cloud keys or model training."""
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from kaggle_bootstrap import checkout_repo

ROOT=Path(__file__).resolve().parents[1]
REPO='https://github.com/Phat-le2005/Coach_Learning.git'


class GitBootstrap(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.dest=Path(self.tmp.name)/'Coach_Learning'
    def tearDown(self): self.tmp.cleanup()
    def stub_checkout(self):
        (self.dest/'.git').mkdir(parents=True)
        p=self.dest/'train/comer_hme500/scripts/run_kaggle.sh'
        p.parent.mkdir(parents=True);p.write_text('# test fixture')
    def test_clone_token_stays_out_of_command_and_origin(self):
        calls=[];askpasses=[]
        def fake_run(cmd,**kw):
            calls.append(cmd)
            self.assertNotIn('fixture-token', ' '.join(cmd))
            self.assertEqual(kw['env']['COACH_GIT_TOKEN'],'fixture-token')
            askpass=Path(kw['env']['GIT_ASKPASS']);askpasses.append(askpass)
            text=askpass.read_text()
            self.assertIn('$COACH_GIT_TOKEN',text);self.assertNotIn('fixture-token',text)
            if 'clone' in cmd:self.stub_checkout()
            return subprocess.CompletedProcess(cmd,0,stdout='a'*40 if 'rev-parse' in cmd else '')
        with patch('kaggle_bootstrap.subprocess.run',side_effect=fake_run):
            lab,rev=checkout_repo(REPO,'main',self.dest,token='fixture-token')
        self.assertEqual(lab,self.dest/'train/comer_hme500');self.assertEqual(rev,'a'*40)
        self.assertTrue(any(REPO in c and 'clone' in c for c in calls))
        self.assertTrue(all(not p.exists() for p in askpasses))
    def test_existing_clean_repo_fast_forward_only(self):
        self.stub_checkout();calls=[]
        def fake_run(cmd,**kw):
            calls.append(cmd)
            val=REPO if 'get-url' in cmd else ('main' if '--show-current' in cmd else ('a'*40 if 'rev-parse' in cmd else ''))
            return subprocess.CompletedProcess(cmd,0,stdout=val)
        with patch('kaggle_bootstrap.subprocess.run',side_effect=fake_run):checkout_repo(REPO,'main',self.dest)
        self.assertTrue(any('pull' in c and '--ff-only' in c for c in calls))
    def test_dirty_checkout_is_preserved(self):
        self.stub_checkout();calls=[]
        def fake_run(cmd,**kw):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd,0,stdout=REPO if 'get-url' in cmd else ' M local.py')
        with patch('kaggle_bootstrap.subprocess.run',side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError,'local edits'):checkout_repo(REPO,'main',self.dest)
        self.assertFalse(any('pull' in c or 'reset' in c for c in calls))
    def test_credential_urls_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'without credentials'):
            checkout_repo('https://user:fixture-token@github.com/owner/repo.git','main',self.dest)
    def test_git_auth_error_does_not_expose_stderr(self):
        def fake_run(cmd,**kw):
            raise subprocess.CalledProcessError(128,cmd,stderr='fixture-token authentication details')
        with patch('kaggle_bootstrap.subprocess.run',side_effect=fake_run):
            with self.assertRaises(RuntimeError) as caught:checkout_repo(REPO,'main',self.dest)
        self.assertNotIn('fixture-token',str(caught.exception))


class Notebook(unittest.TestCase):
    def test_notebook_clone_and_bash_cells_are_clean(self):
        nb=json.loads((ROOT/'CoachLearning_CoMER_HME500_Kaggle.ipynb').read_text(encoding='utf-8'))
        sources=[]
        for c in nb['cells']:
            if c['cell_type']=='code':
                text=''.join(c['source']);ast.parse(text);sources.append(text)
                self.assertEqual(c['outputs'],[]);self.assertIsNone(c['execution_count'])
        joined='\n'.join(sources)
        self.assertIn((ROOT/'kaggle_bootstrap.py').read_text(encoding='utf-8').strip(),joined)
        self.assertIn('scripts/run_kaggle.sh',joined)
        self.assertNotIn('sgu-2026-facial-expression-recognition',joined)
        self.assertNotIn('EMBEDDED_SOURCE_B64',joined)
        for text in sources:
            for node in ast.walk(ast.parse(text)):
                if isinstance(node,ast.Import):
                    self.assertNotIn('wandb',[n.name for n in node.names])
                if isinstance(node,ast.ImportFrom): self.assertNotEqual(node.module,'wandb')
        self.assertNotIn('wandb==0.22.3',joined)


class BashWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        candidates=[os.environ.get('COACH_TEST_BASH'),
                    'C:/Program Files/Git/bin/bash.exe' if os.name=='nt' else shutil.which('bash')]
        cls.bash=next((x for x in candidates if x and Path(x).is_file()),None)
        if not cls.bash:raise unittest.SkipTest('Bash is not installed')
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.calls=self.root/'calls.txt';self.fake=self.root/'python-fixture.sh'
        self.fake.write_text('#!/usr/bin/env bash\nset -eu\n'
            'if [[ "${1:-}" == -c ]]; then exec "$REAL_PYTHON" "$@"; fi\n'
            'printf "%s\\t" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
            'exit "${FIXTURE_EXIT:-0}"\n',encoding='utf-8')
        self.fake.chmod(0o700)
        self.config=self.root/'config with spaces.json'
        self.output=self.root/'output with spaces'
        self.config.write_text(json.dumps({'output':str(self.output),'device':'cpu'}))
        self.env={**os.environ,'PYTHON_BIN':self.fake.as_posix(),'CALL_LOG':self.calls.as_posix(),
                  'REAL_PYTHON':Path(sys.executable).as_posix(),'RUN_FINAL_TEST':'1'}
    def tearDown(self):self.tmp.cleanup()
    def run_script(self,*args):
        return subprocess.run([self.bash,str(ROOT/'scripts/run_kaggle.sh'),*map(str,args)],
            env=self.env,capture_output=True,text=True)
    def test_help(self):
        p=self.run_script('--help');self.assertEqual(p.returncode,0);self.assertIn('all CONFIG.json',p.stdout)
    def test_all_order_and_final_output_path(self):
        p=self.run_script('all',self.config);self.assertEqual(p.returncode,0,p.stderr)
        calls=self.calls.read_text().splitlines()
        self.assertEqual(len(calls),6)
        for c,keyword in zip(calls,('pip','check_runtime','unittest','fetch_upstream','hme_comer.launch','--finish')):
            self.assertIn(keyword,c)
        self.assertIn(str(self.config),calls[-1])
    def test_setup_failure_prevents_training(self):
        self.env['FIXTURE_EXIT']='17'
        p=self.run_script('all',self.config);self.assertEqual(p.returncode,17)
        self.assertEqual(len(self.calls.read_text().splitlines()),1)
    def test_resume_and_qa_flags_forwarded(self):
        p=self.run_script('train',self.config,'--resume','checkpoint with spaces.pt','--qa')
        self.assertEqual(p.returncode,0,p.stderr)
        c=self.calls.read_text();self.assertIn('--resume\tcheckpoint with spaces.pt\t--qa',c)
    def test_qa_final_test_guard_runs_before_setup(self):
        p=self.run_script('all',self.config,'--qa');self.assertEqual(p.returncode,2)
        self.assertFalse(self.calls.exists())
    def test_disable_final_test(self):
        self.env['RUN_FINAL_TEST']='0'
        p=self.run_script('all',self.config);self.assertEqual(p.returncode,0,p.stderr)
        self.assertNotIn('--finish',self.calls.read_text())
    def test_review_dispatch_does_not_run_setup_or_training(self):
        p=self.run_script('review',self.output)
        self.assertEqual(p.returncode,0,p.stderr)
        calls=self.calls.read_text().splitlines();self.assertEqual(len(calls),1)
        self.assertIn('hme_comer.review',calls[0]);self.assertIn(str(self.output),calls[0])


if __name__=='__main__':unittest.main()
