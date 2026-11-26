# -*- coding: utf-8 -*-
"""Real semantic event data: real turns -> strong-model proposal -> fact
verification -> human spot-check file.

The labeler is optional at runtime (cache first). The verifier only accepts a
field whose support string appears verbatim in the action/narration. The
spot-check file is for the user; it is not auto-approved.
"""
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path('D:/others/Jity')
HERE = ROOT / 'artifacts/goal/micro-workflow'
CACHE = HERE / 'real-semantic-cache.jsonl'
DATASET = HERE / 'real-semantic.jsonl'
SPOT = HERE / 'real-semantic-spotcheck.md'
TEST_IDS = {'sc06-env-hatch-route', 'sc08-env-foyer-table', 'sc01-dialogue-nono-neutrality',
            's11-task-ask', 'g8-t3-talk-lin'}


def load_env():
    path = ROOT / 'backend/.env'
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf8').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_run41():
    files = ['run41-turns-20-chunk1.json', 'run41-turns-20-chunk2.json', 'run41-turns-20-chunk3.json',
             'run41-turns-20-chunk3b-r2.json', 'run41-turns-20-chunk5-r3.json']
    rows = []
    for name in files:
        data = json.loads((ROOT / 'artifacts/goal/acceptance' / name).read_text(encoding='utf8'))
        for turn in data.get('turns') or []:
            rows.append({'id': turn['id'], 'source': '20-input', 'input': turn.get('input') or '',
                         'text': turn.get('text') or '', 'before': turn.get('before') or {},
                         'after': turn.get('after') or {}, 'snapshot': turn.get('snapshotAfterTurn') or {}})
    unique = {}
    for row in rows:
        unique[row['id']] = row
    return list(unique.values())


def load_scenarios():
    data = json.loads((HERE / 'evidence-independent-scenarios-6b.json').read_text(encoding='utf8'))
    checks = {row['id']: row for row in json.loads(
        (HERE / 'scenarios-independent.json').read_text(encoding='utf8'))}
    rows = []
    for turn in data.get('turns') or []:
        rows.append({'id': turn['id'], 'source': 'scenario', 'input': turn.get('input') or '',
                     'text': turn.get('text') or '', 'before': turn.get('before') or {},
                     'after': turn.get('after') or {}, 'snapshot': turn.get('snapshotAfterTurn') or {},
                     'checks': checks.get(turn['id'], {}).get('checks') or []})
    return rows


def prompt(row):
    before = row['before']
    after = row['after']
    tasks_before = [task.get('goal') for task in before.get('tasks') or [] if not task.get('done')]
    tasks_after = [task.get('goal') for task in after.get('tasks') or [] if task.get('done')]
    checks = row.get('checks') or []
    return f"""你是 Jity（中文 TRPG）的事件标注器。只输出一个 JSON 对象，不要解释。
玩家行动：{row['input']}
同回合正文：{row['text'][:3500]}
回合前：地点={before.get('place')}；在场={before.get('nearby')}；未完成任务={tasks_before[:6]}
回合后：地点={after.get('place')}；在场={after.get('nearby')}；已完成任务={tasks_after[:6]}
场景检查：{json.dumps(checks, ensure_ascii=False)[:800]}
输出格式：
{{"info":{{"present":true/false,"content":"简短中文","support":"原文子串"}},
  "env":{{"present":true/false,"content":"简短中文","support":"原文子串"}}}}
规则：
- info 表示本回合实际获得的新信息；被拒绝、没答出、只回答一部分且没有新事实时 present=false。
- env 表示本回合实际改变的环境或物品状态；没有改变时 present=false。
- content 不超过 30 字；support 必须是“玩家行动”或“同回合正文”里的原文子串；找不到支持就 present=false。
- 不要把计划、意图、别人未完成的行为写成已发生。"""


def label(row):
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf8').splitlines():
            if line.strip():
                record = json.loads(line)
                cache[record['id']] = record['label']
    if row['id'] in cache:
        return cache[row['id']], 'cache'
    env = load_env()
    key = env.get('DEEPSEEK_API_KEY') or os.environ.get('DEEPSEEK_API_KEY', '')
    if not key:
        return None, 'no-key'
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=env.get('LLM_BASE_URL') or 'https://api.deepseek.com')
    model = env.get('LABEL_MODEL') or 'deepseek-v4-pro'
    response = client.chat.completions.create(
        model=model, temperature=0, messages=[{'role': 'user', 'content': prompt(row)}])
    text = response.choices[0].message.content or ''
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return None, 'bad-json'
    label = json.loads(match.group(0))
    with CACHE.open('a', encoding='utf8') as handle:
        handle.write(json.dumps({'id': row['id'], 'label': label}, ensure_ascii=False) + '\n')
    return label, 'model'


ENV_VERBS = re.compile('提开|掀开|翻开|拉开|提起|拖到|拖开|拖走|挪开|移开|让出|侧墙|固定|释放|扣好|放下|放倒')
MOVE_VERBS = re.compile('走|进入|停在|退|跑|爬上|下到|来到|到达|离开|退回')
ACTION_VERBS = re.compile('求助|办成|查完|记下|拿起|取出|塞进|递给|交给|拒绝|决定|答应|告诉')


def verify(row, label):
    source = row['input'] + '\n' + row['text']
    changes = state_summary(row)
    change_text = ' '.join(change.get('text') or '' for change in changes)
    result = {}
    for field in ('info', 'env'):
        item = label.get(field) or {}
        present = bool(item.get('present'))
        support = str(item.get('support') or '').strip()
        content = str(item.get('content') or '').strip()
        if not present:
            result[field] = {'present': False, 'content': '', 'support': '', 'verified': True}
            continue
        ok = bool(support and support in source and content)
        if field == 'env':
            ok = ok and bool(ENV_VERBS.search(support + content)) and not MOVE_VERBS.search(content)
            ok = ok and (bool(change_text) or bool(re.search('提开|掀开|拖到|让出|固定|释放|扣好|打开', content)))
        else:
            ok = ok and not ACTION_VERBS.search(content)
        result[field] = {'present': ok, 'content': content if ok else '',
                         'support': support if ok else '', 'verified': ok}
    return result


def state_summary(row):
    state = (row.get('snapshot') or {}).get('transport', {}).get('state') or {}
    items = state.get('items') or {}
    locations = state.get('locations') or {}
    changed = []
    for identity, item in items.items():
        changes = item.get('appearanceChanges') or []
        active = [change for change in changes if isinstance(change, dict) and not change.get('superseded')]
        if active:
            changed.append({'id': identity, 'text': active[-1].get('text')})
    for identity, location in locations.items():
        changes = location.get('appearanceChanges') or []
        active = [change for change in changes if isinstance(change, dict) and not change.get('superseded')]
        if active:
            changed.append({'id': identity, 'text': active[-1].get('text')})
    return changed


def main():
    rows = load_scenarios() + load_run41()
    output = []
    for index, row in enumerate(rows):
        proposal, source = label(row)
        if proposal is None:
            print(row['id'], source, file=sys.stderr)
            continue
        verified = verify(row, proposal)
        output.append({'id': row['id'], 'source': row['source'], 'input': row['input'], 'text': row['text'],
                       'before': row['before'], 'after': row['after'],
                       'stateChanges': state_summary(row), 'label': verified,
                       'labelSource': source, 'split': 'test' if row['id'] in TEST_IDS else 'train'})
        print(index + 1, row['id'], source, verified, file=sys.stderr)
        time.sleep(0.2)
    DATASET.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in output), encoding='utf8')
    lines = ['# Real semantic spot-check', '',
             'Strong-model proposals after verbatim support verification. Mark each field; this file is not '
             'auto-approved.', '']
    for row in output:
        lines.append(f"## {row['id']} ({row['split']}, {row['labelSource']})")
        lines.append(f"- action: {row['input']}")
        for field in ('info', 'env'):
            item = row['label'][field]
            lines.append(f"- {field}: present={item['present']} content={item['content']!r} "
                         f"support={item['support']!r} verified={item['verified']}")
        lines.append('')
    SPOT.write_text('\n'.join(lines), encoding='utf8')
    print(f'{len(output)} rows -> {DATASET} / {SPOT}', file=sys.stderr)


if __name__ == '__main__':
    main()
