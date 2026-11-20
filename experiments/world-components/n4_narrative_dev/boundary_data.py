"""边界数据：该表达的全部表达，表达完就结束。

三组训练单元（80）＋一套冻结确认集（40）：

  G1 单部位、单状态      40   只写这个部位的这个状态，不扩写、不复述
  G2 主体／部位最小对照  20   只换主体或部位，目标跟着换
  G3 明确包含两项信息    20   两项都保留，避免学成“逗号后一律不写”

不写死字数与分句上限：目标允许两个分句，只要都在事实之内。
"""
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402

ART = HERE.parents[2] / 'artifacts' / 'world-boundary'
PEOPLE = ('沈砚', '顾行舟', '叶知微', '阿棠', '韩渡')
PARTS = ('衣领', '下摆', '鞋面', '手背', '指尖', '鬓角', '肩头', '膝盖',
         '帽檐', '围巾', '腰侧', '发梢', '掌心', '耳后', '脚踝', '裤脚', '前襟', '背脊')
STATES = ('湿了', '沾了泥', '结了盐霜', '落着灰', '冻得发僵', '蹭破了皮')
HEADER = ('短句任务。\n地点=潮汐档案馆>长桌\n'
          '地点可见=潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌\n'
          '场景=夜；浓雾\n视角={pov}；第三人称')

# 10 个真实回合里出现过的表达，不能进训练也不能进确认集
FORBIDDEN = set("""袖口沾了雨 指节发白 斗篷下摆湿了一片 鞋底沾了泥 袖口湿到肘部
灯罩蒙了灰 掌心出汗 钟绳磨出了毛边 衣角结了盐霜 鬓发被雾打湿 被雨打湿半幅 袖口开了线
指缝里塞着泥 鞋跟磨塌了 裤脚沾了铜油 围巾松开一截 脸色发白 背上溅了泥点 手背蹭破了皮
肩头落着灰 帽檐压出折痕 脚踝肿了一块 衣领被雨浸透 指尖磨出茧 膝盖沾了泥""".split())


def unit(fact_id, name, text, kind='appearance_changed'):
    fact = {'kind': kind, 'name': name, 'text': text}
    line = FC.serialize_fact(fact)
    FC.check_line(kind, line)
    header = HEADER.format(pov=name)
    target = f'{name}的{text}。'
    return {'unitId': fact_id, 'kind': kind, 'fact': fact, 'target': target,
            'input': header + '\n事实=' + line + '\n短句：\n'}


def single(bank, start, count, offset=0):
    """bank: [(name, part, state)]；target 只写这一个部位。"""
    units = []
    for index in range(count):
        name, part, state = bank[index]
        unit_id = f'b{start + index}'
        units.append(unit(unit_id, name, f'{part}{state}'))
    return units


def main():
    ART.mkdir(parents=True, exist_ok=True)
    combos = [(name, part, state) for name in PEOPLE for part in PARTS for state in STATES]
    combos = [item for item in combos if f'{item[1]}{item[2]}' not in FORBIDDEN]
    used = set()

    def take(rows):
        out = []
        for item in rows:
            key = (item[0], item[1], item[2])
            if key in used:
                continue
            used.add(key)
            out.append(item)
        return out

    # G1: 单部位、单状态（40）
    g1 = single(take(combos[:44])[:40], 1, 40)

    # G2: 最小对照（20）——5 对只换主体，5 对只换部位
    contrast = []
    subject_pairs = [('沈砚', '顾行舟', '衣领', '湿了'), ('叶知微', '阿棠', '肩头', '沾了泥'),
                     ('韩渡', '沈砚', '腰侧', '落着灰'), ('顾行舟', '叶知微', '发梢', '结了盐霜'),
                     ('阿棠', '韩渡', '裤脚', '冻得发僵')]
    for left, right, part, state in subject_pairs:
        contrast += [(left, part, state), (right, part, state)]
    part_pairs = [('沈砚', '衣领', '袖口', '湿了'), ('顾行舟', '下摆', '前襟', '沾了泥'),
                  ('叶知微', '指尖', '掌心', '蹭破了皮'), ('阿棠', '膝盖', '脚踝', '落着灰'),
                  ('韩渡', '帽檐', '围巾', '结了盐霜')]
    for name, part_a, part_b, state in part_pairs:
        contrast += [(name, part_a, state), (name, part_b, state)]
    contrast = take(contrast)
    filler = [item for item in combos if item not in used]
    for candidate in filler:
        if len(contrast) >= 20:
            break
        contrast += take([candidate])
    g2 = single(contrast[:20], 41, len(contrast[:20]))

    # G3: 两项信息（20）——目标必须保留两项
    g3 = []
    for index in range(20):
        name = PEOPLE[index % len(PEOPLE)]
        part_a = PARTS[(index * 2) % len(PARTS)]
        part_b = PARTS[(index * 2 + 5) % len(PARTS)]
        state = STATES[index % len(STATES)]
        if part_a == part_b:
            part_b = PARTS[(index * 2 + 7) % len(PARTS)]
        text = f'{part_a}{state}，{part_b}也{state}'
        while text in used:
            part_b = PARTS[(PARTS.index(part_b) + 1) % len(PARTS)]
            text = f'{part_a}{state}，{part_b}也{state}'
        used.add(text)
        g3.append(unit(f'b{61 + index}', name, text))

    train = g1 + g2 + g3
    FC.check_units(train)
    keys = [(u['fact']['name'], u['fact']['text']) for u in train]
    assert len(set(keys)) == len(keys), '训练集里出现重复事实'

    # 确认集（40）：全新组合，单项 20 ＋ 双项 20
    seen = {text for _name, text in keys}
    confirm_pool = [item for item in combos if f'{item[1]}{item[2]}' not in seen
                    and (item[0], f'{item[1]}{item[2]}') not in keys]
    confirm_pool = [item for item in confirm_pool if (item[0], item[1], item[2]) not in used]
    confirm = single(confirm_pool[:20], 101, 20)
    for index in range(20):
        name = PEOPLE[(index + 2) % len(PEOPLE)]
        part_a = PARTS[(index * 3 + 1) % len(PARTS)]
        part_b = PARTS[(index * 3 + 7) % len(PARTS)]
        state = STATES[(index + 3) % len(STATES)]
        confirm.append(unit(f'b{121 + index}', name,
                            f'{part_a}{state}，{part_b}也{state}'))
    FC.check_units(confirm)

    def dump(path, rows):
        path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n',
                        encoding='utf-8')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(path.name, len(rows), 'sha256', digest)
        return digest

    digests = {'train': dump(ART / 'boundary-train80.jsonl', train),
               'confirm': dump(ART / 'boundary-confirm40.jsonl', confirm)}
    (ART / 'boundary-manifest.json').write_text(json.dumps({
        'groups': {'g1_single': len(g1), 'g2_contrast': len(g2), 'g3_double': len(g3)},
        'confirm': {'single': 20, 'double': 20},
        'files': {'boundary-train80.jsonl': digests['train'],
                  'boundary-confirm40.jsonl': digests['confirm']},
        'rules': ['目标只写事实内的内容', '允许两个分句', '不写死字数',
                  '不复述同一状态', '不扩写未授权的部位'],
        'forbidden': sorted(FORBIDDEN),
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
