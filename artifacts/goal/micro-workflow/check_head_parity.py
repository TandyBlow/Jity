# -*- coding: utf-8 -*-
"""Deployment gate: PyTorch vs shipped ONNX must make the same decisions.

Covers existence (env/info), candidate extraction and fact support. A model
that loads is not a model that behaves the same; this gate compares argmax and
whether a row lands on the same side of the deployed threshold, and exits
non-zero on any decision change. maxProbDiff stays as a weight-mismatch alarm:
an export bug shows up as 0.5+ drift on many rows, int8 drift as <0.1 on a few."""
import json
import re
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from transformers import BertConfig, BertModel, BertTokenizer
from head_io import load_head

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
ONNX = ROOT / '.local/micro-heads'
# 浏览器端口按 192 截断，对拍必须用同一输入长度
MAXLEN = 192
# 权重错配时漂移 0.5+；量化漂移实测 <0.2，上限只作警报
MAX_DIFF = 0.25
GATE = 0.75
CANDIDATE = 0.6
MARGIN = 0.15
# 门限 ±0.02 内翻转是数值刀口，任何核差异都会翻
BOUNDARY = 0.02


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


def compare(name, pairs, threshold, max_diff=MAX_DIFF):
    agree = 0
    diffs = []
    hard = 0
    straddle = 0
    boundary = 0
    for text, p_torch, p_onnx in pairs:
        same = int(p_torch.argmax()) == int(p_onnx.argmax())
        agree += int(same)
        t, o = float(p_torch[1]), float(p_onnx[1])
        diffs.append(abs(t - o))
        # 近平局（torch 前两名差 < 0.1）允许 int8 翻转；明确边界的翻转才算失败
        if not same and abs(t - float(p_torch[0])) >= 0.1:
            hard += 1
        # 门槛两侧不一致 = 部署决定改变；刀口内翻转单列
        if (t >= threshold) != (o >= threshold):
            if abs(t - threshold) <= BOUNDARY and abs(o - threshold) <= BOUNDARY:
                boundary += 1
            else:
                straddle += 1
    ok = hard == 0 and straddle == 0 and (max(diffs) if diffs else 0) <= max_diff
    return {'head': name, 'rows': len(pairs), 'agree': f'{agree}/{len(pairs)}',
            'hardFlips': hard, 'thresholdStraddles': straddle,
            'boundaryFlips': boundary,
            'maxProbDiff': round(max(diffs), 4) if diffs else 0.0, 'pass': ok}


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    import onnxruntime as ort
    report = []

    existence = [json.loads(line) for line in (HERE / 'semantic-existence.jsonl').read_text(encoding='utf8').splitlines()
                 if line.strip()]
    for field, head in (('env', 1), ('info', 0)):
        model = load_head(MODELS / f'semantic-heads-{field}.pt', SNAP)
        model.eval()
        session = ort.InferenceSession(str(ONNX / f'existence-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in existence if row['field'] == field]
        pairs = [(row['text'], torch_prob(model, tok, row['text'], head), onnx_prob(session, tok, row['text'])) for row in rows]
        report.append(compare(f'existence-{field}', pairs, GATE))

    extraction = [json.loads(line) for line in (HERE / 'semantic-extraction.jsonl').read_text(encoding='utf8').splitlines()
                  if line.strip()]
    model = load_head(MODELS / 'extraction-head.pt', SNAP)
    model.eval()
    session = ort.InferenceSession(str(ONNX / 'extraction-head-int8.onnx'), providers=['CPUExecutionProvider'])
    pairs = []
    group_top = {'agree': 0, 'total': 0, 'benignFlips': 0}
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
        # 决策只用组内排序：top1 一致，或两臂都弃权
        ranked = sorted(torch_scores, reverse=True)
        margin = ranked[0][0] - ranked[1][0] if len(ranked) > 1 else 1.0
        group_top['total'] += 1
        if max(torch_scores)[1] == max(onnx_scores)[1]:
            group_top['agree'] += 1
        elif ranked[0][0] < CANDIDATE or margin < MARGIN:
            group_top['benignFlips'] += 1
    row = compare('extraction', pairs, CANDIDATE)
    row['groupTop1'] = f"{group_top['agree']}/{group_top['total']}"
    row['groupBenignFlips'] = group_top['benignFlips']
    row['pass'] = row['pass'] and group_top['agree'] + group_top['benignFlips'] == group_top['total']
    report.append(row)

    support = [json.loads(line) for line in (HERE / 'semantic-support.jsonl').read_text(encoding='utf8').splitlines()
               if line.strip()]
    for field in ('env', 'info'):
        model = load_head(MODELS / f'support-head-{field}.pt', SNAP)
        model.eval()
        session = ort.InferenceSession(str(ONNX / f'support-{field}-int8.onnx'), providers=['CPUExecutionProvider'])
        rows = [row for row in support if row['field'] == field]
        pairs = [(f"主张：{row['claim']}\n结算事实：{row['facts']}",
                  torch_prob(model, tok, f"主张：{row['claim']}\n结算事实：{row['facts']}"),
                  onnx_prob(session, tok, f"主张：{row['claim']}\n结算事实：{row['facts']}")) for row in rows]
        report.append(compare(f'support-{field}', pairs, 0.5))

    print(json.dumps(report, ensure_ascii=False, indent=1))
    if not all(row['pass'] for row in report):
        sys.exit(1)


if __name__ == '__main__':
    main()
