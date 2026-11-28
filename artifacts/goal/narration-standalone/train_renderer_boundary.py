# -*- coding: utf-8 -*-
"""N10 probe: can a small model learn where the reference starts a new
sentence, from fragment pairs? Grouped by evidence file; baselines included."""
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

HERE = Path(__file__).resolve().parent
HASH_DIM = 1 << 12
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
    if pair['kindB'] == 'result':
        out.append('bresult')
    if pair['kindA'] == 'result':
        out.append('aresult')
    return out


def main():
    data = json.load(open(HERE / 'renderer-dataset.json', encoding='utf8'))
    rows = []
    for point in data:
        for pair in point['pairs']:
            rows.append({**pair, 'evidence': point['evidence']})
    groups = sorted({row['evidence'] for row in rows})
    print('pairs', len(rows), 'groups', len(groups), 'boundaryRate',
          round(sum(r['boundary'] for r in rows) / len(rows), 3))

    hasher = FeatureHasher(n_features=HASH_DIM, input_type='string', alternate_sign=False)
    X = hasher.transform([features(r) for r in rows])
    y = np.array([r['boundary'] for r in rows])
    group = np.array([r['evidence'] for r in rows])

    preds = np.zeros(len(rows), dtype=int)
    for g in groups:
        test = group == g
        train = ~test
        if train.sum() < 20 or test.sum() == 0:
            preds[test] = 1
            continue
        model = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced')
        model.fit(X[train], y[train])
        preds[test] = model.predict(X[test])

    majority = np.ones(len(rows), dtype=int)  # 规则现状：每条片段都另起一句
    print('always-boundary acc', round(accuracy_score(y, majority), 3),
          'f1', round(f1_score(y, majority, zero_division=0), 3))
    print('model acc', round(accuracy_score(y, preds), 3),
          'f1', round(f1_score(y, preds, zero_division=0), 3),
          'joinPred', int((preds == 0).sum()), 'joinTrue', int((y == 0).sum()))
    print('confusion', Counter(zip(y.tolist(), preds.tolist())))
    # 每个 point 的句数对比：参考句数 vs 模型边界重建
    per_point = []
    for point in data:
        if not point['pairs']:
            continue
        idx = [i for i, r in enumerate(rows) if r['evidence'] == point['evidence'] and r['textA'] == point['pairs'][0]['textA']]
        boundaries = sum(preds[i] for i in idx) if idx else 0
        per_point.append((point['sentences'], boundaries + 1))
    if per_point:
        ref = np.mean([p[0] for p in per_point])
        got = np.mean([p[1] for p in per_point])
        print('sentences per point: ref', round(ref, 2), 'model', round(got, 2))
    # 在全部相邻片段上推理（不要求对得上参考），看每 point 句数
    model = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced')
    model.fit(X, y)
    import renderer_dataset as rd
    pts = [json.loads(l) for l in open(HERE / 'pairs.jsonl', encoding='utf8').readlines() if l.strip()]
    full_sentences = []
    for row in pts:
        frags = rd.fragments(row)
        if len(frags) < 2:
            continue
        pairs = [{'textA': a[1], 'kindA': a[0], 'textB': b[1], 'kindB': b[0]} for a, b in zip(frags, frags[1:])]
        pred = model.predict(hasher.transform([features(p) for p in pairs]))
        full_sentences.append(int(pred.sum()) + 1)
    print('full fragments -> sentences per point: rule', round(sum(len(rd.fragments(r)) for r in pts) / len(pts), 2),
          'model', round(sum(full_sentences) / len(full_sentences), 2))
    samples = []
    for row in pts[:2]:
        frags = rd.fragments(row)
        pairs = [{'textA': a[1], 'kindA': a[0], 'textB': b[1], 'kindB': b[0]} for a, b in zip(frags, frags[1:])]
        pred = model.predict(hasher.transform([features(p) for p in pairs])) if pairs else []
        text = frags[0][1] if frags else ''
        for p, (kind, frag) in zip(pred, frags[1:]):
            text += ('。' if p else '，') + frag
        samples.append({'id': row['id'], 'text': text + '。'})
        print('---', row['id'])
        print(text[:260])
    out = {
        'pairs': len(rows), 'groups': len(groups),
        'fullSentencesRule': round(sum(len(rd.fragments(r)) for r in pts) / len(pts), 2),
        'fullSentencesModel': round(sum(full_sentences) / len(full_sentences), 2),
        'alwaysBoundary': {'acc': round(accuracy_score(y, majority), 3),
                           'f1': round(f1_score(y, majority, zero_division=0), 3)},
        'model': {'acc': round(accuracy_score(y, preds), 3),
                  'f1': round(f1_score(y, preds, zero_division=0), 3),
                  'joinPred': int((preds == 0).sum()), 'joinTrue': int((y == 0).sum())},
        'confusion': {f'{a}->{b}': v for (a, b), v in Counter(zip(y.tolist(), preds.tolist())).items()},
        'samples': samples,
    }
    (HERE / 'renderer-boundary-summary.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
