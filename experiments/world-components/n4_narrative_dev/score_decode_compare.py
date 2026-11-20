"""小回归评分：必述／绑定／语义重复／未授权新增，两臂分别统计。

规则与之前几轮一致（允许：移动起终点与地名、方向词、无变化的标准写法、
状态变化的心理描写、场景字段给的现象、地点可见里物件的出场）。
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sys as _paths_sys
_paths_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from component_paths import PATHS

ART = PATHS.inputs
DECODE = PATHS.output('decode-compare')
import argparse
_parser = argparse.ArgumentParser()
_parser.add_argument('--cases', default=str(PATHS.input('decode-compare/cases.json')))
_parser.add_argument('--result', default=str(DECODE / 'arm-ab.json'))
_parser.add_argument('--out', default=str(DECODE / 'scores.json'))
ARGS = _parser.parse_args()
CASES = PATHS.input(ARGS.cases)
RESULT = PATHS.output(ARGS.result)
DIAG = PATHS.input('world-components')
ARGS.out = str(PATHS.output(ARGS.out))

ALIAS = {'潮汐档案馆': ['档案馆'], '潮渡': ['渡口', '栈桥'], '旧灯塔': ['灯塔'],
         '雾堤': ['堤面', '堤上'], '潮生巷': ['巷子'], '早市': ['集市']}
LITERAL_REPEAT = re.compile(r'(.{2,6})[,，]\1')
NO_CHANGE = ('没有', '安静', '还在原处', '一直吹', '没有动', '人来人往', '晃了晃',
             '什么也没有再发生', '没有新的变化')


def field(text, key):
    match = re.search(rf'^{key}=(.*)$', text, re.M)
    return match.group(1) if match else ''


def load_units():
    units = {}
    for name in ('n4-final24-contract.jsonl', 'n4-cf24-contract.jsonl',
                 'n4-object18-contract.jsonl', 'n4-expand36-contract.jsonl'):
        for line in (DIAG / name).read_text(encoding='utf-8').splitlines():
            if line.strip():
                unit = json.loads(line)
                units[unit['unitId']] = unit
    return units


def fact_parts(case, units):
    if case['source'] == 'diag':
        line = field(units[case['caseId']]['input'], '事实')
        return line.split('｜')
    return [case['name'], {'moved': '移动', 'outcome': '结果'}.get(case['kind'], '外貌变化'),
            case['factText']]


def visible_and_scene(case, units):
    if case['source'] != 'diag':
        return ('潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌', '夜；浓雾')
    text = units[case['caseId']]['input']
    return field(text, '地点可见'), field(text, '场景')


def check(case, text, units):
    parts = fact_parts(case, units)
    name, value = parts[0], parts[-1]
    visible, scene = visible_and_scene(case, units)
    problems = {'support': False, 'binding': False, 'direction': False,
                'repeat': False, 'extra': ''}

    if case['kind'] == 'no_change':
        problems['support'] = any(word in text for word in NO_CHANGE)
    elif case['kind'] == 'moved':
        origin, target = value.split('→')
        hit = lambda word: word in text or any(alias in text for alias in ALIAS.get(word, []))
        problems['support'] = hit(origin) and hit(target)
    elif case['kind'] == 'sanity_changed':
        problems['support'] = True          # 方向靠人工，机械不计
    else:
        fragments = [w for w in re.findall(r'[\u4e00-\u9fff]{2,}', value.replace('把', ''))]
        problems['support'] = all(w in text for w in fragments)

    # 绑定：产物里出现的主体必须是事实主体；outcome 还要出现事实里的对象
    other_names = [n for n in ('沈砚', '顾行舟', '叶知微', '阿棠', '韩渡', '林川', '周宁',
                               '陈默', '沈禾', '叶南', '高岭') if n != name]
    problems['binding'] = any(n in text for n in other_names)   # True = 串了主体


    # 方向：moved 单元的方向字段为「平」时不得写上行/下行
    direction_field = ''
    if case['source'] == 'diag':
        direction_field = field(units[case['caseId']]['input'], '方向')
    else:
        match = re.search(r'^方向=(.*)$', case['input'], re.M)
        direction_field = match.group(1).strip() if match else ''
    if case['kind'] == 'moved' and direction_field:
        up_words = ('上来', '上去', '上到')
        down_words = ('下来', '下去', '下到')
        if direction_field == '平' and any(w in text for w in up_words + down_words):
            problems['direction'] = True
        elif direction_field == '下' and any(w in text for w in up_words):
            problems['direction'] = True
        elif direction_field == '上' and any(w in text for w in down_words):
            problems['direction'] = True

    problems['repeat'] = bool(LITERAL_REPEAT.search(text.replace(',', '，')))

    # 未授权新增：去掉姓名、事实片段、可见与场景词后的残余
    body = text
    for token in [name, value, value.replace('把', '')]:
        body = body.replace(token, '')
    for token in (re.findall(r'[\u4e00-\u9fff]{2,}', visible)
                  + re.findall(r'[\u4e00-\u9fff]{2,}', scene)):
        body = body.replace(token, '')
    for char in '的着了也，。、；上下里外把到从过再又还向在是有没有':
        body = body.replace(char, '')
    problems['extra'] = body.strip()
    return problems


def main():
    payload = json.loads(CASES.read_text(encoding='utf-8'))
    result = json.loads(RESULT.read_text(encoding='utf-8'))
    units = load_units()
    by_case = {row['caseId']: row for row in result['rows']}
    report = {'greedy': {'support': 0, 'binding': 0, 'direction': 0, 'repeat': 0, 'extra': 0},
              'beam': {'support': 0, 'binding': 0, 'direction': 0, 'repeat': 0, 'extra': 0},
              'details': []}
    for case in payload['cases']:
        row = by_case[case['caseId']]
        entry = {'caseId': case['caseId'], 'group': case.get('group'),
                 'fact': '｜'.join(fact_parts(case, units))}
        for arm in ('greedy', 'beam'):
            problems = check(case, row[arm]['text'], units)
            entry[arm] = {'text': row[arm]['text'], **problems}
            if problems['support']:
                report[arm]['support'] += 1
            if problems['binding']:
                report[arm]['binding'] += 1
            if problems['direction']:
                report[arm]['direction'] += 1
            if problems['repeat']:
                report[arm]['repeat'] += 1
            if problems['extra']:
                report[arm]['extra'] += 1
        report['details'].append(entry)
    pathlib.Path(ARGS.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')

    for arm in ('greedy', 'beam'):
        stats = report[arm]
        print(f"{arm:7} 必述 {stats['support']}/{len(payload['cases'])} "
              f"绑定失败 {stats['binding']} 方向错 {stats['direction']} "
              f"字面重复 {stats['repeat']} 需查新增 {stats['extra']}")
    print()
    for entry in report['details']:
        if entry['greedy']['text'].replace(',', '，') == entry['beam']['text'].replace(',', '，'):
            continue
        print(entry['caseId'], '|', entry['fact'])
        for arm in ('greedy', 'beam'):
            item = entry[arm]
            flags = [f'必述{"✓" if item["support"] else "✗"}',
                     f'绑定{"✗" if item["binding"] else "✓"}',
                     f'方向{"✗" if item["direction"] else "✓"}',
                     f'重复{"✓" if item["repeat"] else "·"}',
                     f'新增[{item["extra"]}]' if item['extra'] else '新增·']
            print(f"   {arm:6} {' '.join(flags)} | {item['text']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
