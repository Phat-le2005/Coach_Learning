"""Validate shipped model contracts and pin baseline identities."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import onnx

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT/'frontend/public/ocr/comer/v0_1'

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_vocab(vocab: dict) -> None:
    n = vocab['vocab_size']
    pairs = vocab['word2idx']
    if not isinstance(n, int) or n < 4 or len(pairs) != n or len(vocab['idx2word']) != n:
        raise ValueError('VOCAB_SIZE_MISMATCH')
    if sorted(pairs.values()) != list(range(n)):
        raise ValueError('VOCAB_IDS_NOT_CONTIGUOUS')
    if any(vocab['idx2word'].get(str(i)) != token for token,i in pairs.items()):
        raise ValueError('VOCAB_INVERSE_MISMATCH')
    if vocab['special_tokens'] != {'pad':0,'sos':1,'eos':2}:
        raise ValueError('VOCAB_SPECIAL_TOKENS_MISMATCH')

def audit(assets: Path = ASSETS) -> dict:
    vocab = json.loads((assets/'vocab.json').read_text(encoding='utf-8'))
    validate_vocab(vocab)
    report = {'status':'PASS','scope':'static asset and ONNX contract checks only',
              'vocab_size':vocab['vocab_size'], 'models':[]}
    expected = {
        'encoder_int8.onnx': (['pixel_values','pixel_mask'], ['encoder_features','encoder_mask']),
        'decoder_int8.onnx': (['encoder_features','encoder_mask','input_ids'], ['logits']),
    }
    for name,(inputs,outputs) in expected.items():
        model=onnx.load(str(assets/name),load_external_data=False)
        onnx.checker.check_model(model)
        if [v.name for v in model.graph.input] != inputs or [v.name for v in model.graph.output] != outputs:
            raise ValueError('MODEL_IO_MISMATCH: '+name)
        def spec(v):
            return {'name':v.name,'element_type':v.type.tensor_type.elem_type,
                    'shape':[d.dim_param or d.dim_value for d in v.type.tensor_type.shape.dim]}
        if name.startswith('decoder') and model.graph.output[0].type.tensor_type.shape.dim[-1].dim_value != vocab['vocab_size']:
            raise ValueError('DECODER_VOCAB_MISMATCH')
        report['models'].append({'file':name,'bytes':(assets/name).stat().st_size,'sha256':sha256(assets/name),
            'inputs':[spec(v) for v in model.graph.input],'outputs':[spec(v) for v in model.graph.output]})
    report['vocabulary_sha256']=sha256(assets/'vocab.json')
    report['preprocess_sha256']=sha256(ROOT/'frontend/public/ocr/ink-on/chunks/inference-4T2UM6yg.js')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=audit();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'vocab_size':result['vocab_size'],'output':str(args.output)}))
