# -*- coding: utf-8 -*-
"""Export the fact-support heads to ONNX int8 (dynamic length)."""
import json
from pathlib import Path

import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
OUT = ROOT / '.local/micro-heads'


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
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for field in ('env', 'info'):
        saved = torch.load(MODELS / f'support-head-{field}.pt', map_location='cpu', weights_only=False)
        model = Head()
        model.load_state_dict(saved.state_dict())
        model.eval()
        enc = tok('主张：制动轮已锁\n结算事实：床面空着，制动轮已锁，侧边留着担架靠拢的距离。', truncation=True, max_length=192)
        ids = torch.tensor([enc['input_ids']])
        mask = torch.tensor([enc['attention_mask']])
        onnx_path = OUT / f'support-{field}.onnx'
        torch.onnx.export(model, (ids, mask), onnx_path,
                          input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                          dynamic_axes={'input_ids': {0: 'batch', 1: 'len'}, 'attention_mask': {0: 'batch', 1: 'len'}},
                          opset_version=17)
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8 = OUT / f'support-{field}-int8.onnx'
        quantize_dynamic(str(onnx_path), str(int8), weight_type=QuantType.QInt8)
        report[field] = {'int8Mb': round(int8.stat().st_size / 1e6, 2), 'file': str(int8)}
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
