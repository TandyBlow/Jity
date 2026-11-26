# -*- coding: utf-8 -*-
"""Binary existence heads (info/env) on the shared MiniRBT encoder.

Refuses to train unless every field has at least 50 positive and 50 negative
examples, matching the trial gate. `--smoke` exists only for code checks."""
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
DATA = HERE / 'semantic-existence.jsonl'
OUT = ROOT / '.local/micro-semantic'
FIELDS = ['info', 'env']
MAXLEN = 256


class Heads(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.info = nn.Linear(hidden, 2)
        self.env = nn.Linear(hidden, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.info(cls), self.env(cls)


def encode(tok, text):
    enc = tok(text, truncation=True, max_length=MAXLEN)
    return torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--data', default=str(DATA))
    parser.add_argument('--field', choices=FIELDS)
    parser.add_argument('--holdout', default='')
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.data).read_text(encoding='utf8').splitlines() if line.strip()]
    counts = Counter((row['field'], row['label']) for row in rows)
    selected = [args.field] if args.field else FIELDS
    if not args.smoke:
        for field in selected:
            if counts[(field, True)] < 50 or counts[(field, False)] < 50:
                raise SystemExit(f'{field} needs 50 pos + 50 neg, has {counts[(field, True)]}/{counts[(field, False)]}')
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = BertTokenizer.from_pretrained(SNAP)
    model = Heads().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.CrossEntropyLoss()
    feats = []
    test_feats = []
    for row in rows:
        if args.field and row['field'] != args.field:
            continue
        ids, mask = encode(tok, row['text'])
        target = test_feats if args.holdout and str(row.get('rowId', '')).startswith(args.holdout) else feats
        target.append((ids, mask, FIELDS.index(row['field']), int(row['label'])))
    random.seed(20261126)
    torch.manual_seed(20261126)
    for epoch in range(args.epochs):
        random.shuffle(feats)
        model.train()
        total = 0.0
        for ids, mask, field, label in feats:
            opt.zero_grad()
            logits = model(ids.to(device), mask.to(device))
            loss = lossf(logits[field], torch.tensor([label], device=device))
            loss.backward()
            opt.step()
            total += float(loss)
        if epoch % 5 == 0 or epoch == args.epochs - 1:
            print(json.dumps({'epoch': epoch + 1, 'loss': round(total / len(feats), 4)}), flush=True)
    model.eval()
    confusion = {field: Counter() for field in FIELDS}
    eval_rows = test_feats or feats
    with torch.no_grad():
        for ids, mask, field, label in eval_rows:
            logits = model(ids.to(device), mask.to(device))[field]
            pred = int(logits.argmax().item())
            confusion[FIELDS[field]][f'{label}->{pred}'] += 1
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"semantic-heads{'-' + args.field if args.field else ''}.pt"
    torch.save(model.cpu(), target)
    print(json.dumps({'counts': {f'{k[0]}:{k[1]}': v for k, v in counts.items()},
                      'confusion': {field: dict(counter) for field, counter in confusion.items()},
                      'model': str(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
