"""冻结小回归案例清单：10 个真实回合 + 缺陷案例 + 等量正确案例。

两臂使用完全相同的输入文本，所以这里必须把 prompt 固化下来。真实回合的
单元没有自带 prompt（常驻服务用固定表头拼），这里沿用同一表头，保证离线
对照与线上路径一致。
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402

ART = HERE.parents[2] / 'artifacts'
DIAG = ART / 'world-components'
ROUNDS = pathlib.Path('D:/others/Jity/artifacts/world-provenance/pairs')
OUT = ART / 'decode-compare'

SERVICE_HEADER = ('短句任务。\n地点=潮汐档案馆>长桌\n'
                  '地点可见=潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌\n'
                  '场景=夜；浓雾\n视角={pov}；第三人称')

# 已知缺陷单元（重复／加料／对象错配），按诊断集里的 unitId 取
DEFECT_IDS = ['t03:f0', 't18:f1', 'v05:f2', 'ca4B', 't11:f1', 't23:f2',
              'v01:f0', 'v12:f0', 'v13:f0', 't07:f0', 't12:f0', 't14:f0',
              't15:f0', 't17:f0', 't19:f2', 'v20:f0', 't09:f0', 't13:f0',
              'qd3A', 'qa3A']
# 数值相当的正确案例（同批诊断集里没有已知问题的单元）
CLEAN_IDS = ['v02:f0', 'v04:f1', 'v06:f2', 'v08:f2', 'v09:f2', 'v10:f2',
             'v16:f1', 'v17:f1', 'v21:f0', 'v23:f0', 't01:f2', 't02:f2',
             't05:f1', 't06:f1', 't08:f1', 't10:f1', 't20:f2', 't22:f2',
             'ca1A', 'ca3B']


def load_diag():
    units = {}
    for name in ('n4-final24-contract.jsonl', 'n4-cf24-contract.jsonl',
                 'n4-object18-contract.jsonl', 'n4-expand36-contract.jsonl'):
        for line in (DIAG / name).read_text(encoding='utf-8').splitlines():
            if line.strip():
                unit = json.loads(line)
                units[unit['unitId']] = unit
    return units


def load_rounds():
    cases = []
    for path in sorted(ROUNDS.glob('*-authorized.json')):
        payload = json.loads(path.read_text(encoding='utf-8'))
        round_id = path.stem.replace('-authorized', '')
        for unit in payload['units']:
            cases.append({'caseId': f'{round_id}:{unit["factId"]}',
                          'source': 'round', 'roundId': round_id,
                          'factId': unit['factId'], 'kind': unit['kind'],
                          'name': unit['name'], 'factText': unit['text'],
                          'input': SERVICE_HEADER.format(pov=unit['name'])
                                   + '\n事实=' + FC.serialize_fact(
                                       {'kind': unit['kind'], 'name': unit['name'],
                                        'text': unit['text']}) + '\n短句：\n'})
    return cases


def diag_case(unit, group):
    fact = unit['fact']
    payload = {'kind': unit['kind'], 'name': fact.get('name'),
               'text': fact.get('text') or fact.get('resultText') or ''}
    return {'caseId': unit['unitId'], 'source': 'diag', 'group': group,
            'factId': unit['unitId'], 'kind': unit['kind'],
            'name': fact.get('name'), 'factText': payload['text'],
            'input': unit['input']}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    units = load_diag()
    cases = load_rounds()
    for unit_id in DEFECT_IDS:
        cases.append(diag_case(units[unit_id], 'defect'))
    for unit_id in CLEAN_IDS:
        cases.append(diag_case(units[unit_id], 'clean'))
    for case in cases:
        FC.check_units([{'unitId': case['caseId'], 'kind': case['kind'],
                         'input': case['input']}])
    payload = {'frozenAt': '2026-11-04', 'purpose': 'greedy vs beam-2 小回归',
               'counts': {'round': sum(1 for c in cases if c['source'] == 'round'),
                          'defect': sum(1 for c in cases if c.get('group') == 'defect'),
                          'clean': sum(1 for c in cases if c.get('group') == 'clean')},
               'cases': cases}
    path = OUT / 'cases.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / 'cases.manifest.json').write_text(json.dumps(
        {'file': 'cases.json', 'sha256': digest, 'counts': payload['counts']},
        ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'cases': len(cases), 'counts': payload['counts'],
                      'sha256': digest}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
