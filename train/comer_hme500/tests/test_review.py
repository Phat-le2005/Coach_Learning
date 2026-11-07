import base64
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from hme_comer.review import review


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')


class ValidationReview(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data=self.root/'dataset';self.data.mkdir();self.run=self.root/'run';self.run.mkdir()
        self.image=self.data/'original.jpg';self.raw=b'jpeg-fixture-only-not-training-data';self.image.write_bytes(self.raw)
        self.rows=[dict(id='a',split='validation',latex='x',image_path='original.jpg'),
                   dict(id='b',split='validation',latex='y',image_path='original.jpg'),
                   dict(id='test-only',split='test',latex='z',image_path='original.jpg')]
        self.predictions=[dict(id='a',group='Cơ bản',latex='x',prediction='<img onerror="alert(1)">',
                              exact=False,cer=1.,character_edits=1,token_edits=1),
                          dict(id='b',group='Cơ bản',latex='y',prediction='y',exact=True,cer=0.,character_edits=0,token_edits=0)]
        write(self.run/'config.json',{'data':str(self.data)})
        write(self.run/'summary.json',{'selected_best':{'epoch':15},'qa_only':False})
        write(self.run/'dataset-manifest.json',[{**r,'image_sha256':hashlib.sha256(self.raw).hexdigest()} for r in self.rows])
        self.refresh_metadata();self.refresh_predictions()
    def refresh_metadata(self):
        write(self.data/'metadata.json',self.rows)
        write(self.run/'dataset-audit.json',{'metadata_sha256':hashlib.sha256((self.data/'metadata.json').read_bytes()).hexdigest(),'fingerprint':'fixture'})
    def refresh_predictions(self):
        write(self.run/'validation-015.json',{'metrics':{'samples':len(self.predictions),'exp_rate':.5},'predictions':self.predictions})
    def tearDown(self):self.temp.cleanup()
    def test_wrong_samples_only_original_bytes_and_html_escaping(self):
        before=(self.data/'metadata.json').read_bytes()
        details,paths=review(self.run)
        self.assertEqual((details['correct'],details['incorrect']),(1,1))
        with paths['csv'].open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
        self.assertEqual([r['id'] for r in rows],['a']);self.assertEqual(rows[0]['review_note'],'')
        page=paths['html'].read_text(encoding='utf-8')
        self.assertIn(base64.b64encode(self.raw).decode(),page)
        self.assertIn('&lt;img onerror=',page);self.assertNotIn('<img onerror=',page)
        self.assertEqual((self.data/'metadata.json').read_bytes(),before)
        self.assertEqual(self.image.read_bytes(),self.raw)
        with zipfile.ZipFile(paths['zip']) as archive:
            checks=json.loads(archive.read('checksums.json'))
            for name,sha in checks.items():self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),sha)
    def test_test_samples_cannot_enter_validation_review(self):
        self.predictions[0]['id']='test-only';self.refresh_predictions()
        with self.assertRaisesRegex(ValueError,'VALIDATION_SAMPLES_ONLY'):review(self.run)
    def test_incomplete_validation_is_rejected(self):
        self.predictions=self.predictions[:1];self.refresh_predictions()
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):review(self.run)
    def test_changed_image_is_rejected(self):
        self.image.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'IMAGE_CHANGED'):review(self.run)
    def test_changed_metadata_is_rejected(self):
        self.rows[0]['latex']='new';write(self.data/'metadata.json',self.rows)
        with self.assertRaisesRegex(ValueError,'DATASET_CHANGED'):review(self.run)
    def test_csv_manual_notes_are_preserved(self):
        _,paths=review(self.run);paths['csv'].write_text('manual note',encoding='utf-8')
        with self.assertRaisesRegex(FileExistsError,'manual CSV'):review(self.run)
        self.assertEqual(paths['csv'].read_text(),'manual note')
    def test_relocated_dataset_and_qa_subset_are_supported(self):
        write(self.run/'config.json',{'data':'/old/kaggle/input/path'})
        write(self.run/'summary.json',{'selected_best':{'epoch':15},'qa_only':True})
        self.predictions=self.predictions[:1]
        write(self.run/'validation-015.json',{'metrics':{'samples':1,'exp_rate':0.},'predictions':self.predictions})
        details,_=review(self.run,data=self.data)
        self.assertTrue(details['qa_only']);self.assertEqual(details['samples'],1)
    def test_review_module_does_not_import_training_or_wandb(self):
        code="import sys; import hme_comer.review; assert 'torch' not in sys.modules; assert 'wandb' not in sys.modules"
        p=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)


if __name__=='__main__':unittest.main()
