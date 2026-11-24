# -*- coding: utf-8 -*-
"""Train two task heads (act/skip, results 5-way) on a shared MiniRBT encoder.

Run-level split: train on one recorded run, test on the other, then swap.
Exports one ONNX graph with two outputs for the browser runtime.
"""
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
ACT = ['act', 'skip']
RESULT = ['achieved', 'partial', 'not_achieved', 'blocked', 'no_change']


class Heads(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.act = nn.Linear(hidden, len(ACT))
        self.result = nn.Linear(hidden, len(RESULT))

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.act(cls), self.result(cls)


def encode(tok, text):
    enc = tok(text, truncation=True, max_length=MAXLEN)
    return torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']])


def labels_of(row):
    if row['task'] == 'act':
        return 'act', ACT.index(row['label'])
    return 'result', RESULT.index(row['label'])


def run_split(rows, train_runs, test_run, tok, device, epochs=40):
    random.seed(20261124)
    torch.manual_seed(20261124)
    model = Heads().to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-5)
    lossf = nn.CrossEntropyLoss()
    train = [r for r in rows if r['run'] in train_runs]
    test = [r for r in rows if r['run'] == test_run]
    feats = [(encode(tok, r['input'])[0], encode(tok, r['input'])[1], labels_of(r)) for r in train]
    model.train()
    for _ in range(epochs):
        random.shuffle(feats)
        for ids, mask, (task, label) in feats:
            opt.zero_grad()
            act_logits, result_logits = model(ids.to(device), mask.to(device))
            logits = act_logits if task == 'act' else result_logits
            lossf(logits, torch.tensor([label], device=device)).backward()
            opt.step()
    model.eval()
    stats = {'act': [0, 0], 'result': [0, 0], 'confusion': Counter(), 'test': len(test)}
    for r in test:
        ids, mask = encode(tok, r['input'])
        task, label = labels_of(r)
        with torch.no_grad():
            act_logits, result_logits = model(ids.to(device), mask.to(device))
        logits = act_logits if task == 'act' else result_logits
        pred = int(logits.argmax(1).item())
        stats[task][1] += 1
        stats[task][0] += int(pred == label)
        if task == 'result':
            stats['confusion'][f'{RESULT[label]}->{RESULT[pred]}'] += 1
    return model, stats


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    rows = [json.loads(line) for line in open(PUB / 'short-inputs.jsonl', encoding='utf8')]
    runs = sorted({r['run'] for r in rows})
    result = {}
    for test_run in runs:
        train_runs = [r for r in runs if r != test_run]
        if not train_runs:
            continue
        _m, stats = run_split(rows, train_runs, test_run, tok, device)
        result[f'{"+".join(train_runs)}->{test_run}'] = {'act': stats['act'], 'result': stats['result'], 'test': stats['test'],
                                                          'confusion': dict(stats['confusion'])}
    model, _stats = run_split(rows, runs, runs[0], tok, device)
    sample = next(r for r in rows if r['task'] == 'result')
    ids, mask = encode(tok, sample['input'])
    path = OUT / 'task-heads.onnx'
    torch.onnx.export(model.cpu().eval(), (ids, mask), path,
                      input_names=['input_ids', 'attention_mask'], output_names=['act', 'result'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                    'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    lens = sorted(len(tok(r['input'])['input_ids']) for r in rows)
    result['model'] = {'path': str(path), 'bytes': path.stat().st_size,
                       'input_tokens_median': lens[len(lens) // 2], 'input_tokens_max': lens[-1],
                       'train_rows': len(rows), 'label_counts': {f"{k[0]}/{k[1]}": v for k, v in Counter((r['task'], r['label']) for r in rows).items()}}
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'task-heads-int8.onnx'
    quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
    result['int8'] = {'path': str(int8), 'bytes': int8.stat().st_size}
    (PUB / 'head-training-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
