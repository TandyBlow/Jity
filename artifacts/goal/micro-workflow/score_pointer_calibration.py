# -*- coding: utf-8 -*-
"""Can a threshold chosen on train keep the pointer's holdout precision?

Scores every frozen extraction pair with the shipped extraction head, then:
  - reports the (top1, margin) of each decided pair by split,
  - picks (minScore, minMargin) on the train pairs that maximises coverage
    subject to precision >= 0.9,
  - applies that pair to the appearance holdout and compares with the
    deployed 0.6/0.15.
If the wrong holdout decisions sit at high confidence, no train-chosen
threshold can remove them."""
import hashlib
import json
import re
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

from head_io import load_head

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
MAXLEN = 192
SPLIT = re.compile('[；。，,]')
PRECISION_BAR = 0.9


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    model = load_head(MODELS / 'extraction-head.pt', SNAP)
    model.eval()
    pairs = [json.loads(line) for line in (HERE / 'semantic-extraction.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    hashes = sorted({hashlib.sha1(pair['appearance'].encode('utf8')).hexdigest() for pair in pairs})
    holdout_hashes = set(hashes[::5])
    rows = []
    for pair in pairs:
        clauses = [part.strip() for part in SPLIT.split(pair['appearance']) if part.strip()]
        if pair['clause'] not in clauses:
            continue
        scored = []
        for clause in clauses:
            enc = tok(f"动作：{pair['action']}\n分句：{clause}", truncation=True, max_length=MAXLEN)
            with torch.no_grad():
                logits = model(torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']]))[0]
            scored.append((float(torch.softmax(logits, -1)[1]), clause))
        scored.sort(reverse=True)
        best = scored[0]
        margin = best[0] - (scored[1][0] if len(scored) > 1 else 0.0)
        rows.append({'holdout': hashlib.sha1(pair['appearance'].encode('utf8')).hexdigest() in holdout_hashes,
                     'score': round(best[0], 3), 'margin': round(margin, 3),
                     'correct': best[1] == pair['clause'], 'id': pair['id'],
                     'action': pair['action'], 'target': pair['clause']})

    def evaluate(thresholds, subset):
        decided = [row for row in subset if row['score'] >= thresholds[0] and row['margin'] >= thresholds[1]]
        correct = sum(1 for row in decided if row['correct'])
        return {'decided': len(decided), 'correct': correct, 'wrong': len(decided) - correct,
                'coverage': round(len(decided) / max(1, len(subset)), 3),
                'precision': round(correct / max(1, len(decided)), 3)}
    train = [row for row in rows if not row['holdout']]
    holdout = [row for row in rows if row['holdout']]
    best_thresholds, best_cover = None, -1.0
    for score in [round(0.5 + 0.05 * i, 2) for i in range(10)]:
        for margin in [round(0.05 + 0.05 * i, 2) for i in range(10)]:
            stats = evaluate((score, margin), train)
            if stats['decided'] and stats['precision'] >= PRECISION_BAR and stats['coverage'] > best_cover:
                best_cover, best_thresholds = stats['coverage'], (score, margin)
    report = {
        'deployed': {'thresholds': (0.6, 0.15), 'train': evaluate((0.6, 0.15), train), 'holdout': evaluate((0.6, 0.15), holdout)},
        'trainChosen': {'thresholds': best_thresholds, 'train': evaluate(best_thresholds, train) if best_thresholds else None,
                        'holdout': evaluate(best_thresholds, holdout) if best_thresholds else None},
        'holdoutWrong': [row for row in holdout if row['correct'] is False and row['score'] >= 0.6 and row['margin'] >= 0.15],
        'holdoutRows': holdout, 'rows': rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
