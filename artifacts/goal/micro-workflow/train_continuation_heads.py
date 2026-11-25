# -*- coding: utf-8 -*-
"""Four continuation heads on one MiniRBT encoder.

novelty / unfinished / necessity / intervene. Held-out actors answer whether
the heads reproduce the rule labels; they are not evidence of semantic
generalization. Decision-level gates match the browser port.
"""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-heads'
MAXLEN = 160
KEYS = ('novelty', 'unfinished', 'necessity', 'intervene')
THRESHOLDS = {'novelty': 0.5, 'unfinished': 0.4, 'necessity': 0.5, 'intervene': 0.5}


class ContinuationHeads(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.novelty = nn.Linear(hidden, 1)
        self.unfinished = nn.Linear(hidden, 1)
        self.necessity = nn.Linear(hidden, 1)
        self.intervene = nn.Linear(hidden, 1)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return (self.novelty(cls).squeeze(-1), self.unfinished(cls).squeeze(-1),
                self.necessity(cls).squeeze(-1), self.intervene(cls).squeeze(-1))


def rank(row):
    if row['category'] == 'wait':
        return 3
    if row['category'] == 'observe' and not row.get('task_id'):
        return 2
    return 0 if row.get('task_id') else 1


def accepted_from_scores(rows, scores):
    best = None
    for row, score in zip(rows, scores):
        if row['repeat'] == 'same_world' or row['category'] == 'wait':
            continue
        adjusted = {**score, 'intervene': max(score['intervene'], 0.75 if row['involves_protagonist'] else 0)}
        total = adjusted['novelty'] + adjusted['unfinished'] + adjusted['necessity'] - adjusted['intervene']
        passed = (adjusted['novelty'] >= THRESHOLDS['novelty']
                  and adjusted['unfinished'] >= THRESHOLDS['unfinished']
                  and adjusted['necessity'] >= THRESHOLDS['necessity']
                  and adjusted['intervene'] < THRESHOLDS['intervene'])
        if passed and (best is None or total > best[0]):
            best = (total, row['actor'])
    return best[1] if best else None


def main():
    random.seed(20261125)
    torch.manual_seed(20261125)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'continuation-data.jsonl', encoding='utf8')]
    feats = []
    for row in rows:
        enc = tok(row['context'], row['candidate'], truncation=True, max_length=MAXLEN)
        feats.append({
            'split': row['split'], 'ids': torch.tensor([enc['input_ids']]),
            'mask': torch.tensor([enc['attention_mask']]), 'row': row,
        })
    train = [f for f in feats if f['split'] == 'train']
    test = [f for f in feats if f['split'] == 'test']
    pos = {key: sum(float(f['row'][key]) for f in train) / len(train) for key in KEYS}
    weights = {key: torch.tensor([(1 - p) / max(p, 0.05)], device=device) for key, p in pos.items()}
    model = ContinuationHeads().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    losses = {key: nn.BCEWithLogitsLoss(pos_weight=weights[key]) for key in KEYS}
    model.train()
    for _ in range(40):
        random.shuffle(train)
        for f in train:
            opt.zero_grad()
            values = model(f['ids'].to(device), f['mask'].to(device))
            loss = sum(losses[key](value, torch.tensor([float(f['row'][key])], device=device))
                       for key, value in zip(KEYS, values))
            loss.backward()
            opt.step()
    model.eval()
    confusion = {key: Counter() for key in KEYS}
    scored = []
    with torch.no_grad():
        for f in test:
            values = model(f['ids'].to(device), f['mask'].to(device))
            scores = {}
            for key, value in zip(KEYS, values):
                probability = float(torch.sigmoid(value).item())
                scores[key] = probability
                confusion[key][f"{int(f['row'][key])}->{int(probability > 0.5)}"] += 1
            scored.append((f['row'], scores))
    scenarios = defaultdict(list)
    for row, scores in scored:
        scenarios[row['scenario']].append((row, scores))
    decisions = Counter()
    for scenario, items in scenarios.items():
        items.sort(key=lambda pair: rank(pair[0]))
        items = items[:6]
        model_pick = accepted_from_scores([row for row, _ in items], [scores for _, scores in items])
        rule_scores = [{key: float(row[key]) for key in KEYS} for row, _ in items]
        rule_pick = accepted_from_scores([row for row, _ in items], rule_scores)
        decisions['scenarios'] += 1
        decisions['model_continue'] += int(model_pick is not None)
        decisions['rule_continue'] += int(rule_pick is not None)
        decisions['same_character'] += int(model_pick == rule_pick)
    sample = feats[0]
    path = OUT / 'continuation-heads.onnx'
    torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                      input_names=['input_ids', 'attention_mask'], output_names=list(KEYS),
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'continuation-heads-int8.onnx'
    quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
    lengths = sorted(len(tok(row['context'], row['candidate'])['input_ids']) for row in rows)
    report = {
        'rows': len(rows), 'train': len(train), 'test': len(test),
        'held_actors': sorted({f['row']['actor'] for f in test}),
        'positive_rates': {key: round(value, 3) for key, value in pos.items()},
        'test_confusion': {key: dict(value) for key, value in confusion.items()},
        'heldout_decisions': dict(decisions),
        'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
        'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size,
    }
    (PUB / 'continuation-training-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
