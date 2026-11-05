"""Export the pinned pretrained or fine-tuned CoMER to the browser's I/O contract."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import onnx
import onnxruntime as ort
import torch
from torch import nn
from .model import load_model, UPSTREAM

class Encoder(nn.Module):
    def __init__(self, model):
        super().__init__();self.encoder=model.encoder
    def forward(self,pixel_values,pixel_mask):
        return self.encoder(pixel_values,pixel_mask)

class Decoder(nn.Module):
    def __init__(self, model):
        super().__init__();self.decoder=model.decoder
    def forward(self,encoder_features,encoder_mask,input_ids):
        return self.decoder(encoder_features,encoder_mask,input_ids)

class EvalMaskBatchNorm(nn.Module):
    """Equivalent eval-only normalization without dynamic boolean scatter.

    Upstream gathers unmasked positions, applies BatchNorm1d in eval mode and
    scatters them back. Affine normalization is pointwise with running stats,
    so broadcasting it and selecting with where preserves those semantics.
    """
    def __init__(self, original):
        super().__init__();self.bn=original.bn
    def forward(self,x,mask):
        scale=self.bn.weight/torch.sqrt(self.bn.running_var+self.bn.eps)
        bias=self.bn.bias-self.bn.running_mean*scale
        normalized=x*scale[None,:,None,None]+bias[None,:,None,None]
        return torch.where(mask,x,normalized)

def prepare_export(model):
    from comer.model.transformer.arm import MaskBatchNorm2d
    for module in list(model.modules()):
        for name,child in list(module.named_children()):
            if isinstance(child,MaskBatchNorm2d):
                replacement=EvalMaskBatchNorm(child).eval()
                with torch.no_grad():
                    probe=torch.rand(3,child.bn.num_features,4,5)
                    mask=torch.rand(3,1,4,5)>.4
                    torch.testing.assert_close(child(probe.clone(),mask),replacement(probe,mask))
                setattr(module,name,replacement)
    return model

def export(destination: Path, checkpoint: Path|None=None, upstream: Path=UPSTREAM) -> dict:
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Export destination must be new or empty')
    destination.mkdir(parents=True,exist_ok=True)
    torch.manual_seed(7);torch.set_num_threads(4)
    model,vocab,config=load_model(checkpoint, upstream)
    model=prepare_export(model)
    enc=Encoder(model).eval();dec=Decoder(model).eval()
    x=torch.rand(1,1,256,256);mask=torch.zeros(1,256,256,dtype=torch.bool)
    mask[:,128:,:]=True;mask[:,:,220:]=True
    ids=torch.tensor([[1,107,82,110,13,112]],dtype=torch.long)
    with torch.no_grad():
        features,feature_mask=enc(x,mask)
        torch.onnx.export(enc,(x,mask),str(destination/'encoder.onnx'),opset_version=17,dynamo=False,
            input_names=['pixel_values','pixel_mask'],output_names=['encoder_features','encoder_mask'],
            dynamic_axes={'pixel_values':{2:'height',3:'width'},'pixel_mask':{1:'height',2:'width'},
                          'encoder_features':{1:'enc_h',2:'enc_w'},'encoder_mask':{1:'enc_h',2:'enc_w'}})
        torch.onnx.export(dec,(features,feature_mask,ids),str(destination/'decoder.onnx'),opset_version=17,dynamo=False,
            input_names=['encoder_features','encoder_mask','input_ids'],output_names=['logits'],
            dynamic_axes={'encoder_features':{1:'enc_h',2:'enc_w'},'encoder_mask':{1:'enc_h',2:'enc_w'},
                          'input_ids':{1:'seq_len'},'logits':{1:'seq_len'}})
    token_map=vocab.word2idx
    vocabulary={'word2idx':token_map,'idx2word':{str(v):k for k,v in token_map.items()},
                'special_tokens':{'pad':0,'sos':1,'eos':2},'vocab_size':len(vocab)}
    (destination/'vocab.json').write_text(json.dumps(vocabulary,indent=2)+'\n',encoding='utf-8')
    sessions={}
    so=ort.SessionOptions();so.intra_op_num_threads=4;so.inter_op_num_threads=1
    for name in ('encoder','decoder'):
        onnx.checker.check_model(onnx.load(str(destination/(name+'.onnx'))))
        sessions[name]=ort.InferenceSession(str(destination/(name+'.onnx')),sess_options=so,providers=['CPUExecutionProvider'])
    checks=[]
    for h,w,length in ((128,128,1),(256,256,3),(256,384,8)):
        x=torch.rand(1,1,h,w);mask=torch.zeros(1,h,w,dtype=torch.bool)
        mask[:,int(h*.65):,:]=True;mask[:,:,int(w*.8):]=True
        ids=torch.tensor([[1]+[107]*(length-1)],dtype=torch.long)
        with torch.no_grad():
            f,m=enc(x,mask);out=dec(f,m,ids).numpy()
        of,om=sessions['encoder'].run(None,{'pixel_values':x.numpy(),'pixel_mask':mask.numpy()})
        oo=sessions['decoder'].run(None,{'encoder_features':of,'encoder_mask':om,'input_ids':ids.numpy()})[0]
        np.testing.assert_allclose(of,f.numpy(),rtol=1e-3,atol=1e-4)
        np.testing.assert_array_equal(om,m.numpy())
        np.testing.assert_allclose(oo,out,rtol=1e-3,atol=2e-4)
        checks.append({'height':h,'width':w,'prefix_tokens':length,
            'encoder_max_abs':float(np.max(np.abs(of-f.numpy()))),'logits_max_abs':float(np.max(np.abs(oo-out))),
            'last_token_argmax_equal':bool(np.array_equal(oo[:,-1].argmax(-1),out[:,-1].argmax(-1)))})
    report={'status':'PASS','claim':'numeric export parity on synthetic tensors, not handwriting accuracy',
            'model_config':config,'vocab_size':len(vocab),'checks':checks,
            'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in destination.iterdir() if p.is_file()}}
    (destination/'parity.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path)
    p.add_argument('--upstream',type=Path,default=UPSTREAM)
    a=p.parse_args();r=export(a.output,a.checkpoint,a.upstream);print(json.dumps(r))
