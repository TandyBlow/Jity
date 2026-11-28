#!/usr/bin/env python3
"""Score semantic predictions against the frozen probe sets.

Predictions JSONL: {"id": ..., "facts": ["信息=名称:分句", "环境=名称:分句"]}
Optional per-field status: {"id": ..., "info": {"status": "present", "content": "..."},
"env": {"status": "absent", "content": ""}}. When status is absent the status is
inferred from whether a matching fact is present.

Match rule: a predicted fact matches an expected clause when the content after
the entity is a superset/近 copy of any allowed clause (bigram coverage >= 0.5).
Reports status accuracy, content match, per-family and per-split results.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CJK = re.compile(r'[^一-鿿]')


def bigrams(text: str) -> set[str]:
    text = CJK.sub('', text or '')
    return {text[i:i + 2] for i in range(len(text) - 1)}


def coverage(expected: str, predicted: str) -> float:
    grams = bigrams(expected)
    return 1.0 if not grams else len(grams & bigrams(predicted)) / len(grams)


def infer_field(case: dict, predictions: dict, field: str, status_only: bool = False) -> dict:
    expected_status = (case['expected'].get('status') or {}).get(field)
    given = predictions.get(field)
    facts = predictions.get('facts') or []
    prefix = '信息' if field == 'info' else '环境'
    content = ''
    if isinstance(given, dict):
        status = given.get('status') or ('present' if given.get('content') else 'absent')
        content = given.get('content') or ''
    else:
        content = next((f.split(':', 1)[1] for f in facts if f.startswith(prefix + '=') and ':' in f), '')
        status = 'present' if content else 'absent'
    if expected_status is None:
        expected_status = 'present' if case['expected'].get('facts') else 'absent'
    allowed = case['expected'].get('anyOf') or []
    if not allowed:
        allowed = [f.split(':', 1)[1] for f in case['expected'].get('facts') or [] if ':' in f]
    if expected_status != 'present':
        content_ok = status == expected_status
    elif status != 'present':
        content_ok = False
    elif not content:
        content_ok = None if status_only else False
    else:
        content_ok = any(coverage(a, content) >= 0.5 for a in allowed)
    return {'expected': expected_status, 'predicted': status, 'content': content,
            'statusOk': status == expected_status, 'contentOk': content_ok}


def score(cases: list[dict], predictions: dict[str, dict], status_only: bool = False) -> dict:
    rows, missing = [], []
    for case in cases:
        pred = predictions.get(case['id'])
        if pred is None:
            missing.append(case['id'])
            continue
        fields = {field: infer_field(case, pred, field, status_only)
                  for field in (case['expected'].get('status') or {'info': 'present'}).keys()}
        rows.append({'id': case['id'], 'family': case.get('family', '?'),
                     'split': case.get('split', '?'), 'fields': fields})
    by_family = defaultdict(lambda: {'n': 0, 'statusOk': 0, 'contentOk': 0, 'contentN': 0})
    for row in rows:
        for field in row['fields'].values():
            bucket = by_family[row['family']]
            bucket['n'] += 1
            bucket['statusOk'] += int(field['statusOk'])
            if field['contentOk'] is not None:
                bucket['contentN'] += 1
                bucket['contentOk'] += int(field['contentOk'])
    total = sum(len(r['fields']) for r in rows)
    content_total = sum(1 for r in rows for f in r['fields'].values() if f['contentOk'] is not None)
    return {
        'cases': len(rows), 'fields': total, 'missing': missing,
        'statusAccuracy': round(sum(int(f['statusOk']) for r in rows for f in r['fields'].values()) / max(1, total), 3),
        'contentAccuracy': round(sum(int(f['contentOk']) for r in rows for f in r['fields'].values() if f['contentOk'] is not None) / max(1, content_total), 3),
        'contentEvaluated': content_total,
        'byFamily': {k: {**v, 'statusAccuracy': round(v['statusOk'] / max(1, v['n']), 3),
                          'contentAccuracy': round(v['contentOk'] / max(1, v['contentN']), 3)}
                     for k, v in sorted(by_family.items())},
        'bySplit': {split: {'cases': sum(1 for r in rows if r['split'] == split)}
                    for split in sorted({r['split'] for r in rows})},
        'failures': [r for r in rows if not all(f['statusOk'] and f['contentOk'] for f in r['fields'].values())][:20],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--set', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--status-only', action='store_true',
                        help='ignore content for present fields (status-only models)')
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    cases = [json.loads(ln) for ln in Path(args.set).read_text(encoding='utf-8-sig').splitlines() if ln.strip()]
    predictions = {row['id']: row for row in
                   (json.loads(ln) for ln in Path(args.predictions).read_text(encoding='utf-8-sig').splitlines() if ln.strip())}
    report = score(cases, predictions, args.status_only)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(text)
    return 1 if report['missing'] else 0


if __name__ == '__main__':
    sys.exit(main())
