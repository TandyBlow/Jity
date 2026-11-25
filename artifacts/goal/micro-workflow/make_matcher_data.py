# -*- coding: utf-8 -*-
"""Candidate pairs for the item matcher.

Positives come from recorded action texts that name a registered item (full
name or core name after stripping the owner prefix). Hard negatives are items
sharing a 2-char fragment; curated unregistered mentions (水壶/外套/电台/…)
are paired with every candidate as no-match, so the model may say "no such
item" instead of forcing the nearest cup.
"""
import json
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
MEMBER = re.compile(r'^- (.+?)（id=([\w-]+)）行动：(.+)$', re.M)
UNREGISTERED = ['水壶', '外套', '电台', '头盔', '钥匙串', '地图册', '长柄手电']


def core(name):
    stripped = re.sub(r'^.+?的', '', name)
    return stripped if len(stripped) >= 2 else name


def main():
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    items = {}
    for item_id, item in world['items'].items():
        name = item.get('name', item_id)
        items[item_id] = {
            'id': item_id, 'name': name, 'core': core(name),
            'desc': (item.get('initialAppearance') or '')[:60],
            'where': item['initialPosition']['containerId'],
        }
    actions = []
    for line in open(PUB / 'records.jsonl', encoding='utf8'):
        row = json.loads(line)
        if row['task'] != 'results':
            continue
        for _name, _mid, action in MEMBER.findall(row['prompt']):
            actions.append(action[:80])
    random.seed(20261125)
    pairs = []
    for action in actions:
        mentioned = [item for item in items.values() if item['core'] in action or item['name'] in action]
        if not mentioned:
            continue
        for item in mentioned:
            pairs.append({'label': 1, 'mention': item['core'], 'itemId': item['id'],
                          'context': f"行动：{action}；提到：{item['core']}",
                          'candidate': f"候选：{item['name']}；描述：{item['desc']}；位置：{item['where']}"})
            others = [other for other in items.values() if other['id'] != item['id']]
            same = [other for other in others if len(set(other['core']) & set(item['core'])) >= 2]
            pick = same or random.sample(others, min(2, len(others)))
            for other in pick[:2]:
                pairs.append({'label': 0, 'mention': item['core'], 'itemId': other['id'],
                              'context': f"行动：{action}；提到：{item['core']}",
                              'candidate': f"候选：{other['name']}；描述：{other['desc']}；位置：{other['where']}"})
    for mention in UNREGISTERED:
        for item in items.values():
            pairs.append({'label': 0, 'mention': mention, 'itemId': item['id'],
                          'context': f"行动：我把{mention}拿在手里。；提到：{mention}",
                          'candidate': f"候选：{item['name']}；描述：{item['desc']}；位置：{item['where']}"})
    random.shuffle(pairs)
    item_ids = sorted({row['itemId'] for row in pairs})
    held = set(random.sample(item_ids, max(1, len(item_ids) // 5)))
    for row in pairs:
        row['split'] = 'test' if row['itemId'] in held else 'train'
    (PUB / 'matcher-pairs.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in pairs), encoding='utf8')
    print('pairs', len(pairs), 'labels', dict(Counter(r['label'] for r in pairs)),
          'items', len(item_ids), 'held_out_items', len(held),
          'test_rows', sum(1 for r in pairs if r['split'] == 'test'))


if __name__ == '__main__':
    main()