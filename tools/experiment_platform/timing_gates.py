#!/usr/bin/env python3
"""Three independent timing gates: first readable, point text, control returned.

The product goal has three separate limits: first readable prose <=60 s,
point text complete <=300 s, and control returned (the player can act again)
<=60 s. summarize-timing.mjs only checks the first two; this tool adds the
third from driverDoneMs and flags clocks that are identical by construction.

  python -m tools.experiment_platform.timing_gates \
    --timing artifacts/goal/platform/eval/turns20-pi-timing.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIRST_LIMIT_MS = 60_000
POINT_LIMIT_MS = 300_000
CONTROL_LIMIT_MS = 60_000


def evaluate(timing: dict) -> dict:
    rows = []
    for point in timing.get('points') or []:
        clocks = point.get('clocks') or {}
        first = clocks.get('firstReadableAtMs')
        point_ms = clocks.get('pointTextFinishedMinusCommitMs')
        done = clocks.get('driverDoneMs')
        narration = clocks.get('narrationStartedAtMs')
        rows.append({
            'id': point.get('id'),
            'firstReadableMs': first,
            'firstPass': first is not None and first <= FIRST_LIMIT_MS,
            'pointTextMs': point_ms,
            'pointPass': point_ms is not None and point_ms <= POINT_LIMIT_MS,
            'controlReturnedMs': done,
            'controlPass': done is not None and done <= CONTROL_LIMIT_MS,
            'firstEqualsNarrationStart': first is not None and first == narration,
            'excluded': point.get('excluded'),
        })
    active = [r for r in rows if not r.get('excluded')]
    total = max(1, len(active))
    return {
        'schema': 'jity-timing-gates/1',
        'points': len(active),
        'firstReadable': {'pass': sum(r['firstPass'] for r in active), 'worstMs': max((r['firstReadableMs'] or 0) for r in active) if active else None},
        'pointText': {'pass': sum(r['pointPass'] for r in active), 'worstMs': max((r['pointTextMs'] or 0) for r in active) if active else None},
        'controlReturned': {'pass': sum(r['controlPass'] for r in active), 'worstMs': max((r['controlReturnedMs'] or 0) for r in active) if active else None},
        'firstEqualsNarrationStart': sum(r['firstEqualsNarrationStart'] for r in active),
        'overallPass': all(r['firstPass'] and r['pointPass'] and r['controlPass'] for r in active) and bool(active),
        'rows': rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--timing', required=True)
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    timing = json.loads(Path(args.timing).read_text(encoding='utf-8'))
    report = evaluate(timing)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
