# -*- coding: utf-8 -*-
"""Explain where the hybrid changes the rules' target output."""
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


def score(text, cand):
    enc = tok(text, cand, truncation=True, max_length=128)
    feeds = {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)}
    return float(sess.run(None, feeds)[0][0])


def main():
    rows = [json.loads(line) for line in open(PUB / 'dataset.jsonl', encoding='utf8')]
    stats = {'rules_empty_expected_empty': 0, 'rules_empty_expected_empty_model_added': 0,
             'rules_empty_expected_nonempty': 0, 'rules_empty_expected_nonempty_model_right': 0,
             'all_flips': {'rules_right_hybrid_wrong': [], 'rules_wrong_hybrid_right': []}}
    for r in rows:
        rp = settle(r['action'], r['dice'], r['present'], r['current'], r['candidates'])
        text = f"行动：{r['action']}\n在场：{'、'.join(r['present'])}"
        mp_targets = [n for n in r['present'] if score(text, n) > 0]
        hybrid_targets = rp['targets'] if rp['targets'] else mp_targets
        want = r['expect']['targets']
        if not rp['targets']:
            if not want:
                stats['rules_empty_expected_empty'] += 1
                stats['rules_empty_expected_empty_model_added'] += int(bool(mp_targets))
            else:
                stats['rules_empty_expected_nonempty'] += 1
                stats['rules_empty_expected_nonempty_model_right'] += int(sorted(mp_targets) == sorted(want))
        rules_all = (sorted(rp['targets']) == sorted(want)) and rp['destination'] == r['expect']['destination'] and rp['negated'] == r['expect']['negated']
        hybrid_all = (sorted(hybrid_targets) == sorted(want)) and rp['destination'] == r['expect']['destination'] and rp['negated'] == r['expect']['negated']
        if rules_all and not hybrid_all:
            stats['all_flips']['rules_right_hybrid_wrong'].append({'id': r['id'], 'action': r['action'], 'rules': rp['targets'], 'hybrid': hybrid_targets, 'want': want})
        if hybrid_all and not rules_all:
            stats['all_flips']['rules_wrong_hybrid_right'].append({'id': r['id'], 'action': r['action'], 'rules': rp['targets'], 'hybrid': hybrid_targets, 'want': want})
    (PUB / 'hybrid-analysis.json').write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in stats.items() if k != 'all_flips'}, ensure_ascii=False))
    print('rules_right_hybrid_wrong', len(stats['all_flips']['rules_right_hybrid_wrong']))
    print('rules_wrong_hybrid_right', len(stats['all_flips']['rules_wrong_hybrid_right']))


if __name__ == '__main__':
    main()
