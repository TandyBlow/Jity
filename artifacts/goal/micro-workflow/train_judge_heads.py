# -*- coding: utf-8 -*-
"""Three behavior judges (task / personality / scene) on contrast scenarios."""
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
MAXLEN = 128


class Judges(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.task = nn.Linear(hidden, 1)
        self.personality = nn.Linear(hidden, 1)
        self.scene = nn.Linear(hidden, 1)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.task(cls).squeeze(-1), self.personality(cls).squeeze(-1), self.scene(cls).squeeze(-1)


def main():
    random.seed(20261125)
    torch.manual_seed(20261125)
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'judge-data.jsonl', encoding='utf8')]
    actors = sorted({r['actor'] for r in rows})
    held = set(actors[::4])
    feats = []
    for row in rows:
        enc = tok(row['context'], row['candidate'], truncation=True, max_length=MAXLEN)
        feats.append({
            'split': 'test' if row['actor'] in held else 'train',
            'ids': torch.tensor([enc['input_ids']]), 'mask': torch.tensor([enc['attention_mask']]),
            'task': float(row['task']), 'personality': float(row['personality']), 'scene': float(row['scene']),
            'scenario': row['scenario'], 'actor': row['actor'], 'category': row['category'],
        })
    train = [f for f in feats if f['split'] == 'train']
    test = [f for f in feats if f['split'] == 'test']
    pos = {key: sum(f[key] for f in train) / len(train) for key in ('task', 'personality', 'scene')}
    weights = {key: torch.tensor([(1 - p) / max(p, 0.05)], device=device) for key, p in pos.items()}
    model = Judges().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    losses = {key: nn.BCEWithLogitsLoss(pos_weight=weights[key]) for key in pos}
    model.train()
    for _ in range(40):
        random.shuffle(train)
        for f in train:
            opt.zero_grad()
            t, p, s = model(f['ids'].to(device), f['mask'].to(device))
            loss = sum(losses[key](value, torch.tensor([f[key]], device=device))
                       for key, value in (('task', t), ('personality', p), ('scene', s)))
            loss.backward()
            opt.step()
    model.eval()
    confusion = {key: Counter() for key in pos}
    with torch.no_grad():
        for f in test:
            t, p, s = model(f['ids'].to(device), f['mask'].to(device))
            for key, value in (('task', t), ('personality', p), ('scene', s)):
                pred = int(value.item() > 0)
                confusion[key][f"{int(f[key])}->{pred}"] += 1
    sample = feats[0]
    path = OUT / 'judge-heads.onnx'
    torch.onnx.export(model.cpu().eval(), (sample['ids'], sample['mask']), path,
                      input_names=['input_ids', 'attention_mask'], output_names=['task', 'personality', 'scene'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'judge-heads-int8.onnx'
    quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
    lengths = sorted(len(tok(r['context'], r['candidate'])['input_ids']) for r in rows)
    report = {
        'rows': len(rows), 'train': len(train), 'test': len(test), 'held_actors': sorted(held),
        'positive_rates': {k: round(v, 3) for k, v in pos.items()},
        'test_confusion': {k: dict(v) for k, v in confusion.items()},
        'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
        'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size,
    }
    (PUB / 'judge-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
