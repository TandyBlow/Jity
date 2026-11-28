# -*- coding: utf-8 -*-
"""N12: apply the N10 boundary model to the rules renderer. Facts are grouped
by the model; every settlement result stays its own sentence. No fact is
dropped, so coverage stays 100% by construction."""
import json
import re
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression

import renderer_dataset as rd
from train_renderer_boundary import HASH_DIM, features, key_of

HERE = Path(__file__).resolve().parent
TIME = re.compile(r'^时间到了')


def load_model():
    data = json.load(open(HERE / 'renderer-dataset.json', encoding='utf8'))
    rows = []
    for point in data:
        for pair in point['pairs']:
            rows.append(pair)
    hasher = FeatureHasher(n_features=HASH_DIM, input_type='string', alternate_sign=False)
    X = hasher.transform([features(p) for p in rows])
    y = np.array([p['boundary'] for p in rows])
    model = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced').fit(X, y)
    return model, hasher


def pair_of(a, b, prev='', nxt=''):
    return {'textA': a, 'kindA': 'fact', 'textB': b, 'kindB': 'fact',
            'prev': prev, 'next': nxt}


def compose(row, model, hasher):
    frags = rd.fragments(row)
    action = [t for k, t in frags if k == 'action']
    results = [t for k, t in frags if k == 'result']
    facts = [t for k, t in frags if k == 'fact']
    time = next((p.strip() for p in re.split(r'[。；]', row['factsText']) if TIME.match(p.strip())), '')
    out = []
    if action:
        out.append(action[0])
    out.extend(results)
    # 事实按模型边界分组；同一句内用逗号，句间用句号。
    group = []
    for i, text in enumerate(facts):
        if not group:
            group.append(text)
            continue
        prev = facts[i - 2] if i >= 2 else ''
        nxt = facts[i + 1] if i + 1 < len(facts) else ''
        pred = model.predict(hasher.transform([features(pair_of(facts[i - 1], text, prev, nxt))]))[0]
        if pred == 1:
            out.append('，'.join(group))
            group = [text]
        else:
            group.append(text)
    if group:
        out.append('，'.join(group))
    text = '。'.join(out) + '。'
    if time:
        text += time + '。'
    return text, len(out) + (1 if time else 0)


def main():
    model, hasher = load_model()
    rows = [json.loads(l) for l in open(HERE / 'inputs.jsonl', encoding='utf8')]
    sentences, chars, missing = [], [], 0
    samples = []
    for row in rows:
        text, n = compose(row, model, hasher)
        sentences.append(n)
        chars.append(len(text))
        for kind, frag in rd.fragments(row):
            if frag not in text:
                missing += 1
        if len(samples) < 2 and any(k == 'result' for k, _ in rd.fragments(row)):
            samples.append({'id': row['id'], 'text': text})
    summary = {
        'points': len(rows),
        'fragments': sum(len(rd.fragments(r)) for r in rows),
        'missingFragments': missing,
        'sentencesPerPoint': round(sum(sentences) / len(sentences), 2),
        'charsPerPoint': round(sum(chars) / len(chars), 1),
        'samples': samples,
    }
    (HERE / 'renderer-prototype-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, ensure_ascii=False))
    for s in samples:
        print('---', s['id'])
        print(s['text'][:420])


if __name__ == '__main__':
    main()
