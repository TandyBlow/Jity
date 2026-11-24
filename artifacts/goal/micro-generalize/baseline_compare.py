# -*- coding: utf-8 -*-
"""Compare the pair scorer with plain string matching on targets."""
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-generalize'
PUB = ROOT / 'artifacts/goal/micro-generalize'
NAMES = {'lu': '路明非', 'nono': '诺诺', 'fingel': '芬格尔', 'lin': '林亦舟', 'qin': '秦越'}
tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
sess = ort.InferenceSession(str(OUT / 'pair-scorer.onnx'), providers=['CPUExecutionProvider'])


def score(text, cand):
    enc = tok(text, cand, truncation=True, max_length=128)
    feeds = {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)}
    return float(sess.run(None, feeds)[0][0])


def baseline(action, present):
    return {n for n in present if n in action}


def main():
    pairs = json.loads((OUT / 'pairs.json').read_text(encoding='utf8'))
    turns = json.loads((ROOT / 'artifacts/goal/micro-chain/turns.json').read_text(encoding='utf8'))
    rows = {}
    for p in pairs:
        if p['task'] == 'targets' and p['split'] in ('seen', 'held'):
            rows.setdefault((p['split'], p['row']), []).append(p)
    result = {'rows': {}, 'turns': []}
    for split in ('seen', 'held'):
        stats = {'total': 0, 'baseline': 0, 'model': 0, 'diffs': []}
        for (s, row), items in rows.items():
            if s != split:
                continue
            text = items[0]['text']
            present = items[0]['candidates']
            truth = {i['candidate'] for i in items if i['label'] > 0}
            action = text.split('行动：', 1)[1].split('\n在场：', 1)[0]
            base = baseline(action, present)
            model = {i['candidate'] for i in items if score(text, i['candidate']) > 0}
            stats['total'] += 1
            stats['baseline'] += int(base == truth)
            stats['model'] += int(model == truth)
            if base != truth or model != truth:
                stats['diffs'].append({'row': row, 'truth': sorted(truth), 'baseline': sorted(base),
                                       'model': sorted(model), 'action': action})
        result['rows'][split] = stats
        print(split, 'total', stats['total'], 'baseline', stats['baseline'], 'model', stats['model'])
        for d in stats['diffs'][:8]:
            print(' ', d)
    for t in turns:
        action = t['action']
        present = t['present']
        truth = {NAMES[c] for c in t['expect']['targets']}
        text = f"行动：{action}\n在场：{'、'.join(present)}"
        base = baseline(action, present)
        model = {n for n in present if score(text, n) > 0}
        result['turns'].append({'id': t['id'], 'truth': sorted(truth), 'baseline': sorted(base),
                                'model': sorted(model)})
    print('turns', [(r['id'], r['truth'], r['baseline'], r['model']) for r in result['turns']])
    (PUB / 'baseline.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
