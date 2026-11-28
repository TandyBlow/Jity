#!/usr/bin/env python3
"""Score a task-verdict arm on the platform task gold.

Predictions JSONL: {"id": "...", "verdict": "yes|partial|no|not_triggered"}.
Commit rule: only `yes` commits the task. `not_triggered` means the goal's
condition never fired and must not be counted as a negative.

Reports exact accuracy, commit accuracy, yes precision/recall, confusion, and
the false-commit list (expected not-yes but predicted yes).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

LABELS = ('yes', 'partial', 'no', 'not_triggered')


def score(cases: list[dict], predictions: dict[str, str], field: str = 'verdict') -> dict:
    rows, missing, missing_labels = [], [], []
    for case in cases:
        pred = predictions.get(case['id'])
        expected = case.get(field)
        if pred is None:
            missing.append(case['id'])
            continue
        if expected is None:
            missing_labels.append(case['id'])
            continue
        rows.append({'id': case['id'], 'taskId': case.get('taskId'), 'expected': expected,
                     'predicted': pred, 'exact': pred == expected,
                     'commitExpected': expected == 'yes', 'commitPredicted': pred == 'yes'})
    total = max(1, len(rows))
    confusion = Counter((r['expected'], r['predicted']) for r in rows)
    per_task = defaultdict(lambda: {'n': 0, 'exact': 0, 'commit': 0})
    for row in rows:
        bucket = per_task[row['taskId']]
        bucket['n'] += 1
        bucket['exact'] += int(row['exact'])
        bucket['commit'] += int(row['commitExpected'] == row['commitPredicted'])
    tp = sum(1 for r in rows if r['commitExpected'] and r['commitPredicted'])
    fp = sum(1 for r in rows if not r['commitExpected'] and r['commitPredicted'])
    fn = sum(1 for r in rows if r['commitExpected'] and not r['commitPredicted'])
    tn = sum(1 for r in rows if not r['commitExpected'] and not r['commitPredicted'])
    return {
        'cases': len(rows), 'missing': missing, 'missingLabels': missing_labels, 'labelField': field,
        'accuracy': round(sum(int(r['exact']) for r in rows) / total, 3),
        'commitAccuracy': round((tp + tn) / total, 3),
        'yesPrecision': round(tp / max(1, tp + fp), 3),
        'yesRecall': round(tp / max(1, tp + fn), 3),
        'confusion': {f'{a}|{b}': n for (a, b), n in sorted(confusion.items())},
        'falseCommits': [r['id'] for r in rows if not r['commitExpected'] and r['commitPredicted']],
        'missedCommits': [r['id'] for r in rows if r['commitExpected'] and not r['commitPredicted']],
        'byTask': {k: {**v, 'accuracy': round(v['exact'] / max(1, v['n']), 3),
                        'commitAccuracy': round(v['commit'] / max(1, v['n']), 3)}
                   for k, v in sorted(per_task.items())},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--cases', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--field', default='verdict',
                        help='case label field, e.g. verdict (support) or completionVerdict')
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    cases = [json.loads(ln) for ln in Path(args.cases).read_text(encoding='utf-8-sig').splitlines() if ln.strip()]
    predictions = {}
    for line in Path(args.predictions).read_text(encoding='utf-8-sig').splitlines():
        if line.strip():
            row = json.loads(line)
            predictions[row['id']] = row['verdict']
    report = score(cases, predictions, args.field)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(text)
    return 1 if report['missing'] else 0


if __name__ == '__main__':
    sys.exit(main())
