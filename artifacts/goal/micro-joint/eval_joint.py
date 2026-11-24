# -*- coding: utf-8 -*-
"""Evaluate one joint model: natural, truncated lengths, and compressed position rows."""
import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-joint'
COMPRESSED = ROOT / 'artifacts/goal/micro-joint/labels-compressed.jsonl'
ORDER = ['targets', 'position', 'intent', 'judgment']
LENGTHS = [8, 16, 32, 64, 128]
MAXLEN = 128


def expected(label):
    return set(label) if isinstance(label, list) else {label}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--name', required=True)
    ap.add_argument('--model', required=True)
    args = ap.parse_args()
    tasks = json.loads((OUT / 'tasks.json').read_text(encoding='utf8'))
    test_rows = json.loads((OUT / 'test.json').read_text(encoding='utf8'))
    compressed = [json.loads(line) for line in open(COMPRESSED, encoding='utf8')]
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    sess = ort.InferenceSession(args.model, providers=['CPUExecutionProvider'])

    def predict(task, text, limit=None):
        enc = tok(text, truncation=True, max_length=MAXLEN)
        ids = enc['input_ids'][:limit] if limit else enc['input_ids']
        feeds = {'input_ids': np.array([ids], dtype=np.int64),
                 'attention_mask': np.array([[1] * len(ids)], dtype=np.int64)}
        logits = sess.run(None, feeds)[ORDER.index(task)][0]
        return [tasks[task][j] for j, v in enumerate(logits) if v > 0]

    def score(task, rows, limit=None):
        hits = 0
        for row in rows:
            hits += int(set(predict(task, row['input'], limit)) == expected(row['label']))
        return f'{hits}/{len(rows)}'

    result = {'natural': {}, 'truncated': {}, 'compressed': {}}
    for task in ORDER:
        rows = [r for r in test_rows if r['task'] == task]
        result['natural'][task] = score(task, rows)
        result['truncated'][task] = {str(L): score(task, rows, L) for L in LENGTHS}
        crows = [r for r in compressed if r['task'] == task]
        if crows:
            result['compressed'][task] = score(task, crows)
    path = COMPRESSED.parent / f'accuracy-{args.name}.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
