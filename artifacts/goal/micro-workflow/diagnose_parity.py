# -*- coding: utf-8 -*-
"""Per-row torch vs ONNX diff for the heads whose parity gate fails."""
import json
import sys

import __main__

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

import check_head_parity as parity
from check_head_parity import MODELS, ONNX, SNAP, HERE, load_head, prob, torch_prob, onnx_prob

__main__.Heads = parity.Heads
__main__.Head = parity.Head


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    existence = [json.loads(line) for line in (HERE / 'semantic-existence.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    for field, head in (('info', 0),):
        model = load_head(MODELS / f'semantic-heads-{field}.pt', SNAP)
        model.eval()
        session = ort.InferenceSession(str(ONNX / f'existence-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in existence if row['field'] == field]
        diffs = []
        for row in rows:
            p1 = torch_prob(model, tok, row['text'], head)
            p2 = onnx_prob(session, tok, row['text'])
            diffs.append((abs(float(p1[1]) - float(p2[1])), row.get('rowId'), row['label'],
                          round(float(p1[1]), 4), round(float(p2[1]), 4), len(row['text'])))
        diffs.sort(reverse=True)
        print(field, 'top diffs:')
        for d in diffs[:8]:
            print(' ', d)
        print(field, 'n>0.15:', sum(1 for d in diffs if d[0] > 0.15), '/', len(diffs))

    support = [json.loads(line) for line in (HERE / 'semantic-support.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    for field in ('env',):
        model = load_head(MODELS / f'support-head-{field}.pt', SNAP)
        model.eval()
        session = ort.InferenceSession(str(ONNX / f'support-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in support if row['field'] == field]
        diffs = []
        for row in rows:
            text = f"主张：{row['claim']}\n结算事实：{row['facts']}"
            diffs.append((abs(float(torch_prob(model, tok, text)[1]) - float(onnx_prob(session, tok, text)[1])),
                          row.get('rowId'), row['label'], round(float(torch_prob(model, tok, text)[1]), 4),
                          round(float(onnx_prob(session, tok, text)[1]), 4), len(text)))
        diffs.sort(reverse=True)
        print('support', field, 'top diffs:')
        for d in diffs[:5]:
            print(' ', d)


if __name__ == '__main__':
    sys.exit(main())
