# -*- coding: utf-8 -*-
"""Context-aware replacement choice: for a source phrase, pick the rewrite the
same phrase received under a similar clause+previous-sentence context.
Baselines: copy, most-frequent rewrite, context-similarity retrieval.
Split is by passage id so the phrase may be seen while its context differs."""
import json
import math

import numpy as np
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAIRS = HERE / 'replace-pairs-ctx.jsonl'
OUT = HERE / 'rewrite-rank-summary.json'


def char_f1(a, b):
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    p = common / max(1, len(a)); r = common / max(1, len(b))
    return 2 * p * r / (p + r)


def grams(text, n=2):
    text = text.replace(' ', '')
    return {text[i:i + n] for i in range(max(0, len(text) - n + 1))} or {text}


def cosine(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))


def main():
    pairs = [json.loads(l) for l in PAIRS.read_text(encoding='utf8').splitlines() if l.strip()]
    ids = sorted({p['id'] for p in pairs})
    hold = set(ids[len(ids) * 4 // 5:])
    train = [p for p in pairs if p['id'] not in hold]
    test = [p for p in pairs if p['id'] in hold]

    by_src = defaultdict(list)
    for p in train:
        by_src[p['src']].append(p)
    overall = Counter(p['dst'] for p in train)
    default_dst = overall.most_common(1)[0][0] if overall else ''

    def context(p):
        return grams(p['clause'] + '|' + p['prev'])

    cache = {}

    def ctx_of(p):
        key = (p['src'], p['dst'], p['clause'], p['prev'])
        if key not in cache:
            cache[key] = context(p)
        return cache[key]
    def feats(p, cand):
        ctx = ctx_of(p)
        cctx = ctx_of(cand)
        cand_counts = Counter(c['dst'] for c in by_src.get(p['src'], []))
        return np.array([
            1.0,
            math.log1p(cand_counts[cand['dst']]),
            cosine(ctx, cctx),
            len(cand['dst']) / 8.0,
            abs(len(cand['dst']) - len(p['src'])) / 8.0,
            1.0 if cand['prev'] else 0.0,
            1.0 if cand['sent'] == p['sent'] else 0.0,
            cosine(grams(cand['dst']), grams(p['clause'])),
            cosine(grams(cand['dst']), grams(p['prev'])) if p['prev'] else 0.0,
            cosine(grams(cand['clause']), grams(p['clause'])),
        ])

    rng = np.random.default_rng(20261128)
    X, y = [], []
    for p in train:
        cands = [c for c in by_src.get(p['src'], []) if not (c['clause'] == p['clause'] and c['dst'] == p['dst'])]
        if not cands:
            continue
        picked = cands if len(cands) <= 8 else list(rng.choice(cands, 8, replace=False))
        for c in picked:
            X.append(feats(p, c)); y.append(1.0 if c['dst'] == p['dst'] else 0.0)
    X = np.array(X); y = np.array(y)
    mu, sd = X.mean(0), X.std(0) + 1e-6
    Xs = (X - mu) / sd
    w = np.zeros(X.shape[1])
    for _ in range(3000):
        p_hat = 1 / (1 + np.exp(-Xs @ w))
        w -= 2.0 * (Xs.T @ (p_hat - y)) / max(1, len(y)) + 0.001 * w

    results = {}
    for name in ('copy', 'freq', 'ctx', 'rank'):
        exact, f1, covered = 0, 0.0, 0
        for p in test:
            cands = by_src.get(p['src'], [])
            if name == 'copy':
                pred = p['src']
            elif not cands:
                pred = default_dst
            elif name == 'freq':
                pred = Counter(c['dst'] for c in cands).most_common(1)[0][0]
            else:
                covered += 1
                best, best_score = None, -1e9
                for c in cands:
                    score = cosine(context(p), ctx_of(c)) if name == 'ctx' else float(((feats(p, c) - mu) / sd) @ w)
                    if score > best_score:
                        best, best_score = c, score
                pred = best['dst'] if best else default_dst
            exact += int(pred == p['dst'])
            f1 += char_f1(pred, p['dst'])
        results[name] = {'exact': round(exact / len(test), 3), 'charF1': round(f1 / len(test), 3)}
    results['pairs'] = {'train': len(train), 'test': len(test), 'passages': len(ids)}
    results['coverage'] = round(sum(1 for p in test if p['src'] in by_src) / len(test), 3)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
