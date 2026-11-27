# -*- coding: utf-8 -*-
"""Candidate-pointer extraction head on the shared MiniRBT encoder.

Input: player action + one candidate clause from the entity appearance.
Target: whether this clause is the content the read action asked for.
At inference the clause with the highest probability wins; a low score
abstains instead of guessing."""
import argparse
import hashlib
import os
import json
import random
import re
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path(os.environ.get('JITY_ROOT', 'D:/others/Jity'))
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
DATA = HERE / 'semantic-extraction.jsonl'
OUT = ROOT / '.local/micro-semantic'
MAXLEN = 256
SPLIT = re.compile('[；。，,]')


def clauses_of(appearance):
    return [part.strip() for part in SPLIT.split(appearance) if part.strip()]


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
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--holdout', default='')
    args = parser.parse_args()
    pairs = [json.loads(line) for line in DATA.read_text(encoding='utf8').splitlines() if line.strip()]
    rows = []
    for pair in pairs:
        candidates = clauses_of(pair['appearance'])
        if pair['clause'] not in candidates:
            continue
        for clause in candidates:
            rows.append({'text': f"动作：{pair['action']}\n分句：{clause}", 'label': int(clause == pair['clause']),
                         'groupId': pair['id'], 'rowId': pair['rowId'], 'clause': clause,
                         'target': pair['clause'], 'appearance': pair['appearance'],
                         'action': pair['action']})
    # 按外貌留出：同一段外貌的所有动作/候选只出现在一边
    appearances = sorted({hashlib.sha1(row['appearance'].encode('utf8')).hexdigest(): row['appearance']
                          for row in rows}.items())
    held_hashes = {digest for digest, _ in appearances[::5]}
    held_groups = ({row['groupId'] for row in rows if str(row['rowId']).startswith(args.holdout)}
                   if args.holdout else set())
    holdout = [row for row in rows if hashlib.sha1(row['appearance'].encode('utf8')).hexdigest() in held_hashes
               or row['groupId'] in held_groups]
    train = [row for row in rows if row not in holdout]
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    tok = BertTokenizer.from_pretrained(SNAP)
    model = Head().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.CrossEntropyLoss()
    random.seed(20261127)
    torch.manual_seed(20261127)
    for epoch in range(args.epochs):
        random.shuffle(train)
        model.train()
        total = 0.0
        for row in train:
            ids, mask = encode(tok, row['text'])
            opt.zero_grad()
            logits = model(ids.to(device), mask.to(device))
            loss = lossf(logits, torch.tensor([row['label']], device=device))
            loss.backward()
            opt.step()
            total += float(loss)
        if epoch % 5 == 0 or epoch == args.epochs - 1:
            print(json.dumps({'epoch': epoch + 1, 'loss': round(total / max(1, len(train)), 4)}), flush=True)
    model.eval()
    groups = {}
    for row in (holdout or rows):
        groups.setdefault(row['groupId'], []).append(row)
    def bigrams(text):
        chars = re.sub('[^一-鿿A-Za-z0-9]', '', text)
        return {chars[i:i + 2] for i in range(len(chars) - 1)}
    def overlap(action, clause):
        left, right = bigrams(action), bigrams(clause)
        return len(left & right)
    arms = {'head': 0, 'first': 0, 'longest': 0, 'bigram': 0}
    for group in groups.values():
        scores = []
        for row in group:
            ids, mask = encode(tok, row['text'])
            with torch.no_grad():
                logits = model(ids.to(device), mask.to(device))[0]
            scores.append((float(logits[1] - logits[0]), row['clause']))
        target = group[0]['target']
        arms['head'] += int(max(scores)[1] == target)
        arms['first'] += int(group[0]['clause'] == target)
        arms['longest'] += int(max(group, key=lambda row: len(row['clause']))['clause'] == target)
        arms['bigram'] += int(max(group, key=lambda row: overlap(group[0]['action'], row['clause']))['clause'] == target)
    OUT.mkdir(parents=True, exist_ok=True)
    torch.save(model.cpu(), OUT / 'extraction-head.pt')
    print(json.dumps({'pairs': len(pairs), 'rows': len(rows), 'train': len(train), 'holdout': len(holdout),
                      'groups': len(groups), 'top1': {arm: f'{hit}/{len(groups)}' for arm, hit in arms.items()},
                      'model': str(OUT / 'extraction-head.pt')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
