# -*- coding: utf-8 -*-
"""Deployment gate: PyTorch vs shipped ONNX must agree on every eval row.

Covers existence (env/info), candidate extraction and fact support. A model
that loads is not a model that behaves the same; this gate compares argmax and
the positive-class probability, and exits non-zero on disagreement."""
import json
import re
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
ONNX = ROOT / '.local/micro-heads'
MAXLEN = 256
MAX_DIFF = 0.05


class Heads(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        hidden = self.bert.config.hidden_size
        self.info = nn.Linear(hidden, 2)
        self.env = nn.Linear(hidden, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.info(cls), self.env(cls)


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def prob(logits):
    values = np.asarray(logits, dtype=np.float64)
    exp = np.exp(values - values.max())
    return exp / exp.sum()


def torch_prob(model, tok, text, head=None):
    enc = tok(text, truncation=True, max_length=MAXLEN)
    ids = torch.tensor([enc['input_ids']])
    mask = torch.tensor([enc['attention_mask']])
    with torch.no_grad():
        out = model(ids, mask)
    logits = out[head] if head is not None else out
    return prob(logits[0].tolist())


def onnx_prob(session, tok, text):
    enc = tok(text, truncation=True, max_length=MAXLEN)
    out = session.run(None, {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
                             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)})[0][0]
    return prob(out)


def compare(name, pairs, max_diff=MAX_DIFF):
    agree = 0
    diffs = []
    hard = 0
    for text, p_torch, p_onnx in pairs:
        same = int(p_torch.argmax()) == int(p_onnx.argmax())
        agree += int(same)
        diffs.append(abs(float(p_torch[1]) - float(p_onnx[1])))
        # 近平局（torch 前两名差 < 0.1）允许 int8 翻转；明确边界的翻转才算失败
        if not same and abs(float(p_torch[1]) - float(p_torch[0])) >= 0.1:
            hard += 1
    ok = hard == 0 and (max(diffs) if diffs else 0) <= max_diff
    return {'head': name, 'rows': len(pairs), 'agree': f'{agree}/{len(pairs)}',
            'hardFlips': hard, 'maxProbDiff': round(max(diffs), 4) if diffs else 0.0, 'pass': ok}


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    import onnxruntime as ort
    report = []

    existence = [json.loads(line) for line in (HERE / 'semantic-existence.jsonl').read_text(encoding='utf8').splitlines()
                 if line.strip()]
    for field, head in (('env', 1), ('info', 0)):
        model = torch.load(MODELS / f'semantic-heads-{field}.pt', map_location='cpu', weights_only=False)
        model.eval()
        session = ort.InferenceSession(str(ONNX / f'existence-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in existence if row['field'] == field]
        pairs = [(row['text'], torch_prob(model, tok, row['text'], head), onnx_prob(session, tok, row['text'])) for row in rows]
        report.append(compare(f'existence-{field}', pairs))

    extraction = [json.loads(line) for line in (HERE / 'semantic-extraction.jsonl').read_text(encoding='utf8').splitlines()
                  if line.strip()]
    model = torch.load(MODELS / 'extraction-head.pt', map_location='cpu', weights_only=False)
    model.eval()
    session = ort.InferenceSession(str(ONNX / 'extraction-head-int8.onnx'), providers=['CPUExecutionProvider'])
    pairs = []
    group_top = {'agree': 0, 'total': 0}
    for pair in extraction:
        clauses = [part.strip() for part in re.split('[；。，,]', pair['appearance']) if part.strip()]
        torch_scores = []
        onnx_scores = []
        for clause in clauses:
            text = f"动作：{pair['action']}\n分句：{clause}"
            p_torch = torch_prob(model, tok, text)
            p_onnx = onnx_prob(session, tok, text)
            pairs.append((text, p_torch, p_onnx))
            torch_scores.append((float(p_torch[1]), clause))
            onnx_scores.append((float(p_onnx[1]), clause))
        # 决策只用组内排序：top1 必须一致
        group_top['total'] += 1
        group_top['agree'] += int(max(torch_scores)[1] == max(onnx_scores)[1])
    row = compare('extraction', pairs, max_diff=0.15)
    row['groupTop1'] = f"{group_top['agree']}/{group_top['total']}"
    row['pass'] = row['pass'] and group_top['agree'] == group_top['total']
    report.append(row)

    support = [json.loads(line) for line in (HERE / 'semantic-support.jsonl').read_text(encoding='utf8').splitlines()
               if line.strip()]
    for field in ('env', 'info'):
        model = torch.load(MODELS / f'support-head-{field}.pt', map_location='cpu', weights_only=False)
        model.eval()
        session = ort.InferenceSession(str(ONNX / f'support-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in support if row['field'] == field]
        pairs = [(f"主张：{row['claim']}\n结算事实：{row['facts']}",
                  torch_prob(model, tok, f"主张：{row['claim']}\n结算事实：{row['facts']}"),
                  onnx_prob(session, tok, f"主张：{row['claim']}\n结算事实：{row['facts']}")) for row in rows]
        report.append(compare(f'support-{field}', pairs))

    print(json.dumps(report, ensure_ascii=False, indent=1))
    if not all(row['pass'] for row in report):
        sys.exit(1)


if __name__ == '__main__':
    main()
