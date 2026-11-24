# -*- coding: utf-8 -*-
"""Movement samples from the position-stage prompts and their accepted answers.

An entity is a positive only when the accepted answer contains a *valid*
position entry for it; invalid container/slot entries are dropped with the
whole call, never used as labels.
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
ENTITY = re.compile(r'^- ([^=\n]+)=([^@\n]+)@([^/\n]+)(?:/([^\n]+))?', re.M)
FACT = re.compile(r'^f\d+ \[([^\]]+)\] (.+)$', re.M)


def slots_of(container):
    return {slot.get('id') for slot in (container or {}).get('slots') or [] if slot.get('id')}


def main():
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    containers = {loc['id']: slots_of(loc) for loc in world.get('locations', {}).values()}
    for item in world.get('items', {}).values():
        if item.get('slots'):
            containers[item['id']] = slots_of(item)
    rows = [json.loads(line) for line in open(PUB / 'records.jsonl', encoding='utf8')]
    out, dropped = [], 0
    for row in rows:
        if row['task'] != 'updates':
            continue
        try:
            raw = json.loads(row['raw'])
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or 'positions' not in raw:
            continue
        entities = ENTITY.findall(row['prompt'])
        if not entities:
            continue
        positions = raw.get('positions') or []
        invalid = False
        moved = {}
        for pos in positions:
            cid, sid = pos.get('containerId'), pos.get('slotId')
            if cid not in containers or (sid is not None and sid not in containers[cid]):
                invalid = True
                break
            moved[pos.get('entityId')] = (cid, sid)
        if invalid:
            dropped += 1
            continue
        facts = ' | '.join(f'{key}: {text[:50]}' for key, text in FACT.findall(row['prompt'])[:3])
        for entity_id, name, cid, sid in entities:
            label = 1 if entity_id in moved else 0
            out.append({'run': row['run'], 'task': 'move', 'label': label,
                        'input': f'实体：{name}；当前：{cid}/{sid or "-"}；本组结果：{facts[:160]}'})
    (PUB / 'movement-inputs.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out), encoding='utf8')
    print('samples', len(out), 'labels', dict(Counter(r['label'] for r in out)), 'dropped_calls', dropped)


if __name__ == '__main__':
    main()
