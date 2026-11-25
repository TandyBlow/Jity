# -*- coding: utf-8 -*-
"""Aggregate the seeded A/B reports into one table."""
import json
import sys
from pathlib import Path

PUB = Path('D:/others/Jity/artifacts/goal/micro-workflow')


def main():
    reports = [json.loads(Path(p).read_text(encoding='utf8')) for p in sys.argv[1:]] or [
        json.loads((PUB / 'ab-seed-report.json').read_text(encoding='utf8')),
    ]
    out = []
    for index, report in enumerate(reports, start=1):
        row = {'pair': index, 'firstReadableMs': {}, 'totals': {}, 'stages': {}}
        for arm in ('baseline', 'micro'):
            data = report[arm]
            row['firstReadableMs'][arm] = data['firstReadableMs']
            row['totals'][arm] = data['totals']
            for task, entry in data['stats'].items():
                stage = row['stages'].setdefault(task, {})
                stage[arm] = entry
        out.append(row)
    (PUB / 'ab-multi-seed.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    for row in out:
        print('pair', row['pair'], 'firstReadable', row['firstReadableMs'], 'totals', row['totals'])
        for task, stage in sorted(row['stages'].items()):
            print(' ', task, stage)


if __name__ == '__main__':
    main()
