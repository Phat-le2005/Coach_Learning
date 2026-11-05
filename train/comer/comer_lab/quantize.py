"""Create separate INT8 candidates. Accuracy and browser checks are still required."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import onnx
from onnxruntime.quantization import QuantType,quantize_dynamic

def quantize(source:Path,destination:Path):
    if destination.exists() and any(destination.iterdir()): raise ValueError('Choose a new INT8 directory')
    destination.mkdir(parents=True,exist_ok=True)
    for name in ('encoder','decoder'):
        # Unsigned weights allow ConvInteger execution in ORT CPU and browser WASM.
        quantize_dynamic(str(source/(name+'.onnx')),str(destination/(name+'_int8.onnx')),
                         weight_type=QuantType.QUInt8,per_channel=False,reduce_range=False)
        onnx.checker.check_model(onnx.load(str(destination/(name+'_int8.onnx'))))
    shutil.copy2(source/'vocab.json',destination/'vocab.json')
    report={'status':'CANDIDATE_ONLY','claim':'No INT8 recognition accuracy claim; evaluate against FP32 and browser beam=3',
            'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
                     for p in destination.iterdir() if p.is_file()}}
    (destination/'quantization.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);a=p.parse_args();print(json.dumps(quantize(a.source,a.output)))
