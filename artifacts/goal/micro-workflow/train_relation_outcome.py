# -*- coding: utf-8 -*-
"""Outcome-family relation head on the shared MiniRBT encoder (5 classes).

Gold is the kernel outcome marker; the input is the fact text with the marker
and structured tags stripped. Reads only the frozen `relation-probes/outcome.jsonl`
and reports accuracy/macro-F1 plus the lexical and majority baselines, because
a head that does not clear the negation-word rule has learned nothing about
outcomes."""
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
DATA = HERE / 'relation-probes/outcome.jsonl'
OUT = ROOT / '.local/micro-semantic'
LABELS = ['achieved', 'partial', 'not_achieved', 'blocked', 'no_change']
NEG = re.compile('没有成功|未能|没能|没有|未|无法|失败|卡住|纹丝不动|被阻止')
PARTIAL = re.compile('一部分|部分|一半')


def lexical(text):
    if NEG.search(text):
        return 'not_achieved'
    if PARTIAL.search(text):
        return 'partial'
    return 'achieved'


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, len(LABELS))

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def encode(tok, text):
    enc = tok(text, truncation=True, max_length=192)
    return (torch.tensor([enc['input_ids']]),
            torch.tensor([[1] * len(enc['input_ids'])]))


def score(rows, guesses):
    conf = Counter()
    for row, guess in zip(rows, guesses):
        conf[f"{row['gold']}->{guess}"] += 1
    correct = sum(c for k, c in conf.items() if k.split('->')[0] == k.split('->')[1])
    f1s = []
    for label in LABELS:
        tp = conf[f'{label}->{label}']
        fp = sum(c for k, c in conf.items() if k.split('->')[1] == label and k.split('->')[0] != label)
        fn = sum(c for k, c in conf.items() if k.split('->')[0] == label and k.split('->')[1] != label)
        f1s.append(2 * tp / max(1, 2 * tp + fp + fn))
    return {'accuracy': round(correct / max(1, len(rows)), 3),
            'macroF1': round(sum(f1s) / len(f1s), 3), 'confusion': dict(conf)}


def main():
    rows = [json.loads(line) for line in DATA.read_text(encoding='utf8').splitlines() if line.strip()]
    train = [r for r in rows if r['split'] == 'train']
    test = [r for r in rows if r['split'] == 'test']
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = BertTokenizer.from_pretrained(SNAP)
    model = Head().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.CrossEntropyLoss()
    random.seed(20261127)
    torch.manual_seed(20261127)
    order = train[:]
    for epoch in range(30):
        random.shuffle(order)
        model.train()
        total = 0.0
        for row in order:
            ids, mask = encode(tok, row['input'])
            opt.zero_grad()
            loss = lossf(model(ids.to(device), mask.to(device)),
                         torch.tensor([LABELS.index(row['gold'])], device=device))
            loss.backward()
            opt.step()
            total += float(loss)
        if epoch % 5 == 0 or epoch == 29:
            print(json.dumps({'epoch': epoch + 1, 'loss': round(total / max(1, len(order)), 4)}), flush=True)
    model.eval()
    guesses = []
    with torch.no_grad():
        for row in test:
            ids, mask = encode(tok, row['input'])
            guesses.append(LABELS[int(model(ids.to(device), mask.to(device))[0].argmax().item())])
    majority = Counter(r['gold'] for r in train).most_common(1)[0][0]
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'relation-outcome-head.pt'
    torch.save(model.cpu(), target)
    print(json.dumps({'rows': len(rows), 'train': len(train), 'test': len(test),
                      'head': score(test, guesses),
                      'lexical': score(test, [lexical(r['input']) for r in test]),
                      'majority': score(test, [majority] * len(test)),
                      'model': str(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
