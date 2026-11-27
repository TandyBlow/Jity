# -*- coding: utf-8 -*-
"""Outcome-family probes: lexical baselines now; optional MiniRBT head arm.

Gold = the kernel marker (program-record ceiling). Baselines ignore the marker
in the input: majority class, and negation words (没有/未能/被阻止/无法/失败/卡住
-> not_achieved; 部分/一半 -> partial; else achieved)."""
import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
HERE = ROOT / 'artifacts/goal/micro-workflow'
PROBES = HERE / 'relation-probes/outcome.jsonl'
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
    return torch.tensor([enc['input_ids']]), torch.tensor([[1] * len(enc['input_ids'])])


def report(rows, guesses, name):
    conf = Counter()
    for row, guess in zip(rows, guesses):
        conf[f"{row['gold']}->{guess}"] += 1
    correct = sum(count for key, count in conf.items() if key.split('->')[0] == key.split('->')[1])
    f1s = []
    for label in LABELS:
        tp = conf[f'{label}->{label}']
        fp = sum(count for key, count in conf.items() if key.split('->')[1] == label and key.split('->')[0] != label)
        fn = sum(count for key, count in conf.items() if key.split('->')[0] == label and key.split('->')[1] != label)
        f1s.append(2 * tp / max(1, 2 * tp + fp + fn))
    return {'arm': name, 'rows': len(rows), 'accuracy': round(correct / max(1, len(rows)), 3),
            'macroF1': round(sum(f1s) / len(f1s), 3), 'confusion': dict(conf)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--head', action='store_true')
    args = parser.parse_args()
    rows = [json.loads(line) for line in PROBES.read_text(encoding='utf8').splitlines() if line.strip()]
    test = [row for row in rows if row['split'] == 'test']
    train = [row for row in rows if row['split'] == 'train']
    out = {'probes': len(rows), 'train': len(train), 'test': len(test), 'arms': []}
    out['arms'].append(report(test, [max(Counter(row['gold'] for row in train), key=Counter(row['gold'] for row in train).get)] * len(test), 'majority'))
    out['arms'].append(report(test, [lexical(row['input']) for row in test], 'lexical'))
    if args.head:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        tok = BertTokenizer.from_pretrained(SNAP)
        random.seed(20261127)
        torch.manual_seed(20261127)
        model = Head().to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        lossf = nn.CrossEntropyLoss()
        shuffled = train[:]
        random.shuffle(shuffled)
        for epoch in range(20):
            model.train()
            for row in shuffled:
                ids, mask = encode(tok, row['input'])
                opt.zero_grad()
                loss = lossf(model(ids.to(device), mask.to(device)), torch.tensor([LABELS.index(row['gold'])], device=device))
                loss.backward()
                opt.step()
        model.eval()
        guesses = []
        with torch.no_grad():
            for row in test:
                ids, mask = encode(tok, row['input'])
                guesses.append(LABELS[int(model(ids.to(device), mask.to(device))[0].argmax().item())])
        out['arms'].append(report(test, guesses, 'head'))
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
