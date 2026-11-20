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
    """Position, sanity, tasks and appearance per point, read from the checkpoints."""
    positions = {}
    for point_id, state_json in db.execute(
            'SELECT point_id, state_json FROM world_state_checkpoints WHERE world_id=?', (world_id,)):
        state = json.loads(state_json)
        characters = state.get('characters') or {}
        items = state.get('items') or {}
        positions[point_id] = {
            'position': {key: (value.get('position') or {}).get('containerId')
                         for key, value in characters.items()},
            'sanity': {key: value.get('sanity') for key, value in characters.items()},
            'tasks': {key: {task_id: {'goal': task.get('goal'), 'status': task.get('status')}
                            for task_id, task in (value.get('tasks') or {}).items()}
                      for key, value in characters.items()},
            # appearance belongs to characters and items alike; keep the kind so a missing roster entry is visible
            'appearance': {**{key: value.get('appearanceChanges') or [] for key, value in items.items()},
                           **{key: value.get('appearanceChanges') or [] for key, value in characters.items()}},
        }
    return positions


def expectations(db, world_id, problems):
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
                stored = (states.get(point_id) or {}).get('appearance', {}).get(entity_id, [])
                match = [item for item in stored if item.get('id') == entry.get('id')]
                if len(match) != 1:
                    problems.append('appearance delta at %s names %r, the checkpoint holds %d such entries'
                                    % (point_id, entry.get('id'), len(match)))
                    expected['must'].append('暂无法恢复')
                    continue
                stored_entry = match[0]
                if any((
                    stored_entry.get('text') != entry.get('text'),
                    stored_entry.get('supersedes') != (entry.get('supersedes') or []),
                    stored_entry.get('sourcePointId') != point_id,
                    stored_entry.get('sourceSequence') != sequence,
                    stored_entry.get('active') is not True,
                )):
                    problems.append('appearance delta/checkpoint disagree at %s (%s)' % (point_id, entity_id))
                    expected['must'].append('暂无法恢复')
                    continue
                # 模板叙事句来自 projectCommittedNarration：它先核对增量与检查点，再渲染同一段原文
                expected['must'].append('%s的外貌变化为「%s」' % (subject, stored_entry['text']))
                expected['must'].append('%s：%s。' % (subject, stored_entry['text']))
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


def appearance_audit(db, world_id, problems):
    """For the smile flow, verify every saved appearance history point by point.

    Repeated commands must preserve the prior list, and each new change must
    carry the allocated ID and its own point as source. This flow only adds
    descriptions; it does not exercise supersession.
    """
    states = previous_positions(db, world_id)
    checks = []
    for point_id, sequence, previous, delta_json in db.execute(
            'SELECT id, sequence, previous_point_id, delta_json FROM world_points '
            'WHERE world_id=? AND kind != ? ORDER BY sequence', (world_id, 'root')):
        delta = json.loads(delta_json) if delta_json else {}
        if point_id not in states or previous not in states:
            problems.append('checkpoint missing for %s or its predecessor %s' % (point_id, previous))
            continue
        before = states[previous]['appearance']
        after = states[point_id]['appearance']
        for actor_id in sorted(set(before) | set(after)):
            changes = (delta.get(actor_id) or {}).get('appearanceChanges') or []
            expected = before.get(actor_id, []) + [
                dict(change, active=True, sourcePointId=point_id, sourceSequence=sequence) for change in changes]
            matches = expected == after.get(actor_id, [])
            checks.append({'pointId': point_id, 'sequence': sequence, 'actorId': actor_id,
                           'added': changes, 'stored': after.get(actor_id, []), 'matches': matches})
            if not matches:
                problems.append('appearance history disagrees at %s/%s' % (point_id, actor_id))
    return checks


def facts_route_audit(record, db, world_id, names, problems):
    """The page reads its sentences from GET /world/facts; check that response, not the page text.

    For an appearance point the returned fact must name the committed change ID
    and the point that recorded it. A point whose command was refused has an
    empty delta, so it must return the empty-delta sentence and no appearance
    fact - that is the evidence that a repeated command added nothing.
    """
    states = previous_positions(db, world_id)
    by_point = {}
    for request in record.get('factsRequests') or []:
        point_id = (request.get('url') or '').rstrip('/').split('/')[-1]
        if request.get('status') != 200:
            problems.append('facts request for %s answered %s' % (point_id, request.get('status')))
            continue
        if point_id in states:
            by_point[point_id] = request.get('body') or {}
    checks = []
    for point_id, sequence, kind, delta_json in db.execute(
            'SELECT id, sequence, kind, delta_json FROM world_points WHERE world_id=? ORDER BY sequence', (world_id,)):
        if kind == 'root':
            continue
        delta = json.loads(delta_json) if delta_json else {}
        body = by_point.get(point_id)
        if body is None:
            problems.append('no facts response captured for point %s' % point_id)
            continue
        facts = body.get('facts') or []
        appearance_facts = [fact for fact in facts if fact.get('kind') == 'appearance_changed']
        committed = states.get(point_id, {}).get('appearance', {})
        for actor_id, change in delta.items():
            for entry in change.get('appearanceChanges') or []:
                stored = next((item for item in committed.get(actor_id, [])
                               if item.get('id') == entry.get('id')), None)
                if stored is None:
                    problems.append('appearance change %s is not in the checkpoint at %s' % (entry.get('id'), point_id))
                    continue
                expected = '%s：%s。' % (names.get(actor_id, actor_id), stored.get('text'))
                fact = next((item for item in appearance_facts if item.get('changeId') == entry.get('id')), None)
                provenance = (fact or {}).get('provenance') or {}
                matches = bool(fact) and fact.get('sentence') == expected                     and provenance.get('pointId') == point_id                     and 'appearanceChanges.%s.sourcePointId' % entry.get('id') in (provenance.get('fieldsRead') or [])
                checks.append({'pointId': point_id, 'sequence': sequence, 'actorId': actor_id,
                               'changeId': entry.get('id'), 'stored': stored, 'expected': expected,
                               'matches': matches})
                if not matches:
                    problems.append('facts response for %s lacks the committed appearance change %s'
                                    % (point_id, entry.get('id')))
        if not delta:
            if appearance_facts:
                problems.append('empty-delta point %s still reports an appearance change' % point_id)
            if not any(fact.get('kind') == 'no_change' for fact in facts):
                problems.append('empty-delta point %s lacks the no-change sentence' % point_id)
    return checks


def main():
    record = json.loads(pathlib.Path(RECORD).read_text(encoding='utf-8'))
    world_id = record['worldId']
    db = sqlite3.connect(DATABASE)
    names = names_of(db, world_id)
    problems = []
    rows = expectations(db, world_id, problems)
    # 用页面上出现过的最大快照（脚本末尾还会再加一个回合）
    steps = {key: value for key, value in record['steps'].items() if isinstance(value, list)}
    longest = max(steps, key=lambda key: len(steps[key]))
    page = {i: item['text'] for i, item in enumerate(steps[longest])}
    refreshed = {i: item['text'] for i, item in enumerate(record['steps']['afterRun'])}
    if len(rows) != len(page):
        problems.append('page shows %d rounds, record holds %d points' % (len(page), len(rows)))
    appearance_checks = appearance_audit(db, world_id, problems) if record.get('appearance') else []
    route_checks = facts_route_audit(record, db, world_id, names, problems) if record.get('appearance') else []
    if record['steps']['afterRun'] != record['steps']['afterRefresh']:
        problems.append('refresh changed the round log')
    if not record['steps']['historyStable']['previousRoundsUnchanged']:
        problems.append('new commands changed earlier rounds')
    if record.get('problems') or record.get('errors'):
        problems.append('browser acceptance reported errors')
    if record.get('appearance'):
        appearance_rounds = [row for row in rows if any('面带微笑' in part for part in row['must'])]
        if len(appearance_rounds) != 1:
            problems.append('expected exactly one committed appearance change, found %d' % len(appearance_rounds))
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
    checks = (sum(len(row['must']) + len(row['mustNot']) + 1 for row in rows)
              + len(appearance_checks) + len(route_checks))
    summary = {
        'worldId': world_id,
        'rounds': len(rows),
        'checks': checks,
        'problems': problems,
        'snapshot': longest,
        'appearanceStateChecks': appearance_checks,
        'factsRouteChecks': route_checks,
        'perRound': [{'pointId': row['pointId'], 'sequence': row['sequence'], 'must': row['must'],
                      'page': page.get(index, '')[:200]} for index, row in enumerate(rows)],
    }
    out = pathlib.Path(SUMMARY)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + chr(10), encoding='utf-8', newline=chr(10))
    print('rounds %d checks %d problems %d' % (len(rows), checks, len(problems)))
    for problem in problems:
        print('  ' + problem)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
