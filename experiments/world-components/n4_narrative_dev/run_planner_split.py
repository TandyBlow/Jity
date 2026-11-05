"""规划模型 → u240 成句 → 程序装配：与现有编辑的 20 源对照。

规划模型只输出结构化计划（JSON），不写正文：

    {"paragraphs": [["f0","f1"], ["f2"]],
     "units": [{"factIds": ["f0"], "subject": "keep"},
               {"factIds": ["f1"], "subject": "omit"}],
     "background": [{"fragmentId": "bg2", "beforeFactId": "f2"}],
     "connections": ["r0"]}

程序校验后执行：合并只在同主体相邻事实之间、省略主语只在同主体承接处、
背景只能用白名单片段、连接只能引用已授权关系。
"""
import json
import pathlib
import re
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import n4_pipeline as P  # noqa: E402
from conservative_edit import strip_subject  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / 'artifacts' / 'cohesion-split'
D = json.loads((OUT / 'dw-results.json').read_text(encoding='utf-8'))

OLLAMA = 'http://127.0.0.1:11434/api/generate'
MODEL = 'qwen2.5:7b'


def background_fragments(source):
    """把授权背景整理成带来源的完整片段；不从物件名扩写状态。"""
    fragments = []
    place = source['place']
    head = place.split('>')[0]
    fragments.append({'fragmentId': 'bg1', 'text': head, 'source': '地点'})
    for index, piece in enumerate([p for p in source['scene'].split('；') if p], start=2):
        fragments.append({'fragmentId': f'bg{index}', 'text': piece, 'source': '场景'})
    return fragments


def fact_list(source):
    return [{'factId': f['factId'], 'name': f['name'], 'u240': f['u240'],
             'factText': f['factText']} for f in source['facts']]


PROMPT = """你是叙事规划器。你不写正文，只输出一个 JSON 计划，供程序装配已经写好的短句。

【可规划的范围】
1. paragraphs：把哪些相邻事实放进同一段（事实顺序不变，必须覆盖全部事实、不得重复）。
2. units：每个装配单元包含哪些事实；只有**同主体且相邻**的事实才能合并。
   subject 取值：keep（保留姓名）或 omit（省略主语，只能用于同一主体承接处）。
3. background：从白名单片段里选择要插入的片段，用 fragmentId 引用，只能插在某个事实之前。
4. connections：只能引用下面列出的已授权关系 ID。

【硬约束】
- 事实顺序不得改变；不得遗漏事实；不得新增事实。
- 背景只能引用白名单 fragmentId，不得自行写景。
- 关系只能引用已授权 ID，不得自行添加先后、因果、同时。
- 输出只允许一个 JSON 对象，不要解释、不要代码块标记。

【事实】（顺序固定，短句是已经写好的成品）
{facts}

【背景白名单】
{background}

【可连接关系】
{relations}

【输出要求】
只输出一个 JSON 对象，包含四个字段，**不要写示例、不要代码块标记、不要解释**：
- paragraphs：数组；每项是一组 factId（字符串），按顺序覆盖全部事实，不得缺项。
- units：数组；每项 {{"factIds": [...], "subject": "keep" 或 "omit"}}，按顺序覆盖全部事实。
- background：数组；每项 {{"fragmentId": "...", "beforeFactId": "..."}}；没有要插的就填空数组。
- connections：数组；元素必须是上面“可连接关系”里给出的 ID；没有就填空数组。

上面的 factId、fragmentId、关系 ID 都是真实编号，请直接使用，不要另造编号。"""


def build_prompt(source):
    facts = '\n'.join(f"{f['factId']} | {f['name']} | {f['factText']} | 短句: {f['u240']}"
                      for f in fact_list(source))
    background = '\n'.join(f"{b['fragmentId']} | {b['text']}（来源：{b['source']}）"
                           for b in background_fragments(source))
    relations = '\n'.join(f"r{i} | {a} 之后可写“随后”，后一条是 {b}"
                          for i, (a, b) in enumerate(source['relations'])) or '（无）'
    return PROMPT.format(facts=facts, background=background, relations=relations)


def call(prompt):
    body = json.dumps({'model': MODEL, 'prompt': prompt, 'stream': False,
                       'options': {'temperature': 0, 'num_predict': 400,
                                   'num_ctx': 3072}}).encode()
    request = urllib.request.Request(OLLAMA, data=body,
                                     headers={'content-type': 'application/json'})
    started = time.perf_counter()
    payload = json.load(urllib.request.urlopen(request, timeout=900))
    return {'raw': (payload.get('response') or '').strip(),
            'seconds': round(time.perf_counter() - started, 2)}


def parse_plan(raw):
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(json)?', '', cleaned).strip()
    cleaned = re.sub(r'```$', '', cleaned).strip()
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start < 0 or end < 0:
        raise ValueError('没有 JSON 对象')
    return json.loads(cleaned[start:end + 1])


def validate_plan(plan, source):
    """结构 + 语义检查；返回 (是否通过, 问题列表)。"""
    problems = []
    facts = fact_list(source)
    ids = [f['factId'] for f in facts]
    names = {f['factId']: f['name'] for f in facts}
    allowed_bg = {b['fragmentId'] for b in background_fragments(source)}
    allowed_rel = {f'r{i}': pair for i, pair in enumerate(source['relations'])}

    units = plan.get('units')
    if not isinstance(units, list) or not units:
        return False, ['units 缺失或为空']
    flat = [fid for unit in units for fid in unit.get('factIds', [])]
    if flat != ids:
        problems.append(f'事实顺序或覆盖不符：{flat}')

    previous_name = None
    for unit in units:
        unit_ids = unit.get('factIds', [])
        if not unit_ids:
            problems.append('存在空单元')
            continue
        unit_names = {names.get(fid) for fid in unit_ids}
        if len(unit_names) > 1:
            problems.append(f'跨主体合并：{unit_ids}')
        if len(unit_ids) > 1:
            positions = [ids.index(fid) for fid in unit_ids if fid in ids]
            if positions != list(range(positions[0], positions[0] + len(positions))):
                problems.append(f'合并非相邻事实：{unit_ids}')
        if unit.get('subject') == 'omit' and previous_name not in unit_names:
            problems.append(f'省略主语但上文不是同一主体：{unit_ids}')
        previous_name = list(unit_names)[0] if unit_names else previous_name

    paragraphs = plan.get('paragraphs') or []
    # 模型有时把 paragraphs 写成扁平编号列表（等于“不分段”），按整段处理
    if paragraphs and all(isinstance(item, str) for item in paragraphs):
        paragraphs = [paragraphs]
    paragraph_flat = [fid for word in paragraphs for fid in word]
    if paragraph_flat and paragraph_flat != ids:
        problems.append('段落划分没有按顺序覆盖全部事实')

    for item in plan.get('background') or []:
        if item.get('fragmentId') not in allowed_bg:
            problems.append(f'背景片段不在白名单：{item.get("fragmentId")}')
        if item.get('beforeFactId') not in ids:
            problems.append(f'背景插入位置无效：{item.get("beforeFactId")}')

    for rel in plan.get('connections') or []:
        if rel not in allowed_rel:
            problems.append(f'关系未授权：{rel}')

    extra_keys = set(plan) - {'paragraphs', 'units', 'background', 'connections'}
    if extra_keys:
        problems.append(f'多余字段：{sorted(extra_keys)}')
    return (not problems), problems


def assemble(plan, source):
    """按计划装配：合并、省主语、插背景、加“随后”。"""
    facts = {f['factId']: f for f in fact_list(source)}
    background = {b['fragmentId']: b['text'] for b in background_fragments(source)}
    before_bg = {}
    for item in plan.get('background') or []:
        before_bg.setdefault(item['beforeFactId'], []).append(background[item['fragmentId']])
    allowed_rel = {f'r{i}': pair for i, pair in enumerate(source['relations'])}
    connection_after = {}
    for rel in plan.get('connections') or []:
        source_id, target_id = allowed_rel[rel]
        connection_after.setdefault(source_id, []).append(target_id)

    blocks = []
    for unit in plan['units']:
        unit_ids = unit['factIds']
        head = unit_ids[0]
        prefix = ''.join(f'{text}。' for text in before_bg.get(head, []))
        head_text = facts[head]['u240'].strip()
        if unit.get('subject') == 'omit':
            body, _op = strip_subject(head_text, facts[head]['name'])
            head_text = body if body else head_text
        parts = [head_text.rstrip('。')]
        for extra in unit_ids[1:]:
            text = facts[extra]['u240'].strip()
            if unit.get('subject') == 'omit':
                body, _op = strip_subject(text, facts[extra]['name'])
                text = body if body else text
            parts.append(text.rstrip('。'))
        sentence = '，'.join(parts).replace(',', '，') + '。'
        blocks.append({'factIds': unit_ids, 'text': prefix + sentence})

    # 段落装配：单元之间若存在已授权关系，就在后一句前加“随后，”
    text = ''
    paragraphs = plan.get('paragraphs') or []
    if paragraphs and all(isinstance(item, str) for item in paragraphs):
        paragraphs = [paragraphs]
    groups = paragraphs or [[b['factIds'][0] for b in blocks]]
    for group in groups:
        piece = ''
        pending_connector = False
        for block in blocks:
            if block['factIds'][0] not in group:
                continue
            chunk = block['text']
            if pending_connector:
                chunk = '随后，' + chunk
                pending_connector = False
            piece += chunk
            last_fact = block['factIds'][-1]
            if any(last_fact == a for pair in source['relations'] for a in pair[:1]):
                pending_connector = True
        text += piece
    return {'text': text, 'blocks': blocks}


def arm_a(source):
    rows = [{'factId': f['factId'], 'name': f['name'], 'text': f['u240']}
            for f in source['facts']]
    verdict = {'verdict': 'pass' if source['relations'] else 'reject',
               'relations': [{'type': 'before', 'fromFactId': a, 'toFactId': b,
                              'evidence': [],
                              'authorization': {'verdict': 'pass',
                                                'validatorVersion': P.VALIDATOR}}
                             for a, b in source['relations']]}
    people = {f['name'] for f in source['facts']}
    edited = P.two_layer_edit(rows, verdict, people)
    return edited['text']


def main():
    results = []
    for source in D['sources']:
        prompt = build_prompt(source)
        produced = call(prompt)
        entry = {'sourceId': source['sourceId'], 'facts': source['facts'],
                 'relations': source['relations'],
                 'background': background_fragments(source),
                 'promptChars': len(prompt), 'seconds': produced['seconds'],
                 'raw': produced['raw'], 'A': arm_a(source)}
        try:
            plan = parse_plan(produced['raw'])
            ok, problems = validate_plan(plan, source)
        except Exception as error:  # noqa: BLE001 - 解析失败也是结果
            plan, ok, problems = None, False, [f'解析失败：{error}']
        entry['plan'] = plan
        entry['planValid'] = ok
        entry['problems'] = problems
        entry['B'] = assemble(plan, source)['text'] if ok else None
        results.append(entry)
        print(json.dumps({'source': entry['sourceId'], 'valid': ok,
                          'problems': problems[:2],
                          'B': (entry['B'] or '')[:60]}, ensure_ascii=False), flush=True)
    (OUT / 'plan-results.json').write_text(
        json.dumps({'model': MODEL, 'sources': results}, ensure_ascii=False, indent=1),
        encoding='utf-8')
    valid = sum(1 for r in results if r['planValid'])
    print('DONE', len(results), 'valid plans', valid,
          'seconds', round(sum(r['seconds'] for r in results), 1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
