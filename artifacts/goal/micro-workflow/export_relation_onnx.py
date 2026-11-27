# -*- coding: utf-8 -*-
"""Export the relation heads (condition, cross_turn) to ONNX int8 and compare
PyTorch vs ONNX on the frozen rows with the deployment rule: same argmax, no
row crossing 0.5 outside the ±0.02 knife-edge band, and a 0.25 drift alarm."""
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer
from head_io import load_head

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
OUT = ROOT / '.local/micro-heads'
HERE = ROOT / 'artifacts/goal/micro-workflow'
MAXLEN = 192
BOUNDARY = 0.02


class Head(nn.Module):
    def __init__(self, classes=2):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, classes)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def softmax(logits):
    values = np.asarray(logits, dtype=np.float64)
    exp = np.exp(values - values.max())
    return exp / exp.sum()


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    import onnxruntime as ort
    report = []
    for family, export in (('condition', 'condition'), ('cross_turn', 'cross-turn'), ('outcome', 'outcome')):
        rows = [json.loads(line) for line in (HERE / f'relation-probes/{family}.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
        saved = load_head(MODELS / f'relation-{family}-head.pt', SNAP)
        model = Head(5 if family == 'outcome' else 2)
        model.load_state_dict(saved.state_dict())
        model.eval()
        enc = tok(rows[0]['input'], truncation=True, max_length=MAXLEN)
        ids = torch.tensor([enc['input_ids']])
        mask = torch.tensor([enc['attention_mask']])
        onnx_path = OUT / f'relation-{export}.onnx'
        torch.onnx.export(model, (ids, mask), onnx_path,
                          input_names=['input_ids', 'attention_mask'], output_names=['logits'],
                          dynamic_axes={'input_ids': {0: 'batch', 1: 'len'}, 'attention_mask': {0: 'batch', 1: 'len'}},
                          opset_version=17)
        from onnxruntime.quantization import QuantType, quantize_dynamic
        int8 = OUT / f'relation-{export}-int8.onnx'
        quantize_dynamic(str(onnx_path), str(int8), weight_type=QuantType.QInt8, per_channel=True)
        session = ort.InferenceSession(str(int8), providers=['CPUExecutionProvider'])
        agree = hard = straddle = boundary = 0
        diffs = []
        for row in rows:
            enc = tok(row['input'], truncation=True, max_length=MAXLEN)
            with torch.no_grad():
                p_t = softmax(model(torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']]))[0].tolist())
            out = session.run(None, {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
                                     'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)})[0][0]
            p_o = softmax(out)
            t, o = float(p_t[1]), float(p_o[1])
            same = int(p_t.argmax()) == int(p_o.argmax())
            agree += int(same)
            diffs.append(abs(t - o))
            if not same and abs(t - float(p_t[0])) >= 0.1:
                hard += 1
            if (t >= 0.5) != (o >= 0.5):
                if abs(t - 0.5) <= BOUNDARY and abs(o - 0.5) <= BOUNDARY:
                    boundary += 1
                else:
                    straddle += 1
        ok = hard == 0 and straddle == 0 and max(diffs) <= 0.25
        report.append({'head': f'relation-{export}', 'rows': len(rows), 'agree': f'{agree}/{len(rows)}',
                       'hardFlips': hard, 'thresholdStraddles': straddle, 'boundaryFlips': boundary,
                       'maxProbDiff': round(max(diffs), 4), 'int8Mb': round(int8.stat().st_size / 1e6, 2),
                       'pass': ok})
    print(json.dumps(report, ensure_ascii=False, indent=1))
    if not all(row['pass'] for row in report):
        sys.exit(1)


if __name__ == '__main__':
    main()
