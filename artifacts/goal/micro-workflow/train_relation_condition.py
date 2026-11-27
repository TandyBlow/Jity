# -*- coding: utf-8 -*-
"""Condition-family relation head: does this point's fact satisfy the task goal?

Binary head on the shared MiniRBT encoder. Gold is the kernel task flip
(pending -> achieved) frozen in `relation-probes/condition.jsonl`; the lexical
baseline is the program rule (goal/fact bigram overlap >= 0.2), which is what
the head has to beat to be worth deploying."""
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
DATA_NAME = 'condition'
OUT = ROOT / '.local/micro-semantic'
MAXLEN = 192


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
    return (torch.tensor([enc['input_ids']]),
            torch.tensor([[1] * len(enc['input_ids'])]))


def grams(text):
    clean = re.sub('[^一-鿿A-Za-z0-9]', '', text)
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def overlap(input_text):
    goal = input_text.split('\n', 1)[0].removeprefix('任务：')
    fact = input_text.split('\n', 1)[1].removeprefix('事实：') if '\n' in input_text else ''
    goal_grams = grams(goal)
    return len(goal_grams & grams(fact)) / max(1, len(goal_grams))


def score(rows, guesses):
    conf = Counter()
    for row, guess in zip(rows, guesses):
        conf[f"{row['gold']}->{guess}"] += 1
    correct = sum(c for k, c in conf.items() if k.split('->')[0] == k.split('->')[1])
    f1s = []
    for label in (0, 1):
        tp = conf[f'{label}->{label}']
        fp = sum(c for k, c in conf.items() if k.split('->')[1] == str(label) and k.split('->')[0] != str(label))
        fn = sum(c for k, c in conf.items() if k.split('->')[0] == str(label) and k.split('->')[1] != str(label))
        f1s.append(2 * tp / max(1, 2 * tp + fp + fn))
    return {'accuracy': round(correct / max(1, len(rows)), 3),
            'macroF1': round(sum(f1s) / len(f1s), 3), 'confusion': dict(conf)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--family', choices=['condition', 'cross_turn'], default=DATA_NAME)
    args = parser.parse_args()
    data = HERE / f'relation-probes/{args.family}.jsonl'
    rows = [json.loads(line) for line in data.read_text(encoding='utf8').splitlines() if line.strip()]
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
            loss = lossf(model(ids.to(device), mask.to(device)), torch.tensor([int(row['gold'])], device=device))
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
            guesses.append(int(model(ids.to(device), mask.to(device))[0].argmax().item()))
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f'relation-{args.family}-head.pt'
    torch.save(model.cpu(), target)
    print(json.dumps({'family': args.family, 'rows': len(rows), 'train': len(train), 'test': len(test),
                      'head': score(test, guesses),
                      'lexicalRule': score(test, [1 if overlap(r['input']) >= 0.2 else 0 for r in test]),
                      'majority': score(test, [Counter(r['gold'] for r in train).most_common(1)[0][0]] * len(test)),
                      'model': str(target)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
