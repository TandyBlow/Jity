# -*- coding: utf-8 -*-
"""Train a small structure-prediction model: facts -> pattern id + span pointers.

The model never emits characters. It picks one of the frozen patterns and copies
contiguous spans of the fact text into that pattern's slots. Grouped split by the
fact string so no fact set appears in both train and test.
"""
import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

from render_frames_v2 import PATTERNS, render

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

HERE = Path(__file__).resolve().parent
MAX_ROLES = max(len(v[1]) for v in PATTERNS.values())
PATTERN_NAMES = sorted(PATTERNS)


def load_rows(path):
    rows = [json.loads(l) for l in Path(path).read_text(encoding='utf8').splitlines() if l.strip()]
    out = []
    for r in rows:
        text = '；'.join(r['facts'])
        roles = PATTERNS[r['pattern']][1]
        spans = []
        ok = True
        for role in roles:
            i = text.find(r['slots'][role])
            if i < 0:
                ok = False
                break
            spans.append((i, i + len(r['slots'][role])))
        if not ok:
            continue
        out.append({'id': r['id'], 'text': text, 'pattern': r['pattern'],
                    'roles': roles, 'spans': spans, 'slots': r['slots'],
                    'ref': r.get('ref')})
    return out


def build_vocab(rows):
    chars = Counter()
    for r in rows:
        chars.update(r['text'])
    return {c: i + 2 for i, c in enumerate(sorted(chars))}, len(chars) + 2


class Net(nn.Module):
    def __init__(self, vocab, n_patterns, d=128, layers=4, ff=256):
        super().__init__()
        self.emb = nn.Embedding(vocab, d, padding_idx=0)
        self.pos = nn.Parameter(torch.zeros(1, 512, d))
        layer = nn.TransformerEncoderLayer(d, 4, ff, batch_first=True, dropout=0.1)
        self.enc = nn.TransformerEncoder(layer, layers)
        self.pattern = nn.Linear(d, n_patterns)
        self.start = nn.Linear(d, MAX_ROLES, bias=False)
        self.end = nn.Linear(d, MAX_ROLES, bias=False)

    def forward(self, x, mask):
        h = self.enc(self.emb(x) + self.pos[:, :x.size(1)], src_key_padding_mask=~mask)
        pooled = (h * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True)
        return self.pattern(pooled), self.start(h).permute(0, 2, 1), self.end(h).permute(0, 2, 1)


def encode(rows, vocab, max_len=384):
    xs = torch.zeros(len(rows), max_len, dtype=torch.long)
    mask = torch.zeros(len(rows), max_len, dtype=torch.bool)
    for i, r in enumerate(rows):
        ids = [vocab.get(c, 1) for c in r['text'][:max_len]]
        xs[i, :len(ids)] = torch.tensor(ids)
        mask[i, :len(ids)] = True
    return xs, mask


def train(train_rows, vocab, vocab_size, epochs, seed, d, layers, ff):
    torch.manual_seed(seed)
    random.seed(seed)
    net = Net(vocab_size, len(PATTERN_NAMES), d=d, layers=layers, ff=ff).to(DEVICE)
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=0.01)
    xs, mask = (x.to(DEVICE) for x in encode(train_rows, vocab))
    pat = torch.tensor([PATTERN_NAMES.index(r['pattern']) for r in train_rows]).to(DEVICE)
    roles = PATTERNS
    start_t = torch.zeros(len(train_rows), MAX_ROLES, dtype=torch.long).to(DEVICE)
    end_t = torch.zeros(len(train_rows), MAX_ROLES, dtype=torch.long).to(DEVICE)
    role_mask = torch.zeros(len(train_rows), MAX_ROLES, dtype=torch.bool).to(DEVICE)
    for i, r in enumerate(train_rows):
        for j, (s, e) in enumerate(r['spans']):
            start_t[i, j] = s
            end_t[i, j] = e
            role_mask[i, j] = True
    net.train()
    for epoch in range(epochs):
        perm = torch.randperm(len(train_rows))
        total = 0.0
        for b in range(0, len(perm), 16):
            idx = perm[b:b + 16]
            p, s, e = net(xs[idx], mask[idx])
            loss = F.cross_entropy(p, pat[idx])
            ls = F.cross_entropy(s.reshape(-1, s.size(-1)), start_t[idx].reshape(-1), reduction='none')
            le = F.cross_entropy(e.reshape(-1, e.size(-1)), end_t[idx].reshape(-1), reduction='none')
            ls = ls.reshape(idx.shape[0], -1)
            le = le.reshape(idx.shape[0], -1)
            rm = role_mask[idx]
            loss = loss + (ls * rm).sum() / rm.sum() + (le * rm).sum() / rm.sum()
            opt.zero_grad()
            loss.backward()
            opt.step()
            total += float(loss) * len(idx)
        if (epoch + 1) % 40 == 0:
            print(f'  epoch {epoch + 1} loss {total / len(train_rows):.3f}', flush=True)
    return net


def predict(net, rows, vocab, max_len=384, oracle_pattern=False):
    net.eval()
    xs, mask = (x.to(DEVICE) for x in encode(rows, vocab, max_len))
    with torch.no_grad():
        p, s, e = net(xs, mask)
    p, s, e = p.cpu(), s.cpu(), e.cpu()
    out = []
    for i, r in enumerate(rows):
        pattern = r['pattern'] if oracle_pattern else PATTERN_NAMES[int(p[i].argmax())]
        roles = PATTERNS[pattern][1]
        slots, ok = {}, True
        for j, role in enumerate(roles):
            a = int(s[i, j, :len(r['text'])].argmax())
            b = int(e[i, j, :len(r['text'])].argmax())
            if b <= a:
                b = min(a + 3, len(r['text']))
            slots[role] = r['text'][a:b]
        out.append({'id': r['id'], 'pattern': pattern, 'slots': slots,
                    'render': render({'pattern': pattern, 'slots': slots})})
    return out


def char_f1(a, b):
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    p = common / max(1, len(a))
    r = common / max(1, len(b))
    return 2 * p * r / (p + r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=str(HERE / 'frames-v2-all.jsonl'))
    ap.add_argument('--epochs', type=int, default=300)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--d', type=int, default=160)
    ap.add_argument('--layers', type=int, default=4)
    ap.add_argument('--ff', type=int, default=512)
    ap.add_argument('--holdout', type=float, default=0.2)
    ap.add_argument('--out', default=str(HERE / 'frame-model-summary.json'))
    ap.add_argument('--tag', default='')
    ap.add_argument('--oracle-pattern', action='store_true')
    args = ap.parse_args()

    rows = load_rows(args.data)
    groups = defaultdict(list)
    for r in rows:
        groups[r['text']].append(r)
    keys = sorted(groups)
    rng = random.Random(args.seed)
    rng.shuffle(keys)
    n_test = max(1, int(len(keys) * args.holdout))
    test_keys = set(keys[:n_test])
    train_rows = [r for k in keys if k not in test_keys for r in groups[k]]
    test_rows = [r for k in keys if k in test_keys for r in groups[k]]

    vocab, vocab_size = build_vocab(train_rows)
    net = train(train_rows, vocab, vocab_size, args.epochs, args.seed, args.d, args.layers, args.ff)
    params = sum(p.numel() for p in net.parameters())
    preds = predict(net, test_rows, vocab, oracle_pattern=args.oracle_pattern)

    preds_train = predict(net, train_rows, vocab, oracle_pattern=args.oracle_pattern)
    train_acc = sum(1 for r, p in zip(train_rows, preds_train) if p['pattern'] == r['pattern']) / len(train_rows)
    train_f1 = sum(char_f1(p['render'], r['ref']) for r, p in zip(train_rows, preds_train) if r['ref']) / max(1, len(train_rows))
    exact = sum(1 for r, p in zip(test_rows, preds) if p['pattern'] == r['pattern'])
    pat_acc = exact / len(test_rows)
    f1s = [char_f1(p['render'], r['ref']) for r, p in zip(test_rows, preds) if r['ref']]
    valid = sum(1 for p in preds if len(p['render'] or '') > 2)
    rows_out = [{'id': r['id'], 'ref': r['ref'], 'pred': p['render'],
                 'patternTrue': r['pattern'], 'patternPred': p['pattern']}
                for r, p in zip(test_rows, preds)]
    majority = Counter(r['pattern'] for r in train_rows).most_common(1)[0][0]
    base_acc = sum(1 for r in test_rows if r['pattern'] == majority) / len(test_rows)
    summary = {'tag': args.tag, 'device': str(DEVICE), 'oraclePattern': args.oracle_pattern, 'rows': len(rows), 'majorityPattern': majority, 'majorityAcc': round(base_acc, 3), 'train': len(train_rows), 'test': len(test_rows),
               'groups': len(keys), 'params': params, 'seed': args.seed,
               'patternAccTrain': round(train_acc, 3), 'charF1Train': round(train_f1, 3),
               'patternAcc': round(pat_acc, 3),
               'renderValid': round(valid / len(preds), 3),
               'charF1VsRef': round(sum(f1s) / max(1, len(f1s)), 3),
               'preds': rows_out}
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'preds'}, ensure_ascii=False))
    for r in rows_out:
        print(r['id'], r['patternTrue'], '->', r['patternPred'], '|', r['pred'])


if __name__ == '__main__':
    main()
