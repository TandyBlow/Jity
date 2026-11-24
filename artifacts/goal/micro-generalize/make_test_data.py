# -*- coding: utf-8 -*-
"""Tokenize test pairs (seen + held) for in-browser evaluation."""
import json
from pathlib import Path

from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
OUT = ROOT / '.local/micro-generalize'
PROBE = ROOT / '.local/probe-transformers/models'
MAXLEN = 128
NAMES = {'lu': '路明非', 'nono': '诺诺', 'fingel': '芬格尔', 'lin': '林亦舟', 'qin': '秦越'}


def main():
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    pairs = json.loads((OUT / 'pairs.json').read_text(encoding='utf8'))
    rows, out_pairs = {}, []
    for p in pairs:
        if p['split'] not in ('seen', 'held'):
            continue
        enc = tok(p['text'], p['candidate'], truncation=True, max_length=MAXLEN)
        key = f"{p['task']}:{p['row']}"
        if p['task'] == 'position':
            truth = [p['row_label']]
        else:
            truth = [NAMES[c] for c in p['row_label'] if c in NAMES]
        rows[key] = {'task': p['task'], 'split': p['split'], 'label': truth}
        out_pairs.append({'row': key, 'candidate': p['candidate'], 'ids': enc['input_ids'], 'label': p['label']})
    data = {'rows': rows, 'pairs': out_pairs}
    (PROBE / 'pairs-test.json').write_text(json.dumps(data, ensure_ascii=False), encoding='utf8')
    lens = sorted(len(p['ids']) for p in out_pairs)
    print('rows', len(rows), 'pairs', len(out_pairs), 'tokens median', lens[len(lens) // 2], 'max', lens[-1])


if __name__ == '__main__':
    main()
