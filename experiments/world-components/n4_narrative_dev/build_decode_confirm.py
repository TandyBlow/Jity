"""冻结束搜索确认集 40 条：单项、双项、移动、物件绑定各 10 条。

全部新组合，不复用旧确认集的句子。
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402

import sys as _paths_sys
_paths_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from component_paths import PATHS

ART = PATHS.output('decode-compare')
PEOPLE = ('沈砚', '顾行舟', '叶知微', '阿棠', '韩渡')
PARTS = ('衣领', '下摆', '鞋面', '手背', '指尖', '鬓角', '肩头', '膝盖',
         '帽檐', '围巾', '腰侧', '发梢', '掌心', '耳后', '脚踝', '裤脚', '前襟', '背脊')
STATES = ('湿了', '沾了泥', '结了盐霜', '落着灰', '冻得发僵', '蹭破了皮')
ITEMS = ('铜灯罩', '抹布', '潮汐簿', '钟绳', '警示灯', '铁链', '案板', '鱼筐',
         '油纸伞', '缆绳')
ITEM_STATES = ('蒙了盐雾', '裂了缝', '边角磨破', '生了锈', '沾了铜油', '落着灰')
MOVES = (('潮渡', '雾堤', '上'), ('雾堤', '潮渡', '下'), ('潮生巷', '早市', '平'),
         ('早市', '潮生巷', '平'), ('潮汐档案馆', '潮渡', '平'), ('潮渡', '潮汐档案馆', '平'),
         ('旧灯塔', '雾堤', '平'), ('雾堤', '旧灯塔', '平'), ('早市', '潮渡', '平'),
         ('潮生巷', '潮汐档案馆', '平'))

HEADER = ('短句任务。\n地点={place}\n地点可见={visible}\n场景={scene}\n视角={pov}；第三人称')
PLACES = {
    '潮渡': ('潮渡>栈桥', '缆绳、渡船、船灯、系泊绳、木桩、水面、栈桥', '清晨；薄雾；船灯'),
    '雾堤': ('雾堤>堤面', '钟绳、雾警钟、警示灯、铁链、钟架、石壁、铁皮、石阶', '夜；浓雾；警示灯'),
    '旧灯塔': ('旧灯塔>塔顶', '铜灯罩、灯芯、抹布、擦铜油、玻璃罩、火苗、石阶、旋梯',
             '夜；夜雾，海风；铜灯已点亮'),
    '潮汐档案馆': ('潮汐档案馆>长桌', '潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌',
              '夜；小雨；铜灯'),
    '潮生巷': ('潮生巷', '油纸伞、鱼筐、石板、纸灯笼、排水沟、墙根、水洼', '入夜；小雨；纸灯笼'),
    '早市': ('早市', '银鳞鱼、鱼筐、案板、抹布、帆布棚、石板、白汽', '清晨；薄雾；棚下散光'),
}

BOUNDARY_DIR = PATHS.input('world-boundary')
PRIOR = set()
for previous in ('boundary-train80.jsonl', 'boundary-confirm40.jsonl',
                 'boundary2-train80.jsonl', 'boundary2-confirm40.jsonl'):
    path = BOUNDARY_DIR / previous
    if not path.exists():
        continue
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            unit = json.loads(line)
            PRIOR.add((unit['fact']['name'], unit['fact']['text']))

USED = set("""袖口沾了雨 指节发白 斗篷下摆湿了一片 鞋底沾了泥 袖口湿到肘部
灯罩蒙了灰 掌心出汗 钟绳磨出了毛边 衣角结了盐霜 鬓发被雾打湿 被雨打湿半幅 袖口开了线
指缝里塞着泥 鞋跟磨塌了 裤脚沾了铜油 围巾松开一截 脸色发白 背上溅了泥点 手背蹭破了皮
肩头落着灰 帽檐压出折痕 脚踝肿了一块 衣领被雨浸透 指尖磨出茧 膝盖沾了泥""".split())


def unit(case_id, kind, name, text, place='潮汐档案馆', extra=None):
    fact = {'kind': kind, 'name': name}
    if kind == 'moved':
        fact.update({'from': extra['from'], 'to': extra['to'],
                     'direction': extra.get('direction', '平')})
    else:
        fact['text'] = text
    line = FC.serialize_fact(fact)
    FC.check_line(kind, line)
    location, visible, scene = PLACES[place]
    prompt = HEADER.format(place=location, visible=visible, scene=scene, pov=name)
    if kind == 'moved':
        prompt += f"\n方向={fact['direction']}"
    prompt += '\n事实=' + line + '\n短句：\n'
    return {'caseId': case_id, 'group': kind, 'kind': kind, 'name': name,
            'factText': text or f"{fact['from']}→{fact['to']}",
            'input': prompt}


def main():
    ART.mkdir(parents=True, exist_ok=True)
    cases = []
    index = 0
    # 单项 10
    made = 0
    for name in PEOPLE:
        for part in PARTS:
            for state in STATES:
                if made >= 10:
                    break
                text = f'{part}{state}'
                if text in USED or (name, text) in PRIOR:
                    continue
                USED.add(text)
                place = list(PLACES)[index % len(PLACES)]
                cases.append(unit(f'd{index:03d}', 'appearance_changed', name, text, place))
                index += 1
                made += 1
            if made >= 10:
                break
        if made >= 10:
            break
    # 双项 10（同状态 5 / 不同状态 5）
    for offset in range(10):
        name = PEOPLE[offset % len(PEOPLE)]
        part_a = PARTS[(offset * 3) % len(PARTS)]
        part_b = PARTS[(offset * 3 + 5) % len(PARTS)]
        state_a = STATES[offset % len(STATES)]
        state_b = state_a if offset < 5 else STATES[(offset + 2) % len(STATES)]
        text = (f'{part_a}{state_a}，{part_b}也{state_a}' if offset < 5
                else f'{part_a}{state_a}，{part_b}{state_b}')
        guard = 0
        while (name, text) in PRIOR and guard < 40:
            part_b = PARTS[(PARTS.index(part_b) + 1) % len(PARTS)]
            text = (f'{part_a}{state_a}，{part_b}也{state_a}' if offset < 5
                    else f'{part_a}{state_a}，{part_b}{state_b}')
            guard += 1
        cases.append(unit(f'd{index:03d}', 'appearance_changed', name, text,
                          list(PLACES)[offset % len(PLACES)]))
        index += 1
    # 移动 10
    for offset, (origin, target, direction) in enumerate(MOVES):
        name = PEOPLE[offset % len(PEOPLE)]
        cases.append(unit(f'd{index:03d}', 'moved', name, f'{origin}→{target}',
                          target, {'from': origin, 'to': target,
                                   'direction': direction}))
        index += 1
    # 物件绑定 10
    for offset in range(10):
        item = ITEMS[offset % len(ITEMS)]
        state = ITEM_STATES[offset % len(ITEM_STATES)]
        cases.append(unit(f'd{index:03d}', 'appearance_changed', item, state,
                          list(PLACES)[offset % len(PLACES)]))
        index += 1
    FC.check_units([{'unitId': c['caseId'], 'kind': c['kind'], 'input': c['input']}
                    for c in cases])
    payload = {'frozenAt': '2026-11-04', 'counts': {'single': 10, 'double': 10,
                                                    'moved': 10, 'object': 10},
               'cases': cases}
    path = ART / 'confirm40.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (ART / 'confirm40.manifest.json').write_text(json.dumps(
        {'file': 'confirm40.json', 'sha256': digest, 'counts': payload['counts']},
        ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({'cases': len(cases), 'sha256': digest}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
