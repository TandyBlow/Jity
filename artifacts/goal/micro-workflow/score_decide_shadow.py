# -*- coding: utf-8 -*-
"""Decide vs shadow arm on the same read turns, from acceptance evidence.

Decide lines ([world-local decide] info <entity>:<clause>) are the model's
information events. A decided clause is corroborated when it is a verbatim
substring of the read entity's registered appearance; otherwise it is wrong.
Both arms are compared on decided events, state deltas, waits and the results
port's inference cost."""
import json
import re
import sys
from pathlib import Path

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'frontend/public/worlds/dragon-raja-free-day.world.json'
DECIDE = re.compile(r'\[world-local decide\] info ([^:：]+)[:：](.*)')
PROGRAM = re.compile(r'\[world-local info\] program ([^:：]+)[:：](.*)')


def appearances():
    world = json.loads(WORLD.read_text(encoding='utf8'))
    initial = world.get('initial') or world
    out = {}
    for space in ('items', 'characters', 'locations'):
        for eid, entry in (initial.get(space) or {}).items():
            text = entry.get('initialAppearance') or ''
            if text:
                out[eid] = text
    return out


def summarize(path, app):
    data = json.loads(Path(path).read_text(encoding='utf8'))
    rows = []
    for turn in data.get('turns') or []:
        decided = []
        programs = []
        for line in turn.get('console') or []:
            match = DECIDE.search(line)
            if match:
                entity, clause = match.group(1).strip(), match.group(2).strip()
                decided.append({'entity': entity, 'clause': clause,
                                'corroborated': clause in (app.get(entity) or '')})
            pMatch = PROGRAM.search(line)
            if pMatch:
                entity, clause = pMatch.group(1).strip(), pMatch.group(2).strip()
                programs.append({'entity': entity, 'clause': clause,
                                 'corroborated': clause in (app.get(entity) or '')})
        deltas = 0
        for point in ((turn.get('snapshotAfterTurn') or {}).get('transport') or {}).get('points', {}).values():
            deltas += len(point.get('entityDeltas') or {})
        stats = (turn.get('product') or {}).get('microStatsAll') or []
        results_ms = sum((row.get('inferMs') or 0) + (row.get('buildMs') or 0) for row in stats if row.get('port') == 'results')
        rows.append({'id': turn['id'], 'waitMs': (turn.get('timings') or {}).get('waitMs'),
                     'decided': decided, 'programs': programs, 'deltas': deltas,
                     'resultsMs': round(results_ms), 'problems': turn.get('problems') or [],
                     'source': (turn.get('product') or {}).get('firstReadableSource')})
    return rows


def main():
    decide_path, shadow_path = sys.argv[1], sys.argv[2]
    app = appearances()
    arms = {'decide': summarize(decide_path, app), 'shadow': summarize(shadow_path, app)}
    report = {'arms': {}, 'pairs': []}
    for arm, rows in arms.items():
        decided = [d for row in rows for d in row['decided']]
        programs = [d for row in rows for d in row['programs']]
        report['arms'][arm] = {
            'turns': len(rows),
            'decidedEvents': len(decided),
            'programEvents': len(programs),
            'decidedCorroborated': sum(1 for d in decided if d['corroborated']),
            'decidedWrong': sum(1 for d in decided if not d['corroborated']),
            'programCorroborated': sum(1 for d in programs if d['corroborated']),
            'programWrong': sum(1 for d in programs if not d['corroborated']),
            'meanWaitMs': round(sum(row['waitMs'] or 0 for row in rows) / max(1, len(rows))),
            'meanResultsMs': round(sum(row['resultsMs'] for row in rows) / max(1, len(rows))),
            'meanDeltas': round(sum(row['deltas'] for row in rows) / max(1, len(rows)), 2),
            'problemTurns': sum(1 for row in rows if row['problems']),
        }
    by_id = {arm: {row['id']: row for row in rows} for arm, rows in arms.items()}
    for identity in sorted(set(by_id['decide']) & set(by_id['shadow'])):
        left, right = by_id['decide'][identity], by_id['shadow'][identity]
        report['pairs'].append({'id': identity, 'decidedA': len(left['decided']), 'decidedB': len(right['decided']),
                                'programA': len(left['programs']), 'programB': len(right['programs']),
                                'waitA': left['waitMs'], 'waitB': right['waitMs'],
                                'deltasA': left['deltas'], 'deltasB': right['deltas']})
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
