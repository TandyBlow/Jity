"""同模型对照：D 直接表达 vs W 协同表达（都走同一个 7B 替身）。

D：权威事实 + 授权背景/关系 → 段落
W：同一份材料 + u240 中间短句 → 同一段落

两臂使用完全相同的强约束与解码配置；评分以权威事实为准，u240 短句不是标准答案。
"""
import json
import pathlib
import re
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sys as _paths_sys
_paths_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from component_paths import PATHS

ROOT = PATHS.worktree
OUT = PATHS.output('cohesion-split')
DECODE = PATHS.input('decode-compare')
DIAG_OUT = PATHS.input('world-components/n4-ce-u240.json')
ROUNDS_OUT = PATHS.input('world-provenance/pairs/rounds-out.jsonl')
ROUNDS_DIR = PATHS.input('world-provenance/pairs')

OLLAMA = 'http://127.0.0.1:11434/api/generate'
MODEL = 'qwen2.5:7b'

DIAG_SOURCES = ['v01', 'v02', 'v03', 'v05', 'v06', 't01', 't05', 't19']
ROUND_IDS = ['fixture-r1', 'fixture-r2', 'fixture-r3', 'fixture-r4', 'fixture-r5',
             'train-r1', 'train-r2', 'train-r3', 'train-r4', 'train-r5']
DOUBLE_UNITS = ['d010', 'd011']

KIND_LABEL = {'appearance_changed': '外貌变化', 'outcome': '结果', 'moved': '移动',
              'sanity_changed': '状态变化', 'no_change': '无变化'}

RULES = """写作约束（两臂相同，必须逐条遵守）：
1. 事实顺序不得改变；事件只能来自下面的事实清单。
2. 实体名称只允许原名或既有合法别名，不得换人、换物。
3. 允许：合句、指代（指代对象必须能从上下文唯一确定）、断句、不改变含义的改写。
4. 背景只能引用“授权背景”里给出的完整描述片段；可见物件不等于允许它发生新事件。
5. 时间、因果、目的、感知只能来自已有授权；不得写“仿佛”“似乎”“显然”“为了”“因为”这类推测或目的。
6. 只能在标注“可连接”的相邻两条之间使用“随后”这类先后词；其余位置不得添加先后或同时关系。
7. 不得新增人物、物件、动作、感官、事件。"""


def field(text, key):
    match = re.search(rf'^{key}=(.*)$', text, re.M)
    return match.group(1) if match else ''


def diag_units():
    data = json.loads(DIAG_OUT.read_text(encoding='utf-8'))
    units = {}
    for _, rows in data.items():
        for row in rows:
            units[row['unitId']] = row['text']
    return units


def diag_inputs():
    inputs = {}
    for name in ('n4-final24-contract.jsonl', 'n4-cf24-contract.jsonl',
                 'n4-object18-contract.jsonl', 'n4-expand36-contract.jsonl'):
        path = PATHS.input('world-components/' + name)
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                unit = json.loads(line)
                inputs[unit['unitId']] = unit
    return inputs


def build_sources():
    sentences = diag_units()
    units = diag_inputs()
    rounds = {}
    for line in ROUNDS_OUT.read_text(encoding='utf-8').splitlines():
        if line.strip():
            item = json.loads(line)
            if 'result' in item:
                rounds[item['roundId']] = item['result']
    sources = []

    for rid in ROUND_IDS:
        payload = json.loads((ROUNDS_DIR / f'{rid}-authorized.json').read_text(encoding='utf-8'))
        result = rounds[rid]
        by_fact = {g['factId']: g['text'] for g in result['generation']}
        facts = [{'factId': u['factId'], 'name': u['name'], 'kind': u['kind'],
                  'factText': u['text'], 'u240': by_fact[u['factId']]}
                 for u in payload['units']]
        relations = [(r['fromFactId'], r['toFactId'])
                     for r in result['authorization']['relations']]
        sources.append({'sourceId': rid, 'place': '潮汐档案馆>长桌',
                        'visible': '潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌',
                        'scene': '夜；浓雾', 'facts': facts, 'relations': relations})

    for sid in DIAG_SOURCES:
        ids = sorted(uid for uid in sentences if uid.split(':')[0] == sid)
        first = units[ids[0]]['input']
        facts = []
        for uid in ids:
            unit = units[uid]
            fact = unit['fact']
            facts.append({'factId': uid.split(':')[1], 'name': fact.get('name'),
                          'kind': unit['kind'],
                          'factText': fact.get('text') or fact.get('resultText')
                          or f"{fact.get('from')}→{fact.get('to')}",
                          'u240': sentences[uid]})
        sources.append({'sourceId': sid, 'place': field(first, '地点'),
                        'visible': field(first, '地点可见'), 'scene': field(first, '场景'),
                        'facts': facts, 'relations': []})

    confirm = json.loads((DECODE / 'confirm40.json').read_text(encoding='utf-8'))['cases']
    confirm_rows = {row['caseId']: row for row in
                    json.loads((DECODE / 'confirm40-ab.json').read_text(encoding='utf-8'))['rows']}
    for case_id in DOUBLE_UNITS:
        case = next(c for c in confirm if c['caseId'] == case_id)
        sources.append({'sourceId': f'double-{case_id}', 'place': '潮汐档案馆>长桌',
                        'visible': '潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌',
                        'scene': '夜；浓雾',
                        'facts': [{'factId': 'f0', 'name': case['name'],
                                   'kind': 'appearance_changed',
                                   'factText': case['factText'],
                                   'u240': confirm_rows[case_id]['greedy']['text']}],
                        'relations': []})
    return sources


def relation_note(source):
    if not source['relations']:
        return '【可连接】无（任何位置都不得使用先后词）。'
    index = {fact['factId']: i for i, fact in enumerate(source['facts'], start=1)}
    parts = [f'第{index[a]}条与第{index[b]}条之间可写“随后”' for a, b in source['relations']]
    return '【可连接】' + '；'.join(parts) + '。'


def fact_block(source, with_u240):
    lines = []
    for i, fact in enumerate(source['facts'], start=1):
        label = KIND_LABEL.get(fact['kind'], fact['kind'])
        line = f"{i}. {fact['name']}｜{label}｜{fact['factText']}"
        if with_u240:
            line += f"（已写好的短句：{fact['u240']}）"
        lines.append(line)
    return '\n'.join(lines)


def prompt_for(source, arm):
    head = f"""你是叙事整合器。下面是已经确定的事实清单与已授权背景。把事实写成一段连贯的中文叙事。

{RULES}

【授权背景】
地点={source['place']}；可见={source['visible']}；场景={source['scene']}

【事实清单】（顺序固定）
{fact_block(source, arm == 'W')}

{relation_note(source)}

先按顺序输出事实对齐记录（每条事实对应输出的哪一句，一句一行，格式：`n. 事实要点 -> 原文片段`），
然后输出一行 `---`，再输出叙事段落。不要解释、不要额外说明："""
    return head


def call(prompt):
    body = json.dumps({'model': MODEL, 'prompt': prompt, 'stream': False,
                       'options': {'temperature': 0, 'num_predict': 320,
                                   'num_ctx': 3072}}).encode()
    request = urllib.request.Request(OLLAMA, data=body,
                                     headers={'content-type': 'application/json'})
    started = time.perf_counter()
    payload = json.load(urllib.request.urlopen(request, timeout=900))
    return {'text': (payload.get('response') or '').strip(),
            'seconds': round(time.perf_counter() - started, 2),
            'promptChars': len(prompt),
            'evalCount': payload.get('eval_count')}


def split_alignment(text):
    if '---' in text:
        head, tail = text.split('---', 1)
        return head.strip(), tail.strip()
    return '', text.strip()


def main():
    sources = build_sources()
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for source in sources:
        entry = {'sourceId': source['sourceId'], 'facts': source['facts'],
                 'relations': source['relations'], 'place': source['place'],
                 'visible': source['visible'], 'scene': source['scene']}
        for arm in ('D', 'W'):
            produced = call(prompt_for(source, arm))
            alignment, body = split_alignment(produced['text'])
            entry[arm] = {**produced, 'alignment': alignment, 'body': body}
        results.append(entry)
        print(json.dumps({'source': entry['sourceId'],
                          'D': entry['D']['body'][:60],
                          'W': entry['W']['body'][:60],
                          'Dsec': entry['D']['seconds'], 'Wsec': entry['W']['seconds']},
                         ensure_ascii=False), flush=True)
    (OUT / 'dw-results.json').write_text(json.dumps({'model': MODEL, 'sources': results},
                                                    ensure_ascii=False, indent=1),
                                         encoding='utf-8')
    print('DONE', len(results),
          'D total', round(sum(r['D']['seconds'] for r in results), 1),
          'W total', round(sum(r['W']['seconds'] for r in results), 1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
