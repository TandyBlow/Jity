# -*- coding: utf-8 -*-
"""NPC behavior category head (7-way) on the recorded action sheets."""
import json
import os
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path(os.environ.get('JITY_HPC_ROOT', 'D:/others/Jity'))
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-heads'
MAXLEN = 96
EXPORT = os.environ.get('BEHAVIOR_EXPORT', '1') != '0'
LABELS = ['move', 'assist', 'guard', 'communicate', 'observe', 'use', 'other']


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, len(LABELS))

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def main():
    random.seed(20261125)
    torch.manual_seed(20261125)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'behavior-data.jsonl', encoding='utf8')]
    feats = []
    for row in rows:
        enc = tok(row['input'], truncation=True, max_length=MAXLEN)
        feats.append({'run': row['run'], 'label': LABELS.index(row['label']),
                      'ids': torch.tensor([enc['input_ids']]), 'mask': torch.tensor([enc['attention_mask']])})
    runs = sorted({row['run'] for row in feats})

    def train_eval(train_rows, test_rows):
        model = Head().to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        lossf = nn.CrossEntropyLoss()
        model.train()
        for _ in range(40):
            random.shuffle(train_rows)
            for row in train_rows:
                opt.zero_grad()
                lossf(model(row['ids'].to(device), row['mask'].to(device)), torch.tensor([row['label']], device=device)).backward()
                opt.step()
        model.eval()
        confusion = Counter()
        for row in test_rows:
            with torch.no_grad():
                pred = int(model(row['ids'].to(device), row['mask'].to(device)).argmax(1).item())
            confusion[f"{LABELS[row['label']]}->{LABELS[pred]}"] += 1
        return model, confusion

    cv = {}
    for test_run in runs:
        train_rows = [row for row in feats if row['run'] != test_run]
        test_rows = [row for row in feats if row['run'] == test_run]
        if not train_rows:
            continue
        _, confusion = train_eval(train_rows, test_rows)
        correct = sum(count for key, count in confusion.items() if key.split('->')[0] == key.split('->')[1])
        cv[test_run] = {'correct': correct, 'total': len(test_rows), 'confusion': dict(confusion)}
    model, _ = train_eval(feats, feats)
    sizes = {}
    if EXPORT:
        sample = feats[0]
        path = OUT / 'behavior-head.onnx'
        torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                          input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                          dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                        'attention_mask': {0: 'batch', 1: 'len'}},
                          opset_version=17)
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8 = OUT / 'behavior-head-int8.onnx'
        quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
        sizes = {'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size}
    else:
        pt = OUT / 'behavior-head.pt'
        torch.save(model.state_dict(), pt)
        sizes = {'pt_bytes': pt.stat().st_size}
    lengths = sorted(len(tok(row['input'])['input_ids']) for row in rows)
    report = {'rows': len(rows), 'labels': dict(Counter(row['label'] for row in rows)),
              'cv': cv, 'input_tokens_median': lengths[len(lengths) // 2],
              'input_tokens_max': lengths[-1], **sizes}
    (PUB / 'behavior-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
