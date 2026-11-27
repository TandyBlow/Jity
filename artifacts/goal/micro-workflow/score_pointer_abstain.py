# -*- coding: utf-8 -*-
"""Candidate-pointer arm at fixed events, with the deployed abstention rule.

For each frozen extraction pair the pointer scores every clause; it decides
only when top1 >= 0.6 and top1 - top2 >= 0.15 (the page's thresholds), and the
chosen clause must be one of the committed candidates. Reports decided /
correct / wrong / abstained, overall and on the appearance holdout subset."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer

from head_io import load_head

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / '.local/micro-semantic'
ONNX = ROOT / '.local/micro-heads'
MAXLEN = 192
MIN_SCORE = 0.6
MIN_MARGIN = 0.15
SPLIT = re.compile('[；。，,]')


class Head(nn.Module):
    """Same shape as the trainer, so the pickled module loads."""

    def __init__(self):
        super().__init__()
        self.bert = BertModel.from_pretrained(SNAP)
        self.out = nn.Linear(self.bert.config.hidden_size, 2)

    def forward(self, ids, mask):
        cls = self.bert(input_ids=ids, attention_mask=mask).last_hidden_state[:, 0]
        return self.out(cls)


def main():
    tok = BertTokenizer.from_pretrained(SNAP)
    model = load_head(MODELS / 'extraction-head.pt', SNAP)
    model.eval()
    session = ort.InferenceSession(str(ONNX / 'extraction-head-int8.onnx'), providers=['CPUExecutionProvider'])
    pairs = [json.loads(line) for line in (HERE / 'semantic-extraction.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    appear_hashes = sorted({hashlib.sha1(pair['appearance'].encode('utf8')).hexdigest() for pair in pairs})
    holdout_hashes = set(appear_hashes[::5])
    rows = []
    onnx_rows = []
    for pair in pairs:
        clauses = [part.strip() for part in SPLIT.split(pair['appearance']) if part.strip()]
        if pair['clause'] not in clauses:
            continue
        scored = []
        for clause in clauses:
            text = f"动作：{pair['action']}\n分句：{clause}"
            enc = tok(text, truncation=True, max_length=MAXLEN)
            with torch.no_grad():
                logits = model(torch.tensor([enc['input_ids']]), torch.tensor([enc['attention_mask']]))[0]
            exp = torch.softmax(logits, dim=-1)
            scored.append((float(exp[1]), clause))
        scored.sort(reverse=True)
        best, second = scored[0], scored[1] if len(scored) > 1 else (0.0, '')
        margin = best[0] - second[0]
        decided = best[0] >= MIN_SCORE and margin >= MIN_MARGIN and best[1] in clauses
        rows.append({'id': pair['id'], 'holdout': hashlib.sha1(pair['appearance'].encode('utf8')).hexdigest() in holdout_hashes,
                     'decided': decided, 'correct': decided and best[1] == pair['clause'],
                     'abstainScore': None if decided else round(best[0], 3),
                     'abstainMargin': None if decided else round(margin, 3)})
        onnx_scored = []
        for clause in clauses:
            text = f"动作：{pair['action']}\n分句：{clause}"
            enc = tok(text, truncation=True, max_length=MAXLEN)
            out = session.run(None, {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
                                     'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)})[0][0]
            exp = np.exp(out - out.max()); prob = float(exp[1] / exp.sum())
            onnx_scored.append((prob, clause))
        onnx_scored.sort(reverse=True)
        o_best = onnx_scored[0]
        o_margin = o_best[0] - (onnx_scored[1][0] if len(onnx_scored) > 1 else 0.0)
        o_decided = o_best[0] >= MIN_SCORE and o_margin >= MIN_MARGIN
        onnx_rows.append({'holdout': hashlib.sha1(pair['appearance'].encode('utf8')).hexdigest() in holdout_hashes,
                          'decided': o_decided, 'correct': o_decided and o_best[1] == pair['clause']})

    def summary(subset):
        decided = [row for row in subset if row['decided']]
        return {'pairs': len(subset), 'decided': len(decided),
                'correct': sum(1 for row in decided if row['correct']),
                'wrong': sum(1 for row in decided if not row['correct']),
                'abstained': len(subset) - len(decided),
                'accuracyWhenDecided': round(sum(1 for row in decided if row['correct']) / max(1, len(decided)), 3)}
    def onnx_summary(subset):
        decided = [row for row in subset if row['decided']]
        return {'pairs': len(subset), 'decided': len(decided),
                'correct': sum(1 for row in decided if row['correct']),
                'wrong': sum(1 for row in decided if not row['correct']),
                'abstained': len(subset) - len(decided),
                'accuracyWhenDecided': round(sum(1 for row in decided if row['correct']) / max(1, len(decided)), 3)}
    report = {'thresholds': {'minScore': MIN_SCORE, 'minMargin': MIN_MARGIN},
              'all': summary(rows), 'appearanceHoldout': summary([row for row in rows if row['holdout']]),
              'onnxAll': onnx_summary(onnx_rows), 'onnxAppearanceHoldout': onnx_summary([row for row in onnx_rows if row['holdout']]),
              'abstainScoreBuckets': dict(Counter('<0.3' if (row['abstainScore'] or 0) < 0.3 else '0.3-0.6' for row in rows if not row['decided']))}
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
