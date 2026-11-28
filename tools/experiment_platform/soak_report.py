#!/usr/bin/env python3
"""Summarize a soak acceptance run: per-turn timing/heap and tree memory drift.

  python -m tools.experiment_platform.soak_report \
    --evidence results/product/evidence/platform-soak-10-*.json \
    --memory artifacts/goal/platform/lab/soak-memory.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.experiment_platform.perf_report import memory_summary  # noqa: E402


def summarize(doc: dict, memory: dict | None = None) -> dict:
    turns = []
    for turn in doc.get('turns') or []:
        product = turn.get('product') or {}
        heap = (turn.get('jsHeap') or {}).get('usedJSHeapSize')
        timing = turn.get('timings') or {}
        turns.append({
            'id': turn.get('id'),
            'source': product.get('source'),
            'model': product.get('narrationModel'),
            'waitMs': timing.get('waitMs'),
            'acceptedMs': product.get('acceptedMs'),
            'doneMs': timing.get('doneMs'),
            'textChars': len(turn.get('text') or ''),
            'heapMB': round(heap / 1048576, 1) if heap else None,
            'problems': turn.get('problems') or [],
        })
    heaps = [t['heapMB'] for t in turns if t['heapMB'] is not None]
    waits = [t['waitMs'] for t in turns if t['waitMs'] is not None]
    return {
        'schema': 'jity-soak-report/1',
        'status': doc.get('status'), 'turns': len(turns),
        'turnsDetail': turns,
        'heapPeakMB': max(heaps) if heaps else None,
        'heapEndMB': heaps[-1] if heaps else None,
        'heapDriftMB': round(heaps[-1] - heaps[0], 1) if len(heaps) > 1 else None,
        'waitMaxMs': max(waits) if waits else None,
        'failures': doc.get('failures') or [],
        'treeMemory': memory,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--evidence', required=True)
    parser.add_argument('--memory', default=None)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    doc = json.loads(Path(args.evidence).read_text(encoding='utf-8-sig'))
    memory = memory_summary(Path(args.memory)) if args.memory and Path(args.memory).exists() else None
    report = summarize(doc, memory)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'turnsDetail'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
