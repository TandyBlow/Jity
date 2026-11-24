# -*- coding: utf-8 -*-
"""Compare rules with the model composition on the fact test set."""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-facts'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
sys.path.insert(0, str(PUB))
from rules import settle  # noqa: E402

PAIR = ROOT / '.local/micro-generalize/pair-scorer.onnx'
POS = ROOT / '.local/micro-generalize/pair-scorer.onnx'
tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
pair_sess = ort.InferenceSession(str(PAIR), providers=['CPUExecutionProvider'])


def score(text, cand):
    enc = tok(text, cand, truncation=True, max_length=128)
    feeds = {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)}
    return float(pair_sess.run(None, feeds)[0][0])


def model(rows):
    pred = {}
    for r in rows:
        present = r['present']
        text = f"行动：{r['action']}\n在场：{'、'.join(present)}"
        targets = [n for n in present if score(text, n) > 0]
        pos_text = f"事实：{r['action']}\n当前：{r['current']}"
        dest = max(r['candidates'], key=lambda c: score(pos_text, c))
        pred[r['id']] = {'targets': targets, 'destination': dest, 'negated': None}
    return pred


def main():
    rows = [json.loads(line) for line in open(PUB / 'facts-test.jsonl', encoding='utf8')]
    rules = {}
    for r in rows:
        rules[r['id']] = settle(r['action'], r['dice'], r['present'], r['current'], r['candidates'])
    model_pred = model(rows)
    stats = {'rules': {}, 'model': {}}
    for name, preds in (('rules', rules), ('model', model_pred)):
        for field in ('targets', 'destination'):
            hits = 0
            for r in rows:
                want = r['expect'][field]
                got = preds[r['id']][field]
                hits += int(sorted(want) == sorted(got) if field == 'targets' else want == got)
            stats[name][field] = f'{hits}/{len(rows)}'
        # negation only exists in rules
        if name == 'rules':
            hits = sum(int(preds[r['id']]['negated'] == r['expect']['negated']) for r in rows)
            stats[name]['negated'] = f'{hits}/{len(rows)}'
    by_tag = {}
    for tag in sorted({r['tag'] for r in rows}):
        subset = [r for r in rows if r['tag'] == tag]
        def hits(preds, field):
            n = 0
            for r in subset:
                want, got = r['expect'][field], preds[r['id']][field]
                n += int(sorted(want) == sorted(got) if field == 'targets' else want == got)
            return f'{n}/{len(subset)}'
        by_tag[tag] = {'rules': {f: hits(rules, f) for f in ('targets', 'destination')},
                       'model': {f: hits(model_pred, f) for f in ('targets', 'destination')}}
    out = {'field': stats, 'by_tag': by_tag}
    (PUB / 'facts-accuracy.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
