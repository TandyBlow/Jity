# -*- coding: utf-8 -*-
"""Program position rule over the recorded merged scene calls.

A member's fact that names a registered location is read as a position: the
location is the container; a slot whose label shares a 2+ char fragment with
the fact becomes slotId. Agreement is measured against the LLM's engine-valid
answer for the same point.
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
MOVE_WORDS = ['走进', '走入', '走到', '走向', '进入', '来到', '回到', '退回', '退到', '跑到', '冲向', '赶到', '爬上', '走下', '钻出', '穿过']


def slots_of(container):
    return {slot.get('id') for slot in (container or {}).get('slots') or [] if slot.get('id')}


def fragments(text, size=3):
    return {text[i:i + size] for i in range(len(text) - size + 1)}


def main():
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    locations = world['locations']
    slots = {loc['id']: (loc.get('slots') or []) for loc in locations.values()}
    containers = {loc['id']: slots_of(loc) for loc in locations.values()}
    for item in world['items'].values():
        if item.get('slots'):
            containers[item['id']] = slots_of(item)
    rows = [json.loads(line) for line in open(PUB / 'records.jsonl', encoding='utf8')]
    points = 0
    loc_facts = 0
    fact_total = 0
    exact = container_only = mismatch = 0
    points_all_match = 0
    points_any_mismatch = 0
    unmoved = 0
    for row in rows:
        if row['task'] != 'updates' or '顺带结算外貌' not in row['prompt']:
            continue
        try:
            raw = json.loads(row['raw'])
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict) or 'positions' not in raw:
            continue
        points += 1
        current = {entity_id: (cid, sid) for _n, entity_id, cid, sid in ENTITY.findall(row['prompt'])}
        truth = {}
        for pos in raw.get('positions') or []:
            cid, sid = pos.get('containerId'), pos.get('slotId')
            if cid not in containers or (sid is not None and sid not in containers[cid]):
                continue
            truth[pos.get('entityId')] = (cid, sid)
        proposed = {}
        for key, text in FACT.findall(row['prompt']):
            member = key.split(' ')[0]
            fact_total += 1
            named = [(at, lid) for lid, loc in locations.items()
                     if len(loc.get('name') or '') >= 2 for at in [text.rfind(loc['name'])] if at >= 0]
            if named:
                at, lid = max(named)
                loc_facts += 1
                slot_id, best = None, 0
                for slot in slots.get(lid, []):
                    label = slot.get('label') or slot.get('name') or ''
                    score = len(max((frag for frag in fragments(label) if frag in text), key=len, default=''))
                    if score > best:
                        best, slot_id = score, slot['id']
                if best < 3:
                    slot_id = None
            else:
                slot_id, best, lid = None, 0, None
                for owner, entries in slots.items():
                    for slot in entries:
                        label = slot.get('label') or slot.get('name') or ''
                        score = len(max((frag for frag in fragments(label) if frag in text), key=len, default=''))
                        if score > best:
                            best, slot_id, lid = score, slot['id'], owner
                if best < 4:
                    continue
            if current.get(member) == (lid, slot_id):
                unmoved += 1
                continue
            proposed[member] = (lid, slot_id)
        if proposed:
            matched = 0
            for member, value in proposed.items():
                if member not in truth:
                    continue
                if truth[member] == value:
                    exact += 1
                    matched += 1
                elif truth[member][0] == value[0]:
                    container_only += 1
                    matched += 1
                else:
                    mismatch += 1
            if matched == len(proposed):
                points_all_match += 1
            else:
                points_any_mismatch += 1
    result = {
        'points': points,
        'facts': fact_total,
        'facts_with_location': loc_facts,
        'facts_already_there': unmoved,
        'proposals_exact': exact,
        'proposals_container_only': container_only,
        'proposals_mismatch': mismatch,
        'points_all_proposals_match': points_all_match,
        'points_with_mismatch': points_any_mismatch,
    }
    (PUB / 'position-rule-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
