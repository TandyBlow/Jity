# -*- coding: utf-8 -*-
"""Real semantic event data with four label states and a before/after diff.

The labeler proposes; the verifier assigns one of:
  present      verified by the settled action/narration and, for env, a new
               appearance record this turn
  absent       confirmed negative (explicit no-answer/no-change), not merely a
               failed verification
  insufficient evidence is missing or the before snapshot is unknown
  conflict     the action/narration and the old state disagree; this is the
               fix set (for example sc06/sc08 where the old state never
               committed the environment change), never a negative sample

The 8 frozen scenarios are test-only; the 20 product turns are train. The
spot-check file is for the user and is not auto-approved.
"""
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
SCENARIO_IDS = {'sc01-dialogue-nono-neutrality', 'sc02-conflict-yard-cover', 'sc03-move-shed',
                'sc04-item-magazine', 'sc05-move-hatch', 'sc06-env-hatch-route', 'sc07-move-foyer',
                'sc08-env-foyer-table'}

ENV_VERBS = re.compile('提开|掀开|翻开|拉开|提起|拖到|拖开|拖走|挪开|移开|让出|侧墙|固定|释放|扣好|放下|放倒')
MOVE_VERBS = re.compile('走|进入|停在|退|跑|爬上|下到|来到|到达|离开|退回')
ACTION_VERBS = re.compile('求助|办成|查完|记下|拿起|取出|塞进|递给|交给|拒绝|决定|答应|告诉')
NEG_INFO = re.compile('没有答|没答|未答|拒绝回答|没有说|没说|未能|问不出|没有回应')
NEG_ENV = re.compile('没有动|没有打开|没有移动|未打开|未移动|保持原样|没有变化')


def load_env():
    path = ROOT / 'backend/.env'
    values = {}
    if path.exists():
        for line in path.read_text(encoding='utf8').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def settled(row):
    results = []
    for action in row.get('actions') or []:
        if action.get('recordKind') != 'result':
            continue
        value = action.get('value')
        if isinstance(value, dict):
            results.append({'task': action.get('task'), 'key': action.get('key'),
                            'kind': value.get('kind'), 'text': value.get('text'),
                            'targets': value.get('targets')})
        elif isinstance(value, str) and value.strip():
            results.append({'task': action.get('task'), 'key': action.get('key'),
                            'kind': 'text', 'text': value, 'targets': None})
    return results


def load_turn(turn, source, previous, checks=None):
    return {'id': turn['id'], 'source': source, 'input': turn.get('input') or '',
            'text': turn.get('text') or '', 'before': turn.get('before') or {},
            'after': turn.get('after') or {}, 'snapshotBefore': previous,
            'snapshot': turn.get('snapshotAfterTurn') or {},
            'settled': settled(turn), 'checks': checks or []}


def load_run41():
    files = ['run41-turns-20-chunk1.json', 'run41-turns-20-chunk2.json', 'run41-turns-20-chunk3.json',
             'run41-turns-20-chunk3b-r2.json', 'run41-turns-20-chunk5-r3.json']
    rows = []
    for name in files:
        data = json.loads((ROOT / 'artifacts/goal/acceptance' / name).read_text(encoding='utf8'))
        previous = None
        for turn in data.get('turns') or []:
            rows.append(load_turn(turn, '20-input', previous))
            previous = turn.get('snapshotAfterTurn') or {}
    unique = {}
    for row in rows:
        if row['id'] not in unique:
            unique[row['id']] = row
    return list(unique.values())


def load_scenarios():
    data = json.loads((HERE / 'evidence-independent-scenarios-6b.json').read_text(encoding='utf8'))
    checks = {row['id']: row for row in json.loads(
        (HERE / 'scenarios-independent.json').read_text(encoding='utf8'))}
    rows = []
    previous = None
    for turn in data.get('turns') or []:
        rows.append(load_turn(turn, 'scenario', previous,
                              (checks.get(turn['id']) or {}).get('checks') or []))
        previous = turn.get('snapshotAfterTurn') or {}
    return rows


def active_changes(snapshot, bucket):
    state = (snapshot or {}).get('transport', {}).get('state') or {}
    entries = state.get(bucket) or {}
    changes = {}
    for identity, entry in entries.items():
        records = entry.get('appearanceChanges') or []
        active = [record for record in records if isinstance(record, dict) and not record.get('superseded')]
        if active:
            changes[identity] = str(active[-1].get('text') or '')
    return changes


def state_diff(row):
    before = row.get('snapshotBefore')
    after = row.get('snapshot') or {}
    before_changes = {}
    after_changes = {}
    if before:
        before_changes.update(active_changes(before, 'items'))
        before_changes.update(active_changes(before, 'locations'))
    after_changes.update(active_changes(after, 'items'))
    after_changes.update(active_changes(after, 'locations'))
    added = [{'id': identity, 'text': text} for identity, text in after_changes.items()
             if before_changes.get(identity) != text]
    removed = [{'id': identity, 'text': text} for identity, text in before_changes.items()
               if identity not in after_changes]
    return {'known': bool(before), 'added': added, 'removed': removed}


def prompt(row, diff):
    settled_text = json.dumps(row['settled'][:32], ensure_ascii=False)[:3500]
    return f"""你是 Jity（中文 TRPG）的事件标注器。只输出一个 JSON 对象，不要解释。
玩家意图（只是意图，不是已发生）：{row['input']}
已结算行动（程序/模型已接受的结果）：{settled_text}
同回合叙事（只能当描述，不得补写状态）：{row['text'][:3000]}
本回合状态差分（旧快照的新增/移除；known=false 表示没有回合前快照）：{json.dumps(diff, ensure_ascii=False)}
输出：
{{"info":{{"present":true/false,"content":"<=30字","support":"原文子串","evidence":"settled|narrative"}},
  "env":{{"present":true/false,"content":"<=30字","support":"原文子串","evidence":"settled|state"}}}}
规则：
- 只标已结算行动/状态差分支持的事实；意图、计划、别人未完成的行为不算。
- info：本回合实际获得的新信息；被拒绝/没答出 = present=false。
- env：环境或物品状态实际改变；移动、拿起、转移不算 env。
- support 必须是“玩家意图”“已结算行动”或“叙事”里的原文子串；没有支持 = present=false。
- 如果行动说 env 改变但状态差分没有新增，不要改成 false；保留候选，核验器会标 conflict。"""


def label(row, cache_only=False):
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf8').splitlines():
            if line.strip():
                record = json.loads(line)
                cache[record['id']] = record['label']
    if row['id'] in cache:
        return cache[row['id']], 'cache'
    if cache_only:
        return None, 'cache-miss'
    env = load_env()
    key = env.get('DEEPSEEK_API_KEY') or os.environ.get('DEEPSEEK_API_KEY', '')
    if not key:
        return None, 'no-key'
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=env.get('LLM_BASE_URL') or 'https://api.deepseek.com')
    model = env.get('LABEL_MODEL') or 'deepseek-v4-pro'
    response = client.chat.completions.create(
        model=model, temperature=0, messages=[{'role': 'user', 'content': prompt(row, state_diff(row))}])
    text = response.choices[0].message.content or ''
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return None, 'bad-json'
    proposal = json.loads(match.group(0))
    with CACHE.open('a', encoding='utf8') as handle:
        handle.write(json.dumps({'id': row['id'], 'label': proposal}, ensure_ascii=False) + '\n')
    return proposal, 'model'


def classify(field, item, row, diff, support, content, source, settled_text):
    present = bool(item.get('present'))
    support_ok = bool(support and support in source)
    if field == 'env':
        if present:
            if not support_ok or not content:
                return 'insufficient'
            if not diff['known']:
                return 'insufficient'
            if diff['added']:
                overlap = any(support in change['text'] or content in change['text'] or
                              change['text'] in support or change['text'] in content
                              for change in diff['added'])
                return 'present' if overlap else 'conflict'
            if ENV_VERBS.search(settled_text + source):
                return 'conflict'
            return 'insufficient'
        if not diff['known']:
            return 'insufficient'
        if not diff['added'] and ENV_VERBS.search(settled_text + source):
            return 'conflict'
        if not diff['added'] and not ENV_VERBS.search(settled_text):
            return 'absent'
        if NEG_ENV.search(settled_text):
            return 'absent'
        return 'insufficient'
    # info
    if present:
        if not support_ok or not content:
            return 'insufficient'
        if ACTION_VERBS.search(content):
            return 'insufficient'
        return 'present' if (support in settled_text or support in source) else 'insufficient'
    if NEG_INFO.search(settled_text + source):
        return 'absent'
    if re.search('告诉|回答|说明|报告|问清|核实', settled_text) and not ACTION_VERBS.search(settled_text):
        return 'conflict'
    return 'insufficient'


def verify(row, proposal):
    diff = state_diff(row)
    source = row['input'] + '\n' + row['text']
    settled_text = json.dumps(row['settled'], ensure_ascii=False)
    result = {'stateDiff': diff, 'fields': {}}
    for field in ('info', 'env'):
        item = proposal.get(field) or {}
        support = str(item.get('support') or '').strip()
        content = str(item.get('content') or '').strip()
        status = classify(field, item, row, diff, support, content, source, settled_text)
        result['fields'][field] = {'status': status, 'present': status == 'present',
                                   'content': content, 'support': support,
                                   'proposed': bool(item.get('present')),
                                   'evidence': item.get('evidence') or ''}
    return result


def main():
    rows = load_scenarios() + load_run41()
    cache_only = os.environ.get('CACHE_ONLY', '').lower() in ('1', 'true')
    output = []
    for index, row in enumerate(rows):
        proposal, source = label(row, cache_only)
        if proposal is None:
            print(row['id'], source, file=sys.stderr)
            continue
        verified = verify(row, proposal)
        output.append({'id': row['id'], 'source': row['source'], 'input': row['input'],
                       'text': row['text'], 'settled': row['settled'],
                       'before': row['before'], 'after': row['after'],
                       'stateDiff': verified['stateDiff'], 'label': verified['fields'],
                       'labelSource': source,
                       'split': 'test' if row['id'] in SCENARIO_IDS else 'train'})
        print(index + 1, row['id'], source,
              {field: verified['fields'][field]['status'] for field in ('info', 'env')}, file=sys.stderr)
        time.sleep(0.2)
    DATASET.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in output), encoding='utf8')
    counts = {}
    for row in output:
        for field in ('info', 'env'):
            status = row['label'][field]['status']
            counts[f'{field}:{status}'] = counts.get(f'{field}:{status}', 0) + 1
    lines = ['# Real semantic spot-check', '',
             'Four states: present / absent / insufficient / conflict. conflict is the fix set; '
             'insufficient and conflict are not negative samples.', '',
             f'Counts: {json.dumps(counts, ensure_ascii=False)}', '']
    for row in output:
        lines.append(f"## {row['id']} ({row['split']}, {row['labelSource']})")
        lines.append(f"- action: {row['input']}")
        lines.append(f"- state diff: {json.dumps(row['stateDiff'], ensure_ascii=False)[:500]}")
        for field in ('info', 'env'):
            item = row['label'][field]
            lines.append(f"- {field}: {item['status']} proposed={item['proposed']} "
                         f"content={item['content']!r} support={item['support']!r} "
                         f"evidence={item['evidence']}")
        lines.append('')
    SPOT.write_text('\n'.join(lines), encoding='utf8')
    print(f'{len(output)} rows -> {DATASET} / {SPOT}', file=sys.stderr)


if __name__ == '__main__':
    main()
