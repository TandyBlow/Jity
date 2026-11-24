# -*- coding: utf-8 -*-
"""Compare rules, the 10M model and the hybrid on the 300-row eval set."""
import json
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-eval'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
sys.path.insert(0, str(ROOT / 'artifacts/goal/micro-facts'))
from rules import settle  # noqa: E402

tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
sess = ort.InferenceSession(str(ROOT / '.local/micro-generalize/pair-scorer-int8.onnx'), providers=['CPUExecutionProvider'])
TAGS = ['unknown_person', 'unknown_place', 'multi_turn', 'compound', 'implicit', 'context']


def score(text, cand):
    enc = tok(text, cand, truncation=True, max_length=128)
    feeds = {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)}
    return float(sess.run(None, feeds)[0][0])


def model_pred(r):
    text = f"行动：{r['action']}\n在场：{'、'.join(r['present'])}"
    targets = [n for n in r['present'] if score(text, n) > 0]
    pos_text = f"事实：{r['action']}\n当前：{r['current']}"
    dest = max(r['candidates'], key=lambda c: score(pos_text, c))
    return {'targets': targets, 'destination': dest, 'negated': None}


def rules_pred(r):
    return settle(r['action'], r['dice'], r['present'], r['current'], r['candidates'])


def hybrid_pred(r):
    rp, mp = rules_pred(r), model_pred(r)
    return {'targets': rp['targets'] if rp['targets'] else mp['targets'],
            'destination': rp['destination'], 'negated': rp['negated']}


def ok(want, got):
    return sorted(want) == sorted(got)


def main():
    rows = [json.loads(line) for line in open(PUB / 'dataset.jsonl', encoding='utf8')]
    systems = {'rules': {}, 'model': {}, 'hybrid': {}}
    for r in rows:
        systems['rules'][r['id']] = rules_pred(r)
        systems['model'][r['id']] = model_pred(r)
        systems['hybrid'][r['id']] = hybrid_pred(r)
    result = {}
    for name, preds in systems.items():
        stats = {'targets': 0, 'destination': 0, 'negated': 0, 'negated_total': 0, 'rows_common': 0, 'rows_all': 0}
        for r in rows:
            p = preds[r['id']]
            t = ok(r['expect']['targets'], p['targets'])
            d = r['expect']['destination'] == p['destination']
            stats['targets'] += t
            stats['destination'] += d
            stats['rows_common'] += t and d
            if p['negated'] is not None:
                n = p['negated'] == r['expect']['negated']
                stats['negated'] += n
                stats['negated_total'] += 1
                stats['rows_all'] += t and d and n
        stats['n'] = len(rows)
        result[name] = stats
    by_tag = {}
    for tag in TAGS:
        subset = [r for r in rows if tag in r['tags']]
        entry = {'n': len(subset)}
        for name, preds in systems.items():
            entry[name] = {'targets': 0, 'destination': 0, 'rows_common': 0}
            for r in subset:
                p = preds[r['id']]
                t = ok(r['expect']['targets'], p['targets'])
                d = r['expect']['destination'] == p['destination']
                entry[name]['targets'] += t
                entry[name]['destination'] += d
                entry[name]['rows_common'] += t and d
        by_tag[tag] = entry
    out = {'overall': result, 'by_tag': by_tag}
    (PUB / 'results-20261124.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
