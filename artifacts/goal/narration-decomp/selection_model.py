# -*- coding: utf-8 -*-
"""Planning step 1: per-clause 'does this fact enter the prose' classifier.

0.1M-class model (hashed char n-grams + type/index features, logistic
regression). Grouped CV by identical-facts hash so no fact set leaks across
folds. Reports selection F1 and the E31 reconstruction score it achieves
with the fixed type order."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold

HERE = Path(__file__).resolve().parent
PLAN = HERE / 'planning-examples-v2.jsonl'
RANK = {'player_action': 0, 'location_state': 1, 'actor_result': 2, 'scene': 3, 'appearance': 4, 'time': 5}
TYPES = list(RANK)


def char_ngrams(text: str, n: int = 2):
    clean = re.sub(r'\s', '', text)
    return [clean[i:i+n] for i in range(max(1, len(clean) - n + 1))]


def features(clause: str, kind: str, index: int, total: int, length: int):
    grams = char_ngrams(clause)
    return {**{f'g:{g}': 1.0 for g in grams},
            **{f't:{kind}': 1.0, 'idx': index / max(1, total - 1), 'len': length / 50.0,
               'first': 1.0 if index == 0 else 0.0}}


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[一-龥]{1,4}[：:]', '', body)
    return body.strip()


def char_f1(a: str, b: str) -> float:
    ca, cb = Counter(a), Counter(b)
    common = sum((ca & cb).values())
    if not common:
        return 0.0
    precision = common / max(1, len(a))
    recall = common / max(1, len(b))
    return 2 * precision * recall / (precision + recall)


def main():
    rows = [json.loads(l) for l in PLAN.read_text(encoding='utf8').splitlines() if l.strip()]
    X_rows, y, groups, meta = [], [], [], []
    for row in rows:
        clauses = row['clauses']
        facts_key = hashlib.sha256('|'.join(clauses).encode('utf8')).hexdigest()[:12]
        for index, clause in enumerate(clauses):
            X_rows.append(features(clause, row['types'][index], index, len(clauses), len(clause)))
            y.append(1 if index in row['selected'] else 0)
            groups.append(facts_key)
            meta.append((row['id'], index))
    hasher = FeatureHasher(n_features=2 ** 16, input_type='dict')
    X = hasher.transform(X_rows)
    y = np.array(y)
    groups = np.array(groups)
    f1s, f1s_oracle = [], []
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=20261128)
    selected_by_id = {}
    from sklearn.metrics import f1_score
    for train_idx, test_idx in cv.split(X, y, groups):
        model = LogisticRegression(C=1.0, max_iter=400, solver='liblinear')
        model.fit(X[train_idx], y[train_idx])
        pred = model.predict(X[test_idx])
        f1s.append(f1_score(y[test_idx], pred))
        for position, pred_value in zip(test_idx, pred):
            rid, index = meta[position]
            selected_by_id.setdefault(rid, []).append((index, int(pred_value)))
    # reconstruction with the model's selection and the fixed type order
    plans = {row['id']: row for row in rows}
    scores = []
    for rid, picks in selected_by_id.items():
        plan = plans[rid]
        chosen = sorted((i for i, keep in picks if keep), key=lambda i: (RANK.get(plan['types'][i], 3), i))
        if not chosen:
            continue
        text = '。'.join(strip_prefix(plan['clauses'][i]) for i in chosen)
        # target text is not stored in the plan file; approximate with the clause-set F1 vs facts-free target is not available here
        scores.append(len(chosen) / max(1, len(plan['clauses'])))
    # targets for reconstruction scoring
    target_by_id = {}
    src = Path('D:/others/Jity/.local/narr-train/sft-v13.jsonl')
    for line in src.read_text(encoding='utf8').splitlines():
        if line.strip():
            row = json.loads(line)
            target_by_id[str(row['id'])] = row['target']
    recon = []
    for rid, picks in selected_by_id.items():
        plan = plans[rid]
        target = target_by_id.get(rid)
        if not target:
            continue
        chosen = sorted((i for i, keep in picks if keep), key=lambda i: (RANK.get(plan['types'][i], 3), i))
        if not chosen:
            continue
        text = '。'.join(strip_prefix(plan['clauses'][i]) for i in chosen)
        recon.append(char_f1(text, target))
    # type-prior baseline: per-type majority, evaluated on the same labels
    type_rate = {}
    for row in rows:
        for index, clause in enumerate(row['clauses']):
            kind = row['types'][index]
            total, used = type_rate.get(kind, (0, 0))
            type_rate[kind] = (total + 1, used + (1 if index in row['selected'] else 0))
    pred = []
    for row in rows:
        for index in range(len(row['clauses'])):
            total, used = type_rate[row['types'][index]]
            pred.append(1 if used / max(1, total) >= 0.5 else 0)
    from sklearn.metrics import f1_score as f1_metric
    summary = {
        'clauses': int(len(y)),
        'positives': int(y.sum()),
        'cvF1Mean': round(float(np.mean(f1s)), 3),
        'cvF1Sd': round(float(np.std(f1s)), 3),
        'modelSelectionRate': round(float(np.mean(scores)), 3) if scores else None,
        'baselineSelectionRate': round(float(y.mean()), 3),
        'typePriorF1': round(float(f1_metric(y, pred)), 3),
        'reconstructionCharF1Mean': round(float(np.mean(recon)), 3) if recon else None,
    }
    (HERE / 'selection-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
