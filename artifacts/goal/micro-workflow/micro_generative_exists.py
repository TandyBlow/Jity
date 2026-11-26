# -*- coding: utf-8 -*-
"""Open-field existence classifier + span/generation comparison."""
import importlib.util
import json
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import BertModel, BertTokenizer

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('v3', HERE / 'micro_generative_v3.py')
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)
v2 = v3.v2
from scale_data import finalize, make_rows  # noqa: E402

FIELDS = ['info', 'env', 'promise', 'decision', 'cause', 'neg']


class Existence(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(v2.SNAP.as_posix())
        for parameter in self.bert.parameters():
            parameter.requires_grad = False
        self.linear = nn.Linear(256, len(FIELDS))

    def forward(self, ids, mask):
        with torch.no_grad():
            hidden = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state
        pooled = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdim=True).clamp(min=1)
        return self.linear(pooled)


def train(rows, tokenizer, device, epochs=20):
    model = Existence().to(device)
    counts = torch.tensor([sum(1 for row in rows if field in row['gold']) for field in FIELDS],
                          dtype=torch.float)
    pos_weight = ((len(rows) - counts) / counts.clamp(min=1)).to(device)
    opt = torch.optim.AdamW(model.linear.parameters(), lr=1e-3)
    for _ in range(epochs):
        random.shuffle(rows)
        for start in range(0, len(rows), 16):
            batch = rows[start:start + 16]
            encoded = tokenizer([row['input'] for row in batch], padding=True, truncation=True,
                                max_length=256, return_tensors='pt')
            ids, mask = encoded['input_ids'].to(device), encoded['attention_mask'].to(device)
            target = torch.tensor([[1.0 if field in row['gold'] else 0.0 for field in FIELDS]
                                   for row in batch], device=device)
            opt.zero_grad()
            loss = F.binary_cross_entropy_with_logits(model(ids, mask), target, pos_weight=pos_weight)
            loss.backward()
            opt.step()
    return model, pos_weight.tolist()


@torch.no_grad()
def evaluate(model, tokenizer, rows, device):
    model.eval()
    counts = {field: {'tp': 0, 'fp': 0, 'fn': 0, 'gold': 0, 'pred': 0} for field in FIELDS}
    for row in rows:
        encoded = tokenizer([row['input']], padding=True, truncation=True, max_length=256,
                            return_tensors='pt')
        ids, mask = encoded['input_ids'].to(device), encoded['attention_mask'].to(device)
        probs = torch.sigmoid(model(ids, mask))[0]
        for index, field in enumerate(FIELDS):
            gold = field in row['gold']
            pred = bool(probs[index] >= 0.5)
            counts[field]['gold'] += gold
            counts[field]['pred'] += pred
            counts[field]['tp'] += gold and pred
            counts[field]['fp'] += (not gold) and pred
            counts[field]['fn'] += gold and (not pred)
    result = {}
    for field, row in counts.items():
        precision = row['tp'] / (row['tp'] + row['fp']) if row['tp'] + row['fp'] else 0.0
        recall = row['tp'] / (row['tp'] + row['fn']) if row['tp'] + row['fn'] else 0.0
        result[field] = {'gold': row['gold'], 'predicted': row['pred'],
                         'precision': round(precision, 3), 'recall': round(recall, 3),
                         'f1': round(2 * precision * recall / (precision + recall), 3)
                         if precision + recall else 0.0}
    return result


def span(rows):
    result = {}
    for field in FIELDS:
        values = [row for row in rows if row['gold'].get(field)]
        hits = sum(1 for row in values if str(row['gold'][field]) in row['input'])
        result[field] = {'rows': len(values), 'substringRate': round(hits / max(1, len(values)), 3)}
    return result


def main():
    random.seed(20261126)
    torch.manual_seed(20261126)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    train_rows = v2.training_rows() + [v2.row_from_hand(row) for row in v3.HAND_TRAIN]
    train_rows += finalize(make_rows(877, seed=20261126))
    test_rows = [v2.row_from_hand(row) for row in v2.HAND_ROWS]
    tokenizer = BertTokenizer.from_pretrained(v2.SNAP.as_posix())
    model, pos_weight = train(train_rows, tokenizer, device)
    report = {'trainRows': len(train_rows), 'testRows': len(test_rows),
              'posWeight': pos_weight, 'existence': evaluate(model, tokenizer, test_rows, device),
              'span': span(test_rows)}
    scale_path = v2.OUT / 'scale-report.json'
    if scale_path.exists():
        scale = json.loads(scale_path.read_text(encoding='utf8'))
        report['generationOpen'] = {stage: metrics.get('fieldMetrics', {})
                                    for stage, metrics in scale.get('stages', {}).items()}
    (v2.OUT / 'exists-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                               encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
