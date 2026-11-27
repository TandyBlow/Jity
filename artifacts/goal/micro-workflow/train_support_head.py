# -*- coding: utf-8 -*-
"""Fact-support verification head: does the settled record support the claim?

Input: 主张：<claim>\\n结算事实：<facts>. Target: supported / not supported.
Refuses to train below 50 positives + 50 negatives for the field. Reports the
holdout confusion and the subset where the claim is not a verbatim substring
of the facts (the semantically interesting part)."""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATA = HERE / 'semantic-support.jsonl'
OUT = ROOT / '.local/micro-semantic'
MAXLEN = 256


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def encode(tok, text):
    enc = tok(text, truncation=True, max_length=MAXLEN)
    return torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--field', choices=['info', 'env'], default='info')
    parser.add_argument('--holdout', default='sm10-')
    parser.add_argument('--epochs', type=int, default=30)
    args = parser.parse_args()
    rows = [json.loads(line) for line in DATA.read_text(encoding='utf8').splitlines() if line.strip()]
    rows = [row for row in rows if row['field'] == args.field]
    counts = Counter(row['label'] for row in rows)
    if counts[True] < 50 or counts[False] < 50:
        raise SystemExit(f"{args.field} needs 50 pos + 50 neg, has {counts[True]}/{counts[False]}")
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = BertTokenizer.from_pretrained(SNAP)
    model = Head().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.CrossEntropyLoss()
    def feats(subset):
        out = []
        for row in subset:
            text = f"主张：{row['claim']}\n结算事实：{row['facts']}"
            ids, mask = encode(tok, text)
            out.append((ids, mask, int(row['label']), row))
        return out
    holdout_rows = [row for row in rows if str(row['rowId']).startswith(args.holdout)]
    train_rows = [row for row in rows if not str(row['rowId']).startswith(args.holdout)]
    train = feats(train_rows)
    random.seed(20261127)
    torch.manual_seed(20261127)
    for epoch in range(args.epochs):
        random.shuffle(train)
        model.train()
        total = 0.0
        for ids, mask, label, _ in train:
            opt.zero_grad()
            logits = model(ids.to(device), mask.to(device))
            loss = lossf(logits, torch.tensor([label], device=device))
            loss.backward()
            opt.step()
            total += float(loss)
        if epoch % 5 == 0 or epoch == args.epochs - 1:
            print(json.dumps({'epoch': epoch + 1, 'loss': round(total / max(1, len(train)), 4)}), flush=True)
    model.eval()
    eval_rows = holdout_rows or train_rows
    confusion = Counter()
    hard = Counter()
    with torch.no_grad():
        for ids, mask, label, row in feats(eval_rows):
            pred = int(model(ids.to(device), mask.to(device))[0].argmax().item())
            confusion[f'{label}->{pred}'] += 1
            if row['claim'] not in row['facts']:
                hard[f'{label}->{pred}'] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f'support-head-{args.field}.pt'
    torch.save(model.cpu(), target)
    print(json.dumps({'field': args.field, 'rows': len(rows), 'train': len(train), 'holdout': len(holdout_rows),
                      'confusion': dict(confusion), 'hardSubset': dict(hard), 'model': str(target)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
