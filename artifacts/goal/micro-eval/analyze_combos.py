# -*- coding: utf-8 -*-
"""Cue-gated hybrid and 0.6B negation combinations."""
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
CUE = ['他', '她', '他们', '她们', '两人', '两个人', '第一个人', '第二个人', '第三个人', '最后一个人', '在场的', '对方', '剩下的']
NEG_CUE = ['没', '没有', '未', '谁也没', '别']


def score(text, cand):
    enc = tok(text, cand, truncation=True, max_length=128)
    feeds = {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)}
    return float(sess.run(None, feeds)[0][0])


def ok(want, got):
    return sorted(want) == sorted(got)


def main():
    rows = [json.loads(line) for line in open(PUB / 'dataset.jsonl', encoding='utf8')]
    preds = {}
    for line in open(PUB / 'eval-06b.log', encoding='utf8'):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not rec.get('ok'):
            continue
        for row in rec['rows']:
            if row['pred']:
                preds[row['id']] = row['pred']
    result = {'cue_hybrid': 0, 'rules_06b_neg': 0, 'hybrid_06b_neg': 0, 'cue_hybrid_06b_neg': 0, 'n': len(rows)}
    for r in rows:
        rp = settle(r['action'], r['dice'], r['present'], r['current'], r['candidates'])
        mt = [n for n in r['present'] if score(f"行动：{r['action']}\n在场：{'、'.join(r['present'])}", n) > 0]
        hy_un = rp['targets'] if rp['targets'] else mt
        hy = rp['targets'] if rp['targets'] else (mt if any(c in r['action'] for c in CUE) else [])
        p = preds.get(r['id'], {})
        pneg = p.get('negated')
        n06 = (pneg is r['expect']['negated']) if isinstance(pneg, bool) else False
        nr = rp['negated'] == r['expect']['negated']
        cue = any(c in r['action'] for c in NEG_CUE)
        ok_d = rp['destination'] == r['expect']['destination']
        ok_tr = ok(rp['targets'], r['expect']['targets'])
        ok_th = ok(hy, r['expect']['targets'])
        result['cue_hybrid'] += ok_th and ok_d and nr
        result['rules_06b_neg'] += ok_tr and ok_d and n06
        result['hybrid_06b_neg'] += ok(hy_un, r['expect']['targets']) and ok_d and n06
        result['cue_hybrid_06b_neg'] += ok_th and ok_d and (n06 if cue else nr)
    (PUB / 'combos.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
