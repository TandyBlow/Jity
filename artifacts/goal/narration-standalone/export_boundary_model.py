# -*- coding: utf-8 -*-
"""Export the N10 boundary model as a plain hashed-weight asset and check that
a dependency-free scorer reproduces sklearn's decision."""
import json
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression

import renderer_dataset as rd
from train_renderer_boundary import HASH_DIM, features

HERE = Path(__file__).resolve().parent


def main():
    data = json.load(open(HERE / 'renderer-dataset.json', encoding='utf8'))
    rows = [pair for point in data for pair in point['pairs']]
    hasher = FeatureHasher(n_features=HASH_DIM, input_type='string', alternate_sign=False)
    X = hasher.transform([features(p) for p in rows])
    y = np.array([p['boundary'] for p in rows])
    model = LogisticRegression(max_iter=2000, C=0.5, class_weight='balanced').fit(X, y)
    weights = np.zeros(HASH_DIM, dtype=np.float32)
    for idx, value in zip(model.coef_[0].nonzero()[0], model.coef_[0][model.coef_[0].nonzero()[0]]):
        weights[idx] = value
    asset = {
        'version': 'n10-boundary-v1',
        'hashDim': HASH_DIM,
        'intercept': float(model.intercept_[0]),
        'weights': [round(float(w), 6) for w in weights],
        'features': 'char bigrams of A and B (40 each), prev/next (20 each), kind, name/place flags',
        'trainedPairs': len(rows),
    }
    out = HERE / 'renderer-boundary-model.json'
    out.write_text(json.dumps(asset), encoding='utf8')

    # 独立复算：只用导出权重，按 same hashing 规则打分。
    from sklearn.utils import murmurhash3_32

    def bucket(feature):
        return abs(murmurhash3_32(feature)) % HASH_DIM

    def score(pair):
        ids = {}
        for feature in features(pair):
            idx = bucket(feature)
            ids[idx] = ids.get(idx, 0) + 1
        total = asset['intercept']
        for idx, count in ids.items():
            total += asset['weights'][idx] * count
        return 1 if total > 0 else 0

    agree = sum(1 for p in rows if score(p) == model.predict(hasher.transform([features(p)]))[0])
    print(json.dumps({
        'assetBytes': out.stat().st_size,
        'weightsNonZero': int((weights != 0).sum()),
        'parity': f'{agree}/{len(rows)}',
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
