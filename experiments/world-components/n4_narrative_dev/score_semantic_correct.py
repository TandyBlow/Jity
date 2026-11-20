"""对已生成的语义纠错结果重跑程序安全检查，不重跑模型。

首轮检查漏了“删除片段含句号、把两句拼在一起”的语病；修正后重评分。
"""
from __future__ import annotations

import json
import pathlib
from collections import Counter

import run_semantic_correct as R

import sys as _paths_sys
_paths_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from component_paths import PATHS

ROOT = PATHS.worktree
A1 = PATHS.input('cohesion-split/a1.jsonl')
RESULTS = PATHS.output('cohesion-split/semantic-correct-results.jsonl')
OUT = PATHS.output('cohesion-split/semantic-correct-scores.jsonl')
SUMMARY = PATHS.output('cohesion-split/semantic-correct-scores-summary.json')


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = {r['sourceId']: r for r in
            (json.loads(l) for l in A1.read_text(encoding='utf-8').splitlines() if l.strip())}
    results = [json.loads(l) for l in RESULTS.read_text(encoding='utf-8').splitlines() if l.strip()]
    scored = []
    for r in results:
        row = rows[r['sourceId']]
        flags, status, c_text, applied = R.check_and_apply(row, r.get('parsed'))
        scored.append({
            'sourceId': r['sourceId'],
            'A0': row['A0'],
            'A1': row['A1'],
            'status': status,
            'flags': flags,
            'applied': applied,
            'C': c_text,
            'proposed': r.get('proposed', []),
        })
    OUT.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in scored) + '\n',
                   encoding='utf-8')
    status = Counter(x['status'] for x in scored)
    flags = Counter(f for x in scored for f in x['flags'])
    summary = {
        'sourceCount': len(scored),
        'statusCounts': dict(status),
        'proposedCount': sum(len(x['proposed']) for x in scored),
        'appliedCount': sum(len(x['applied']) for x in scored),
        'flagCounts': dict(flags),
        'appliedSources': [x['sourceId'] for x in scored if x['applied']],
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for x in scored:
        print(x['sourceId'], x['status'], x['flags'], 'applied=', len(x['applied']))


if __name__ == '__main__':
    main()
