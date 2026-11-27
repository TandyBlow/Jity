# -*- coding: utf-8 -*-
"""Freeze relation probes from existing verified facts (no authored rows here).

Families built now:
  outcome   one row per unique results fact; gold = the kernel outcome marker
            (achieved/partial/not_achieved/blocked/no_change); input text strips
            the marker and structured tags.
  target    one row per unique fact carrying 涉及=; gold = the involved entity.
  condition task goal vs this point's facts; gold = the kernel task status flip
            (pending -> achieved). Negatives are the same owner's pending task
            whose goal wording overlaps the fact most (hard negative).
  cross_turn the same flip, but the input also carries the previous point's
            facts in the same session; gold and negatives as in condition.
A manifest records source and output sha256, counts, and the route-family
holdout. Model arms must read only the frozen files."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'real-semantic.jsonl'
WORLD = HERE.parents[2] / 'frontend/public/worlds/dragon-raja-free-day.world.json'
OUT = HERE / 'relation-probes'
HOLDOUT_ROUTES = {'sm6-', 'sm10-', 'sm14-', 'sm18-', 'sm22-'}
MARKERS = {'（达到目的）': 'achieved', '（只完成一部分）': 'partial', '（没有成功）': 'not_achieved',
           '（被阻止）': 'blocked', '（没有变化）': 'no_change'}
STRIP = re.compile('；?(?:去向|环境|信息|涉及)=[^；。]*')


def sha256_text(text):
    return hashlib.sha256(text.encode('utf8')).hexdigest()


def grams(text):
    clean = re.sub('[^一-鿿A-Za-z0-9]', '', text)
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


def overlap(fact, goal):
    goal_grams = grams(goal)
    return len(goal_grams & grams(fact)) / max(1, len(goal_grams))


def task_goals():
    world = json.loads(WORLD.read_text(encoding='utf8'))
    initial = world.get('initial') or world
    out = {}
    for cid, character in (initial.get('characters') or {}).items():
        tasks = character.get('tasks') or {}
        for tid, task in (tasks.items() if isinstance(tasks, dict) else ()):
            if task.get('goal'):
                out[(cid, tid)] = task['goal']
    return out


def main():
    rows = [json.loads(line) for line in SOURCE.read_text(encoding='utf8').splitlines() if line.strip()]
    rows = [row for row in rows if row.get('source') == 'semantic']
    goals = task_goals()
    outcome = {}
    target = {}
    condition = {}
    cross = {}
    sessions = {}
    for row in rows:
        sessions.setdefault(row.get('evidenceFile'), []).append(row)
    for members in sessions.values():
        members.sort(key=lambda r: int((r.get('before') or {}).get('historyCount') or 0))
        for index, row in enumerate(members):
            if index == 0:
                continue
            prior = members[index - 1]
            route = row['id'].split('-')[0] + '-'
            split = 'test' if str(row['id']).startswith('sc') or route in HOLDOUT_ROUTES else 'train'
            prior_by_owner = {}
            for fact in prior.get('settled') or []:
                if fact.get('task') == 'results' and fact.get('text'):
                    prior_by_owner.setdefault(fact.get('key'), []).append(str(fact['text']))
            own_by_owner = {}
            for fact in row.get('settled') or []:
                if fact.get('task') == 'results' and fact.get('text'):
                    own_by_owner.setdefault(fact.get('key'), []).append(str(fact['text']))
            for change in (row.get('stateDiff') or {}).get('changed') or []:
                key = str(change.get('key') or '')
                if not key.startswith('char:'):
                    continue
                owner = key.split(':', 1)[1]
                before_tasks = (change.get('before') or {}).get('tasks') or {}
                after_tasks = (change.get('after') or {}).get('tasks') or {}
                if not own_by_owner.get(owner):
                    continue
                prior_text = STRIP.sub('', '；'.join(prior_by_owner.get(owner) or []))
                fact_text = STRIP.sub('', '；'.join(own_by_owner.get(owner) or []))
                pending = [(tid, goals[(owner, tid)]) for tid, status in after_tasks.items()
                           if status != 'achieved' and (owner, tid) in goals]
                for tid, status in after_tasks.items():
                    goal = goals.get((owner, tid))
                    if not goal or status != 'achieved' or before_tasks.get(tid) == 'achieved':
                        continue
                    record = {'id': f"{row['id']}#x{tid}", 'rowId': row['id'], 'family': 'cross_turn',
                              'input': f"任务：{goal}\n上一回合：{prior_text or '（无）'}\n本回合：{fact_text}",
                              'goal': goal, 'gold': 1, 'split': split,
                              'provenance': 'program_task_flip', 'class': row.get('class')}
                    cross.setdefault((owner, tid, prior_text, fact_text), record)
                if pending:
                    hard = max(pending, key=lambda pair: overlap(f'{prior_text}；{fact_text}', pair[1]))
                    record = {'id': f"{row['id']}#x{hard[0]}n", 'rowId': row['id'], 'family': 'cross_turn',
                              'input': f"任务：{hard[1]}\n上一回合：{prior_text or '（无）'}\n本回合：{fact_text}",
                              'goal': hard[1], 'gold': 0, 'split': split,
                              'provenance': 'program_task_flip', 'class': row.get('class')}
                    cross.setdefault((owner, hard[0], prior_text, fact_text), record)
    for row in rows:
        route = row['id'].split('-')[0] + '-'
        split = 'test' if str(row['id']).startswith('sc') or route in HOLDOUT_ROUTES else 'train'
        # 条件族：任务状态翻转是 gold；负例取同一人物措辞最近的在办任务
        facts_by_owner = {}
        for fact in row.get('settled') or []:
            if fact.get('task') == 'results' and fact.get('text'):
                facts_by_owner.setdefault(fact.get('key'), []).append(str(fact['text']))
        for change in (row.get('stateDiff') or {}).get('changed') or []:
            key = str(change.get('key') or '')
            if not key.startswith('char:'):
                continue
            owner = key.split(':', 1)[1]
            before_tasks = (change.get('before') or {}).get('tasks') or {}
            after_tasks = (change.get('after') or {}).get('tasks') or {}
            fact_text = '；'.join(facts_by_owner.get(owner) or []).strip()
            if not fact_text:
                continue
            pending = [(tid, goals[(owner, tid)]) for tid, status in after_tasks.items()
                       if status != 'achieved' and (owner, tid) in goals]
            for tid, status in after_tasks.items():
                goal = goals.get((owner, tid))
                if not goal or status != 'achieved' or before_tasks.get(tid) == 'achieved':
                    continue
                record = {'id': f"{row['id']}#c{tid}", 'rowId': row['id'], 'family': 'condition',
                          'input': f"任务：{goal}\n事实：{STRIP.sub('', fact_text)}", 'goal': goal,
                          'gold': 1, 'split': split, 'provenance': 'program_task_flip', 'class': row.get('class')}
                condition.setdefault((owner, tid, fact_text), record)
            if pending:
                hard = max(pending, key=lambda pair: overlap(fact_text, pair[1]))
                record = {'id': f"{row['id']}#c{hard[0]}n", 'rowId': row['id'], 'family': 'condition',
                          'input': f"任务：{hard[1]}\n事实：{STRIP.sub('', fact_text)}", 'goal': hard[1],
                          'gold': 0, 'split': split, 'provenance': 'program_task_flip', 'class': row.get('class')}
                condition.setdefault((owner, hard[0], fact_text), record)
        for index, fact in enumerate(row.get('settled') or []):
            if fact.get('task') != 'results' or not fact.get('text'):
                continue
            text = str(fact['text'])
            key = (fact.get('key'), text)
            if key in outcome:
                continue
            raw = text
            for marker, label in MARKERS.items():
                raw = raw.replace(marker, '')
            clean = STRIP.sub('', raw).strip()
            involved = re.search('涉及=([^；。]*)', text)
            record = {'id': f"{row['id']}#{index}", 'rowId': row['id'], 'family': 'outcome',
                      'input': clean, 'raw': text, 'gold': None, 'split': split,
                      'provenance': 'program_record', 'class': row.get('class')}
            for marker, label in MARKERS.items():
                if marker in text:
                    record['gold'] = label
                    break
            if record['gold']:
                outcome[key] = record
            if involved:
                target.setdefault((fact.get('key'), clean), {
                    'id': f"{row['id']}#t{index}", 'rowId': row['id'], 'family': 'target',
                    'input': clean, 'raw': text, 'gold': [part.strip() for part in involved.group(1).split(',') if part.strip()],
                    'split': split, 'provenance': 'program_span', 'class': row.get('class')})
    OUT.mkdir(exist_ok=True)
    files = {}
    for name, records in (('outcome', list(outcome.values())), ('target', list(target.values())),
                          ('condition', list(condition.values())), ('cross_turn', list(cross.values()))):
        payload = ''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records)
        path = OUT / f'{name}.jsonl'
        path.write_text(payload, encoding='utf8')
        files[name] = {'rows': len(records), 'sha256': sha256_text(payload),
                       'split': dict(Counter(record['split'] for record in records)),
                       'gold': dict(Counter(str(record['gold']) for record in records))}
    manifest = {'source': {'file': SOURCE.name, 'sha256': sha256_text(SOURCE.read_text(encoding='utf8'))},
                'holdoutRoutes': sorted(HOLDOUT_ROUTES), 'files': files,
                'note': 'Outcome gold is the kernel marker (not independent semantics); target gold is the program 涉及 span; condition/cross_turn gold is the kernel task flip (pending -> achieved) with hard negatives from the same owner; cross_turn adds the previous point of the same session as 上一回合.'}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
