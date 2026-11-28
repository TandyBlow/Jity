#!/usr/bin/env python3
"""Build a narration content-selection / sentence-organization eval set.

Input: the independent 162-point narration holdout (facts not in the corpus or
the 161-point dev bundle). Each case records the fact clauses that must be
selected, the outcome labels, the fact order, and organization constraints:
no adjacent same-subject sentences, no invented names/numbers, bounded 8-gram
repetition. Dev/test split is deterministic by id hash.

  python -m tools.experiment_platform.build_narration_org_set
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'artifacts/goal/platform/eval/narration-holdout-v1.jsonl'
OUT_DIR = ROOT / 'artifacts/goal/platform/eval'


def build(case: dict) -> dict:
    facts = case['expected']['facts']
    outcomes = case['expected'].get('outcomes') or []
    order = [[a, b] for a, b in zip(facts, facts[1:])]
    split = 'dev' if int(hashlib.sha1(case['id'].encode('utf-8')).hexdigest()[:2], 16) % 5 == 0 else 'test'
    return {
        'id': case['id'], 'modality': 'narration', 'world': case['world'], 'split': split,
        'input': case['input'],
        'expected': {'facts': facts, 'mustSelect': facts, 'outcomes': outcomes, 'order': order},
        'constraints': {'maxSameHeadPairs': 0, 'maxInventedNames': 0,
                        'maxRepeated8Gram': 0.02, 'requireOutcomeCue': True},
        'forbidden': case.get('forbidden') or {},
        'provenance': {'labelSource': 'independent holdout facts/outcomes',
                       'note': 'selection and order derived from the fact block; organization constraints are advisory'},
    }


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
    built = [build(case) for case in cases]
    dev = [c for c in built if c['split'] == 'dev']
    test = [c for c in built if c['split'] == 'test']
    out = Path(args.out_dir)
    manifests = {'dev': write_set(dev, out / 'narration-selection-org-v1.dev.jsonl'),
                 'test': write_set(test, out / 'narration-selection-org-v1.test.jsonl')}
    summary = {'schema': 'jity-narration-org/1', 'source': args.src, 'cases': len(built),
               'dev': len(dev), 'test': len(test),
               'avgMustSelect': round(sum(len(c['expected']['mustSelect']) for c in built) / max(1, len(built)), 1),
               'avgOutcomes': round(sum(len(c['expected']['outcomes']) for c in built) / max(1, len(built)), 2),
               'manifests': manifests}
    (out / 'narration-selection-org-v1.summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
