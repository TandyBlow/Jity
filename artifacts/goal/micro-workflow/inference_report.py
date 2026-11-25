# -*- coding: utf-8 -*-
"""Micro-model inferences during one player operation, per port.

Encoder runs (inferences) and head outputs are counted separately from task
calls. For continuation a candidate score is one encoder run and four head
outputs, so "hundreds of collaborative inferences" can be compared with what the
turn actually executed.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HEADS = {'results': 5, 'judge': 3, 'behavior': 7, 'updates': 2, 'targets': 1, 'continuation': 4, 'reaction': 1}


def main():
    for path in sys.argv[1:]:
        data = json.loads(Path(path).read_text(encoding='utf8'))
        turns = data.get('turns') or []
        for turn in turns:
            product = turn.get('product') or {}
            stats = product.get('microStats') or product.get('microStatsAll') or []
            rows = {}
            for row in stats:
                port = row.get('port')
                if port not in HEADS:
                    continue
                entry = rows.setdefault(port, {'task_calls': 0, 'inferences': 0, 'candidate_scores': 0})
                entry['task_calls'] += 1
                if port in ('results', 'judge', 'continuation', 'reaction'):
                    count = int(row.get('inferences', row.get('members', row.get('pairs', 1))) or 0)
                elif port == 'behavior':
                    count = int(row.get('inferences', 1) or 0)
                elif port == 'updates':
                    count = int(row.get('inferences', row.get('entities', 0)) or 0)
                else:
                    count = int(row.get('calls', 0) or 0)
                entry['inferences'] += count
                entry['candidate_scores'] += count
            total_inf = sum(row['inferences'] for row in rows.values())
            total_heads = sum(row['inferences'] * HEADS[port] for port, row in rows.items())
            total_calls = sum(row['task_calls'] for row in rows.values())
            calls = product.get('semanticCalls') or []
            sources = Counter((call.get('source') or 'unlabelled') for call in calls)
            print(f"{Path(path).name} turn={turn.get('turn')} input={turn.get('input', '')[:20]!r}")
            for port, row in sorted(rows.items()):
                print(f"  {port:12s} task_calls={row['task_calls']:3d} encoder_runs={row['inferences']:4d} "
                      f"head_outputs={row['inferences'] * HEADS[port]:5d} candidate_scores={row['candidate_scores']:4d}")
            print(f"  micro total  task_calls={total_calls:3d} encoder_runs={total_inf:4d} head_outputs={total_heads:5d}")
            print(f"  task sources {dict(sources)}")
            if not stats:
                print('  (no per-turn microStats; older evidence records only the session array)')
    if not sys.argv[1:]:
        print('usage: python inference_report.py evidence-*.json')


if __name__ == '__main__':
    main()
