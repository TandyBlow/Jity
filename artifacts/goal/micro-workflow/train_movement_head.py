# -*- coding: utf-8 -*-
"""Train the movement head (binary) on the validated position samples."""
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
MAXLEN = 64


class Move(nn.Module):
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
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'movement-inputs.jsonl', encoding='utf8')]
    runs = sorted({r['run'] for r in rows})
    feats = [(encode(tok, r['input'])[0], encode(tok, r['input'])[1], r['label'], r['run']) for r in rows]
    result = {}

    def train_eval(train_runs, test_run=None):
        random.seed(20261124)
        torch.manual_seed(20261124)
        model = Move().to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
        lossf = nn.CrossEntropyLoss()
        train = [f for f in feats if f[3] in train_runs]
        model.train()
        for _ in range(40):
            random.shuffle(train)
            for ids, mask, label, _run in train:
                opt.zero_grad()
                lossf(model(ids.to(device), mask.to(device)), torch.tensor([label], device=device)).backward()
                opt.step()
        model.eval()
        stats = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
        test = [f for f in feats if test_run is None or f[3] == test_run]
        for ids, mask, label, _run in test:
            with torch.no_grad():
                pred = int(model(ids.to(device), mask.to(device)).argmax(1).item())
            stats['tp' if pred and label else 'fp' if pred else 'fn' if label else 'tn'] += 1
        return model, stats

    for test_run in runs:
        train_runs = [r for r in runs if r != test_run]
        if not train_runs:
            continue
        _m, stats = train_eval(train_runs, test_run)
        result[f'{"+".join(train_runs)}->{test_run}'] = stats
    model, _ = train_eval(runs)
    sample = feats[0]
    path = OUT / 'movement-head.onnx'
    torch.onnx.export(model.cpu().eval(), (sample[0], sample[1]), path,
                      input_names=['input_ids', 'attention_mask'], output_names=['move'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'movement-head-int8.onnx'
    quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
    lens = sorted(len(tok(r['input'])['input_ids']) for r in rows)
    result['model'] = {'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size,
                       'input_tokens_median': lens[len(lens) // 2], 'input_tokens_max': lens[-1],
                       'rows': len(rows), 'labels': dict(Counter(r['label'] for r in rows))}
    (PUB / 'movement-training-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
