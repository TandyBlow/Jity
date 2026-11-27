# -*- coding: utf-8 -*-
"""Recompute the shared-vs-split ablation report from the saved models."""
import json
import re
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
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


def metrics(counter):
    pos = counter['tp'] + counter['fn']
    neg = counter['tn'] + counter['fp']
    precision = counter['tp'] / max(1, counter['tp'] + counter['fp'])
    recall = counter['tp'] / max(1, pos)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    return {'pos': pos, 'neg': neg, 'precision': round(precision, 3), 'recall': round(recall, 3),
            'f1': round(f1, 3), 'accuracy': round((counter['tp'] + counter['tn']) / max(1, pos + neg), 3)}


def main():
    rows = [json.loads(line) for line in (HERE / 'semantic-existence.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    raw = {}
    for line in (HERE / 'real-semantic.jsonl').read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            raw[row['id']] = row
    tag = {'env': re.compile('环境[=＝]'), 'info': re.compile('信息[=＝]')}

    def rule_guess(row):
        dataset = raw.get(row['rowId']) or {}
        facts = [str(item.get('text') or '') for item in dataset.get('settled') or [] if item.get('task') == 'results']
        return any(tag[row['field']].search(text) for text in facts)

    tok = BertTokenizer.from_pretrained(SNAP)
    report = {}
    for arm in ('shared', 'split'):
        model = torch.load(MODELS / f'joint-ablation-{arm}.pt', map_location='cpu', weights_only=False)
        model.eval()
        counts = {field: Counter() for field in FIELDS}
        rule_counts = {field: Counter() for field in FIELDS}
        hybrid_counts = {field: Counter() for field in FIELDS}
        with torch.no_grad():
            for row in rows:
                if not str(row['rowId']).startswith(HOLDOUT[row['field']]):
                    continue
                field = row['field']
                text = row['text'] if arm == 'split' else f"字段：{field}\n{row['text']}"
                enc = tok(text, truncation=True, max_length=MAXLEN)
                ids = torch.tensor([enc['input_ids']])
                mask = torch.tensor([enc['attention_mask']])
                out = model(ids, mask)
                logits = out if arm == 'shared' else out[FIELDS.index(field)]
                pred = int(logits[0].argmax().item()) == 1
                label = bool(row['label'])
                guess_rules = rule_guess(row)
                guess_hybrid = guess_rules if guess_rules else pred
                for target, guess in ((counts, pred), (rule_counts, guess_rules), (hybrid_counts, guess_hybrid)):
                    cell = ('tp' if guess else 'fn') if label else ('fp' if guess else 'tn')
                    target[field][cell] += 1
        report[arm] = {field: {'head': metrics(counts[field]), 'rules': metrics(rule_counts[field]),
                               'hybrid': metrics(hybrid_counts[field])} for field in FIELDS}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
