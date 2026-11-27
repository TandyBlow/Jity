# -*- coding: utf-8 -*-
"""Compare the independent information-event annotation with the old rule labels.

The old `info` label marks a turn as present only when the program emitted a
`信息=` clause. The v2 annotation lists 0..N items the receiver learned from
facts/narration/prior turns. This report shows how far the two task definitions
diverge; it is a measurement, not a gate."""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE / 'semantic-info-events-v2.jsonl'
OLD = HERE / 'real-semantic.jsonl'


def main():
    v2 = [json.loads(line) for line in V2.read_text(encoding='utf8').splitlines() if line.strip()]
    old = {row['id']: row for row in (json.loads(line) for line in OLD.read_text(encoding='utf8').splitlines() if line.strip())}
    table = Counter()
    modes = Counter()
    sources = Counter()
    per_class = Counter()
    examples = []
    for entry in v2:
        items = [item for item in entry.get('items') or [] if item.get('novel')]
        old_row = old.get(entry['id']) or {}
        old_info = (old_row.get('label') or {}).get('info') or {}
        old_present = old_info.get('status') == 'present'
        table[('v2_items' if items else 'v2_none', 'old_present' if old_present else 'old_absent')] += 1
        per_class[(entry.get('class') or 'none', 'items' if items else 'none')] += 1
        for item in entry.get('items') or []:
            modes[item['mode']] += 1
            sources[item['source']] += 1
        if not items and old_present:
            examples.append({'id': entry['id'], 'action': entry.get('action'), 'why': 'old_present_v2_none'})
        elif items and not old_present:
            examples.append({'id': entry['id'], 'action': entry.get('action'), 'why': 'v2_items_old_absent',
                             'first': items[0]['content'][:40]})
    report = {
        'turns': len(v2),
        'agreement': {f'{a}|{b}': count for (a, b), count in table.items()},
        'modes': dict(modes),
        'sources': dict(sources),
        'perClass': {f'{cls}|{flag}': count for (cls, flag), count in sorted(per_class.items())},
        'examples': examples[:30],
    }
    (HERE / 'semantic-info-events-v2-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=1)[:3000])


if __name__ == '__main__':
    main()
