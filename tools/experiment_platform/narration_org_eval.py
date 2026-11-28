#!/usr/bin/env python3
"""Score narration content selection and sentence organization.

Predictions JSONL: {"id": "...", "text": "..."}. Metrics per set:
event-clause selection, optional/avoid-repeat coverage, correct attribution,
negation retention, adjacent same-subject sentences, invented names/numbers,
8-gram repetition, and event-order violations. The set's own negative fixtures
are scored too, so a metric that cannot catch its intended error is visible.

  python -m tools.experiment_platform.narration_org_eval \
    --set artifacts/goal/platform/eval/narration-selection-org-v1.test.jsonl \
    --predictions preds.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.experiment_platform.narration_metrics import (  # noqa: E402
    FAIL_CUE, NAMES, NEG, NUM, PART_CUE, bigrams, coverage, parse_result,
    repetition, sentences,
)


def first_index(clause: str, sents: list[str]) -> int | None:
    best, best_ov = None, 0.0
    for index, sent in enumerate(sents):
        ov = coverage(clause, bigrams(sent))
        if ov > best_ov:
            best, best_ov = index, ov
    return best if best_ov >= 0.5 else None


def evaluate(case: dict, text: str) -> dict:
    expected = case['expected']
    must = expected.get('mustSelect') or expected.get('facts') or []
    optional = expected.get('optional') or []
    avoid = expected.get('avoidRepeat') or []
    sents = sentences(text)
    selected = [c for c in must if coverage(c, bigrams(text)) >= 0.5]
    optional_selected = [c for c in optional if coverage(c, bigrams(text)) >= 0.5]
    avoid_hit = [c for c in avoid if coverage(c, bigrams(text)) >= 0.5]
    events = expected.get('mustEvents')
    if events is None:
        events = [p for p in (parse_result(x) for x in case['input'].get('resultLines') or []) if p]
    fact_text = case['input']['factsText'] + ' '.join(case['input'].get('resultLines') or [])
    invented_names = [n for n in NAMES if n in text and n not in fact_text]
    invented_nums = sorted(set(NUM.findall(text)) - set(NUM.findall(fact_text)))
    heads = []
    for sent in sents:
        head = next((n for n in sorted(NAMES, key=len, reverse=True) if sent.startswith(n)), '')
        heads.append(head)
    same_head = sum(1 for a, b in zip(heads, heads[1:]) if a and a == b)
    attribution_total = attribution_mismatch = 0
    for event in events:
        action = event.get('action') or ''
        if len(action) < 2:
            continue
        index = first_index(action, sents)
        if index is None:
            continue
        attribution_total += 1
        sent = sents[index]
        if event.get('actor') and event['actor'] not in sent and any(n in sent for n in NAMES):
            attribution_mismatch += 1
    neg_total = neg_lost = 0
    for fact in optional:
        if not NEG.search(fact):
            continue
        index = first_index(fact, sents)
        if index is None:
            continue
        neg_total += 1
        if not NEG.search(sents[index]):
            neg_lost += 1
    outcomes = [r for r in (parse_result(x) for x in case['input'].get('resultLines') or []) if r and r['outcome']]
    out_total = out_hit = 0
    for res in outcomes:
        cue = FAIL_CUE if res['outcome'] in ('没有成功', '无法完成', '失败') else (
            PART_CUE if res['outcome'] in ('只完成一部分', '部分成功') else None)
        if not cue:
            continue
        out_total += 1
        if any(cue.search(s) for s in sents if res['actor'] in s):
            out_hit += 1
    order_violations = 0
    for left, right in expected.get('order') or []:
        li, ri = first_index(left, sents), first_index(right, sents)
        if li is None or ri is None or li == ri:
            continue
        if ri < li:
            order_violations += 1
    return {
        'id': case['id'], 'mustSelect': len(must), 'selected': len(selected),
        'selectionRate': round(len(selected) / max(1, len(must)), 3),
        'optional': len(optional), 'optionalSelected': len(optional_selected),
        'avoidRepeat': len(avoid), 'avoidRepeatHit': len(avoid_hit),
        'attributionTotal': attribution_total, 'attributionMismatches': attribution_mismatch,
        'negationTotal': neg_total, 'negationLost': neg_lost,
        'outcomeTotal': out_total, 'outcomeHit': out_hit,
        'inventedNames': len(invented_names), 'inventedNums': len(invented_nums),
        'sameHeadPairs': same_head, 'repetition8': repetition(text, 8),
        'orderViolations': order_violations, 'chars': len(text), 'sentences': len(sents),
    }


def calibrate(case: dict) -> list[dict]:
    checks = {'wrongAttribution': 'attributionMismatches',
              'negationLost': 'negationLost', 'wrongOrder': 'orderViolations'}
    rows = []
    for negative in case['expected'].get('negatives') or []:
        kind = negative['type']
        row = evaluate(case, negative['text'])
        rows.append({'id': case['id'], 'type': kind, 'detected': row.get(checks[kind], 0) > 0})
    return rows


def summarize(rows: list[dict], calibration: list[dict]) -> dict:
    if not rows:
        return {}
    event_rows = [r for r in rows if r['mustSelect']]
    detection = {}
    for kind in ('wrongAttribution', 'negationLost', 'wrongOrder'):
        items = [c for c in calibration if c['type'] == kind]
        detection[kind] = {'generated': len(items), 'detected': sum(c['detected'] for c in items)}
    return {
        'cases': len(rows),
        'selectionCases': len(event_rows),
        'selectionRate': round(sum(r['selected'] for r in event_rows) / max(1, sum(r['mustSelect'] for r in event_rows)), 3),
        'optionalRate': round(sum(r['optionalSelected'] for r in rows) / max(1, sum(r['optional'] for r in rows)), 3),
        'avoidRepeatRate': round(sum(r['avoidRepeatHit'] for r in rows) / max(1, sum(r['avoidRepeat'] for r in rows)), 3),
        'attributionMismatches': sum(r['attributionMismatches'] for r in rows),
        'negationLost': sum(r['negationLost'] for r in rows),
        'outcomeRate': round(sum(r['outcomeHit'] for r in rows) / max(1, sum(r['outcomeTotal'] for r in rows)), 3),
        'inventedNames': sum(r['inventedNames'] for r in rows),
        'inventedNums': sum(r['inventedNums'] for r in rows),
        'sameHeadPairs': sum(r['sameHeadPairs'] for r in rows),
        'repetition8Mean': round(statistics.mean([r['repetition8'] for r in rows]), 3),
        'orderViolations': sum(r['orderViolations'] for r in rows),
        'charsPerCase': round(statistics.mean([r['chars'] for r in rows]), 1),
        'sentencesPerCase': round(statistics.mean([r['sentences'] for r in rows]), 1),
        'negativeDetection': detection,
        'negativeMisses': [c for c in calibration if not c['detected']],
        'worstCases': sorted(event_rows, key=lambda r: (r['selectionRate'], -r['orderViolations']))[:10],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--set', required=True)
    parser.add_argument('--predictions', required=True)
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    cases = [json.loads(ln) for ln in Path(args.set).read_text(encoding='utf-8-sig').splitlines() if ln.strip()]
    preds = {row['id']: row.get('text', '') for row in
             (json.loads(ln) for ln in Path(args.predictions).read_text(encoding='utf-8-sig').splitlines() if ln.strip())}
    rows = [evaluate(case, preds.get(case['id'], '')) for case in cases]
    calibration = [item for case in cases for item in calibrate(case)]
    report = summarize(rows, calibration)
    report['missing'] = [case['id'] for case in cases if case['id'] not in preds]
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'worstCases'}, ensure_ascii=False, indent=1))
    return 1 if report['missing'] else 0


if __name__ == '__main__':
    sys.exit(main())
