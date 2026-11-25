# -*- coding: utf-8 -*-
"""Task/fact verifier pilot: MiniRBT pair encoder + relevance + satisfaction."""
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
SAT = ['yes', 'partial', 'no']


class TaskMatch(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.relevance = nn.Linear(hidden, 1)
        self.satisfaction = nn.Linear(hidden, 3)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.relevance(cls).squeeze(-1), self.satisfaction(cls)


def main():
    random.seed(20261125)
    torch.manual_seed(20261125)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'task-match-data.jsonl', encoding='utf8')]
    feats = []
    for row in rows:
        context = f"任务：{row['goal']}"
        enc = tok(context, row['fact'], truncation=True, max_length=MAXLEN)
        feats.append({
            'split': row['split'], 'ids': torch.tensor([enc['input_ids']]),
            'mask': torch.tensor([enc['attention_mask']]), 'row': row, 'context': context,
        })
    train = [f for f in feats if f['split'] == 'train']
    test = [f for f in feats if f['split'] == 'test']
    pos = sum(row['relevance'] for row in (f['row'] for f in train)) / len(train)
    relevance_weight = torch.tensor([(1 - pos) / max(pos, 0.05)], device=device)
    sat_counts = Counter(row['satisfaction'] for row in (f['row'] for f in train))
    sat_weights = torch.tensor([len(train) / (3 * max(sat_counts[label], 1)) for label in SAT], device=device)
    model = TaskMatch().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    bce = nn.BCEWithLogitsLoss(pos_weight=relevance_weight)
    ce = nn.CrossEntropyLoss(weight=sat_weights)
    model.train()
    for _ in range(40):
        random.shuffle(train)
        for f in train:
            opt.zero_grad()
            relevance, satisfaction = model(f['ids'].to(device), f['mask'].to(device))
            loss = bce(relevance, torch.tensor([float(f['row']['relevance'])], device=device))
            label = torch.tensor([SAT.index(f['row']['satisfaction'])], device=device)
            loss = loss + ce(satisfaction, label)
            loss.backward()
            opt.step()
    model.eval()
    relevance_conf = Counter()
    sat_conf = Counter()
    with torch.no_grad():
        for f in test:
            relevance, satisfaction = model(f['ids'].to(device), f['mask'].to(device))
            r = int(float(relevance.item()) > 0)
            relevance_conf[f"{f['row']['relevance']}->{r}"] += 1
            if f['row']['relevance'] == 1:
                pred = int(satisfaction.argmax(dim=1).item())
                sat_conf[f"{f['row']['satisfaction']}->{SAT[pred]}"] += 1
    sample = feats[0]
    path = OUT / 'task-match.onnx'
    torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                      input_names=['input_ids', 'attention_mask'], output_names=['relevance', 'satisfaction'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'task-match-int8.onnx'
    quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
    lengths = sorted(len(tok(f['context'], f['row']['fact'])['input_ids']) for f in feats)
    report = {
        'rows': len(rows), 'train': len(train), 'test': len(test),
        'held_tasks': sorted({f['row']['task_id'] for f in test}),
        'relevance_confusion': dict(relevance_conf), 'satisfaction_confusion': dict(sat_conf),
        'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
        'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size,
    }
    (PUB / 'task-match-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
