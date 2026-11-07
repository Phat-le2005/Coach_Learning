"""Transparent greedy decoding metrics, not the official CROHME evaluator."""
import torch
import torch.nn.functional as F
from torch.utils.data import Dataset
from .data import input_array

CONTRACT = {
    'loss': 'Bidirectional teacher-forced cross entropy, summed / non-PAD output tokens.',
    'decoder': 'L2R greedy, SOS=1 EOS=2 PAD=0; PAD/SOS suppressed; no beam or LaTeX repair.',
    'exp_rate': 'Exact token sequence match, requiring EOS, reported as a fraction [0,1].',
    'cer': 'Sum character Levenshtein edits / sum reference characters, joined model tokens.',
    'token_error_rate': 'Sum token Levenshtein edits / sum reference tokens.',
    'selection': 'Max validation exp_rate, tie broken by min validation loss.',
    'test': 'Only separate final evaluation of the frozen selected checkpoint.',
    'limits': 'No semantic equivalence, official CROHME benchmark or writer-disjoint claim.'}


class InkDataset(Dataset):
    def __init__(self, rows): self.rows = rows
    def __len__(self): return len(self.rows)
    def __getitem__(self, i): return torch.from_numpy(input_array(self.rows[i]))[None], self.rows[i]['_tokens']


def collate(items):
    h = max(64, ((max(x.shape[-2] for x,t in items) + 31) // 32) * 32)
    w = max(64, ((max(x.shape[-1] for x,t in items) + 31) // 32) * 32)
    images = torch.zeros(len(items), 1, h, w)
    masks = torch.ones(len(items), h, w, dtype=torch.bool)
    for i, (x, _) in enumerate(items):
        ih, iw = x.shape[-2:]
        images[i, :, :ih, :iw] = x
        masks[i, :ih, :iw] = False
    return images, masks, [t for _,t in items]


def teacher_loss(model, x, mask, tokens):
    from comer.utils.utils import to_bi_tgt_out
    tgt, out = to_bi_tgt_out(tokens, x.device)
    logits = model(x, mask, tgt)
    loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), out.reshape(-1),
                           ignore_index=0, reduction='sum')
    return loss, int(out.ne(0).sum())


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1): cur.append(min(cur[-1]+1, prev[j]+1, prev[j-1]+(x!=y)))
        prev = cur
    return prev[-1]


@torch.inference_mode()
def greedy(model, x, mask, max_tokens):
    features, m = model.encoder(x, mask)
    ids = torch.ones((1,1), dtype=torch.long, device=x.device)
    seq = []
    for _ in range(max_tokens):
        logits = model.decoder(features, m, ids)[:, -1, :].clone()
        logits[:, :2] = -torch.inf
        t = int(logits.argmax(-1))
        if t == 2: return seq, True
        seq.append(t)
        ids = torch.cat([ids, torch.tensor([[t]], device=x.device)], dim=1)
    return seq, False


@torch.inference_mode()
def evaluate(model, rows, vocabulary, device, max_tokens):
    if not rows: raise ValueError('EMPTY_EVALUATION_SPLIT')
    model.eval()
    idx = {i:t for t,i in vocabulary.items()}
    predictions = []
    loss_sum = count = 0
    for row in rows:
        x, m, ts = collate([InkDataset([row])[0]])
        x, m = x.to(device), m.to(device)
        loss, n = teacher_loss(model, x, m, ts)
        if not torch.isfinite(loss): raise FloatingPointError('Non-finite evaluation loss')
        loss_sum += float(loss); count += n
        seq, ended = greedy(model, x, m, max_tokens)
        target = row['_tokens']
        truth = ''.join(idx[t] for t in target)
        pred = ''.join(idx[t] for t in seq)
        ce, te = edit_distance(pred, truth), edit_distance(seq, target)
        predictions.append(dict(id=row['id'], group=row['group'], latex=row['latex'],
            target=truth, prediction=pred, exact=seq==target and ended, ended=ended,
            character_edits=ce, reference_characters=len(truth), token_edits=te,
            reference_tokens=len(target), cer=ce/max(1,len(truth))))
    total = len(rows)
    metrics = dict(samples=total, loss=loss_sum/count,
        exp_rate=sum(p['exact'] for p in predictions)/total,
        cer=sum(p['character_edits'] for p in predictions)/sum(p['reference_characters'] for p in predictions),
        token_error_rate=sum(p['token_edits'] for p in predictions)/sum(p['reference_tokens'] for p in predictions),
        empty_rate=sum(not p['prediction'] for p in predictions)/total,
        truncation_rate=sum(not p['ended'] for p in predictions)/total)
    groups = {}
    for g in sorted({r['group'] for r in rows}):
        ps = [p for p in predictions if p['group']==g]
        groups[g] = dict(samples=len(ps), exp_rate=sum(p['exact'] for p in ps)/len(ps),
                         cer=sum(p['character_edits'] for p in ps)/sum(p['reference_characters'] for p in ps))
    return metrics, predictions, groups
