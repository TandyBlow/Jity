"""多模型协同最小对照：A = u240＋保守编辑；B = 相同事实短句＋独立整合模型。

B 的整合模型是**现成模型替身**（qwen2.5:7b，经本机 ollama），只用来验证
“职责拆分是否有收益”这一上限，不能据此声称最终小模型工作流已经实现。

两侧输入完全相同：同一条 u240 短句列表、同一份授权背景、同一组可连接关系。
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
from conservative_edit import edit_source  # noqa: E402

ROOT = HERE.parents[2]
OUT = ROOT / 'artifacts' / 'cohesion-split'
DECODE = ROOT / 'artifacts' / 'decode-compare'
DIAG_OUT = ROOT / 'artifacts' / 'world-components' / 'n4-ce-u240.json'
ROUNDS_OUT = pathlib.Path('D:/others/Jity/artifacts/world-provenance/pairs/rounds-out.jsonl')
ROUNDS_DIR = pathlib.Path('D:/others/Jity/artifacts/world-provenance/pairs')

OLLAMA = 'http://127.0.0.1:11434/api/generate'
MODEL = 'qwen2.5:7b'

DIAG_SOURCES = ['v01', 'v02', 'v03', 'v05', 'v06', 't01', 't05', 't19']
ROUND_IDS = ['fixture-r1', 'fixture-r2', 'fixture-r3', 'fixture-r4', 'fixture-r5',
             'train-r1', 'train-r2', 'train-r3', 'train-r4', 'train-r5']
DOUBLE_UNITS = ['d010', 'd011']

PROMPT = """你是叙事整合器。下面是一组已经确定的事实短句（顺序固定）与已授权背景。只做整合：断句、指代、措辞、少量背景穿插、句间衔接。

禁止：新增人物、物件、动作、感官、事件、目的、因果或时间关系；不得改变顺序；不得省略任何一条事实。
只有标注“可连接”的相邻两条之间，才能使用“随后”这类先后词。

【授权背景】
地点={place}；可见={visible}；场景={scene}

【事实短句】
{facts}

{relations}
请输出一段中文叙事，只写这一段，不要解释："""


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
        path = ROOT / 'artifacts' / 'world-components' / name
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                unit = json.loads(line)
                inputs[unit['unitId']] = unit
    return inputs


def field(text, key):
    match = re.search(rf'^{key}=(.*)$', text, re.M)
    return match.group(1) if match else ''


def build_diag_source(source_id, sentences, units):
    ids = sorted(uid for uid in sentences if uid.split(':')[0] == source_id)
    first = units[ids[0]]['input']
    place = field(first, '地点')
    visible = field(first, '地点可见')
    scene = field(first, '场景')
    names = [field(units[uid]['input'], '事实').split('｜')[0] for uid in ids]
    rows = [(uid.split(':')[1], names[i], sentences[uid]) for i, uid in enumerate(ids)]
    return {'sourceId': source_id, 'place': place, 'visible': visible, 'scene': scene,
            'rows': rows, 'relations': []}


def build_round_source(round_id, rounds, diag):
    text = None
    for line in ROUNDS_OUT.read_text(encoding='utf-8').splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get('roundId') == round_id and 'result' in item:
                text = item['result']
    payload = json.loads((ROUNDS_DIR / f'{round_id}-authorized.json').read_text(encoding='utf-8'))
    rows = [(g['factId'], g['name'], g['text']) for g in text['generation']]
    relations = [(r['fromFactId'], r['toFactId']) for r in text['authorization']['relations']]
    place = '潮汐档案馆>长桌'
    visible = '潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌'
    scene = '夜；浓雾'
    return {'sourceId': round_id, 'place': place, 'visible': visible, 'scene': scene,
            'rows': rows, 'relations': relations,
            'verdict': text['authorization']}


def arm_a(source):
    """A：现有两层编辑（保守合并 + 已授权连接），复用 n4_pipeline.two_layer_edit。"""
    rows = [{'factId': fid, 'name': name, 'text': text} for fid, name, text in source['rows']]
    verdict = {'verdict': 'pass', 'relations': [
        {'type': 'before', 'fromFactId': a, 'toFactId': b,
         'evidence': [], 'authorization': {'verdict': 'pass',
                                           'validatorVersion': P.VALIDATOR}}
        for a, b in source['relations']]}
    if not verdict['relations']:
        verdict = {'verdict': 'reject', 'relations': []}
    people = {name for _, name, _ in source['rows']}
    edited = P.two_layer_edit(rows, verdict, people)
    return {'text': edited['text'], 'edit': edited}


def arm_b(source):
    facts = '\n'.join(f'{i}. {text}' for i, (_, _, text) in enumerate(source['rows'], start=1))
    if source['relations']:
        index = {fid: i for i, (fid, _, _) in enumerate(source['rows'], start=1)}
        notes = '；'.join(f'第{index[a]}条与第{index[b]}条之间可写“随后”'
                          for a, b in source['relations'])
        relations = f'【可连接】{notes}。'
    else:
        relations = '【可连接】无（不得使用先后词）。'
    prompt = PROMPT.format(place=source['place'], visible=source['visible'],
                           scene=source['scene'], facts=facts, relations=relations)
    body = json.dumps({'model': MODEL, 'prompt': prompt, 'stream': False,
                       'options': {'temperature': 0, 'num_predict': 220,
                                   'num_ctx': 2048}}).encode()
    request = urllib.request.Request(OLLAMA, data=body,
                                     headers={'content-type': 'application/json'})
    started = time.perf_counter()
    payload = json.load(urllib.request.urlopen(request, timeout=900))
    return {'text': (payload.get('response') or '').strip(),
            'seconds': round(time.perf_counter() - started, 2),
            'promptChars': len(prompt),
            'evalCount': payload.get('eval_count')}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sentences = diag_units()
    units = diag_inputs()
    rounds = {}
    for line in ROUNDS_OUT.read_text(encoding='utf-8').splitlines():
        if line.strip():
            item = json.loads(line)
            if 'result' in item:
                rounds[item['roundId']] = item['result']

    sources = [build_round_source(rid, rounds, sentences) for rid in ROUND_IDS]
    sources += [build_diag_source(sid, sentences, units) for sid in DIAG_SOURCES]
    confirm = json.loads((DECODE / 'confirm40.json').read_text(encoding='utf-8'))['cases']
    confirm_rows = {row['caseId']: row for row in
                    json.loads((DECODE / 'confirm40-ab.json').read_text(encoding='utf-8'))['rows']}
    for case_id in DOUBLE_UNITS:
        case = next(c for c in confirm if c['caseId'] == case_id)
        sources.append({'sourceId': f'double-{case_id}',
                        'place': '潮汐档案馆>长桌',
                        'visible': '潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌',
                        'scene': '夜；浓雾',
                        'rows': [(case_id, case['name'],
                                  confirm_rows[case_id]['greedy']['text'])],
                        'relations': []})

    results = []
    for source in sources:
        a = arm_a(source)
        b = arm_b(source)
        entry = {'sourceId': source['sourceId'],
                 'facts': [{'factId': fid, 'name': name, 'u240': text}
                           for fid, name, text in source['rows']],
                 'relations': source['relations'],
                 'place': source['place'], 'visible': source['visible'],
                 'scene': source['scene'],
                 'A': {'text': a['text'],
                       'connectorOps': len(a['edit']['connectorOps']),
                       'mergeOps': len(a['edit']['mergeOps'])},
                 'B': b}
        results.append(entry)
        print(json.dumps({'source': entry['sourceId'],
                          'A': entry['A']['text'], 'B': b['text'],
                          'seconds': b['seconds']}, ensure_ascii=False), flush=True)

    (OUT / 'results.json').write_text(json.dumps({'model': MODEL, 'sources': results},
                                                 ensure_ascii=False, indent=1),
                                      encoding='utf-8')
    print('DONE', len(results), 'sources; B seconds total',
          round(sum(r['B']['seconds'] for r in results), 1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
