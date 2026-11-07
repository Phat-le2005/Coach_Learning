"""Load the pinned upstream model, without invoking its legacy Trainer CLI."""
from __future__ import annotations
import hashlib
import inspect
import json
import sys
from pathlib import Path
import torch
from torch import nn
from pytorch_lightning.callbacks import ModelCheckpoint

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / '.cache/upstream'
MODEL_KEYS = ('d_model', 'growth_rate', 'num_layers', 'nhead', 'num_decoder_layers',
              'dim_feedforward', 'dropout', 'dc', 'cross_coverage', 'self_coverage')

def expand_vocabulary(model, vocab, mapping):
    """Keep original token IDs/weights; initialize new train-observed symbols only."""
    old = dict(vocab.word2idx)
    if any(mapping.get(t) != i for t, i in old.items()):
        raise ValueError('PRETRAINED_VOCABULARY_IDS_CHANGED')
    n = len(mapping)
    if sorted(mapping.values()) != list(range(n)): raise ValueError('INVALID_VOCABULARY_IDS')
    if n > len(old):
        embed = model.decoder.word_embed[0]
        proj = model.decoder.proj
        new_embed = nn.Embedding(n, embed.embedding_dim)
        new_proj = nn.Linear(proj.in_features, n)
        with torch.no_grad():
            nn.init.normal_(new_embed.weight, std=float(embed.weight.std()))
            nn.init.normal_(new_proj.weight, std=float(proj.weight.std()))
            new_proj.bias.fill_(float(proj.bias.mean()))
            new_embed.weight[:len(old)].copy_(embed.weight)
            new_proj.weight[:len(old)].copy_(proj.weight)
            new_proj.bias[:len(old)].copy_(proj.bias)
        model.decoder.word_embed[0] = new_embed
        model.decoder.proj = new_proj
    # Do not mutate upstream's singleton; only special IDs are used by teacher_loss/greedy.
    from copy import deepcopy
    result = deepcopy(vocab)
    result.word2idx = dict(mapping)
    result.idx2word = {i:t for t,i in mapping.items()}
    return result


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
    if payload.get('vocabulary'):
        vocab = expand_vocabulary(model, vocab, payload['vocabulary'])
    state = {k.removeprefix('comer_model.'): v for k,v in payload['state_dict'].items()
             if k.startswith('comer_model.')}
    if not state:  # our own fine-tuned checkpoints store the model directly
        state = payload['state_dict']
    model.load_state_dict(state, strict=True)
    model.eval()
    return model, vocab, config
