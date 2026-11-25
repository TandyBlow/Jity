# -*- coding: utf-8 -*-
"""Export and quantize the pilot state dicts fetched from the cluster.

The cluster has no onnx; training there saves `.pt` files. This script loads
them, exports ONNX, quantizes int8, and merges the sizes into the report.
"""
import json
import os
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
FETCH = ROOT / '.local/pilot-fetch'
OUT = ROOT / '.local/micro-heads'
MAXLEN = 192


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def main():
    report = json.loads((FETCH / 'pilot-training-report.json').read_text(encoding='utf8'))
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    OUT.mkdir(parents=True, exist_ok=True)
    for key, name, data in (
        ('act_skip', 'act-skip-head', 'pilot-act.jsonl'),
        ('appearance', 'appearance-head', 'pilot-appearance.jsonl'),
    ):
        model = Head()
        model.load_state_dict(torch.load(FETCH / f'{name}.pt', map_location='cpu'))
        model.eval()
        text = json.loads(next(open(PUB / data, encoding='utf8')))
        enc = tok(text['input'], truncation=True, max_length=MAXLEN)
        ids = torch.tensor([enc['input_ids']])
        mask = torch.tensor([enc['attention_mask']])
        path = OUT / f'{name}.onnx'
        torch.onnx.export(model, (ids, mask), path,
                          input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                          dynamic_axes={'input_ids': {0: 'batch', 1: 'len'},
                                        'attention_mask': {0: 'batch', 1: 'len'}},
                          opset_version=17)
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8 = OUT / f'{name}-int8.onnx'
        quantize_dynamic(str(path), str(int8), weight_type=QuantType.QInt8)
        rows = [json.loads(line) for line in open(PUB / data, encoding='utf8')]
        lengths = sorted(len(tok(row['input'])['input_ids']) for row in rows)
        report[key].update({
            'bytes': path.stat().st_size, 'int8_bytes': int8.stat().st_size,
            'input_tokens_median': lengths[len(lengths) // 2], 'input_tokens_max': lengths[-1],
        })
        print(name, report[key]['int8_bytes'])
    (PUB / 'pilot-training-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
