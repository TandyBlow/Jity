# -*- coding: utf-8 -*-
"""Snapshot/history growth per committed turn, measured on the real env-11
evidence (12 turns): serialized snapshot size, transport.state size and the
points/narrations/commands counts after each turn."""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
EVIDENCE = ROOT / 'artifacts/goal/micro-workflow/evidence-semantic-env-11-2026-11-27T1848-1519.json'
OUT = Path(__file__).resolve().parent / 'snapshot-growth.json'


def main():
    data = json.loads(EVIDENCE.read_text(encoding='utf8'))
    rows = []
    for turn in data.get('turns') or []:
        snapshot = turn.get('snapshotAfterTurn') or {}
        transport = snapshot.get('transport') or {}
        state = transport.get('state') or {}
        points = transport.get('points') or {}
        narrations = transport.get('narrations') or {}
        rows.append({
            'turn': turn.get('id'),
            'snapshotKB': round(len(json.dumps(snapshot, ensure_ascii=False)) / 1024, 1),
            'stateKB': round(len(json.dumps(state, ensure_ascii=False)) / 1024, 1),
            'points': len(points),
            'narrations': len(narrations),
            'commands': len(snapshot.get('commands') or []),
        })
    growth = []
    for index in range(1, len(rows)):
        growth.append(rows[index]['snapshotKB'] - rows[index - 1]['snapshotKB'])
    summary = {
        'turns': len(rows),
        'snapshotKbFirst': rows[0]['snapshotKB'] if rows else None,
        'snapshotKbLast': rows[-1]['snapshotKB'] if rows else None,
        'meanGrowthKbPerTurn': round(sum(growth) / max(1, len(growth)), 1),
        'rows': rows,
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, ensure_ascii=False))
    for row in rows:
        print(row)


if __name__ == '__main__':
    main()
