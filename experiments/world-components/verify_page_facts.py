"""Check the page rows against the committed record, without asking the adapter.

The browser record carries the text the page showed for each round. This script derives what each round
must mention straight from `world_points` and the initial world names - the subject, the origin and
destination for a move, the two sanity numbers, the recorded description text, or the fact that the point
carries no entity change at all - and then checks the page text against that.
"""
import json
import os
import pathlib
import sqlite3
import sys

RECORD = os.environ.get('WORLD_FACTS_RECORD', 'artifacts/next-runs/integration-r1/browser/record.json')
DATABASE = os.environ.get('WORLD_FACTS_DB', 'artifacts/next-runs/integration-r1/world.db')
SUMMARY = os.environ.get('WORLD_FACTS_VERIFY', 'artifacts/next-runs/integration-r1/verify.json')


def names_of(db, world_id):
    row = db.execute('SELECT initial_json FROM worlds WHERE id=?', (world_id,)).fetchone()
    initial = json.loads(row[0])
    names = {}
    for group in ('locations', 'characters', 'items'):
        for key, value in (initial.get(group) or {}).items():
            names[key] = value.get('name') or key
    return names


def previous_positions(db, world_id):
    """Position, sanity and tasks per point, read from the checkpoints in sequence order."""
    positions = {}
    for point_id, state_json in db.execute(
            'SELECT point_id, state_json FROM world_state_checkpoints WHERE world_id=?', (world_id,)):
        state = json.loads(state_json)
        characters = state.get('characters') or {}
        positions[point_id] = {
            'position': {key: (value.get('position') or {}).get('containerId')
                         for key, value in characters.items()},
            'sanity': {key: value.get('sanity') for key, value in characters.items()},
            'tasks': {key: {task_id: {'goal': task.get('goal'), 'status': task.get('status')}
                            for task_id, task in (value.get('tasks') or {}).items()}
                      for key, value in characters.items()},
        }
    return positions


def expectations(db, world_id):
    names = names_of(db, world_id)
    states = previous_positions(db, world_id)
    rows = []
    for point_id, sequence, kind, previous, delta_json in db.execute(
            'SELECT id, sequence, kind, previous_point_id, delta_json FROM world_points '
            'WHERE world_id=? ORDER BY sequence', (world_id,)):
        delta = json.loads(delta_json) if delta_json else {}
        expected = {'pointId': point_id, 'sequence': sequence, 'kind': kind, 'must': [], 'mustNot': []}
        # every delta kind in this world has a display shape; a hint here would mean the adapter lost one
        expected['mustNot'].append('尚未展示')
        if kind == 'root':
            expected['mustNot'].append('没有实体变化')
        elif not delta:
            expected['must'].append('没有实体变化')
        for entity_id, change in delta.items():
            subject = names.get(entity_id, entity_id)
            expected['must'].append(subject)
            if change.get('positionSet'):
                to_id = change['positionSet'].get('containerId')
                before = (states.get(previous) or {}).get('position', {}).get(entity_id)
                if before:
                    expected['must'].append('%s从%s到%s' % (subject, names.get(before, before), names.get(to_id, to_id)))
                else:
                    expected['must'].append(names.get(to_id, to_id))
            if change.get('sanitySet') is not None:
                before = (states.get(previous) or {}).get('sanity', {}).get(entity_id)
                expected['must'].append('（%s→%s）' % (before, change['sanitySet']))
            for entry in change.get('appearanceChanges') or []:
                expected['must'].append(entry['text'])
            for entry in change.get('personalityChanges') or []:
                expected['must'].append(entry['text'])
            if change.get('tasksAchieved') or change.get('subtasksAdded'):
                committed = (states.get(point_id) or {}).get('tasks', {}).get(entity_id, {})
                for task_id in change.get('tasksAchieved') or []:
                    task = committed.get(task_id) or {}
                    if not task.get('goal') or task.get('status') != 'achieved':
                        expected['must'].append('暂无法恢复')
                    else:
                        expected['must'].append('%s达成任务：%s。' % (subject, task['goal']))
                for task in change.get('subtasksAdded') or []:
                    goal = (task or {}).get('goal')
                    if not goal:
                        expected['must'].append('暂无法恢复')
                    else:
                        expected['must'].append('%s新增小任务：%s' % (subject, goal))
            if set(change) - {'entityId', 'positionSet', 'sanitySet', 'appearanceChanges',
                              'personalityChanges', 'tasksAchieved', 'subtasksAdded'}:
                expected['must'].append('暂无法恢复')
        rows.append(expected)
    return rows


def main():
    record = json.loads(pathlib.Path(RECORD).read_text(encoding='utf-8'))
    world_id = record['worldId']
    db = sqlite3.connect(DATABASE)
    rows = expectations(db, world_id)
    # 用页面上出现过的最大快照（脚本末尾还会再加一个回合），并只比对快照覆盖的点位
    steps = {key: value for key, value in record['steps'].items() if isinstance(value, list)}
    longest = max(steps, key=lambda key: len(steps[key]))
    page = {i: item['text'] for i, item in enumerate(steps[longest])}
    refreshed = {i: item['text'] for i, item in enumerate(record['steps']['afterRun'])}
    rows = rows[:len(page)]
    if len(rows) != len(page):
        problems_prefix = ['page shows %d rounds, record holds %d points' % (len(page), len(expectations(db, world_id)))]
    else:
        problems_prefix = []
    problems = list(problems_prefix)
    for index, expected in enumerate(rows):
        text = page.get(index, '')
        after = refreshed.get(index, '')
        for fragment in expected['must']:
            if fragment not in text:
                problems.append('round %d (%s) missing %r' % (index, expected['pointId'], fragment))
        for fragment in expected['mustNot']:
            if fragment in text:
                problems.append('round %d (%s) must not say %r' % (index, expected['pointId'], fragment))
        if index < len(refreshed) and text != refreshed.get(index, ''):
            problems.append('round %d differs between the first run and after refresh' % index)
    summary = {
        'worldId': world_id,
        'rounds': len(rows),
        'checks': sum(len(row['must']) + len(row['mustNot']) + 1 for row in rows),
        'problems': problems,
        'snapshot': longest,
        'perRound': [{'pointId': row['pointId'], 'sequence': row['sequence'], 'must': row['must'],
                      'page': page.get(index, '')[:200]} for index, row in enumerate(rows)],
    }
    out = pathlib.Path(SUMMARY)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print('rounds %d checks %d problems %d' % (len(rows), summary['checks'], len(problems)))
    for problem in problems:
        print('  ' + problem)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
