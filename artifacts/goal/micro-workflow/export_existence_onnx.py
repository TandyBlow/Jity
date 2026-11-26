# -*- coding: utf-8 -*-
"""Export the env/info existence heads to ONNX int8 and measure CPU latency.

Fixed length 192 matches the other browser heads; the browser port pads every
fact text to this length. The int8 file size and p50 here are the desktop
reference; ORT-WASM latency is measured by the page runtime, not this script."""
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
OUT = ROOT / '.local/micro-heads'
LEN = 192


class Heads(nn.Module):
    """Same class name and shape as the trainer, so the pickled module loads."""

    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.info = nn.Linear(hidden, 2)
        self.env = nn.Linear(hidden, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.info(cls), self.env(cls)


class One(nn.Module):
    def __init__(self, field):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.head = nn.Linear(self.bert.config.hidden_size, 2)
        self.field = field

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.head(cls)


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    for field in ('env', 'info'):
        saved = torch.load(MODELS / f'semantic-heads-{field}.pt', map_location='cpu', weights_only=False)
        model = One(field)
        state = {'bert.' + key.split('.', 1)[1] if key.startswith('bert.') else 'head.' + key.split('.', 1)[1]: value
                 for key, value in saved.state_dict().items()}
        model.load_state_dict(state)
        model.eval()
        enc = tok('路明非把盖子提开，锁梁完整。', truncation=True, max_length=LEN)
        ids = torch.tensor([enc['input_ids']])
        mask = torch.tensor([enc['attention_mask']])
        onnx_path = OUT / f'existence-{field}.onnx'
        torch.onnx.export(model, (ids, mask), onnx_path,
                          input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                          dynamic_axes={'input_ids': {0: 'batch', 1: 'len'}, 'attention_mask': {0: 'batch', 1: 'len'}},
                          opset_version=17)
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8 = OUT / f'existence-{field}-int8.onnx'
        quantize_dynamic(str(onnx_path), str(int8), weight_type=QuantType.QInt8)
        import onnxruntime as ort
        session = ort.InferenceSession(str(int8), providers=['CPUExecutionProvider'])
        inputs = {'input_ids': ids.numpy().astype(np.int64), 'attention_mask': mask.numpy().astype(np.int64)}
        short = tok('锁梁完整。', truncation=True, max_length=64)
        for _ in range(3):
            session.run(None, inputs)
        # 两个长度都能跑才说明动态轴是真的
        session.run(None, {'input_ids': np.array([short['input_ids']], dtype=np.int64),
                           'attention_mask': np.array([short['attention_mask']], dtype=np.int64)})
        times = []
        for _ in range(20):
            start = time.perf_counter()
            session.run(None, inputs)
            times.append((time.perf_counter() - start) * 1000)
        times.sort()
        report[field] = {'fp32Mb': round(onnx_path.stat().st_size / 1e6, 2),
                         'int8Mb': round(int8.stat().st_size / 1e6, 2),
                         'p50Ms': round(times[len(times) // 2], 1),
                         'len': LEN, 'file': str(int8)}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
