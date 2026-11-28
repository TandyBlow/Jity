#!/usr/bin/env python3
"""Normalize existing timing and memory records into one perf report.

Reads artifacts/goal/timing-baseline.json (summarize-timing.mjs output) and
memory CSVs (t,freeMB,edgeMB,edgeProcs). Reports what is measured, what is
missing, and the top stage costs; it does not start a browser or invent clocks.

  python -m tools.experiment_platform.perf_report
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def memory_summary(path: Path) -> dict:
    rows = list(csv.DictReader(path.open(encoding='utf-8-sig')))
    edges = [float(r['edgeMB']) for r in rows if r.get('edgeMB')]
    frees = [float(r['freeMB']) for r in rows if r.get('freeMB')]
    return {'file': path.name, 'samples': len(rows),
            'peakEdgeMB': max(edges) if edges else None,
            'endEdgeMB': edges[-1] if edges else None,
            'driftMB': round(edges[-1] - edges[0], 1) if len(edges) > 1 else None,
            'minFreeMB': min(frees) if frees else None,
            'peakProcesses': max((int(r['edgeProcs']) for r in rows if r.get('edgeProcs')), default=None)}


def summarize(timing: dict, memory: list[dict]) -> dict:
    points = timing.get('points') or []
    stages = defaultdict(float)
    stage_counts = defaultdict(int)
    for point in points:
        for stage in point.get('stages') or []:
            stages[stage.get('task') or '?'] += float(stage.get('ms') or 0)
            stage_counts[stage.get('task') or '?'] += 1
    top = sorted(stages.items(), key=lambda kv: -kv[1])[:10]
    cold = [c.get('readyMs') for c in timing.get('coldStarts') or [] if c.get('readyMs') is not None]
    nulls = {key: sum(1 for p in points if (p.get('clocks') or {}).get(key) is None)
             for key in ('pointCommittedAtMs', 'narrationStartedAtMs', 'firstReadableAtMs',
                         'pointTextFinishedAtMs')}
    return {
        'sources': [s.get('file') for s in timing.get('sources') or []],
        'points': len(points),
        'gates': timing.get('gates'),
        'coldStart': {'samples': len(cold),
                      'minMs': min(cold) if cold else None,
                      'medianMs': statistics.median(cold) if cold else None,
                      'maxMs': max(cold) if cold else None},
        'topStagesByTotalMs': [{'task': k, 'totalMs': round(v), 'calls': stage_counts[k]} for k, v in top],
        'nullClocks': nulls,
        'memory': memory,
        'notMeasured': ['controlReturnedAt (explicit clock)', 'page/process RSS at peak',
                        'GPU memory/utilisation', 'long-term drift beyond a 2-turn window',
                        'per-model cold-start breakdown'],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--timing', default=str(ROOT / 'artifacts/goal/timing-baseline.json'))
    parser.add_argument('--memory', action='append', default=None)
    parser.add_argument('--out', default=str(ROOT / 'artifacts/goal/platform/perf-report.json'))
    args = parser.parse_args(argv)
    timing = json.loads(Path(args.timing).read_text(encoding='utf-8'))
    memory_paths = args.memory or [str(ROOT / 'artifacts/goal/memory-baseline/ab2-process-memory.csv')]
    memory = [memory_summary(Path(p)) for p in memory_paths if Path(p).exists()]
    report = {'schema': 'jity-perf-report/1', **summarize(timing, memory)}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
