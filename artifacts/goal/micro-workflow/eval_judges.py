# -*- coding: utf-8 -*-
"""Four-arm offline comparison on held-out actors: category head, task-only
judge, three-judge sum, and the oracle (a reasonable candidate exists)."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

ROOT = Path('D:/others/Jity')
PUB = ROOT / 'artifacts/goal/micro-workflow'
SNAP = ROOT / 'artifacts/benchmark/minirbt-h256-snapshot'
WORLD = ROOT / 'data/worlds/dragon-raja-free-day.world.json'
BEHAVIOR_LABELS = ['move', 'assist', 'guard', 'communicate', 'observe', 'use', 'other']


def main():
    tok = BertTokenizer(vocab_file=str(SNAP / 'vocab.txt'))
    judges = ort.InferenceSession(str(ROOT / '.local/micro-heads/judge-heads-int8.onnx'), providers=['CPUExecutionProvider'])
    behavior = ort.InferenceSession(str(ROOT / '.local/micro-heads/behavior-head-int8.onnx'), providers=['CPUExecutionProvider'])
    world = json.loads(WORLD.read_text(encoding='utf8'))['initial']
    rooms = {loc['id']: loc['name'] for loc in world['locations'].values()}
    rows = [json.loads(line) for line in open(PUB / 'judge-data.jsonl', encoding='utf8')]
    held = {'caesar', 'lin', 'qin', 'tomiyama'}
    scenarios = defaultdict(list)
    for row in rows:
        if row['actor'] not in held:
            continue
        enc = tok(row['context'], row['candidate'], truncation=True, max_length=128)
        ids = np.array([enc['input_ids']], dtype=np.int64)
        mask = np.array([enc['attention_mask']], dtype=np.int64)
        task, personality, scene = judges.run(None, {'input_ids': ids, 'attention_mask': mask})
        scenarios[row['scenario']].append({**row, 'score_task': float(task[0]), 'score_personality': float(personality[0]), 'score_scene': float(scene[0])})
    arms = {name: Counter() for name in ('category', 'task_only', 'multi', 'oracle')}
    for scenario, items in scenarios.items():
        actor_id = scenario.split(':')[0]
        actor = world['characters'][actor_id]
        task = next(iter(actor['tasks'].values()))
        head_input = f"角色：{actor['name']}；位置：{rooms.get(actor['initialPosition']['containerId'], '')}；个性：{actor.get('initialPersonality', '')[:40]}；待办：{task['id']}={task['goal']}"
        enc = tok(head_input, truncation=True, max_length=96)
        logits = behavior.run(['logits'], {'input_ids': np.array([enc['input_ids']], dtype=np.int64),
                                           'attention_mask': np.array([enc['attention_mask']], dtype=np.int64)})[0][0]
        category = BEHAVIOR_LABELS[int(logits.argmax())]
        picked = next((row for row in items if row['category'] == category), None)
        for arm, row in (
            ('category', picked),
            ('task_only', max(items, key=lambda r: r['score_task'])),
            ('multi', max(items, key=lambda r: r['score_task'] + r['score_personality'] + r['score_scene'])),
        ):
            if row is None:
                arms[arm]['no_selection'] += 1
                continue
            arms[arm]['scenarios'] += 1
            arms[arm]['task'] += int(row['task'])
            arms[arm]['scene'] += int(row['scene'])
            arms[arm]['personality'] += int(row['personality'])
            reasonable = row['scene'] == 1 and (row['task'] == 1 or row['category'] in ('wait', 'other'))
            arms[arm]['reasonable'] += int(reasonable)
        arms['oracle']['scenarios'] += 1
        arms['oracle']['reasonable'] += int(any(r['scene'] == 1 and (r['task'] == 1 or r['category'] in ('wait', 'other')) for r in items))
    out = {arm: dict(counts) for arm, counts in arms.items()}
    for arm, counts in out.items():
        n = counts.get('scenarios', 0)
        counts['reasonable_rate'] = round(counts.get('reasonable', 0) / n, 3) if n else 0
        counts['task_rate'] = round(counts.get('task', 0) / n, 3) if n else 0
        counts['scene_rate'] = round(counts.get('scene', 0) / n, 3) if n else 0
    (PUB / 'judge-eval.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
