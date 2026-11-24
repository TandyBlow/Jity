# -*- coding: utf-8 -*-
"""Compare the micro arm with the LLM baseline per task."""
import json
from collections import Counter
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
        if task == 'results' and call.get('ms', 0) < 1000 and not raw:
            entry['micro'] += 1
        else:
            entry['llm'] += 1
    for entry in stats.values():
        entry['ms'] = round(entry['ms'])
    return {'waitMs': turn.get('waitMs') or (turn['product'].get('clocks') or {}).get('inputAtMs'),
            'acceptedFirstReadableMs': turn.get('acceptedFirstReadableMs'),
            'stats': stats}


def main():
    base = arm(BASELINE)
    micro = arm(MICRO)
    out = {'baseline': base, 'micro': micro}
    (PUB / 'ab-report.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    for name, arm_data in (('baseline', base), ('micro', micro)):
        print(name, 'accepted', arm_data['acceptedFirstReadableMs'])
        for task, entry in sorted(arm_data['stats'].items(), key=lambda kv: -kv[1]['ms']):
            print(' ', task, entry)


if __name__ == '__main__':
    main()
