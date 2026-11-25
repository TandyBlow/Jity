# -*- coding: utf-8 -*-
"""Continuation contrast scenarios for the four heads.

Mirrors the browser candidate generator: task-linked move/guard/use/communicate/
assist candidates plus wait/observe. Variants vary the event record and repeat
kind. Labels are rule-derived and multi-positive; the evaluation reports the
rule arm on the same rows, so the model is never credited with beating a rule
it was trained to imitate.
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'

MOVE = ['前往', '走向', '走进', '进入', '赶到', '回到', '退到', '离开', '去', '到']
GUARD = ['守住', '护住', '挡住', '拦住', '守']
RECENT_EVENT = '远处传来一声枪响'


def core(name):
    value = re.sub(r'^.+?的', '', name)
    return value if len(value) >= 2 else name


def overlap(left, right):
    best = 0
    for i in range(len(left)):
        for j in range(i + 2, len(left) + 1):
            if left[i:j] in right:
                best = max(best, j - i)
    return best


def match_items(text, names, owner):
    scored = [(max(overlap(core(name), text), overlap(name, text)), cid, name)
              for cid, name in names]
    scored = [row for row in scored if row[0] >= 2]
    scored.sort(reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        mine = [row for row in scored if row[0] == scored[0][0] and owner and row[2].startswith(f'{owner}的')]
        return mine[0][1] if len(mine) == 1 else None
    return scored[0][1]


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
            if text.rfind(part) >= 0:
                suffix.append((text.rfind(part), lid, part))
                break
    if full:
        full.sort(reverse=True)
        return full[0] if len(full) == 1 or full[0][0] != full[1][0] else None
    if not suffix:
        return None
    suffix.sort(key=lambda row: (row[0], len(row[2])), reverse=True)
    if len(suffix) > 1 and (suffix[0][0] == suffix[1][0] or suffix[0][2] == suffix[1][2]):
        return None
    return suffix[0]


def room_of(state, entity_id):
    pos = state['characters'][entity_id]['initialPosition']
    container = pos['containerId']
    seen = set()
    while container in state['items'] and container not in seen:
        seen.add(container)
        container = state['items'][container]['initialPosition']['containerId']
    if container in state['characters']:
        return room_of(state, container)
    return container


def candidates_for(state, actor_id, recent):
    actor = state['characters'][actor_id]
    name = actor['name']
    room = room_of(state, actor_id)
    room_name = state['locations'][room]['name']
    visible = sorted(cid for cid in state['characters'] if cid != actor_id and room_of(state, cid) == room)
    items = [(iid, item['name']) for iid, item in state['items'].items()
             if room_of_item(state, iid) == room or item['initialPosition']['containerId'] == actor_id]
    # The scene view sorts tasks by status then id before the generator reads
    # the first three; mirror that order or the candidate sets diverge.
    pending = sorted(
        [(tid, task['goal']) for tid, task in actor['tasks'].items() if task.get('status') == 'pending'],
        key=lambda row: row[0],
    )
    rows = []

    def push(category, text, task_id, target_ids=None, item_ids=None):
        if any(row['text'] == text for row in rows):
            return
        rows.append({
            'category': category, 'text': text, 'task_id': task_id,
            'target_ids': target_ids or [], 'item_ids': item_ids or [],
        })

    for tid, _goal in pending[1:2]:
        push('other', f'{name}先放下手上这件事，转向另一件待办。', tid)
    if recent:
        push('observe', f'{name}查看{room_name}里的变化。', pending[0][0] if pending else '')
    push('wait', f'{name}留在{room_name}等待。', pending[0][0] if pending else '')
    for tid, goal in pending[:3]:
        loc = match_location(state['locations'], goal)
        if loc:
            _at, lid, lname = loc
            if any(verb in goal for verb in MOVE) and room_name != lname:
                push('move', f'{name}走向{lname}。', tid)
            if any(verb in goal for verb in GUARD):
                push('guard', f'{name}守住{lname}。', tid)
        item_id = match_items(goal, items, name)
        if item_id:
            item_name = core(dict(items)[item_id])
            push('observe', f'{name}查看{item_name}。', tid, item_ids=[item_id])
            push('use', f'{name}拿起{item_name}。', tid, item_ids=[item_id])
        target = next((cid for cid in visible if state['characters'][cid]['name'] in goal), None)
        if target:
            push('communicate', f'{name}向{state["characters"][target]["name"]}询问下一步。', tid, target_ids=[target])
            if item_id:
                item_name = core(dict(items)[item_id])
                push('assist', f'{name}把{item_name}递给{state["characters"][target]["name"]}。', tid,
                     target_ids=[target], item_ids=[item_id])
        helper = next((cid for cid in visible if cid != target), None)
        if helper:
            push('communicate', f'{name}向{state["characters"][helper]["name"]}求助。', tid, target_ids=[helper])
    return rows[:10], room_name, visible


def room_of_item(state, item_id):
    container = state['items'][item_id]['initialPosition']['containerId']
    seen = set()
    while container in state['items'] and container not in seen:
        seen.add(container)
        container = state['items'][container]['initialPosition']['containerId']
    if container in state['characters']:
        return room_of(state, container)
    return container


def labels_for(row, recent, repeat, protagonist_id, protagonist_name):
    text = row['text']
    category = row['category']
    task_pending = bool(row['task_id'])
    involves = protagonist_id in row['target_ids'] or protagonist_name in text
    novelty = 0
    if repeat == 'same_world' or category == 'wait':
        novelty = 0
    elif recent or repeat == 'new_world':
        novelty = 1
    elif task_pending and category not in ('wait', 'observe'):
        novelty = 1
    elif category == 'observe' and not recent:
        novelty = 0
    else:
        novelty = 1
    unfinished = 0
    if category != 'wait' and (task_pending or (recent and category in ('guard', 'observe', 'move', 'communicate', 'assist'))):
        unfinished = 1
    necessity = 0
    if repeat != 'same_world' and category != 'wait':
        if recent and category in ('guard', 'observe', 'move', 'communicate', 'assist'):
            necessity = 1
        elif task_pending and category in ('move', 'guard', 'use', 'assist', 'communicate'):
            necessity = 1
    intervene = 1 if involves and category in ('communicate', 'assist', 'guard', 'move', 'use') else 0
    return {
        'novelty': novelty, 'unfinished': unfinished, 'necessity': necessity, 'intervene': intervene,
        'involves_protagonist': int(involves), 'repeat': repeat,
    }


def repeat_label(repeat):
    return {'new': '没有重复', 'new_world': '做过类似的事但世界已变', 'same_world': '刚做过同样的事且世界未变'}[repeat]


def rank(row):
    if row['category'] == 'wait':
        return 3
    if row['category'] == 'observe' and not row.get('task_id'):
        return 2
    return 0 if row.get('task_id') else 1


def main():
    raw = json.loads(WORLD.read_text(encoding='utf8'))
    state = raw['initial']
    protagonist_id = state['protagonistId']
    protagonist_name = state['characters'][protagonist_id]['name']
    rows = []
    actors = [cid for cid in state['characters'] if state['characters'][cid].get('tasks')]
    for actor_id in actors:
        for variant, recent, player_present, idle in (
            ('base', False, False, False), ('event', True, False, False),
            ('repeat_same', False, False, False), ('continuous', True, False, False),
            ('player_present', False, True, False), ('idle', False, False, True),
        ):
            case = json.loads(json.dumps(state))
            if player_present:
                # A same-room protagonist makes the helper candidate a player
                # decision, which is the intervene positive the held-out actors
                # otherwise never see.
                case['characters'][protagonist_id]['initialPosition']['containerId'] = room_of(state, actor_id)
            if idle:
                for task in case['characters'][actor_id]['tasks'].values():
                    task['status'] = 'achieved'
            cands, room_name, _visible = candidates_for(case, actor_id, recent)
            if not cands:
                continue
            repeat_text = next((row['text'] for row in cands if row['category'] in ('move', 'guard')), cands[0]['text'])
            for row in cands:
                if variant == 'repeat_same' and row['text'] == repeat_text:
                    repeat = 'same_world'
                elif variant == 'continuous' and row['text'] == repeat_text:
                    repeat = 'new_world'
                else:
                    repeat = 'new'
                labels = labels_for(row, recent, repeat, protagonist_id, protagonist_name)
                context = (
                    f"现场：本轮事件={RECENT_EVENT if recent else '无'}；重复={repeat_label(repeat)}；"
                    f"任务状态={'未完成' if row['task_id'] else '无待办'}；涉及主角={'是' if labels['involves_protagonist'] else '否'}；"
                    f"类别={row['category']}；角色={state['characters'][actor_id]['name']}；位置={room_name}；"
                    f"个性={state['characters'][actor_id].get('initialPersonality', '')[:40]}"
                )
                rows.append({
                    'scenario': f'{actor_id}:{variant}', 'actor': actor_id, 'variant': variant,
                    'candidate': row['text'], 'category': row['category'], 'context': context,
                    'task_id': row['task_id'], **labels,
                })
    held = sorted(set(actors))[::4]
    for row in rows:
        row['split'] = 'test' if row['actor'] in held else 'train'
    (PUB / 'continuation-data.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf8')
    print('rows', len(rows), 'scenarios', len({row['scenario'] for row in rows}),
          'actors', len({row['actor'] for row in rows}), 'held', held)
    print('labels', {key: dict(Counter(row[key] for row in rows)) for key in ('novelty', 'unfinished', 'necessity', 'intervene')})
    print('categories', dict(Counter(row['category'] for row in rows)))


if __name__ == '__main__':
    main()
