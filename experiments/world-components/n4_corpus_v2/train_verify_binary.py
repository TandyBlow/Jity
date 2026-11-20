"""First binary statement-verification round.

Task: MiniRBT-H256 base + masked mean-pool + linear(2), supported/unsupported.
`uncertain` is NOT a trained class: it is produced at inference by a
dev-selected confidence threshold. No source head in this round.

Frozen inputs are checked before training. Inputs are dynamically padded and
never truncated; any sequence over 256 tokens raises.
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import json
import pathlib
import random
import shutil
import sys
import time
import types
from collections import Counter, defaultdict

# Local ABI workaround used by the existing N5 evaluator: pyarrow/pandas/sklearn
# are transitively imported by transformers.generation in this base env.
try:
    import pyarrow  # noqa: F401
except Exception:
    _stub = types.ModuleType('pyarrow')
    _stub.__version__ = '16.1.0'
    _stub.__path__ = []
    sys.modules['pyarrow'] = _stub
_tf = types.ModuleType('tensorflow')
_tf.__spec__ = importlib.machinery.ModuleSpec('tensorflow', None)
_tf.__path__ = []
sys.modules.setdefault('tensorflow', _tf)

import torch
from torch import nn
from transformers.models.bert.modeling_bert import BertModel
from transformers.models.bert.tokenization_bert import BertTokenizer

HERE = pathlib.Path(__file__).resolve().parent
import sys as _paths_sys
_paths_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from component_paths import PATHS

ROOT = PATHS.worktree
ART = PATHS.output('statement-verification')
PAIRS = PATHS.input('statement-verification/pairs-v1.jsonl')
REGRESSION = PATHS.input('statement-verification/regression-v1.jsonl')
FREEZE = PATHS.input('statement-verification/split-freeze.json')
METRIC = PATHS.input('statement-verification/metric-freeze.json')
REVIEW = PATHS.input('statement-verification/review-v1-summary.json')
BASE = HERE.parent / 'assets' / 'minirbt-h256-snapshot'
CKPT = None
SEED = 20261104
EPOCHS = 12
BATCH = 32
LR = 3e-5
MAX_LEN = 256
T_GRID = [round(0.50 + 0.01 * i, 2) for i in range(50)]
LABELS = {'supported': 0, 'unsupported': 1}
CATEGORIES = ['general', 'body', 'background', 'visible-state', 'extra-action']


def sha_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def check_frozen():
    freeze = json.loads(FREEZE.read_text(encoding='utf-8'))
    metric = json.loads(METRIC.read_text(encoding='utf-8'))
    review = json.loads(REVIEW.read_text(encoding='utf-8'))
    checks = {
        'pairs-v1.jsonl': (sha_file(PAIRS), freeze['hashes']['pairs-v1.jsonl']),
        'regression-v1.jsonl': (sha_file(REGRESSION), freeze['hashes']['regression-v1.jsonl']),
        'metric-freeze.json': (sha_file(METRIC), freeze['metricFreezeSha256']),
        'review-v1-summary.json': (sha_file(REVIEW), freeze['reviewSha256']),
    }
    for name, (got, want) in checks.items():
        if got != want:
            raise SystemExit(f'REFUSED: {name} sha {got[:16]} != frozen {want[:16]}')
    if metric.get('model', {}).get('head') != 'masked mean-pool + linear(2)':
        raise SystemExit('REFUSED: metric freeze is not the binary head')
    if freeze.get('reviewType', '').find('not independent') < 0:
        raise SystemExit('REFUSED: review independence status missing')
    return freeze, metric, review


def load_rows():
    rows = [json.loads(l) for l in PAIRS.read_text(encoding='utf-8').splitlines() if l.strip()]
    reg = [json.loads(l) for l in REGRESSION.read_text(encoding='utf-8').splitlines() if l.strip()]
    train = [r for r in rows if r['split'] == 'train']
    dev = [r for r in rows if r['split'] == 'dev']
    confirm = [r for r in rows if r['split'] == 'confirm']
    assert all(r['label'] in LABELS or r['label'] == 'uncertain' for r in rows)
    return rows, train, dev, confirm, reg


def binary(rows):
    return [r for r in rows if r['label'] in LABELS]


def serialize_rows(rows):
    sys.path.insert(0, str(HERE))
    from verify_input import serialize
    return [serialize(r)['text'] for r in rows]


def make_tokenizer():
    return BertTokenizer(vocab_file=str(BASE / 'vocab.txt'), do_lower_case=True)


def length_check(tok, rows):
    lengths = [len(tok.encode(t, add_special_tokens=True)) for t in serialize_rows(rows)]
    over = [(r['exampleId'], n) for r, n in zip(rows, lengths) if n > MAX_LEN]
    if over:
        raise SystemExit(f'REFUSED: {len(over)} inputs exceed {MAX_LEN}: {over[:5]}')
    return {'n': len(lengths), 'min': min(lengths), 'p50': sorted(lengths)[len(lengths)//2],
            'p90': sorted(lengths)[int(len(lengths) * .9)], 'max': max(lengths)}


class BinaryHead(nn.Module):
    def __init__(self, base_dir, hidden=256, n_classes=2):
        super().__init__()
        self.encoder = BertModel.from_pretrained(str(base_dir), add_pooling_layer=False)
        self.dropout = nn.Dropout(0.1)
        self.classifier = nn.Linear(hidden, n_classes)

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask,
                           token_type_ids=token_type_ids)
        mask = attention_mask.unsqueeze(-1).to(out.last_hidden_state.dtype)
        pooled = (out.last_hidden_state * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return self.classifier(self.dropout(pooled))


def encode_batch(tok, texts, device):
    enc = tok(texts, padding=True, truncation=False, return_tensors='pt')
    n = enc['input_ids'].shape[1]
    if n > MAX_LEN:
        raise SystemExit(f'REFUSED: batch length {n} > {MAX_LEN}; no silent truncation')
    return {k: v.to(device) for k, v in enc.items()}


@torch.no_grad()
def predict(model, tok, rows, device, batch=64):
    model.eval()
    out = []
    for s in range(0, len(rows), batch):
        chunk = rows[s:s + batch]
        enc = encode_batch(tok, serialize_rows(chunk), device)
        logits = model(**enc)
        probs = torch.softmax(logits, dim=-1).cpu().tolist()
        out.extend(probs)
    return out


def classify(probs, t_conf):
    result = []
    for p in probs:
        p_sup, p_uns = float(p[0]), float(p[1])
        base = 'unsupported' if p_uns >= 0.5 else 'supported'
        conf = max(p_sup, p_uns)
        pred = 'uncertain' if conf < t_conf else base
        result.append({'pred': pred, 'p_supported': round(p_sup, 6),
                       'p_unsupported': round(p_uns, 6), 'confidence': round(conf, 6),
                       't_conf': t_conf})
    return result


def metrics(rows, preds):
    pairs = [(r, p) for r, p in zip(rows, preds) if r['label'] in LABELS]
    n_sup = sum(1 for r, _ in pairs if r['label'] == 'supported')
    n_uns = sum(1 for r, _ in pairs if r['label'] == 'unsupported')
    cm = Counter((r['label'], p['pred']) for r, p in pairs)
    pred_uns = sum(1 for r, p in pairs if p['pred'] == 'unsupported')
    return {
        'n': len(pairs), 'nSupported': n_sup, 'nUnsupported': n_uns,
        'confusion': {f'{a}->{b}': cm.get((a, b), 0) for a in LABELS for b in ('supported', 'unsupported', 'uncertain')},
        'unsupportedRecall': cm.get(('unsupported', 'unsupported'), 0) / n_uns if n_uns else None,
        'legalRejection': cm.get(('supported', 'unsupported'), 0) / n_sup if n_sup else None,
        'legalPending': cm.get(('supported', 'uncertain'), 0) / n_sup if n_sup else None,
        'unsupportedPrecision': cm.get(('unsupported', 'unsupported'), 0) / pred_uns if pred_uns else None,
        'overallUncertainRate': ((cm.get(('supported', 'uncertain'), 0) + cm.get(('unsupported', 'uncertain'), 0)) / len(pairs)) if pairs else None,
        'uncertainCount': cm.get(('supported', 'uncertain'), 0) + cm.get(('unsupported', 'uncertain'), 0),
    }


def by_category(rows, preds):
    out = {}
    for cat in CATEGORIES:
        idx = [i for i, r in enumerate(rows) if r['category'] == cat]
        if not idx:
            continue
        sub = [rows[i] for i in idx]
        ps = [preds[i] for i in idx]
        out[cat] = metrics(sub, ps)
    return out


def eligible(m):
    return (m['unsupportedRecall'] is not None and m['unsupportedRecall'] >= 0.80
            and m['legalRejection'] is not None and m['legalRejection'] <= 0.05
            and m['legalPending'] is not None and m['legalPending'] <= 0.15)


def select(dev, probs_by_epoch):
    table = []
    for epoch, probs in probs_by_epoch.items():
        for t in T_GRID:
            preds = classify(probs, t)
            m = metrics(dev, preds)
            table.append({'epoch': epoch, 't_conf': t, 'eligible': eligible(m), **m})
    valid = [x for x in table if x['eligible']]
    if not valid:
        return None, table
    # fixed order: max recall, min legal rejection, min legal pending,
    # earliest epoch, lowest t_conf
    best = min(valid, key=lambda x: (-x['unsupportedRecall'], x['legalRejection'],
                                     x['legalPending'], x['epoch'], x['t_conf']))
    return best, table


def write_jsonl(path, rows, preds, extra=None):
    with path.open('w', encoding='utf-8') as f:
        for r, p in zip(rows, preds):
            rec = {'exampleId': r['exampleId'], 'pairId': r['pairId'], 'split': r['split'],
                   'origin': r['origin'], 'category': r['category'], 'label': r['label'],
                   **p, 'sourceStatus': 'not_implemented'}
            if extra:
                rec.update(extra)
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')


def main():
    import argparse
    global BASE, CKPT
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', required=True)
    parser.add_argument('--out', required=True, help='Checkpoint directory under N4_OUTPUT_ROOT')
    args = parser.parse_args()
    BASE = pathlib.Path(args.base).resolve()
    CKPT = PATHS.checkpoint(args.out)
    if CKPT.is_relative_to(BASE) or BASE.is_relative_to(CKPT):
        raise ValueError('Training output overlaps the base model')
    ART.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    freeze, metric, review = check_frozen()
    rows, train_all, dev_all, confirm_all, reg = load_rows()
    train = binary(train_all)
    dev = binary(dev_all)
    confirm = binary(confirm_all)
    boundary = [r for r in rows if r['label'] == 'uncertain']
    print(json.dumps({'train': len(train), 'dev': len(dev), 'confirm': len(confirm),
                      'boundary': len(boundary), 'regression': len(reg),
                      'confirmTotal': len(confirm_all)}, ensure_ascii=False))
    tok = make_tokenizer()
    length_stats = length_check(tok, rows + reg)
    print('lengths', json.dumps(length_stats, ensure_ascii=False))

    random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('device', device, torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')
    model = BinaryHead(BASE).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    lossf = nn.CrossEntropyLoss()
    CKPT.mkdir(parents=True, exist_ok=True)
    dev_probs = {}
    epoch_rows = []
    model.train()
    for epoch in range(1, EPOCHS + 1):
        order = list(range(len(train)))
        random.shuffle(order)
        losses = []
        e0 = time.perf_counter()
        for s in range(0, len(order), BATCH):
            idx = order[s:s + BATCH]
            batch = [train[i] for i in idx]
            enc = encode_batch(tok, serialize_rows(batch), device)
            y = torch.tensor([LABELS[r['label']] for r in batch], device=device)
            logits = model(**enc)
            loss = lossf(logits, y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss))
        dev_probs[epoch] = predict(model, tok, dev, device)
        probs = dev_probs[epoch]
        # report the un-rejected 0.5 baseline and the best t on this epoch
        base_m = metrics(dev, classify(probs, 0.5))
        epoch_rows.append({'epoch': epoch, 'lossMean': round(sum(losses) / len(losses), 6),
                           'wallSeconds': round(time.perf_counter() - e0, 1),
                           'devAt05': base_m})
        state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
        torch.save({'epoch': epoch, 'model': state, 'config': {
            'base': str(BASE), 'seed': SEED, 'epochs': EPOCHS, 'batch': BATCH,
            'lr': LR, 'maxLen': MAX_LEN, 'head': 'linear(2)'}}, CKPT / f'epoch-{epoch:02d}.pt')
        print(json.dumps({'epoch': epoch, 'loss': round(sum(losses) / len(losses), 4),
                          'devAt05': {k: base_m[k] for k in
                                      ('unsupportedRecall', 'legalRejection', 'legalPending',
                                       'unsupportedPrecision', 'uncertainCount')}}, ensure_ascii=False), flush=True)

    selected, dev_table = select(dev, dev_probs)
    dev_payload = {'selected': selected, 'table': dev_table, 'epochs': epoch_rows,
                   'selectionOrder': ['max unsupportedRecall', 'min legalRejection',
                                      'min legalPending', 'earliest epoch', 'lowest t_conf'],
                   'tConfGrid': T_GRID}
    (ART / 'verify-binary-dev.json').write_text(json.dumps(dev_payload, ensure_ascii=False, indent=2), encoding='utf-8')
    if selected is None:
        report = {'purpose': 'binary statement verification, first round',
                  'result': 'no dev-eligible checkpoint/threshold',
                  'freeze': freeze['hashes'], 'dev': dev_payload,
                  'sourceStatus': 'not_implemented',
                  'wallSeconds': round(time.perf_counter() - t0, 1)}
        (ART / 'train-verify-binary-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('NO ELIGIBLE DEV CANDIDATE; confirm not run')
        return 2

    best_epoch = selected['epoch']
    best_t = selected['t_conf']
    selected_path = CKPT / f'epoch-{best_epoch:02d}.pt'
    shutil.copyfile(selected_path, CKPT / 'selected.pt')
    load = torch.load(selected_path, map_location='cpu', weights_only=False)
    model.load_state_dict(load['model'])
    model.to(device)
    model.eval()
    (CKPT / 'selected.json').write_text(json.dumps({'epoch': best_epoch, 't_conf': best_t,
                                                    'dev': selected}, ensure_ascii=False, indent=2), encoding='utf-8')

    # confirm: one pass only
    confirm_probs = predict(model, tok, confirm, device)
    confirm_preds = classify(confirm_probs, best_t)
    write_jsonl(ART / 'verify-binary-confirm.jsonl', confirm, confirm_preds,
                extra={'selectedEpoch': best_epoch, 'selectedTConf': best_t})
    confirm_m = metrics(confirm, confirm_preds)
    confirm_gates = {
        'unsupportedRecall>=0.80': confirm_m['unsupportedRecall'] is not None and confirm_m['unsupportedRecall'] >= 0.80,
        'legalRejection<=0.05': confirm_m['legalRejection'] is not None and confirm_m['legalRejection'] <= 0.05,
        'legalPending<=0.15': confirm_m['legalPending'] is not None and confirm_m['legalPending'] <= 0.15,
    }
    confirm_summary = {'selected': {'epoch': best_epoch, 't_conf': best_t},
                       'metrics': confirm_m, 'gates': confirm_gates,
                       'pass': all(confirm_gates.values()),
                       'category': by_category(confirm, confirm_preds),
                       'boundaryExcluded': len(confirm_all) - len(confirm)}
    (ART / 'verify-binary-confirm-summary.json').write_text(json.dumps(confirm_summary, ensure_ascii=False, indent=2), encoding='utf-8')

    # boundary uncertain examples, all three; no capability claim
    boundary_probs = predict(model, tok, boundary, device)
    boundary_preds = classify(boundary_probs, best_t)
    write_jsonl(ART / 'verify-binary-boundary.jsonl', boundary, boundary_preds,
                extra={'selectedEpoch': best_epoch, 'selectedTConf': best_t,
                       'note': 'boundary case; uncertain is not a trained class'})

    # regression: separate, no training/confirm selection
    reg_probs = predict(model, tok, reg, device)
    reg_preds = classify(reg_probs, best_t)
    write_jsonl(ART / 'verify-binary-regression.jsonl', reg, reg_preds,
                extra={'selectedEpoch': best_epoch, 'selectedTConf': best_t})
    reg_bin = [r for r in reg if r['label'] in LABELS]
    reg_summary = {'metrics': metrics(reg_bin, [p for r, p in zip(reg, reg_preds) if r['label'] in LABELS]),
                   'category': {}, 'boundary': []}
    for cat in sorted({r['category'] for r in reg_bin}):
        rs = [r for r in reg_bin if r['category'] == cat]
        ps = [p for r, p in zip(reg, reg_preds) if r['label'] in LABELS and r['category'] == cat]
        reg_summary['category'][cat] = metrics(rs, ps)
    for r, p in zip(reg, reg_preds):
        if r['label'] == 'uncertain':
            reg_summary['boundary'].append({'exampleId': r['exampleId'], **p})
    (ART / 'verify-binary-regression-summary.json').write_text(json.dumps(reg_summary, ensure_ascii=False, indent=2), encoding='utf-8')

    report = {
        'purpose': 'binary statement verification, first round',
        'freeze': freeze['hashes'],
        'review': {'file': str(REVIEW), 'sha256': sha_file(REVIEW), 'notIndependent': review.get('notIndependent')},
        'base': {'dir': str(BASE), 'sha256': sha_file(BASE / 'pytorch_model.bin')},
        'data': {'train': len(train), 'dev': len(dev), 'confirm': len(confirm),
                 'confirmTotal': len(confirm_all), 'boundary': len(boundary), 'regression': len(reg)},
        'lengths': length_stats,
        'config': {'seed': SEED, 'epochs': EPOCHS, 'batch': BATCH, 'lr': LR,
                   'maxLen': MAX_LEN, 'head': 'linear(2)', 'device': str(device)},
        'dev': dev_payload,
        'confirm': confirm_summary,
        'regression': reg_summary,
        'sourceStatus': 'not_implemented',
        'wallSeconds': round(time.perf_counter() - t0, 1),
    }
    (ART / 'train-verify-binary-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'selected': {'epoch': best_epoch, 't_conf': best_t},
                      'dev': selected, 'confirm': confirm_m, 'gates': confirm_gates,
                      'pass': confirm_summary['pass']}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
