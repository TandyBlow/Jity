# -*- coding: utf-8 -*-
"""Fixed-scale ablation, corrected protocol.

Arms share one MiniRBT-H256 encoder, the same rows, epochs, optimizer and seed.
  shared-text  body + `字段：<field>\n` prefix, one 2-logit head
  shared-embed body only, CLS + learned field embedding, one 2-logit head
  split        body only, per-field heads (the shipped heads)
Bodies are truncated to 240 tokens before any prefix so the prefix cannot
displace content. Each arm starts from the same seeded initialization.
Holdouts: env sm6-, info sm10-. Five seeds; mean and sd are reported."""
import argparse
import json
import os
import random
import re
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path(os.environ.get('JITY_ROOT', 'D:/others/Jity'))
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATA = HERE / 'semantic-existence.jsonl'
DATASET = HERE / 'real-semantic.jsonl'
OUT = ROOT / '.local/micro-semantic'
BODY_LEN = 240
FIELDS = ['info', 'env']
HOLDOUT = {'env': 'sm6-', 'info': 'sm10-'}


class SharedText(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


class SharedEmbed(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.field = nn.Embedding(2, hidden)
        self.out = nn.Linear(hidden, 2)

    def forward(self, ids, mask, field):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls + self.field(field))


class Split(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.info = nn.Linear(hidden, 2)
        self.env = nn.Linear(hidden, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.info(cls), self.env(cls)


def encode(tok, text, field=None, arm='split'):
    body = tok(text, truncation=True, max_length=BODY_LEN)
    if arm == 'shared-text':
        full = tok(f"字段：{field}\n{text}", truncation=True, max_length=BODY_LEN + 16)
        ids = full['input_ids']
    else:
        ids = body['input_ids']
    return torch.tensor([ids]), torch.tensor([[1] * len(ids)])


def metrics(counter):
    pos = counter['tp'] + counter['fn']
    neg = counter['tn'] + counter['fp']
    precision = counter['tp'] / max(1, counter['tp'] + counter['fp'])
    recall = counter['tp'] / max(1, pos)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    return {'pos': pos, 'neg': neg, 'precision': round(precision, 3), 'recall': round(recall, 3),
            'f1': round(f1, 3), 'accuracy': round((counter['tp'] + counter['tn']) / max(1, pos + neg), 3)}


def train_arm(arm, seed, rows, tok, device, epochs=30):
    random.seed(seed)
    torch.manual_seed(seed)
    model = {'shared-text': SharedText, 'shared-embed': SharedEmbed, 'split': Split}[arm]().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.CrossEntropyLoss()
    train = [row for row in rows if not str(row['rowId']).startswith(HOLDOUT[row['field']])]
    random.shuffle(train)
    for epoch in range(epochs):
        model.train()
        for row in train:
            ids, mask = encode(tok, row['text'], row['field'], arm)
            field_index = FIELDS.index(row['field'])
            opt.zero_grad()
            if arm == 'shared-embed':
                logits = model(ids.to(device), mask.to(device), torch.tensor([field_index], device=device))
            elif arm == 'split':
                logits = model(ids.to(device), mask.to(device))[field_index]
            else:
                logits = model(ids.to(device), mask.to(device))
            loss = lossf(logits, torch.tensor([int(row['label'])], device=device))
            loss.backward()
            opt.step()
    model.eval()
    counts = {field: Counter() for field in FIELDS}
    with torch.no_grad():
        for row in rows:
            if not str(row['rowId']).startswith(HOLDOUT[row['field']]):
                continue
            field_index = FIELDS.index(row['field'])
            ids, mask = encode(tok, row['text'], row['field'], arm)
            if arm == 'shared-embed':
                logits = model(ids.to(device), mask.to(device), torch.tensor([field_index], device=device))
            elif arm == 'split':
                logits = model(ids.to(device), mask.to(device))[field_index]
            else:
                logits = model(ids.to(device), mask.to(device))
            pred = int(logits[0].argmax().item()) == 1
            cell = ('tp' if pred else 'fn') if bool(row['label']) else ('fp' if pred else 'tn')
            counts[row['field']][cell] += 1
    return {field: metrics(counts[field]) for field in FIELDS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=5)
    parser.add_argument('--epochs', type=int, default=30)
    args = parser.parse_args()
    rows = [json.loads(line) for line in DATA.read_text(encoding='utf8').splitlines() if line.strip()]
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = BertTokenizer.from_pretrained(SNAP)
    report = {}
    for arm in ('shared-text', 'shared-embed', 'split'):
        runs = []
        for seed in range(20261127, 20261127 + args.seeds):
            result = train_arm(arm, seed, rows, tok, device, args.epochs)
            runs.append(result)
            print(json.dumps({'arm': arm, 'seed': seed, 'result': result}, ensure_ascii=False), flush=True)
        summary = {}
        for field in FIELDS:
            f1s = [run[field]['f1'] for run in runs]
            mean = sum(f1s) / len(f1s)
            sd = (sum((value - mean) ** 2 for value in f1s) / len(f1s)) ** 0.5
            summary[field] = {'f1Mean': round(mean, 3), 'f1Sd': round(sd, 3),
                              'precisionMean': round(sum(run[field]['precision'] for run in runs) / len(runs), 3),
                              'recallMean': round(sum(run[field]['recall'] for run in runs) / len(runs), 3)}
        report[arm] = summary
    (HERE / 'ablation-report-v2.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
