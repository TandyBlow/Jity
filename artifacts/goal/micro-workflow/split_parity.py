# -*- coding: utf-8 -*-
"""Split the parity gap: torch vs fp32 ONNX (export correctness) vs int8 (quantization)."""
import __main__
import json

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

import check_head_parity as parity
from check_head_parity import MODELS, ONNX, SNAP, HERE, load_head, torch_prob, onnx_prob

__main__.Heads = parity.Heads
__main__.Head = parity.Head


def top(session_t, session_f, session_i, tok, rows, text_of, head=None):
    out = []
    for row in rows:
        text = text_of(row)
        pt = torch_prob(session_t['model'], tok, text, head)
        pf = onnx_prob(session_f, tok, text)
        pi = onnx_prob(session_i, tok, text)
        out.append((round(abs(float(pt[1]) - float(pf[1])), 4), round(abs(float(pf[1]) - float(pi[1])), 4),
                    round(abs(float(pt[1]) - float(pi[1])), 4), row.get('rowId'),
                    round(float(pt[1]), 4), round(float(pf[1]), 4), round(float(pi[1]), 4), len(text)))
    out.sort(reverse=True)
    return out[:6]


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    existence = [json.loads(line) for line in (HERE / 'semantic-existence.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    for field, head in (('info', 0), ('env', 1)):
        model = load_head(MODELS / f'semantic-heads-{field}.pt', SNAP)
        model.eval()
        sf = ort.InferenceSession(str(ONNX / f'existence-{field}.onnx'), providers=['CPUExecutionProvider'])
        si = ort.InferenceSession(str(ONNX / f'existence-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in existence if row['field'] == field]
        print(field, 'torch-vs-fp32 | fp32-vs-int8 | torch-vs-int8 | row | p_t p_fp p_i len')
        for line in top({'model': model}, sf, si, tok, rows, lambda r: r['text'], head):
            print(' ', line)

    support = [json.loads(line) for line in (HERE / 'semantic-support.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    for field in ('env', 'info'):
        model = load_head(MODELS / f'support-head-{field}.pt', SNAP)
        model.eval()
        sf = ort.InferenceSession(str(ONNX / f'support-{field}.onnx'), providers=['CPUExecutionProvider'])
        si = ort.InferenceSession(str(ONNX / f'support-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in support if row['field'] == field]
        print('support', field, 'torch-vs-fp32 | fp32-vs-int8 | torch-vs-int8')
        for line in top({'model': model}, sf, si, tok, rows,
                        lambda r: f"主张：{r['claim']}\n结算事实：{r['facts']}"):
            print(' ', line)


if __name__ == '__main__':
    main()
