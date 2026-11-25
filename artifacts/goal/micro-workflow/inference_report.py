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
                entry = rows.setdefault(port, {'task_calls': 0, 'inferences': 0, 'candidate_scores': 0, 'ms': 0, 'loadMs': 0})
                entry['task_calls'] += 1
                entry['ms'] += row.get('ms') or 0
                entry['loadMs'] = max(entry['loadMs'], row.get('loadMs') or 0)
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
            total_ms = sum(row['ms'] for row in rows.values())
            max_load = max((row['loadMs'] for row in rows.values()), default=0)
            calls = product.get('semanticCalls') or []
            accepted = [call for call in calls if not call.get('attempt')]
            attempts = [call for call in calls if call.get('attempt')]
            sources = Counter((call.get('source') or 'unlabelled') for call in accepted)
            print(f"{Path(path).name} turn={turn.get('turn')} input={turn.get('input', '')[:20]!r}")
            for port, row in sorted(rows.items()):
                print(f"  {port:12s} task_calls={row['task_calls']:3d} encoder_runs={row['inferences']:4d} "
                      f"head_outputs={row['inferences'] * HEADS[port]:5d} candidate_scores={row['candidate_scores']:4d} "
                      f"time_ms={round(row['ms']):4d} load_ms={round(row['loadMs']):4d}")
            print(f"  micro total  task_calls={total_calls:3d} encoder_runs={total_inf:4d} "
                  f"head_outputs={total_heads:5d} time_ms={round(total_ms):4d} max_load_ms={round(max_load):4d}")
            print(f"  task sources {dict(sources)}")
            print(f"  task attempts {len(attempts)}")
            micro_fallbacks = [row for row in stats if row.get('source') == 'abstain']
            model_fallbacks = [call for call in accepted if call.get('source') == 'fallback']
            print(f"  fallbacks micro={len(micro_fallbacks)} ({sum(row.get('ms') or 0 for row in micro_fallbacks):.0f} ms) "
                  f"model={len(model_fallbacks)} ({sum(call.get('ms') or 0 for call in model_fallbacks):.0f} ms)")
            heap = turn.get('jsHeap') or {}
            ready = data.get('jsHeapAtReady') or {}
            if heap.get('usedJSHeapSize'):
                print(f"  js_heap used_after={heap['usedJSHeapSize'] / 1e6:.0f} MB "
                      f"used_ready={ready.get('usedJSHeapSize', 0) / 1e6:.0f} MB (not GPU VRAM)")
            if not stats:
                print('  (no per-turn microStats; older evidence records only the session array)')
    if not sys.argv[1:]:
        print('usage: python inference_report.py evidence-*.json')


if __name__ == '__main__':
    main()
