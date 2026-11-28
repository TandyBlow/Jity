#!/usr/bin/env python3
"""Run the shipped existence heads (info/env int8 ONNX) on semantic probes.

Builds the same `玩家：... 事实：...` input the heads were scored on in
score_fixed_arms.py, tokenizes with the MiniRBT snapshot, and writes
predictions in semantic_score.py format. Status only: the existence heads do
not emit the content clause.

  python -m tools.experiment_platform.head_predict \
    --set artifacts/goal/platform/eval/semantic-probes-v1.test.jsonl \
    --out artifacts/goal/platform/eval/semantic-probes-v1.test.pred.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
TOKENIZER = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
MODELS = ROOT / 'frontend/public/micro'
MAXLEN = 256


def load():
    import onnxruntime as ort
    from transformers import BertTokenizer
    tokenizer = BertTokenizer.from_pretrained(str(TOKENIZER))
    sessions = {field: ort.InferenceSession(str(MODELS / f'existence-{field}-int8.onnx'),
                                           providers=['CPUExecutionProvider'])
                for field in ('info', 'env')}
    return tokenizer, sessions


def predict(case: dict, tokenizer, sessions) -> dict:
    inp = case.get('input') or {}
    text = f"玩家：{inp.get('playerLine', '')}\n事实：{inp.get('settledLine', '')}"
    enc = tokenizer(text, truncation=True, max_length=MAXLEN)
    ids = np.array([enc['input_ids']], dtype=np.int64)
    mask = np.array([enc['attention_mask']], dtype=np.int64)
    row = {'id': case['id']}
    for field, session in sessions.items():
        logits = session.run(None, {'input_ids': ids, 'attention_mask': mask})[0][0]
        exp = np.exp(logits - logits.max())
        prob = exp / exp.sum()
        row[field] = {'status': 'present' if int(np.argmax(logits)) == 1 else 'absent',
                      'score': round(float(prob[1]), 4), 'content': ''}
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--set', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    cases = [json.loads(ln) for ln in Path(args.set).read_text(encoding='utf-8-sig').splitlines() if ln.strip()]
    tokenizer, sessions = load()
    rows = [predict(case, tokenizer, sessions) for case in cases]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    print(json.dumps({'cases': len(rows), 'out': str(out)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
