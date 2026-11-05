"""Load the pinned upstream model, without invoking its legacy Trainer CLI."""
from __future__ import annotations
import hashlib
import inspect
import json
import sys
from pathlib import Path
import torch
from pytorch_lightning.callbacks import ModelCheckpoint

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / '.cache/upstream'
MODEL_KEYS = ('d_model', 'growth_rate', 'num_layers', 'nhead', 'num_decoder_layers',
              'dim_feedforward', 'dropout', 'dc', 'cross_coverage', 'self_coverage')

def load_model(checkpoint: Path | None = None, upstream: Path = UPSTREAM):
    lock = json.loads(Path(__file__).with_name('upstream.lock.json').read_text())
    for item in lock['files']:
        if item['path'].startswith('comer/'):
            p = upstream / item['path']
            data = p.read_bytes()
            git_sha = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            if git_sha != item['sha']:
                raise ValueError(f"Upstream code changed: {p}")
    sys.path.insert(0, str(upstream.resolve()))
    from comer.model.comer import CoMER
    from comer.datamodule import vocab
    if not Path(inspect.getfile(CoMER)).resolve().is_relative_to(upstream.resolve()):
        raise RuntimeError('Unexpected CoMER import owner')
    if checkpoint is None:
        entry=next(e for e in lock['files'] if e['path'].endswith('.ckpt'))
        checkpoint=upstream/entry['path']
        data=checkpoint.read_bytes()
        if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=entry['sha']:
            raise ValueError('Official checkpoint integrity mismatch')
    # Retain the safe tensor unpickler. Only the real Lightning callback class
    # embedded as metadata in the official legacy checkpoint is allowlisted.
    with torch.serialization.safe_globals([ModelCheckpoint]):
        payload = torch.load(checkpoint, map_location='cpu', weights_only=True)
    config = {k: payload['hyper_parameters'][k] for k in MODEL_KEYS}
    model = CoMER(**config)
    state = {k.removeprefix('comer_model.'): v for k,v in payload['state_dict'].items()
             if k.startswith('comer_model.')}
    if not state:  # our own fine-tuned checkpoints store the model directly
        state = payload['state_dict']
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, vocab, config
