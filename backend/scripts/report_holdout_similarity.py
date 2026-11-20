"""Produce the evidence a human needs to judge holdout independence.

For every fact in a built holdout package it prints, and writes out:

  * the exact old-material text with the highest character-bigram Jaccard,
  * that score,
  * whether any old text is byte-identical,
  * a per-source summary (max score over its facts).

This is evidence, not a verdict. The verdict stays in ``semantic-review.json``
and c3 only accepts it when a human signs it.

Usage:
    python -X utf8 backend/scripts/report_holdout_similarity.py artifacts/holdout-a-v1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
C3 = ROOT / '.local/parallel/c-organize-plan'
OLD_MATERIAL = [
    C3 / 'artifacts/world-components/organize-wording/controllability-v1.jsonl',
    C3 / 'artifacts/world-components/organize-wording/pairs-v2.jsonl',
    C3 / 'experiments/world-components/parallel/organize_plan/freeze/sources.json',
]


def bigrams(text: str) -> set[str]:
    t = ''.join(ch for ch in text if ch not in '，。、；：！？“”‘’（）《》…—,.!?() \n\t')
    return {t[i:i + 2] for i in range(max(0, len(t) - 1))}


def jaccard(a: str, b: str) -> float:
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def old_texts() -> list[dict]:
    rows = []
    for path in OLD_MATERIAL:
        if not path.exists():
            continue
        if path.suffix == '.jsonl':
            for line in path.read_text(encoding='utf-8').splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                for fact in row.get('facts', []):
                    if fact.get('text'):
                        rows.append({'origin': f'{path.name}:{row.get("pairId") or row.get("sourceId")}',
                                     'text': fact['text']})
        else:
            for source in json.loads(path.read_text(encoding='utf-8'))['sources']:
                for fact in source['facts']:
                    rows.append({'origin': f'{path.name}:{source["sourceId"]}', 'text': fact['text']})
    return rows


def main(package: str) -> int:
    pkg = Path(package)
    manifest = json.loads((pkg / 'manifest.json').read_text(encoding='utf-8'))
    old = old_texts()
    exact = {o['text'] for o in old}
    report, worst = {}, 0.0
    for source_id in manifest['sources']:
        doc = json.loads((pkg / 'pairs' / f'{source_id}-authorized.json').read_text(encoding='utf-8'))
        facts = []
        for unit in doc['units']:
            text = unit['text']
            best = (0.0, '')
            for other in old:
                score = jaccard(text, other['text'])
                if score > best[0]:
                    best = (score, other['text'])
            worst = max(worst, best[0])
            facts.append({'factId': unit['factId'], 'text': text,
                          'identicalToOld': text in exact,
                          'maxJaccard': round(best[0], 3),
                          'nearestOldText': best[1]})
        report[source_id] = {
            'worldId': doc['worldId'],
            'facts': facts,
            'maxJaccard': round(max(f['maxJaccard'] for f in facts), 3),
            'anyIdentical': any(f['identicalToOld'] for f in facts),
        }

    doc = {
        'protocol': 'holdout-similarity-evidence-v1',
        'package': str(pkg),
        'oldMaterialSources': [str(p) for p in OLD_MATERIAL if p.exists()],
        'oldFactCount': len(old),
        'threshold': 0.8,
        'summary': {
            'sources': len(report),
            'facts': sum(len(v['facts']) for v in report.values()),
            'maxJaccardAnyFact': round(worst, 3),
            'identicalFacts': sum(1 for v in report.values() for f in v['facts'] if f['identicalToOld']),
            'sourcesAboveThreshold': [sid for sid, v in report.items() if v['maxJaccard'] >= 0.8],
        },
        'note': ('Jaccard is a screen. A low score is not proof of semantic independence; '
                 'a human still has to read each source against the old material.'),
        'sources': report,
    }
    out = pkg / 'semantic-review-evidence.json'
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(doc['summary'], ensure_ascii=False, indent=1))
    print(f'wrote {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / 'artifacts/holdout-a-v1')))
