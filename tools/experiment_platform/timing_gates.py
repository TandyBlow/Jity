#!/usr/bin/env python3
"""Five timing checks: first readable, point text, control returned, turn count,
and incomplete turns.

The product goal has three separate limits: first readable prose <=60 s,
point text complete <=300 s, and control returned (the player can act again)
<=60 s. summarize-timing.mjs only checks the first two; this tool adds the
third from driverDoneMs and flags clocks that are identical by construction.
A point missing any clock or marked turnIncomplete fails the run; --expect-turns
also checks the turn count and missing turn numbers, so a partial run cannot
pass as a whole.

  python -m tools.experiment_platform.timing_gates \
    --timing artifacts/goal/platform/eval/turns20-pi-timing.json --expect-turns 20
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIRST_LIMIT_MS = 60_000
POINT_LIMIT_MS = 300_000
CONTROL_LIMIT_MS = 60_000


def evaluate(timing: dict, expected_turns: int | None = None) -> dict:
    rows = []
    for point in timing.get('points') or []:
        clocks = point.get('clocks') or {}
        first = clocks.get('firstReadableAtMs')
        point_ms = clocks.get('pointTextFinishedMinusCommitMs')
        done = clocks.get('driverDoneMs')
        narration = clocks.get('narrationStartedAtMs')
        incomplete = bool(point.get('turnIncomplete')) or any(v is None for v in (first, point_ms, done))
        rows.append({
            'id': point.get('id'), 'turn': point.get('turn'),
            'firstReadableMs': first,
            'firstPass': first is not None and first <= FIRST_LIMIT_MS,
            'pointTextMs': point_ms,
            'pointPass': point_ms is not None and point_ms <= POINT_LIMIT_MS,
            'controlReturnedMs': done,
            'controlPass': done is not None and done <= CONTROL_LIMIT_MS,
            'firstEqualsNarrationStart': first is not None and first == narration,
            'incomplete': incomplete,
            'excluded': point.get('excluded'),
        })
    active = [r for r in rows if not r.get('excluded')]
    expected = expected_turns if expected_turns is not None else timing.get('expectedTurns')
    turns = sorted({r['turn'] for r in active if isinstance(r['turn'], int)})
    missing_turns = [] if expected is None else [n for n in range(1, expected + 1) if n not in turns]
    incomplete_ids = [r['id'] for r in active if r['incomplete']]
    count_pass = None if expected is None else len(active) == expected and not missing_turns
    overall = (bool(active) and not incomplete_ids
               and all(r['firstPass'] and r['pointPass'] and r['controlPass'] for r in active)
               and count_pass is not False)
    return {
        'schema': 'jity-timing-gates/2',
        'points': len(active),
        'expectedTurns': expected,
        'observedTurns': len(turns),
        'turnCountPass': count_pass,
        'missingTurnNumbers': missing_turns,
        'incompleteTurns': incomplete_ids,
        'firstReadable': {'pass': sum(r['firstPass'] for r in active), 'worstMs': max((r['firstReadableMs'] or 0) for r in active) if active else None},
        'pointText': {'pass': sum(r['pointPass'] for r in active), 'worstMs': max((r['pointTextMs'] or 0) for r in active) if active else None},
        'controlReturned': {'pass': sum(r['controlPass'] for r in active), 'worstMs': max((r['controlReturnedMs'] or 0) for r in active) if active else None},
        'firstEqualsNarrationStart': sum(r['firstEqualsNarrationStart'] for r in active),
        'overallPass': overall,
        'status': 'PASS' if overall else 'FAIL',
        'rows': rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--timing', required=True)
    parser.add_argument('--expect-turns', type=int, default=None)
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    timing = json.loads(Path(args.timing).read_text(encoding='utf-8'))
    report = evaluate(timing, args.expect_turns)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
