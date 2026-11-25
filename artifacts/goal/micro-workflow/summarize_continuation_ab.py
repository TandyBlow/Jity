# -*- coding: utf-8 -*-
"""Three-arm summary for the continuation micro workflow.

Arms: LLM-only, previous micro workflow (no continuation heads), and the same
workflow with the four continuation heads. The isolated contribution is
micro-off -> micro-on; the LLM arm is not a clean control for the heads alone.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

PUB = Path('D:/others/Jity/artifacts/goal/micro-workflow')
ARMS = {
    'llm': PUB / 'evidence-continuation-llm2.json',
    'micro_off': PUB / 'evidence-continuation-off3.json',
    'micro_rule': PUB / 'evidence-continuation-rule3.json',
    'micro_on': PUB / 'evidence-continuation-micro3.json',
}
HEADS = {'results': 5, 'judge': 3, 'behavior': 7, 'updates': 2, 'targets': 1, 'continuation': 4, 'reaction': 1}


def state_view(state):
    characters = {}
    for cid, row in state.get('characters', {}).items():
        characters[cid] = {
            'position': f"{row['position']['containerId']}/{row['position'].get('slotId') or '-'}",
            'sanity': row.get('sanity'),
            'tasks': {tid: task.get('status') for tid, task in (row.get('tasks') or {}).items()},
            'appearance': [record.get('text') for record in row.get('appearanceChanges') or [] if record.get('active')],
            'personality': [record.get('text') for record in row.get('personalityChanges') or [] if record.get('active')],
        }
    items = {}
    for iid, row in state.get('items', {}).items():
        items[iid] = {
            'position': f"{row['position']['containerId']}/{row['position'].get('slotId') or '-'}",
            'appearance': [record.get('text') for record in row.get('appearanceChanges') or [] if record.get('active')],
        }
    locations = {lid: [record.get('text') for record in row.get('appearanceChanges') or [] if record.get('active')]
                 for lid, row in state.get('locations', {}).items()}
    return {'characters': characters, 'items': items, 'locations': locations}


def summary(path):
    data = json.loads(path.read_text(encoding='utf8'))
    turn = data['turns'][0]
    product = turn.get('product') or {}
    calls = product.get('semanticCalls') or []
    accepted = [call for call in calls if not call.get('attempt')]
    by_task = defaultdict(lambda: {'calls': 0, 'ms': 0.0})
    for call in accepted:
        key = f"{call.get('task')}:{call.get('source') or 'none'}"
        by_task[key]['calls'] += 1
        by_task[key]['ms'] += call.get('ms') or 0
    micro = {}
    for row in product.get('microStats') or []:
        port = row.get('port')
        entry = micro.setdefault(port, {'task_calls': 0, 'encoder_runs': 0, 'head_outputs': 0})
        entry['task_calls'] += 1
        if port in ('results', 'judge', 'continuation', 'reaction'):
            count = int(row.get('inferences', row.get('members', row.get('pairs', 1))) or 0)
        elif port == 'behavior':
            count = int(row.get('inferences', 1) or 0)
        elif port == 'updates':
            count = int(row.get('inferences', row.get('entities', 0)) or 0)
        else:
            count = int(row.get('calls', 0) or 0)
        entry['encoder_runs'] += count
        entry['head_outputs'] += count * HEADS.get(port, 1)
    transport = (turn.get('snapshotAfterTurn') or {}).get('transport') or {}
    points = transport.get('points') or {}
    return {
        'file': path.name,
        'wait_ms': turn['timings'].get('waitMs'),
        'calls': len(calls),
        'by_task': {key: {'calls': value['calls'], 'ms': round(value['ms'] / 1000, 1)}
                    for key, value in sorted(by_task.items())},
        'micro': micro,
        'micro_encoder_runs': sum(row['encoder_runs'] for row in micro.values()),
        'micro_head_outputs': sum(row['head_outputs'] for row in micro.values()),
        'points': len(points),
        'rounds': len({point.get('roundId') for point in points.values()}),
        'automatic_points': sum(1 for point in points.values() if point.get('trigger') == 'automatic'),
        'conclusion': (transport.get('round') or {}).get('conclusion'),
        'state': state_view(transport.get('state') or {}),
    }


def diff(left, right_state):
    fields = []
    for cid in sorted(set(left['state']['characters']) | set(right_state['characters'])):
        a = left['state']['characters'].get(cid) or {}
        b = right_state['characters'].get(cid) or {}
        for key in ('position', 'sanity', 'tasks'):
            if a.get(key) != b.get(key):
                fields.append({'entity': cid, 'field': key, 'a': a.get(key), 'b': b.get(key)})
    for iid in sorted(set(left['state']['items']) | set(right_state['items'])):
        if left['state']['items'].get(iid) != right_state['items'].get(iid):
            fields.append({'entity': iid, 'field': 'item',
                           'a': left['state']['items'].get(iid), 'b': right_state['items'].get(iid)})
    for lid in sorted(set(left['state']['locations']) | set(right_state['locations'])):
        if left['state']['locations'].get(lid) != right_state['locations'].get(lid):
            fields.append({'entity': lid, 'field': 'location_appearance',
                           'a': left['state']['locations'].get(lid), 'b': right_state['locations'].get(lid)})
    return fields


def main():
    arms = {name: summary(path) for name, path in ARMS.items()}
    comparisons = {}
    for a, b in (('micro_rule', 'micro_on'), ('micro_off', 'micro_on'), ('llm', 'micro_on'), ('llm', 'micro_off')):
        comparisons[f'{a}_vs_{b}'] = diff(arms[a], arms[b]['state'])
    for arm in arms.values():
        arm.pop('state')
    report = {'input': '我把护目镜递给诺诺，然后走进庭院。', 'seed': 11, 'arms': arms, 'state_diffs': comparisons}
    (PUB / 'continuation-ab-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps({name: {'wait_s': round(arm['wait_ms'] / 1000, 1), 'calls': arm['calls'],
                             'encoder_runs': arm['micro_encoder_runs'], 'head_outputs': arm['micro_head_outputs'],
                             'points': arm['points'], 'auto_points': arm['automatic_points'],
                             'conclusion': arm['conclusion']} for name, arm in arms.items()},
                     ensure_ascii=False, indent=1))
    print('state diff counts', {key: len(value) for key, value in comparisons.items()})


if __name__ == '__main__':
    main()
