#!/usr/bin/env python3
"""Sample a process tree's memory/CPU and write a CSV plus a summary.

Used to attribute experiment cost: peak tree RSS, end-of-run RSS (drift), CPU
percent and child count. Does not start, stop or kill anything.

  python -m tools.experiment_platform.resource_monitor --pid 1234 --duration 60
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - psutil is present in this environment
    psutil = None


def tree(pid: int):
    root = psutil.Process(pid)
    procs = [root]
    try:
        procs += root.children(recursive=True)
    except psutil.Error:
        pass
    return procs


def sample(pid: int) -> dict:
    procs = tree(pid)
    rss = cpu = 0.0
    for proc in procs:
        try:
            rss += proc.memory_info().rss
            cpu += proc.cpu_percent(None)
        except psutil.Error:
            continue
    return {'rssMB': round(rss / 1048576, 1), 'cpuPercent': round(cpu, 1), 'processes': len(procs)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--interval', type=float, default=1.0)
    parser.add_argument('--duration', type=float, default=60.0)
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    if psutil is None:
        print('psutil is required', file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else Path(f'artifacts/goal/platform/runs/monitor-{args.pid}.csv')
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    started = time.time()
    with out.open('w', newline='', encoding='utf-8') as fh:
        writer = None
        while time.time() - started < args.duration:
            try:
                row = {'at': round(time.time() - started, 2), **sample(args.pid)}
            except psutil.NoSuchProcess:
                break
            if writer is None:
                writer = csv.DictWriter(fh, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(row)
            rows.append(row)
            time.sleep(max(0.05, args.interval))
    if not rows:
        print(json.dumps({'pid': args.pid, 'status': 'no-samples'}))
        return 1
    peak = max(rows, key=lambda r: r['rssMB'])
    summary = {
        'schema': 'jity-resource-monitor/1', 'pid': args.pid,
        'sampledAt': datetime.now(tz=timezone.utc).isoformat(),
        'samples': len(rows), 'durationSec': round(time.time() - started, 1),
        'peakRssMB': peak['rssMB'], 'peakCpuPercent': max(r['cpuPercent'] for r in rows),
        'endRssMB': rows[-1]['rssMB'], 'driftMB': round(rows[-1]['rssMB'] - rows[0]['rssMB'], 1),
        'peakProcesses': max(r['processes'] for r in rows), 'csv': str(out),
    }
    out.with_suffix('.summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n',
                                                encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
