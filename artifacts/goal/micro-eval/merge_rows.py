# -*- coding: utf-8 -*-
"""Merge the six batches and validate the 300-row eval set."""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-eval'
FILES = ['rows-1-unknown-person.jsonl', 'rows-2-unknown-place.jsonl', 'rows-3-multi-turn.jsonl',
         'rows-4-compound.jsonl', 'rows-5-implicit.jsonl', 'rows-6-context.jsonl']


def main():
    rows, errors, ids = [], [], set()
    for name in FILES:
        for line in open(PUB / name, encoding='utf8'):
            r = json.loads(line)
            rows.append(r)
            if r['id'] in ids:
                errors.append(f"dup {r['id']}")
            ids.add(r['id'])
            for key in ('action', 'present', 'current', 'candidates', 'dice', 'expect', 'tags'):
                if key not in r:
                    errors.append(f"missing {key} {r['id']}")
            if not set(r['expect']['targets']) <= set(r['present']):
                errors.append(f"targets not in present {r['id']}")
            if r['expect']['destination'] not in r['candidates']:
                errors.append(f"dest not in candidates {r['id']}")
            if not isinstance(r['expect']['negated'], bool):
                errors.append(f"negated not bool {r['id']}")
    tags = {}
    for r in rows:
        for tag in r['tags']:
            tags[tag] = tags.get(tag, 0) + 1
    print('rows', len(rows), 'errors', len(errors), 'tags', json.dumps(tags, ensure_ascii=False))
    for e in errors[:20]:
        print(' ', e)
    if len(rows) == 300 and not errors:
        (PUB / 'dataset.jsonl').write_text(
            ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf8')
        print('wrote dataset.jsonl')


if __name__ == '__main__':
    main()
