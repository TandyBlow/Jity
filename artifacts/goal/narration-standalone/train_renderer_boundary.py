# -*- coding: utf-8 -*-
"""N10 (corrected): fragment pairs are highly duplicated across files, so the
evaluation groups by pair content, not by evidence file. Reports the label
conflict ceiling and performance on unseen pair contents."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

HERE = Path(__file__).resolve().parent
HASH_DIM = 1 << 12
FOLDS = 5
NAMES = ['路明非', '诺诺', '芬格尔', '秦越', '林亦舟', '楚子航', '凯撒', '顾岚', '唐骁', '夏弥', '绘梨衣',
         '曼施坦因', '苏茜', '沈澄', '周映', '富山雅史', '阿豹', '对方']


def grams(text):
    return [text[i:i + 2] for i in range(len(text) - 1)]


def features(pair):
    a, b = pair['textA'], pair['textB']
    out = [f'k:{pair["kindA"]}>{pair["kindB"]}', f'la:{min(len(a) // 8, 6)}', f'lb:{min(len(b) // 8, 6)}']
    out += ['ga:' + g for g in grams(a)[:40]]
    out += ['gb:' + g for g in grams(b)[:40]]
    if any(b.startswith(n) for n in NAMES):
        out.append('bname')
    if any(a.startswith(n) for n in NAMES):
        out.append('aname')
    if b.startswith('屋') or b.startswith('右') or b.startswith('左') or b.startswith('巷'):
        out.append('bplace')
    out += ['gp:' + g for g in grams(pair.get('prev', ''))[:20]]
    out += ['gn:' + g for g in grams(pair.get('next', ''))[:20]]
    if not pair.get('prev'):
        out.append('bos')
    if not pair.get('next'):
        out.append('eos')
    return out


def key_of(pair):
    return f"{pair['kindA']}|{pair['textA']}|{pair['kindB']}|{pair['textB']}|{pair.get('prev', '')}|{pair.get('next', '')}"


def fold_of(key):
    return int(hashlib.md5(key.encode('utf8')).hexdigest(), 16) % FOLDS


def main():
    data = json.load(open(HERE / 'renderer-dataset.json', encoding='utf8'))
    rows = []
    for point in data:
        for pair in point['pairs']:
            rows.append({**pair, 'evidence': point['evidence'], 'point': point['id'], 'key': key_of(pair)})
    groups = defaultdict(list)
    for r in rows:
        groups[r['key']].append(r)
    print('occurrences', len(rows), 'uniquePairs', len(groups))

    conflicts = {k: v for k, v in groups.items() if len({x['boundary'] for x in v}) > 1}
    print('unique with conflicting labels', len(conflicts))
    for k, v in list(conflicts.items())[:3]:
        print('  conflict', k[:70], Counter(x['boundary'] for x in v))

    # 只看见片段对内容时，最好情况是每个不同输入取多数标签。
    ceiling_hits = sum(max(Counter(x['boundary'] for x in v).values()) for v in groups.values())
    base_hits = sum(sum(x['boundary'] for x in v) for v in groups.values())
    print('label ceiling on occurrences', round(ceiling_hits / len(rows), 3))
    print('always-boundary on occurrences', round(base_hits / len(rows), 3))

    hasher = FeatureHasher(n_features=HASH_DIM, input_type='string', alternate_sign=False)
    X = hasher.transform([features(r) for r in rows])
    y = np.array([r['boundary'] for r in rows])
    folds = np.array([fold_of(r['key']) for r in rows])

    preds = np.zeros(len(rows), dtype=int)
    for f in range(FOLDS):
        test = folds == f
        train = ~test
        model = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced')
        model.fit(X[train], y[train])
        preds[test] = model.predict(X[test])
    unseen_acc = accuracy_score(y, preds)
    unseen_f1 = f1_score(y, preds, zero_division=0)
    first_idx = {k: rows.index(v[0]) for k, v in groups.items()}
    up_true = np.array([groups[k][0]['boundary'] for k in groups])
    up_pred = np.array([preds[first_idx[k]] for k in groups])
    print('unseen-content model acc', round(unseen_acc, 3), 'f1', round(unseen_f1, 3))
    print('per-unique-pair acc', round(accuracy_score(up_true, up_pred), 3),
          'n', len(groups), 'joinPred', int((preds == 0).sum()))

    # 句数：每个 point 的每一对都用“没见过该内容”的折模型预测。
    import renderer_dataset as rd
    pts = [json.loads(l) for l in open(HERE / 'pairs.jsonl', encoding='utf8').readlines() if l.strip()]
    models = {}
    for f in range(FOLDS):
        m = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced')
        m.fit(X[folds != f], y[folds != f])
        models[f] = m
    rule_sent, model_sent = [], []
    for row in pts:
        frags = rd.fragments(row)
        if len(frags) < 2:
            continue
        rule_sent.append(len(frags))
        total = 1
        for a, b in zip(frags, frags[1:]):
            pair = {'textA': a[1], 'kindA': a[0], 'textB': b[1], 'kindB': b[0]}
            f = fold_of(key_of(pair))
            total += int(models[f].predict(hasher.transform([features(pair)]))[0])
        model_sent.append(total)
    print('sentences per point: rule', round(sum(rule_sent) / len(rule_sent), 2),
          'model OOF', round(sum(model_sent) / len(model_sent), 2))

    out = {
        'occurrences': len(rows),
        'uniquePairs': len(groups),
        'conflictingUnique': len(conflicts),
        'ceilingOccurrences': round(ceiling_hits / len(rows), 3),
        'alwaysBoundaryOccurrences': round(base_hits / len(rows), 3),
        'unseenContentAcc': round(unseen_acc, 3),
        'unseenContentF1': round(unseen_f1, 3),
        'uniquePairAcc': round(accuracy_score(up_true, up_pred), 3),
        'sentencesRule': round(sum(rule_sent) / len(rule_sent), 2),
        'sentencesModelOOF': round(sum(model_sent) / len(model_sent), 2),
    }
    (HERE / 'renderer-boundary-summary.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(out, ensure_ascii=False))


if __name__ == '__main__':
    main()
