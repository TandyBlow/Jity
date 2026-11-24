# -*- coding: utf-8 -*-
"""Appearance samples from the merged scene prompts and their accepted answers.

An entity is positive only when the accepted answer writes an add/remove/replace
op for it. Calls whose position half is invalid are dropped with the whole call
(the engine refused that answer).
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
ENTITY = re.compile(r'^- ([^=\n]+)=([^@\n]+)@([^/\n]+)(?:/([^\n]+))?', re.M)
LOOK = re.compile(r'^- (.+?)（id=([^，]+)，(人物|物品|地点)）当前外貌=(.*?)；记录=\[([^\]]*)\]', re.M)
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
    out, dropped, calls = [], 0, 0
    for row in rows:
        if row['task'] != 'updates':
            continue
        try:
            raw = json.loads(row['raw'])
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or 'appearances' not in raw:
            continue
        looks = LOOK.findall(row['prompt'])
        if not looks:
            continue
        calls += 1
        invalid = False
        for pos in raw.get('positions') or []:
            cid, sid = pos.get('containerId'), pos.get('slotId')
            if cid not in containers or (sid is not None and sid not in containers[cid]):
                invalid = True
                break
        if invalid:
            dropped += 1
            continue
        listed = {entity_id for _name, entity_id, _kind, _text, _records in looks}
        changed = {}
        for op in raw.get('appearances') or []:
            if not isinstance(op, dict) or op.get('entityId') not in listed or op.get('op') == 'keep':
                invalid = True
                break
            changed[op['entityId']] = op
        if invalid:
            dropped += 1
            continue
        facts = ' | '.join(f'{key}: {text[:50]}' for key, text in FACT.findall(row['prompt'])[:3])
        for name, entity_id, kind, text, records in looks:
            out.append({'run': row['run'], 'task': 'appearance', 'label': 1 if entity_id in changed else 0,
                        'input': f'实体：{name}；类型：{kind}；当前外貌：{text[:80]}；本组结果：{facts[:160]}'})
    (PUB / 'appearance-inputs.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out), encoding='utf8')
    print('calls_with_appearance', calls, 'dropped_calls', dropped,
          'samples', len(out), 'labels', dict(Counter(r['label'] for r in out)))


if __name__ == '__main__':
    main()
