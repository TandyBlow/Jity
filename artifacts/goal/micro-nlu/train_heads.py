# -*- coding: utf-8 -*-
"""Train <1M hashed-bigram heads for targets and act/skip, with turn-grouped CV."""
import json
from pathlib import Path

import torch
import torch.nn as nn

ROOT = Path('D:/others/Jity')
DATA = ROOT / 'artifacts/goal/micro-nlu/datasets'
OUT = ROOT / '.local/micro-nlu'
OUT.mkdir(parents=True, exist_ok=True)
BUCKETS = 16384
DIM = 32


def fnv1a(text: str) -> int:
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def grams(text: str) -> list[int]:
    return [fnv1a(text[i:i + 2]) % BUCKETS for i in range(len(text) - 1)]


class Head(nn.Module):
    def __init__(self, labels: int):
        super().__init__()
        self.emb = nn.Embedding(BUCKETS, DIM)
        self.out = nn.Linear(DIM, labels)

    def forward(self, ids):  # [B, L]
        return self.out(self.emb(ids).mean(dim=1))


def load(name):
    return [json.loads(line) for line in open(DATA / f'{name}.jsonl', encoding='utf8')]


def targets_labels(row):
    parsed = row.get('parsed') or {}
    return {(t.get('targetId')) for t in parsed.get('targets') or [] if t.get('targetId')}


def folds(rows, k=4):
    turns = sorted({row['turn'] for row in rows})
    groups = {turn: index % k for index, turn in enumerate(turns)}
    return [(group, [row for row in rows if groups[row['turn']] == group]) for group in range(k)]


def train_task(name, label_fn, labels):
    rows = load(name)
    ids = [torch.tensor(grams(row['prompt']), dtype=torch.long) for row in rows]
    ys = [label_fn(row) for row in rows]
    metrics = []
    for group, held in folds(rows):
        train_idx = [i for i, row in enumerate(rows) if row not in held]
        test_idx = [i for i, row in enumerate(rows) if row in held]
        if not train_idx or not test_idx:
            continue
        model = Head(labels)
        opt = torch.optim.Adam(model.parameters(), lr=5e-3)
        lossf = nn.BCEWithLogitsLoss()
        for _ in range(60):
            for i in train_idx:
                opt.zero_grad()
                out = model(ids[i].unsqueeze(0))
                lossf(out, ys[i].unsqueeze(0)).backward()
                opt.step()
        model.eval()
        correct = 0
        for i in test_idx:
            with torch.no_grad():
                pred = (model(ids[i].unsqueeze(0)) > 0).float()
            if torch.equal(pred, ys[i].unsqueeze(0)):
                correct += 1
        metrics.append((len(test_idx), correct))
    total = sum(n for n, _ in metrics)
    hit = sum(c for _, c in metrics)
    print(name, 'labels', labels, 'rows', len(rows), 'cv exact-match', f'{hit}/{total}')
    model = Head(labels)
    opt = torch.optim.Adam(model.parameters(), lr=5e-3)
    lossf = nn.BCEWithLogitsLoss()
    for _ in range(60):
        for i in range(len(rows)):
            opt.zero_grad()
            lossf(model(ids[i].unsqueeze(0)), ys[i].unsqueeze(0)).backward()
            opt.step()
    return model, rows, ids, ys


def export(model, name, labels):
    model.eval()
    dummy = torch.zeros(1, 64, dtype=torch.long)
    path = OUT / f'{name}-head.onnx'
    torch.onnx.export(model, dummy, path, input_names=['ids'], output_names=['logits'],
                      dynamic_axes={'ids': {0: 'batch', 1: 'len'}}, opset_version=17)
    print('exported', path, 'params', sum(p.numel() for p in model.parameters()))
    return path


def main():
    rows = load('targets')
    vocab = sorted({tid for row in rows for tid in targets_labels(row)})
    print('target vocab', len(vocab), vocab)
    (OUT / 'targets-vocab.json').write_text(json.dumps(vocab, ensure_ascii=False), encoding='utf8')
    target_model, _, _, _ = train_task(
        'targets',
        lambda row: torch.tensor([1.0 if tid in targets_labels(row) else 0.0 for tid in vocab]),
        len(vocab))
    export(target_model, 'targets', len(vocab))
    act_model, rows2, _, _ = train_task(
        'action',
        lambda row: torch.tensor([1.0 if (row.get('parsed') or {}).get('kind') == 'act' else 0.0]),
        1)
    export(act_model, 'action', 1)


if __name__ == '__main__':
    main()
