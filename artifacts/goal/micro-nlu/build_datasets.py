# -*- coding: utf-8 -*-
"""Align captured semantic prompts with model answers and emit four datasets.

Semantic prompts are logged per attempt; a call with retries consumes several
prompts. Use the FIRST prompt (no repair feedback) with the call's final answer.
"""
import json
from pathlib import Path

ROOT = Path('D:/others/Jity')
SRC = ROOT / 'artifacts/goal/micro-nlu'
OUT = ROOT / '.local/micro-nlu'
OUT.mkdir(parents=True, exist_ok=True)

FILES = [SRC / f'run138-capture-chunk{i}.json' for i in range(1, 6)]
MARKERS = [('行动判断器', 'action'), ('牵连判断器', 'targets'), ('反应生成器', 'reaction'),
           ('共同结算器', 'results'), ('位置结算器', 'position')]


def family_of(prompt: str) -> str | None:
    for marker, family in MARKERS:
        if marker in prompt[:400]:
            return family
    return None


def parsed(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return None


def logical_calls(turn):
    """Return {family: [(attempts, final_raw)]} in order."""
    out = {name: [] for name in ('action', 'targets', 'reaction', 'results', 'position')}
    actions = [row for row in (turn.get('actions') or [])
               if row.get('recordKind') != 'result' and row.get('task') in ('action', 'targets', 'reaction')]
    grouped = []
    for row in actions:
        key = (row.get('task'), row.get('key'))
        if grouped and grouped[-1]['key'] == key:
            grouped[-1]['attempts'] += 1
            if row.get('raw'):
                grouped[-1]['raw'] = row['raw']
        else:
            grouped.append({'key': key, 'attempts': 1, 'raw': row.get('raw') or ''})
    for item in grouped:
        if item['raw']:
            out[item['key'][0]].append((item['attempts'], item['raw']))
    calls = (turn.get('product') or {}).get('submission', {}).get('calls') or []
    updates = []
    for call in calls:
        if not call.get('promptChars'):
            continue
        raw = str(call.get('raw') or '')
        attempts = int(call.get('calls') or 1)
        if call.get('task') == 'results':
            out['results'].append((attempts, raw))
        elif call.get('task') == 'updates' and '#position' in str(call.get('key') or ''):
            updates.append((attempts, raw))
    out['position'] = updates
    return out


rows = {name: [] for name in ('action', 'targets', 'position', 'results')}
skipped = {'reaction': 0, 'other': 0, 'short': 0}
for path in FILES:
    run = json.loads(path.read_text(encoding='utf8'))
    for turn in run.get('turns') or []:
        prompts = [row['prompt'] for row in ((turn.get('product') or {}).get('semanticPrompts') or [])]
        fams = {name: [] for name in ('action', 'targets', 'reaction', 'results', 'position')}
        for prompt in prompts:
            fam = family_of(prompt)
            if fam:
                fams[fam].append(prompt)
            else:
                skipped['other'] += 1
        calls = logical_calls(turn)
        for fam in fams:
            queue = list(fams[fam])
            if fam == 'reaction':
                skipped['reaction'] += len(queue)
                continue
            for attempts, raw in calls[fam]:
                take = queue[:attempts]
                queue = queue[attempts:]
                if not take:
                    skipped['short'] += 1
                    continue
                rows[fam].append({'turn': turn.get('id'), 'prompt': take[0], 'raw': raw,
                                  'attempts': attempts, 'parsed': parsed(raw)})
            skipped[fam + '_leftover'] = skipped.get(fam + '_leftover', 0) + len(queue)

for fam, data in rows.items():
    path = OUT / f'{fam}.jsonl'
    with open(path, 'w', encoding='utf8') as handle:
        for row in data:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    lengths = sorted(len(row['prompt']) for row in data)
    print(fam, 'rows', len(data), 'chars p50/max',
          (lengths[len(lengths)//2] if lengths else None), (lengths[-1] if lengths else None))
print('skipped', skipped)
