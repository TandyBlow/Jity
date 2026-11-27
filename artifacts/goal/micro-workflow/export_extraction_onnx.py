# -*- coding: utf-8 -*-
"""Export the candidate extraction head to ONNX int8 (dynamic length).

Same encoder as the existence heads; input is 动作：…\n分句：… and the output
is a 2-logit score for whether the clause is the content the action asked for."""
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
SRC = ROOT / '.local/micro-semantic/extraction-head.pt'
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
    saved = torch.load(SRC, map_location='cpu', weights_only=False)
    model = Head()
    state = {'bert.' + key.split('.', 1)[1] if key.startswith('bert.') else 'out.' + key.split('.', 1)[1]: value
             for key, value in saved.state_dict().items()}
    model.load_state_dict(state)
    model.eval()
    enc = tok('动作：读规则牌上关于医护白线的条款\n分句：医护白线禁射', truncation=True, max_length=192)
    ids = torch.tensor([enc['input_ids']])
    mask = torch.tensor([enc['attention_mask']])
    onnx_path = OUT / 'extraction-head.onnx'
    torch.onnx.export(model, (ids, mask), onnx_path,
                      input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                      dynamic_axes={'input_ids': {0: 'batch', 1: 'len'}, 'attention_mask': {0: 'batch', 1: 'len'}},
                      opset_version=17)
    from onnxruntime.quantization import QuantType, quantize_dynamic
    int8 = OUT / 'extraction-head-int8.onnx'
    quantize_dynamic(str(onnx_path), str(int8), weight_type=QuantType.QInt8)
    import onnxruntime as ort
    session = ort.InferenceSession(str(int8), providers=['CPUExecutionProvider'])
    short = tok('动作：查看锁梁\n分句：锁梁完整', truncation=True, max_length=64)
    for _ in range(3):
        session.run(None, {'input_ids': ids.numpy().astype(np.int64), 'attention_mask': mask.numpy().astype(np.int64)})
    session.run(None, {'input_ids': np.array([short['input_ids']], dtype=np.int64),
                       'attention_mask': np.array([short['attention_mask']], dtype=np.int64)})
    times = []
    for _ in range(20):
        start = time.perf_counter()
        session.run(None, {'input_ids': ids.numpy().astype(np.int64), 'attention_mask': mask.numpy().astype(np.int64)})
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    print(json.dumps({'int8Mb': round(int8.stat().st_size / 1e6, 2), 'p50Ms': round(times[len(times) // 2], 2),
                      'file': str(int8)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
