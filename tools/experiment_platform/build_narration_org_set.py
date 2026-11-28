#!/usr/bin/env python3
"""Build a narration content-selection / sentence-organization eval set.

Input: the independent 162-point narration holdout (fact blocks absent from the
corpus and the 161-point dev bundle). Selection labels are split by kind:

- mustSelect: this turn's settlement result events (turn-specific).
- optional: static world/item/character descriptors (not required to appear).
- avoidRepeat: optional facts already stated in earlier prose of the same run.

Split is by source run file, not by case id, so one run's points stay together.
Each case also carries negative fixtures derived from its own facts: wrong
attribution, lost negation, and reversed event order. Dev/test overlap is
reported instead of assumed away.

  python -m tools.experiment_platform.build_narration_org_set
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.experiment_platform.build_narration_holdout import result_lines  # noqa: E402
from tools.experiment_platform.narration_metrics import (  # noqa: E402
    NEG, bigrams, clauses, coverage, parse_result,
)

SRC = ROOT / 'artifacts/goal/platform/eval/narration-holdout-v1.jsonl'
OUT_DIR = ROOT / 'artifacts/goal/platform/eval'
NEG_REPLACE = [('没有', '有'), ('没能', '已'), ('无法', '可以'), ('未能', '已'), ('未', '已'), ('不', '')]


def run_key(case: dict) -> str:
    return (case.get('source') or {}).get('evidence') or case['id'].split(':')[1]


def split_runs(rows: list[dict]) -> set[str]:
    counts = Counter(run_key(r) for r in rows)
    order = sorted(counts, key=lambda r: hashlib.sha1(r.encode('utf-8')).hexdigest())
    dev, total, target = set(), 0, round(len(rows) * 0.2)
    for run in order:
        if total >= target:
            break
        dev.add(run)
        total += counts[run]
    return dev


def prior_prose(rows: list[dict]) -> dict[str, list[list[str]]]:
    """Per case id, bigram sets of prose that appeared earlier in the same run."""
    docs: dict[str, list[dict]] = {}
    index: dict[tuple, list[dict]] = {}
    for row in rows:
        rel = run_key(row)
        if rel not in docs:
            try:
                doc = json.loads((ROOT / rel).read_text(encoding='utf-8-sig'))
            except (OSError, json.JSONDecodeError):
                doc = {}
            seq, by = [], {}
            for ti, turn in enumerate(doc.get('turns') or []):
                product = turn.get('product') or {}
                narration = product.get('narration') or {}
                if narration.get('text'):
                    entry = {'pos': (ti, -1), 'text': narration['text']}
                    seq.append(entry)
                    by[('narration', turn.get('id'), narration.get('pointId') or turn.get('id'))] = entry
                for pi, item in enumerate(product.get('pointPrompts') or []):
                    if isinstance(item, dict) and item.get('text'):
                        entry = {'pos': (ti, pi), 'text': item['text']}
                        seq.append(entry)
                        by[('point', turn.get('id'), item.get('pointId') or turn.get('id'))] = entry
            docs[rel] = seq
            index[rel] = by
        source = row.get('source') or {}
        entry = (index.get(rel) or {}).get((source.get('kind'), source.get('turnId'), source.get('pointId')))
        docs.setdefault(row['id'], []).append(
            [bigrams(e['text']) for e in docs[rel] if entry is not None and e['pos'] < entry['pos']])
    return {k: v[0] if v else [] for k, v in docs.items() if isinstance(k, str) and k.startswith('nar-holdout:')}


def events_of(case: dict) -> list[dict]:
    out = []
    for line in case['input']['resultLines']:
        parsed = parse_result(line)
        if parsed and len(parsed['action']) >= 3:
            out.append(parsed)
    return out


def negatives(events: list[dict], optional: list[str]) -> list[dict]:
    out = []
    for i, left in enumerate(events):
        for right in events[i + 1:]:
            if (left['actor'] != right['actor'] and left['actor'] not in left['action']
                    and left['actor'] not in right['action']):
                out.append({'type': 'wrongAttribution',
                            'text': right['actor'] + left['action'] + '。'})
                break
        if out:
            break
    for fact in optional:
        if not NEG.search(fact):
            continue
        changed = fact
        for old, new in NEG_REPLACE:
            changed = changed.replace(old, new)
        if len(changed) > 4 and coverage(fact, bigrams(changed)) >= 0.5 and not NEG.search(changed):
            out.append({'type': 'negationLost', 'text': changed + '。'})
            break
    for i, left in enumerate(events):
        for right in events[i + 1:]:
            if left['action'] != right['action'] and coverage(left['action'], bigrams(right['action'])) < 0.5:
                out.append({'type': 'wrongOrder', 'text': right['action'] + '。' + left['action'] + '。'})
                break
        if any(n['type'] == 'wrongOrder' for n in out):
            break
    return out


def build(case: dict, dev_runs: set[str], prior: dict[str, list[list[str]]]) -> dict:
    events = events_of(case)
    must = [e['action'] for e in events]
    optional = case['expected']['facts']
    prior_grams = prior.get(case['id']) or []
    avoid = [c for c in optional if any(coverage(c, grams) >= 0.5 for grams in prior_grams)]
    order = [[a['action'], b['action']] for a, b in zip(events, events[1:]) if a['action'] != b['action']]
    split = 'dev' if run_key(case) in dev_runs else 'test'
    return {
        'id': case['id'], 'modality': 'narration', 'world': case['world'], 'split': split,
        'input': case['input'],
        'expected': {'facts': optional, 'mustSelect': must, 'mustEvents': events,
                     'optional': optional, 'avoidRepeat': avoid, 'outcomes': case['expected']['outcomes'],
                     'order': order, 'negatives': negatives(events, optional)},
        'selectionApplicable': bool(must),
        'constraints': {'maxSameHeadPairs': 0, 'maxInventedNames': 0, 'maxRepeated8Gram': 0.02,
                        'requireOutcomeCue': True, 'maxAttributionMismatches': 0, 'maxNegationLost': 0},
        'forbidden': case.get('forbidden') or {},
        'provenance': {'labelSource': 'settlement result lines (events) + static fact clauses (optional)',
                       'avoidRepeatSource': 'earlier prose in the same run file',
                       'splitBasis': 'source run file, sha1 order until ~20% of cases',
                       'humanVerified': False,
                       'note': 'selection metrics apply only when selectionApplicable; negatives are derived fixtures'},
    }


def overlap(built: list[dict], split: str) -> dict:
    dev = [c for c in built if c['split'] == 'dev']
    test = [c for c in built if c['split'] == split]
    dev_events = [e for c in dev for e in c['expected']['mustSelect']]
    test_events = [e for c in test for e in c['expected']['mustSelect']]
    exact = sum(1 for e in test_events if e in set(dev_events))
    viewed = sum(1 for e in test_events if any(coverage(e, bigrams(d)) >= 0.5 for d in dev_events))
    return {'testEvents': len(test_events), 'exactInDev': exact, 'bigramHalfInDev': viewed,
            'devEvents': len(dev_events)}


def write_set(rows: list[dict], path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    canon = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode('utf-8')).hexdigest()
    manifest = {'schema': 'jity-eval-set/1', 'path': path.relative_to(ROOT).as_posix(),
                'rows': len(rows), 'sha256': canon, 'hashMode': 'canonical-json'}
    path.with_suffix('.jsonl.manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--src', default=str(SRC))
    parser.add_argument('--out-dir', default=str(OUT_DIR))
    args = parser.parse_args(argv)
    cases = [json.loads(ln) for ln in Path(args.src).read_text(encoding='utf-8-sig').splitlines() if ln.strip()]
    dev_runs = split_runs(cases)
    prior = prior_prose(cases)
    built = [build(case, dev_runs, prior) for case in cases]
    dev = [c for c in built if c['split'] == 'dev']
    test = [c for c in built if c['split'] == 'test']
    out = Path(args.out_dir)
    manifests = {'dev': write_set(dev, out / 'narration-selection-org-v1.dev.jsonl'),
                 'test': write_set(test, out / 'narration-selection-org-v1.test.jsonl')}
    kinds = Counter(n['type'] for c in built for n in c['expected']['negatives'])
    summary = {'schema': 'jity-narration-org/2',
               'source': Path(args.src).resolve().relative_to(ROOT).as_posix(), 'cases': len(built),
               'dev': len(dev), 'test': len(test), 'devRuns': len(dev_runs),
               'eventsApplicable': sum(c['selectionApplicable'] for c in built),
               'avgMustSelect': round(sum(len(c['expected']['mustSelect']) for c in built) / max(1, len(built)), 2),
               'avgOptional': round(sum(len(c['expected']['optional']) for c in built) / max(1, len(built)), 1),
               'avgAvoidRepeat': round(sum(len(c['expected']['avoidRepeat']) for c in built) / max(1, len(built)), 2),
               'casesWithAvoidRepeat': sum(bool(c['expected']['avoidRepeat']) for c in built),
               'negatives': dict(kinds), 'testOverlapVsDev': overlap(built, 'test'),
               'manifests': manifests}
    (out / 'narration-selection-org-v1.summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
