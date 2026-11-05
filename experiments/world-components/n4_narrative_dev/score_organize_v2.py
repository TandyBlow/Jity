"""对已生成的 v2 组织结果重新跑程序检查，不重跑模型。"""
from __future__ import annotations

import json
import pathlib
from collections import Counter

import run_organize_v2 as R

ROOT = pathlib.Path('D:/others/Jity')
A1 = ROOT / 'artifacts/cohesion-split/a1.jsonl'
RESULTS = ROOT / 'artifacts/cohesion-split/organize-v2-results.jsonl'
OUT = ROOT / 'artifacts/cohesion-split/organize-v2-scores.jsonl'
SUMMARY = ROOT / 'artifacts/cohesion-split/organize-v2-scores-summary.json'


def main():
    rows = {r['sourceId']: r for r in R.load_jsonl(A1)}
    results = R.load_jsonl(RESULTS)
    scored = []
    for r in results:
        row = rows[r['sourceId']]
        parsed = r.get('parsed') or {}
        flags = R.check(row, parsed)
        scored.append({
            'sourceId': r['sourceId'],
            'A1': row['A1'],
            'text': parsed.get('text', ''),
            'operations': parsed.get('operations', []),
            'flags': flags,
            'seconds': r.get('seconds'),
        })
    OUT.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in scored) + '\n',
                   encoding='utf-8')
    op_counts = Counter()
    flag_counts = Counter()
    for x in scored:
        for op in x['operations']:
            if isinstance(op, dict) and op:
                op_counts[op.get('op') or '?'] += 1
        flag_counts.update(x['flags'])
    summary = {
        'sourceCount': len(scored),
        'opCounts': dict(op_counts),
        'flagCounts': dict(flag_counts),
        'sourcesWithFlags': sum(1 for x in scored if x['flags']),
        'sourcesWithoutFlags': sum(1 for x in scored if not x['flags']),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for x in scored:
        print(x['sourceId'], '|', ', '.join(x['flags']) or '-')


if __name__ == '__main__':
    main()
