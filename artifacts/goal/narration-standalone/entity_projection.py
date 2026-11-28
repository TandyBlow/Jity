# -*- coding: utf-8 -*-
"""N18: how many fact fragments can be projected into entity + attributes?
The natural reference needs subject-predicate clauses, but the brief writes
existential sentences ("屋里有X，A，B")."""
import json
import re
from collections import Counter
from pathlib import Path

import renderer_dataset as rd

HERE = Path(__file__).resolve().parent
EXIST = re.compile(r'^[^，。]{0,6}里有(?P<entity>[^，。]+)(?:，(?P<attrs>.+))?$')
ALSO = re.compile(r'^(?P<entity>[^，。]+)也在(?P<place>[^，。]+)(?:，(?P<attrs>.+))?$')
NOW = re.compile(r'^(?P<entity>[^，。]+)现在在(?P<place>[^，。]+)(?:，(?P<attrs>.+))?$')


def project(text):
    for pattern, kind in ((EXIST, 'exist'), (ALSO, 'also'), (NOW, 'now')):
        m = pattern.match(text)
        if not m:
            continue
        parts = [p for p in (m.groupdict().get('attrs') or '').split('，') if p]
        return {'kind': kind, 'entity': m.group('entity'), 'attrs': parts}
    return {'kind': 'atomic', 'entity': None, 'attrs': [text]}


def main():
    rows = [json.loads(l) for l in open(HERE / 'inputs.jsonl', encoding='utf8')]
    kinds = Counter()
    attrs = []
    samples = []
    for row in rows:
        for kind, text in rd.fragments(row):
            if kind != 'fact':
                continue
            p = project(text)
            kinds[p['kind']] += 1
            if p['kind'] != 'atomic':
                attrs.append(len(p['attrs']))
                if len(samples) < 3:
                    samples.append({'text': text[:60], 'entity': p['entity'], 'attrs': p['attrs'][:3]})
    total = sum(kinds.values())
    summary = {
        'factFragments': total,
        'exist': kinds['exist'], 'also': kinds['also'], 'now': kinds['now'], 'atomic': kinds['atomic'],
        'structuredRate': round((total - kinds['atomic']) / max(1, total), 3),
        'meanAttrs': round(sum(attrs) / max(1, len(attrs)), 2),
        'samples': samples,
    }
    (HERE / 'entity-projection-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'samples'}, ensure_ascii=False))
    for s in samples:
        print('---', s['text'], '| entity', s['entity'], '| attrs', s['attrs'])


if __name__ == '__main__':
    main()
