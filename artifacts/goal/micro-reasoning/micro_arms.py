# -*- coding: utf-8 -*-
"""10M arms: single pass, serial collaboration, feedback repair under budgets."""
import json
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-reasoning'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
sys.path.insert(0, str(PUB))
from rules_arm import CHARS, parse, track  # noqa: E402

BUDGETS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
sess = ort.InferenceSession(str(ROOT / '.local/micro-generalize/pair-scorer-int8.onnx'), providers=['CPUExecutionProvider'])


def score(text, cand):
    enc = tok(text, cand, truncation=True, max_length=256)
    feeds = {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
             'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)}
    return float(sess.run(None, feeds)[0][0])


def mentioned(text):
    return [c for c in CHARS if c in text]


def main():
    rows = [json.loads(line) for line in open(PUB / 'test.jsonl', encoding='utf8')]
    cache, calls = {}, 0
    t0 = time.time()
    for r in rows:
        for fi, f in enumerate(r['facts']):
            for c in mentioned(f['text']):
                cache[(r['id'], fi, c)] = score(f['text'], c)
                calls += 1
    mean_ms = (time.time() - t0) * 1000 / calls
    print('cached calls', calls, 'mean ms', round(mean_ms, 2))

    def serial(r, budget):
        holder = r['initial']
        chosen = [None] * len(r['facts'])
        spent = 0
        for fi, f in enumerate(r['facts']):
            kind, giver, rec = parse(f['text'])
            giver = holder if giver == '他' else giver
            if kind != 'give':
                continue
            cands = [c for c in mentioned(f['text']) if c != giver]
            best, best_s = None, -1e9
            for c in cands:
                if spent >= budget:
                    break
                v = cache[(r['id'], fi, c)]
                spent += 1
                if v > best_s:
                    best_s, best = v, c
            if best is not None and best_s > 0:
                holder = best
                chosen[fi] = best
        return holder, chosen, spent

    def repair(r, budget):
        ans0, chosen, spent = serial(r, budget)
        while spent < budget:
            state = r['initial']
            mismatch = None
            for fi, f in enumerate(r['facts']):
                kind, giver, rec = parse(f['text'])
                giver = state if giver == '他' else giver
                if kind == 'give':
                    if chosen[fi] != rec:
                        mismatch = fi
                        break
                    state = rec
            if mismatch is None:
                break
            f = r['facts'][mismatch]
            kind, giver, rec = parse(f['text'])
            giver = state if giver == '他' else giver
            cands = [c for c in mentioned(f['text']) if c != giver]
            best, best_s = None, -1e9
            for c in cands:
                if spent >= budget:
                    break
                v = cache[(r['id'], mismatch, c)]
                spent += 1
                if v > best_s:
                    best_s, best = v, c
            if best is not None and best_s > 0:
                chosen[mismatch] = best
            else:
                break
        state = r['initial']
        for fi, f in enumerate(r['facts']):
            kind, giver, rec = parse(f['text'])
            giver = state if giver == '他' else giver
            if kind == 'give' and chosen[fi]:
                state = chosen[fi]
        return state, ans0, spent

    single_hits = 0
    for r in rows:
        text = ' '.join(f['text'] for f in r['facts'])
        pred = max(CHARS, key=lambda c: score(text, c))
        single_hits += int(pred == r['answer'])
    result = {'rules': sum(int(track(r) == r['answer']) for r in rows),
              'single': {'hits': single_hits, 'n': len(rows), 'calls': len(rows) * 6},
              'mean_ms': mean_ms, 'serial': {}, 'feedback': {}}
    for b in BUDGETS:
        s_hits = f_hits = fixed = new = 0
        spent_sum = f_spent_sum = 0
        for r in rows:
            s_ans, _, spent = serial(r, b)
            f_ans, s_ans2, f_spent = repair(r, b)
            s_hits += int(s_ans == r['answer'])
            f_hits += int(f_ans == r['answer'])
            fixed += int(s_ans != r['answer'] and f_ans == r['answer'])
            new += int(s_ans == r['answer'] and f_ans != r['answer'])
            spent_sum += spent
            f_spent_sum += f_spent
        result['serial'][b] = {'hits': s_hits, 'n': len(rows), 'mean_calls': round(spent_sum / len(rows), 1),
                               'ms': round(spent_sum * mean_ms / len(rows), 1)}
        result['feedback'][b] = {'hits': f_hits, 'n': len(rows), 'fixed': fixed, 'new': new,
                                 'mean_calls': round(f_spent_sum / len(rows), 1),
                                 'ms': round(f_spent_sum * mean_ms / len(rows), 1)}
    (PUB / 'results-micro.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
