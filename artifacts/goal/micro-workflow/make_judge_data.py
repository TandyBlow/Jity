# -*- coding: utf-8 -*-
"""Contrast scenarios for the three behavior judges.

Same actor, task and candidate set; the scene flags (item present, target
present, path open, repeated) are varied to make positives and negatives.
Labels are rule-derived and multi-positive: several candidates may be good in
the same scene. Deterministic checks stay program-side; these labels only cover
task relevance, personality fit and scene fit.
"""
import json
import re
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
MOVE = ['前往', '走向', '走进', '进入', '赶到', '回到', '退到', '离开', '去', '到']
GUARD = ['守住', '护住', '挡住', '拦住', '守']
CAUTIOUS = ['谨慎', '先确认', '不冒险', '稳妥', '耐心', '观察', '先问', '不乱']
BOLD = ['自信', '直接', '主动', '喜欢', '果断', '抢先']


def core(name):
    value = re.sub(r'^.+?的', '', name)
    return value if len(value) >= 2 else name


def match_location(locations, text):
    full, suffix = [], []
    for lid, loc in locations.items():
        name = loc.get('name') or ''
        if len(name) < 2:
            continue
        at = text.rfind(name)
        if at >= 0:
            full.append((at, lid, name))
            continue
        for cut in range(1, len(name) - 1):
            part = name[cut:]
            idx = text.rfind(part)
            if idx >= 0:
                suffix.append((idx, lid, part))
                break
    if full:
        full.sort(reverse=True)
        return full[0]
    if suffix:
        suffix.sort(reverse=True)
        return suffix[0]
    return None


def match_item(items, text):
    best = []
    for iid, item in items.items():
        name = item.get('name') or iid
        score = 0
        for cand in (core(name), name):
            for i in range(len(cand) - 1):
                if cand[i:i + 2] in text:
                    score = max(score, 2)
        if score:
            best.append((score, iid))
    if not best:
        return None
    best.sort(reverse=True)
    if len(best) > 1 and best[1][0] == best[0][0]:
        return None
    return best[0][1]


def personality_labels(personality, category):
    if any(word in personality for word in CAUTIOUS):
        good = category in ('observe', 'guard', 'communicate', 'wait', 'hide')
    elif any(word in personality for word in BOLD):
        good = category in ('move', 'communicate', 'assist', 'use')
    else:
        good = True
    return int(good)


def candidates_for(world, actor_id, task, other_task, other_char):
    actor = world['characters'][actor_id]
    name = actor['name']
    goal = task['goal']
    rows = []
    loc = match_location(world['locations'], goal)
    if loc:
        at, lid, lname = loc
        if any(verb in goal for verb in MOVE):
            rows.append(('move', f'{name}走向{lname}。', task['id']))
        if any(verb in goal for verb in GUARD):
            rows.append(('guard', f'{name}守住{lname}。', task['id']))
    item = match_item(world['items'], goal)
    if item:
        iname = core(world['items'][item]['name'])
        rows.append(('observe', f'{name}查看{iname}。', task['id']))
        rows.append(('use', f'{name}拿起{iname}。', task['id']))
    target = next((c for cid, c in world['characters'].items() if cid != actor_id and c['name'] in goal), None)
    if target:
        rows.append(('communicate', f'{name}向{target["name"]}询问下一步。', task['id']))
        if item:
            rows.append(('assist', f'{name}把{core(world["items"][item]["name"])}递给{target["name"]}。', task['id']))
    if other_char:
        rows.append(('communicate', f'{name}向{other_char["name"]}求助。', task['id']))
    if other_task:
        rows.append(('other', f'{name}先放下手上这件事，转向另一件待办。', other_task['id']))
    rows.append(('wait', f'{name}留在原地等待。', task['id']))
    rows.append(('observe', f'{name}查看四周的变化。', task['id']))
    return rows, loc, item, target


def main():
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    rooms = {loc['id']: loc['name'] for loc in world['locations'].values()}
    rows = []
    actors = [cid for cid, row in world['characters'].items() if row.get('tasks')]
    for actor_id in actors:
        actor = world['characters'][actor_id]
        tasks = list(actor['tasks'].values())
        room = rooms.get(actor['initialPosition']['containerId'], '')
        for task, other_task in ((tasks[0], tasks[1] if len(tasks) > 1 else None),):
            other = next((c for cid, c in world['characters'].items() if cid != actor_id and c.get('tasks')), None)
            cands, loc, item, target = candidates_for(world, actor_id, task, other_task, other)
            for variant, flags in enumerate([
                {'item': True, 'target': True, 'open': True, 'repeat': False},
                {'item': False, 'target': True, 'open': True, 'repeat': False},
                {'item': True, 'target': False, 'open': True, 'repeat': False},
                {'item': True, 'target': True, 'open': False, 'repeat': True},
            ]):
                scene = (f"现场：物品{'在手边' if flags['item'] else '不在手边'}；"
                         f"目标人物{'在场' if flags['target'] else '不在场'}；"
                         f"道路{'畅通' if flags['open'] else '受阻'}；"
                         f"近期{'刚做过同样的事' if flags['repeat'] else '没有重复'}")
                context = f"{scene}；任务：{task['goal'][:60]}；个性：{actor.get('initialPersonality', '')[:60]}；角色：{actor['name']}；位置：{room}"
                for category, text, task_id in cands:
                    direct = task_id == task['id'] and category in ('move', 'guard', 'observe', 'use', 'communicate', 'assist')
                    task_label = int(direct)
                    personal = personality_labels(actor.get('initialPersonality', ''), category)
                    if category in ('move', 'guard'):
                        scene_ok = flags['open']
                    elif category == 'assist':
                        scene_ok = flags['item'] and flags['target'] and flags['open']
                    elif category in ('observe', 'use'):
                        scene_ok = flags['item'] or '四周' in text
                    elif category == 'communicate':
                        scene_ok = flags['target']
                    elif category == 'wait':
                        scene_ok = not flags['open'] or flags['repeat']
                    elif category == 'other':
                        scene_ok = not flags['open']
                    else:
                        scene_ok = True
                    if flags['repeat'] and category not in ('wait', 'other'):
                        scene_ok = False
                    rows.append({
                        'scenario': f"{actor_id}:{task['id']}:{variant}", 'actor': actor_id, 'variant': variant,
                        'candidate': text, 'category': category, 'context': context,
                        'task': task_label, 'personality': personal, 'scene': int(scene_ok),
                    })
    (PUB / 'judge-data.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf8')
    from collections import Counter
    print('rows', len(rows), 'scenarios', len({r['scenario'] for r in rows}),
          'labels', {k: dict(Counter(r[k] for r in rows)) for k in ('task', 'personality', 'scene')},
          'actors', len({r['actor'] for r in rows}))


if __name__ == '__main__':
    main()
