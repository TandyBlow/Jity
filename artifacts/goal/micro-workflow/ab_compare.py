# -*- coding: utf-8 -*-
"""Compare two evidence files per task and per source.

Usage: ab_compare.py [baseline.json] [micro.json] [report.json]
Source is read from each semantic call when present; older evidence falls back
to the empty-raw/under-a-second heuristic for results.
"""
import json
import sys
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
BASELINE = PUB / 'evidence-record-two.json'
MICRO = PUB / 'evidence-ab-micro.json'


def arm(path):
    data = json.loads(path.read_text(encoding='utf8'))
    turn = data['turns'][0]
    calls = turn['product'].get('semanticCalls') or []
    stats = {}
    for call in calls:
        task = call['task']
        entry = stats.setdefault(task, {'calls': 0, 'ms': 0.0, 'llm': 0, 'micro': 0})
        entry['calls'] += 1
        entry['ms'] += call.get('ms') or 0
        raw = call.get('raw') or ''
        source = call.get('source')
        if source in ('micro', 'program'):
            entry['micro'] += 1
        elif source == 'model':
            entry['llm'] += 1
        elif task == 'results' and call.get('ms', 0) < 1000 and not raw:
            entry['micro'] += 1
        else:
            entry['llm'] += 1
    totals = {
        'calls': sum(e['calls'] for e in stats.values()),
        'llm': sum(e['llm'] for e in stats.values()),
        'micro': sum(e['micro'] for e in stats.values()),
        'ms': round(sum(e['ms'] for e in stats.values())),
    }
    for entry in stats.values():
        entry['ms'] = round(entry['ms'])
    after = turn.get('after') or {}
    return {
        'file': str(path),
        'firstReadableMs': turn.get('acceptedFirstReadableMs'),
        'after': {k: after.get(k) for k in ('place', 'nearby', 'sanity', 'tasks')},
        'semanticCalls': len(calls),
        'totals': totals,
        'stats': stats,
    }


def main():
    baseline = Path(sys.argv[1]) if len(sys.argv) > 1 else BASELINE
    micro = Path(sys.argv[2]) if len(sys.argv) > 2 else MICRO
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else PUB / 'ab-report.json'
    out = {'baseline': arm(baseline), 'micro': arm(micro)}
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    for name, row in out.items():
        print(name, 'firstReadable', row['firstReadableMs'], 'totals', row['totals'])
        for task, entry in sorted(row['stats'].items(), key=lambda kv: -kv[1]['ms']):
            print(' ', task, entry)
        print('  after', {k: (v if k != 'tasks' else [t['goal'] for t in v if t['done']]) for k, v in row['after'].items()})


if __name__ == '__main__':
    main()
