# -*- coding: utf-8 -*-
"""Coverage of the structured destination channel on real action texts.

Parses the recorded results prompts, applies the same transfer/walk patterns
`destinationHint()` uses in the browser, and counts how many members would get
a `去向=entity:container` tag on their micro fact.
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
MEMBER = re.compile(r'^- (.+?)（id=([\w-]+)）行动：(.+)$', re.M)
TRANSFER = re.compile(r'把(.+?)(?:递给|交给|塞给|递到)(.+?)(?:[。；，,！？]|$)')
WALK = re.compile(r'(?:走进|走入|走到|走向|进入|来到|回到|退回|退到|跑到|冲向|赶到|爬上|走下)([^。；，,！？]+)')


def main():
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    by_name = {}
    for group in ('characters', 'items', 'locations'):
        for entity_id, entity in world.get(group, {}).items():
            if entity.get('name'):
                by_name[entity['name']] = (entity_id, group)
    rows = [json.loads(line) for line in open(PUB / 'records.jsonl', encoding='utf8')]
    calls = members = tagged = 0
    kinds = Counter()
    unresolved = Counter()
    for row in rows:
        if row['task'] != 'results':
            continue
        blocks = MEMBER.findall(row['prompt'])
        if not blocks:
            continue
        calls += 1
        for _name, member_id, action in blocks:
            members += 1
            match = TRANSFER.search(action)
            if match:
                item = by_name.get(match.group(1).strip())
                person = by_name.get(match.group(2).strip())
                if item and person and item[1] == 'items' and person[1] == 'characters':
                    tagged += 1
                    kinds['transfer'] += 1
                else:
                    unresolved['transfer'] += 1
                continue
            match = WALK.search(action)
            if match:
                location = by_name.get(match.group(1).strip())
                if location and location[1] == 'locations':
                    tagged += 1
                    kinds['walk'] += 1
                else:
                    unresolved['walk'] += 1
    result = {
        'results_calls': calls,
        'members': members,
        'members_with_hint': tagged,
        'share': round(tagged / members, 3) if members else 0,
        'kinds': dict(kinds),
        'unresolved': dict(unresolved),
    }
    (PUB / 'chain-coverage.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
