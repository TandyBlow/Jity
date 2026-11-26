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

ACTION_VERBS = re.compile('求助|办成|查完|记下|拿起|取出|塞进|递给|交给|拒绝|决定|答应|告诉')
CACHE_VERSION = 'v2'
PROMPT_VERSION = 'v2'
NEG_INFO = re.compile('没有答|没答|未答|拒绝回答|没有说|没说|未能|问不出|没有回应')
NEG_ENV = re.compile('没有动|没有打开|没有移动|未打开|未移动|保持原样|没有变化')
ENV_HINT = re.compile(r'环境[=＝]([^:：；\s]+)[:：]([^；。\n]+)')
ENV_FAIL = re.compile('拉不开|打不开|推不开|掀不开|纹丝不动|卡住|卡死|锁着|锁上|被阻止|无法|不能|失败|没有成功|没能|未能')
INFO_WORDS = re.compile('问|打听|询问|请教|读|看|查看|观察|检查|确认|核对|发现|听见|听到|告诉|回答|说明|报告|念|搜索|翻找')
MOVE_WORDS = re.compile('走进|走入|走到|走向|进入|来到|回到|退回|退到|跑到|冲向|赶到|爬上|走下|穿过|离开|前往|走到')


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
        if action.get('recordKind') != 'result' or action.get('task') == 'action':
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


def structured_actions(turn):
    rows = []
    for action in turn.get('actions') or []:
        if not isinstance(action, dict) or action.get('recordKind') != 'result' or action.get('task') != 'action':
            continue
        value = action.get('value')
        if not isinstance(value, dict):
            continue
        structure = value.get('structured')
        if not isinstance(structure, dict):
            continue
        rows.append({'key': action.get('key'), 'text': value.get('text') or '',
                     'category': structure.get('category'),
                     'itemIds': structure.get('itemIds') or [],
                     'destination': structure.get('destination')})
    return rows


def read_env_hints(texts):
    hints = []
    for text in texts:
        if not isinstance(text, str):
            continue
        for match in ENV_HINT.finditer(text):
            entity = match.group(1).strip().strip('<>')
            body = match.group(2).strip()
            if entity and body:
                hints.append({'entityId': entity, 'text': body})
    return hints


def initial_snapshot():
    path = ROOT / 'frontend/public/worlds/dragon-raja-free-day.world.json'
    if not path.exists():
        return None
    world = json.loads(path.read_text(encoding='utf8'))
    initial = world.get('initial') or {}
    state = {'characters': {}, 'items': {}, 'locations': {}}
    for identity, entity in (initial.get('characters') or {}).items():
        state['characters'][identity] = {
            'id': identity, 'position': entity.get('initialPosition'),
            'appearanceChanges': [], 'personalityChanges': [], 'tasks': entity.get('tasks') or {}}
    for identity, entity in (initial.get('items') or {}).items():
        state['items'][identity] = {
            'id': identity, 'position': entity.get('initialPosition'), 'appearanceChanges': []}
    for identity in (initial.get('locations') or {}):
        state['locations'][identity] = {'id': identity, 'appearanceChanges': []}
    return {'transport': {'state': state}}


def world_identity():
    path = ROOT / 'frontend/public/worlds/dragon-raja-free-day.world.json'
    if not path.exists():
        return None, ''
    world = json.loads(path.read_text(encoding='utf8'))
    identity = (world.get('initial') or {}).get('protagonistId') or world.get('protagonistId')
    name = (((world.get('initial') or {}).get('characters') or {}).get(identity) or {}).get('name', '')
    return identity, name


def world_knowledge_text():
    # The static world description is omniscient setup, not the character's
    # prior knowledge; only earlier turns count as known for info.
    return ''


def prompt_facts(turn):
    texts = []
    product = turn.get('product') or {}
    for row in product.get('semanticPrompts') or []:
        if isinstance(row, dict) and isinstance(row.get('prompt'), str):
            texts.append(row['prompt'])
    for call in (product.get('submission') or {}).get('calls') or []:
        if isinstance(call, dict) and isinstance(call.get('prompt'), str):
            texts.append(call['prompt'])
    facts = []
    seen = set()
    for text in texts:
        for chunk in re.split(r'(?=\bf\d+ \[[^\]]+\] )', text):
            match = re.match(r'f\d+ \[([^\]\s]+)[^\]]*\] (.+)', chunk, re.S)
            if not match:
                continue
            fact = match.group(2).split('\n', 1)[0].strip()
            if fact and fact not in seen:
                seen.add(fact)
                facts.append({'memberId': match.group(1), 'text': fact})
    return facts


def prompt_structures(turn):
    rows = []
    seen = set()
    product = turn.get('product') or {}
    texts = [row.get('prompt') for row in (product.get('semanticPrompts') or [])
             if isinstance(row, dict) and isinstance(row.get('prompt'), str)]
    texts += [call.get('prompt') for call in (product.get('submission') or {}).get('calls') or []
              if isinstance(call, dict) and isinstance(call.get('prompt'), str)]
    pattern = re.compile(
        r'- ([^\n（]+)（id=([\w-]+)）行动：([^\n]*)\n[^\n]*\n\s*结构：类别=([^；\n]+)；目标=([^；\n]*)；物品=([^；\n]*)；去向=([^\n]*)')
    for text in texts:
        for match in pattern.finditer(text):
            key = match.group(2)
            action = match.group(3).strip()
            if (key, action) in seen:
                continue
            seen.add((key, action))
            items = [item for item in re.split(r'[,，、]', match.group(6)) if item and item != '无']
            destination = match.group(7).strip()
            rows.append({'key': key, 'text': action, 'category': match.group(4),
                         'itemIds': items, 'destination': None if destination in ('', '无') else destination})
    return rows


def load_turn(turn, source, previous, checks=None, prior_text='', prompt_facts_ok=False):
    settled_rows = settled(turn)
    structured = structured_actions(turn)
    known_structures = {(row.get('key'), row.get('text')) for row in structured}
    for row in prompt_structures(turn):
        if (row['key'], row['text']) not in known_structures:
            structured.append(row)
            known_structures.add((row['key'], row['text']))
    if prompt_facts_ok:
        known = {row.get('text') for row in settled_rows if row.get('text')}
        for fact in prompt_facts(turn):
            if fact['text'] not in known:
                settled_rows.append({'task': 'results', 'key': fact['memberId'], 'kind': 'text',
                                     'text': fact['text'], 'targets': None})
                known.add(fact['text'])
    return {'id': turn['id'], 'source': source, 'input': turn.get('input') or '',
            'text': turn.get('text') or '', 'before': turn.get('before') or {},
            'after': turn.get('after') or {}, 'snapshotBefore': previous,
            'snapshot': turn.get('snapshotAfterTurn') or {},
            'settled': settled_rows, 'structured': structured,
            'priorText': prior_text, 'checks': checks or []}


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


def load_semantic_routes():
    definition = json.loads((HERE / 'semantic-scenarios.json').read_text(encoding='utf8'))
    meta = {}
    invalid = set()
    for route in definition.get('routes') or []:
        invalid.update(route.get('invalid') or [])
        for turn in route.get('turns') or []:
            meta[turn['id']] = {'class': turn.get('class'), 'split': route.get('split', 'train')}
    rows = {}
    for path in sorted(HERE.glob('evidence-semantic-*.json'), key=lambda item: item.stat().st_mtime):
        data = json.loads(path.read_text(encoding='utf8'))
        if data.get('status') not in ('COMPLETED', 'FAILED', 'PREFLIGHT'):
            continue
        previous = initial_snapshot()
        prior = world_knowledge_text()
        for turn in data.get('turns') or []:
            if turn['id'] in invalid:
                previous = turn.get('snapshotAfterTurn') or previous
                continue
            row = load_turn(turn, 'semantic', previous, prior_text=prior, prompt_facts_ok=True)
            info = meta.get(turn['id']) or {}
            row['class'] = info.get('class')
            row['split'] = info.get('split', 'train')
            row['evidenceFile'] = path.name
            rows[row['id']] = row
            previous = turn.get('snapshotAfterTurn') or {}
            prior += '\n' + (turn.get('text') or '') + '\n' + ' '.join(
                str(item.get('text') or '') for item in settled(turn))
    return list(rows.values())


def active_appearance(records):
    superseded = set()
    for record in records:
        if isinstance(record, dict):
            superseded.update(record.get('supersedes') or [])
    return {record.get('id'): str(record.get('text') or '') for record in records
            if isinstance(record, dict) and record.get('id') not in superseded}


def snapshot_view(snapshot):
    state = (snapshot or {}).get('transport', {}).get('state') or {}
    view = {}
    for identity, character in (state.get('characters') or {}).items():
        view['char:' + identity] = {
            'position': character.get('position'),
            'appearance': active_appearance(character.get('appearanceChanges') or []),
            'tasks': {tid: task.get('status') for tid, task in (character.get('tasks') or {}).items()},
        }
    for identity, item in (state.get('items') or {}).items():
        view['item:' + identity] = {
            'position': item.get('position'),
            'appearance': active_appearance(item.get('appearanceChanges') or []),
        }
    for identity, location in (state.get('locations') or {}).items():
        view['loc:' + identity] = {
            'appearance': active_appearance(location.get('appearanceChanges') or []),
        }
    return view


def environment_keys(before_view, after_view, location_ids):
    keys = []
    for key, after in after_view.items():
        before = before_view.get(key) or {}
        if after.get('appearance') != before.get('appearance'):
            keys.append(key)
        elif key.startswith('item:'):
            before_position = before.get('position') or {}
            after_position = after.get('position') or {}
            container = (after_position.get('containerId') or '')
            if before_position != after_position and container in location_ids:
                keys.append(key)
    for key, before in before_view.items():
        if key not in after_view and before.get('appearance'):
            keys.append(key)
    return keys


def state_diff(row):
    before = row.get('snapshotBefore')
    after = row.get('snapshot') or {}
    if not before:
        return {'known': False, 'added': [], 'removed': [], 'changed': [], 'env': []}
    before_view = snapshot_view(before)
    after_view = snapshot_view(after)
    added = [{'key': key, 'after': after_view[key]} for key in after_view if key not in before_view]
    removed = [{'key': key, 'before': before_view[key]} for key in before_view if key not in after_view]
    changed = [{'key': key, 'before': before_view.get(key), 'after': after_view[key]}
               for key in after_view if before_view.get(key) != after_view[key]]
    location_ids = set((after.get('transport', {}).get('state') or {}).get('locations') or {})
    env = environment_keys(before_view, after_view, location_ids)
    return {'known': True, 'added': added, 'removed': removed, 'changed': changed, 'env': env}


def prompt(row, diff):
    settled_text = json.dumps(row['settled'][:32], ensure_ascii=False)[:3500]
    diff_text = json.dumps(diff, ensure_ascii=False)[:2500]
    return f"""你是 Jity（中文 TRPG）的事件标注器。只输出一个 JSON 对象，不要解释。
玩家意图（只是意图，不是已发生）：{row['input']}
已结算行动（程序/模型已接受的结果）：{settled_text}
同回合叙事（只能当描述，不得补写状态）：{row['text'][:3000]}
本回合状态差分（旧快照的新增/移除；known=false 表示没有回合前快照）：{diff_text}
输出：
{{"info":{{"present":true/false,"content":"<=30字","support":"原文子串","evidence":"settled|narrative"}},
  "env":{{"present":true/false,"content":"<=30字","support":"原文子串","evidence":"settled|state"}}}}
规则：
- 只标已结算行动/状态差分支持的事实；意图、计划、别人未完成的行为不算。
- info：本回合实际获得的新信息；被拒绝/没答出 = present=false。
- env：环境或物品状态实际改变；移动、拿起、转移不算 env。
- 已结算事实带 环境=<实体>:<状态> 时，表示该实体本轮被判定发生了环境变化；核验器会对照状态差分。
- support 必须来自已结算行动、叙事或状态差分；玩家意图只是意图，不能当事实支持。
- 如果行动说 env 改变但状态差分没有对应变化，不要改成 false；保留候选，核验器会标 conflict。"""


def input_hash(row):
    payload = row.get('input', '') + '\n' + row.get('text', '') + '\n' + json.dumps(
        row.get('settled') or [], ensure_ascii=False) + '\n' + json.dumps(
        state_diff(row), ensure_ascii=False)
    import hashlib
    return hashlib.sha256(payload.encode('utf8')).hexdigest()


def label(row, cache_only=False):
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf8').splitlines():
            if line.strip():
                record = json.loads(line)
                if record.get('promptVersion') == PROMPT_VERSION and record.get('inputHash') == input_hash(row):
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
    client = OpenAI(api_key=key, base_url=env.get('LLM_BASE_URL') or 'https://api.deepseek.com',
                    timeout=90, max_retries=2)
    model = env.get('LABEL_MODEL') or 'deepseek-v4-pro'
    try:
        response = client.chat.completions.create(
            model=model, temperature=0, messages=[{'role': 'user', 'content': prompt(row, state_diff(row))}])
    except Exception as error:
        print(row['id'], 'api-error', str(error)[:200], file=sys.stderr)
        return None, 'api-error'
    text = response.choices[0].message.content or ''
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return None, 'bad-json'
    proposal = json.loads(match.group(0))
    record = {'id': row['id'], 'inputHash': input_hash(row), 'promptVersion': PROMPT_VERSION,
              'labelModel': model, 'evidence': {'info': (proposal.get('info') or {}).get('evidence'),
                                                 'env': (proposal.get('env') or {}).get('evidence')},
              'label': proposal, 'at': time.time()}
    with CACHE.open('a', encoding='utf8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    return proposal, 'model'


ENV_ACTION = re.compile('提开|掀开|翻开|拉开|打开|推开|推|挪动|挪开|拖动|拖到|拖开|拖走|移开|让出|固定|释放|扣好|放下|放倒|关上|搬到|摆到|挂到|插进|拔出')
ENV_TEXT = ('appearance', 'position')


def classify(field, item, row, diff, support, content, source, settled_text):
    present = bool(item.get('present'))
    support_ok = bool(support and support in source)
    if field == 'env':
        env_keys = diff.get('env') or []
        hints = read_env_hints([settled_text, row.get('text') or ''])
        hint_keys = {hint['entityId'] for hint in hints}
        recorded = {key.split(':', 1)[-1] for key in env_keys}
        structured = row.get('structured') or []
        capable = bool(ENV_ACTION.search(settled_text)) or any(
            ENV_ACTION.search(str(action.get('text') or '')) for action in structured)
        if not diff['known']:
            return 'insufficient'
        # 结构化标签+已记录外观是硬证据
        if hints and env_keys and hint_keys & recorded:
            return 'present'
        if present:
            if not content:
                return 'insufficient'
            if env_keys:
                if hint_keys & {key.split(':', 1)[-1] for key in env_keys}:
                    return 'present'
                values = []
                for key in env_keys:
                    for bucket in ('changed', 'added'):
                        for change in diff.get(bucket) or []:
                            if change.get('key') == key:
                                values.append(json.dumps(change, ensure_ascii=False))
                if any(support in value or content in value or
                       (support and support in value) for value in values):
                    return 'present'
                return 'conflict'
            if hints:
                return 'conflict'
            if capable:
                return 'conflict'
            return 'insufficient'
        if not diff['known']:
            return 'insufficient'
        if env_keys:
            return 'conflict'
        if hints:
            return 'conflict'
        partial = '只完成一部分' in settled_text or '部分' in settled_text
        if not partial and (NEG_ENV.search(settled_text + source) or ENV_FAIL.search(settled_text + source)):
            return 'absent'
        if capable:
            return 'conflict'
        if not structured:
            return 'insufficient'
        return 'absent'
    # info
    prior = row.get('priorText') or ''
    known = bool(prior and content and len(content) >= 4 and content in prior)
    structured = row.get('structured') or []
    info_capable = any(INFO_WORDS.search(str(action.get('text') or '')) for action in structured)
    move_capable = any(MOVE_WORDS.search(str(action.get('text') or '')) for action in structured)
    protagonist = row.get('protagonistName') or ''
    player_source = source
    if protagonist:
        player_facts = [str(item.get('text') or '') for item in row.get('settled') or []
                        if item.get('task') == 'results'
                        and (item.get('key') == row.get('protagonistId') or protagonist in str(item.get('text') or ''))]
        player_narration = ''.join(sentence for sentence in re.split(r'(?<=[。！？\n])', row.get('text') or '')
                                   if protagonist in sentence)
        player_source = player_narration + '\n' + '\n'.join(player_facts)
    if present:
        if not support_ok or not content:
            return 'insufficient'
        if ACTION_VERBS.search(content):
            return 'insufficient'
        # 纯物品操作不算获取信息
        if structured and not info_capable and not move_capable:
            return 'absent'
        if protagonist and support not in player_source:
            return 'insufficient'
        if not protagonist and support not in settled_text and support not in source:
            return 'insufficient'
        if known:
            return 'absent'
        return 'present'
    if NEG_INFO.search(settled_text + source):
        return 'absent'
    if re.search('告诉|回答|说明|报告|问清|核实', settled_text) and not ACTION_VERBS.search(settled_text):
        return 'conflict'
    structured = row.get('structured') or []
    if structured and not any(INFO_WORDS.search(str(action.get('text') or '')) for action in structured) \
            and not any(MOVE_WORDS.search(str(action.get('text') or '')) for action in structured):
        return 'absent'
    return 'insufficient'

def verify(row, proposal):
    diff = state_diff(row)
    settled_text = json.dumps(row['settled'], ensure_ascii=False)
    source = row['text'] + '\n' + settled_text
    result = {'stateDiff': diff, 'fields': {}}
    for field in ('info', 'env'):
        item = proposal.get(field) or {}
        support = str(item.get('support') or '').strip()
        content = str(item.get('content') or '').strip()
        status = classify(field, item, row, diff, support, content, source, settled_text)
        target = True if status == 'present' else False if status == 'absent' else None
        result['fields'][field] = {'status': status, 'target': target,
                                   'trainable': status in ('present', 'absent'),
                                   'content': content, 'support': support,
                                   'proposed': bool(item.get('present')),
                                   'evidence': item.get('evidence') or ''}
    return result


def cache_meta(row):
    if not CACHE.exists():
        return {}
    for line in CACHE.read_text(encoding='utf8').splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if (record.get('id') == row['id'] and record.get('promptVersion') == PROMPT_VERSION
                and record.get('inputHash') == input_hash(row)):
            return {'promptVersion': record.get('promptVersion'), 'inputHash': record.get('inputHash'),
                    'labelModel': record.get('labelModel'), 'evidence': record.get('evidence')}
    return {}


def export_training(rows):
    train, test = [], []
    for row in rows:
        labels = {field: item for field, item in (row.get('label') or {}).items() if item.get('trainable')}
        item = {'id': row['id'], 'split': row['split'], 'class': row.get('class'),
                'input': row['input'], 'text': row['text'],
                'settled': row['settled'], 'stateDiff': row['stateDiff'], 'labels': labels}
        if row['split'] == 'train' and labels:
            train.append(item)
        if row['split'] == 'test':
            test.append(item)
    return train, test


def write_manifest(rows, train, test):
    import hashlib
    manifest = {'promptVersion': PROMPT_VERSION,
                'raw': hashlib.sha256(DATASET.read_bytes()).hexdigest(),
                'train': hashlib.sha256(json.dumps(train, ensure_ascii=False).encode('utf8')).hexdigest(),
                'test': hashlib.sha256(json.dumps(test, ensure_ascii=False).encode('utf8')).hexdigest(),
                'rawRows': len(rows), 'trainRows': len(train), 'testRows': len(test)}
    (HERE / 'real-semantic-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                                      encoding='utf8')
    return manifest


def main():
    rows = load_scenarios() + load_semantic_routes() + load_run41()
    protagonist_id, protagonist_name = world_identity()
    for row in rows:
        row['protagonistId'] = protagonist_id
        row['protagonistName'] = protagonist_name
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
                       'labelSource': source, 'labelMeta': cache_meta(row),
                       'split': 'test' if (row['id'] in SCENARIO_IDS or row.get('split') == 'test') else 'train',
                       'class': row.get('class'), 'evidenceFile': row.get('evidenceFile')})
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
        lines.append(f"## {row['id']} ({row['split']}, {row['labelSource']}, {row.get('class') or row['source']})")
        lines.append(f"- action: {row['input']}")
        lines.append(f"- state diff: {json.dumps(row['stateDiff'], ensure_ascii=False)[:500]}")
        for field in ('info', 'env'):
            item = row['label'][field]
            lines.append(f"- {field}: {item['status']} proposed={item['proposed']} "
                         f"content={item['content']!r} support={item['support']!r} "
                         f"evidence={item['evidence']}")
        lines.append('')
    SPOT.write_text('\n'.join(lines), encoding='utf8')
    train, test = export_training(output)
    (HERE / 'real-semantic-train.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in train), encoding='utf8')
    (HERE / 'real-semantic-test.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in test), encoding='utf8')
    manifest = write_manifest(output, train, test)
    print(f'{len(output)} rows -> {DATASET} / {SPOT}', file=sys.stderr)
    print(json.dumps(manifest, ensure_ascii=False), file=sys.stderr)


if __name__ == '__main__':
    main()
    from validate_real_semantic import main as validate
    validate()
