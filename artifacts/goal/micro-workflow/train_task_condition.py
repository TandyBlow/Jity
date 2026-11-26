# -*- coding: utf-8 -*-
"""Task-condition support pilot: MiniRBT pair + 4-class head."""
import json
import random
from collections import Counter
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-heads'
MAXLEN = 160
LABELS = ['none', 'keyword', 'attempt', 'satisfied']


class ConditionModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.labels = nn.Linear(self.bert.config.hidden_size, len(LABELS))

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.labels(cls)


def main():
    random.seed(20261126)
    torch.manual_seed(20261126)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'task-condition-data.jsonl', encoding='utf8')]
    feats = []
    for row in rows:
        context = f"条件：{row['condition']}"
        enc = tok(context, row['fact'], truncation=True, max_length=MAXLEN)
        feats.append({'split': row['split'], 'ids': torch.tensor([enc['input_ids']]),
                      'mask': torch.tensor([enc['attention_mask']]), 'row': row, 'context': context})
    train = [f for f in feats if f['split'] == 'train']
    test = [f for f in feats if f['split'] == 'test']
    counts = Counter(row['label'] for row in (f['row'] for f in train))
    weights = torch.tensor([len(train) / (len(LABELS) * max(counts[label], 1)) for label in LABELS], device=device)
    model = ConditionModel().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    ce = nn.CrossEntropyLoss(weight=weights)
    model.train()
    for _ in range(40):
        random.shuffle(train)
        for f in train:
            opt.zero_grad()
            logits = model(f['ids'].to(device), f['mask'].to(device))
            loss = ce(logits, torch.tensor([LABELS.index(f['row']['label'])], device=device))
            loss.backward()
            opt.step()
    model.eval()
    confusion = Counter()
    with torch.no_grad():
        for f in test:
            logits = model(f['ids'].to(device), f['mask'].to(device))
            pred = LABELS[int(logits.argmax(dim=1).item())]
            confusion[f"{f['row']['label']}->{pred}"] += 1
    sample = feats[0]
    path = OUT / 'task-condition.onnx'
    torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                      input_names=['input_ids', 'attention_mask'], output_names=['labels'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'task-condition-int8.onnx'
    quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
    lengths = sorted(len(tok(f['context'], f['row']['fact'])['input_ids']) for f in feats)
    report = {
        'rows': len(rows), 'train': len(train), 'test': len(test),
        'held_tasks': sorted({f['row']['task_id'] for f in test if f['row']['task_id']}),
        'test_confusion': dict(confusion), 'test_accuracy': sum(v for k, v in confusion.items() if k.split('->')[0] == k.split('->')[1]) / max(1, sum(confusion.values())),
        'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
        'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size,
    }
    (PUB / 'task-condition-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
