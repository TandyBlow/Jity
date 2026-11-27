# -*- coding: utf-8 -*-
"""Fixed-scale ablation: one shared classifier vs two task-specific heads.

Both arms use the same MiniRBT encoder, the same rows, the same epochs, seed and
optimizer. Arm S receives the field name in the text and one 2-logit head; arm D
routes the field to its own head. Holdouts: env sm6-, info sm10- (route level).
Rules and hybrid (rules when a tag exists, else head) are reported on the same
rows for context."""
import json
import random
import re
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATA = HERE / 'semantic-existence.jsonl'
DATASET = HERE / 'real-semantic.jsonl'
OUT = ROOT / '.local/micro-semantic'
MAXLEN = 256
FIELDS = ['info', 'env']
HOLDOUT = {'env': 'sm6-', 'info': 'sm10-'}


class Shared(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


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


def encode(tok, text):
    enc = tok(text, truncation=True, max_length=MAXLEN)
    return torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']])


def metrics(counter):
    pos = counter['tp'] + counter['fn']
    neg = counter['tn'] + counter['fp']
    precision = counter['tp'] / max(1, counter['tp'] + counter['fp'])
    recall = counter['tp'] / max(1, pos)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    return {'pos': pos, 'neg': neg, 'precision': round(precision, 3), 'recall': round(recall, 3),
            'f1': round(f1, 3), 'accuracy': round((counter['tp'] + counter['tn']) / max(1, pos + neg), 3)}


def main():
    rows = [json.loads(line) for line in DATA.read_text(encoding='utf8').splitlines() if line.strip()]
    raw = {}
    for line in DATASET.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            raw[row['id']] = row
    tag = {'env': re.compile('环境[=＝]'), 'info': re.compile('信息[=＝]')}

    def rule_guess(row):
        dataset = raw.get(row['rowId']) or {}
        facts = [str(item.get('text') or '') for item in dataset.get('settled') or [] if item.get('task') == 'results']
        return any(tag[row['field']].search(text) for text in facts)

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = BertTokenizer.from_pretrained(SNAP)
    report = {}
    for arm in ('shared', 'split'):
        model = (Shared() if arm == 'shared' else Split()).to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        lossf = nn.CrossEntropyLoss()
        random.seed(20261127)
        torch.manual_seed(20261127)
        train = [row for row in rows if not str(row['rowId']).startswith(HOLDOUT[row['field']])]
        random.shuffle(train)
        for epoch in range(30):
            model.train()
            total = 0.0
            for row in train:
                text = row['text'] if arm == 'split' else f"字段：{row['field']}\n{row['text']}"
                ids, mask = encode(tok, text)
                opt.zero_grad()
                out = model(ids.to(device), mask.to(device))
                logits = out if arm == 'shared' else out[FIELDS.index(row['field'])]
                loss = lossf(logits, torch.tensor([int(row['label'])], device=device))
                loss.backward()
                opt.step()
                total += float(loss)
            if epoch % 10 == 0 or epoch == 29:
                print(json.dumps({'arm': arm, 'epoch': epoch + 1, 'loss': round(total / len(train), 4)}), flush=True)
        model.eval()
        per_field = {}
        counts = {field: Counter() for field in FIELDS}
        rule_counts = {field: Counter() for field in FIELDS}
        hybrid_counts = {field: Counter() for field in FIELDS}
        with torch.no_grad():
            for row in rows:
                if not str(row['rowId']).startswith(HOLDOUT[row['field']]):
                    continue
                field = row['field']
                text = row['text'] if arm == 'split' else f"字段：{field}\n{row['text']}"
                ids, mask = encode(tok, text)
                out = model(ids.to(device), mask.to(device))
                logits = out if arm == 'shared' else out[FIELDS.index(field)]
                pred = int(logits[0].argmax().item()) == 1
                label = bool(row['label'])
                guess_rules = rule_guess(row)
                guess_hybrid = guess_rules if guess_rules else pred
                for target, guess in ((counts, pred), (rule_counts, guess_rules), (hybrid_counts, guess_hybrid)):
                    cell = ('tp' if guess else 'fn') if label else ('fp' if guess else 'tn')
                    target[field][cell] += 1
        for field in FIELDS:
            per_field[field] = {'head': metrics(counts[field]), 'rules': metrics(rule_counts[field]),
                                'hybrid': metrics(hybrid_counts[field])}
        report[arm] = per_field
        OUT.mkdir(parents=True, exist_ok=True)
        torch.save(model.cpu(), OUT / f'joint-ablation-{arm}.pt')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
