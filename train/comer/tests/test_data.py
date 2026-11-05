import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image,ImageDraw
from comer_lab.data import tokenize,read_manifest,safe_path,input_array,edit_distance
from comer_lab.collect import store_sample

VOCAB={'word2idx':{'<pad>':0,'<sos>':1,'<eos>':2,'x':3,'+':4,'1':5,'2':6,'^':7,'{':8,'}':9,r'\frac':10,r'\prime':11}}

def example(folder,index,split='train',writer=None):
    image=Image.new('L',(128,256));ImageDraw.Draw(image).line((15+index,15,70,110),fill=255,width=4)
    p=folder/f'{index}.png';image.save(p)
    return dict(sample_id=str(index),writer_id=writer or 'writer_'+str(index),image_path=p.name,
                image_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),latex_verbatim='x+1',split=split,
                source='synthetic_smoke',review_status='APPROVED',usage_permission='GRANTED',
                media_permission='GRANTED',preprocess_version='ink-on-0.1.0-frozen-v1',content_width=120,content_height=128)

class ManifestTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def read(self,rows,**kw):
        p=self.root/'manifest.jsonl';p.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
        return read_manifest(p,VOCAB,**kw)
    def test_tokenization_and_unknown(self):
        self.assertEqual(tokenize(r'\frac{x}{2}',VOCAB['word2idx']),[10,8,3,9,8,6,9])
        self.assertEqual(tokenize("x'",VOCAB['word2idx']),[3,11])
        with self.assertRaisesRegex(ValueError,'Unsupported'): tokenize(r'\unknown{x}',VOCAB['word2idx'])
    def test_smoke_needs_explicit_flag(self):
        with self.assertRaisesRegex(ValueError,'SMOKE_DATA'): self.read([example(self.root,1)])
    def test_mask_and_values(self):
        r=self.read([example(self.root,1)],allow_smoke=True)[0];arr,mask=input_array(r)
        self.assertEqual(arr.shape,(256,128));self.assertEqual(arr.max(),1.)
        self.assertFalse(mask[127,119]);self.assertTrue(mask[128,119]);self.assertTrue(mask[100,120])
    def test_writer_leakage(self):
        rows=[example(self.root,1,'train','writer_a'),example(self.root,2,'val','writer_a')]
        with self.assertRaisesRegex(ValueError,'WRITER_SPLIT'):self.read(rows,allow_smoke=True)
    def test_image_leakage(self):
        row=example(self.root,1);dup={**row,'sample_id':'2','writer_id':'writer_b','split':'test'}
        with self.assertRaisesRegex(ValueError,'IMAGE_SPLIT'):self.read([row,dup],allow_smoke=True)
    def test_corrupted_image(self):
        row=example(self.root,1);(self.root/'1.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'IMAGE_HASH'):self.read([row],allow_smoke=True)
    def test_path_escape(self):
        with self.assertRaisesRegex(ValueError,'PATH_ESCAPE'):safe_path(self.root,'../secret')
    def test_no_unreviewed_labels(self):
        row=example(self.root,1);row['review_status']='DRAFT'
        with self.assertRaisesRegex(ValueError,'UNREVIEWED'):self.read([row],allow_smoke=True)
    def test_preprocessor_version(self):
        row=example(self.root,1);row['preprocess_version']='other'
        with self.assertRaisesRegex(ValueError,'PREPROCESS_VERSION'):self.read([row],allow_smoke=True)
    def test_edit_distance(self):
        self.assertEqual(edit_distance('abc','adc'),1);self.assertEqual(edit_distance([1,2],[]),2)
    def test_collector_requires_review_and_enforces_writer(self):
        img=Image.new('L',(128,256));ImageDraw.Draw(img).line((10,10,80,90),fill=255,width=4)
        b=BytesIO();img.save(b,format='PNG')
        payload=dict(writer_id='writer_001',split='train',latex_verbatim='x+1',reviewed=False,
                     training_permission=True,png_base64=base64.b64encode(b.getvalue()).decode(),
                     content_height=128,content_width=120,model_strokes=[{'lineWidth':5,'points':[{'x':10,'y':10}]}])
        with self.assertRaisesRegex(ValueError,'Confirm'):store_sample(self.root,payload,VOCAB)
        payload['reviewed']=True;self.assertEqual(store_sample(self.root,payload,VOCAB)['total'],1)
        payload['split']='val'
        with self.assertRaisesRegex(ValueError,'WRITER_SPLIT'):store_sample(self.root,payload,VOCAB)

if __name__=='__main__':unittest.main()
