# -*- coding: utf-8 -*-
"""Compare the full committed world state of two A/B arms, not just `after`.

Positions, sanity, task statuses, appearance/personality records and item
positions are compared key by key; the report keeps every differing field.
"""
import json
import sys
from pathlib import Path

PUB = Path('D:/others/Jity/artifacts/goal/micro-workflow')


def load(path):
    data = json.loads(Path(path).read_text(encoding='utf8'))
    turn = data['turns'][0]
    state = turn['snapshotAfterTurn']['transport']['state']
    return state, turn


def view(state):
    characters = {}
    for cid, row in state.get('characters', {}).items():
        characters[cid] = {
            'position': f"{row['position']['containerId']}/{row['position'].get('slotId') or '-'}",
            'sanity': row.get('sanity'),
            'tasks': {tid: task.get('status') for tid, task in (row.get('tasks') or {}).items()},
            'appearance': [record.get('text') for record in row.get('appearanceChanges') or [] if record.get('active')],
            'personality': [record.get('text') for record in row.get('personalityChanges') or [] if record.get('active')],
        }
    items = {iid: f"{row['position']['containerId']}/{row['position'].get('slotId') or '-'}"
             for iid, row in state.get('items', {}).items()}
    locations = {lid: [record.get('text') for record in row.get('appearanceChanges') or [] if record.get('active')]
                 for lid, row in state.get('locations', {}).items()}
    return {'time': state['time']['dateTime'], 'characters': characters, 'items': items, 'locations': locations}


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    left_state, _ = load(a_path)
    right_state, _ = load(b_path)
    left, right = view(left_state), view(right_state)
    diff = {'a': str(a_path), 'b': str(b_path), 'time': [left['time'], right['time']], 'fields': []}
    for cid in sorted(set(left['characters']) | set(right['characters'])):
        lc = left['characters'].get(cid) or {}
        rc = right['characters'].get(cid) or {}
        for field in ('position', 'sanity', 'tasks', 'appearance', 'personality'):
            if lc.get(field) != rc.get(field):
                diff['fields'].append({'entity': cid, 'field': field, 'a': lc.get(field), 'b': rc.get(field)})
    for iid in sorted(set(left['items']) | set(right['items'])):
        if left['items'].get(iid) != right['items'].get(iid):
            diff['fields'].append({'entity': iid, 'field': 'item_position', 'a': left['items'].get(iid), 'b': right['items'].get(iid)})
    for lid in sorted(set(left['locations']) | set(right['locations'])):
        if left['locations'].get(lid) != right['locations'].get(lid):
            diff['fields'].append({'entity': lid, 'field': 'appearance', 'a': left['locations'].get(lid), 'b': right['locations'].get(lid)})
    diff['count'] = len(diff['fields'])
    out = PUB / f"state-diff-{Path(a_path).stem}-vs-{Path(b_path).stem}.json"
    out.write_text(json.dumps(diff, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({'time': diff['time'], 'count': diff['count'],
                      'fields': diff['fields'][:20]}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
