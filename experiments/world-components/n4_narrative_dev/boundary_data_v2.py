"""边界数据 v2：80 训练（20 单项 + 20 对照 + 40 双项）＋ 新确认 40。

双项覆盖不同部位、同状态与不同状态；新确认集 = 20 双项 + 10 带无关可见背景的单项
+ 10 主体／部位最小对照。全部是新组合，不改写旧失败句。
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

PLAIN = ('短句任务。\n地点=潮汐档案馆>长桌\n'
         '地点可见=潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌\n'
         '场景=夜；浓雾\n视角={pov}；第三人称')
# 带无关可见背景：可见清单里塞进与事实无关的物件
BUSY = ('短句任务。\n地点=潮汐档案馆>长桌\n'
        '地点可见=潮汐簿、铜灯、干纸、墨、笔架、门槛、天窗、长桌、'
        '油布包、备用钥匙、铁链、警示灯、钟绳、雾警钟\n'
        '场景=夜；浓雾；铜灯\n视角={pov}；第三人称')

FORBIDDEN = set("""袖口沾了雨 指节发白 斗篷下摆湿了一片 鞋底沾了泥 袖口湿到肘部
灯罩蒙了灰 掌心出汗 钟绳磨出了毛边 衣角结了盐霜 鬓发被雾打湿 被雨打湿半幅 袖口开了线
指缝里塞着泥 鞋跟磨塌了 裤脚沾了铜油 围巾松开一截 脸色发白 背上溅了泥点 手背蹭破了皮
肩头落着灰 帽檐压出折痕 脚踝肿了一块 衣领被雨浸透 指尖磨出茧 膝盖沾了泥
腰侧湿了，前襟也湿了 下摆落着灰，膝盖也落着灰 指尖冻得发僵，腰侧也冻得发僵
膝盖蹭破了皮，耳后也蹭破了皮 耳后沾了泥，下摆也沾了泥 前襟结了盐霜，指尖也结了盐霜""".split())


def unit(fact_id, name, text, header=PLAIN):
    fact = {'kind': 'appearance_changed', 'name': name, 'text': text}
    line = FC.serialize_fact(fact)
    FC.check_line(fact['kind'], line)
    return {'unitId': fact_id, 'kind': fact['kind'], 'fact': fact,
            'target': f'{name}的{text}。',
            'input': header.format(pov=name) + '\n事实=' + line + '\n短句：\n'}


class Bank:
    def __init__(self):
        self.used = set()
        self.combos = [(n, p, s) for n in PEOPLE for p in PARTS for s in STATES
                       if f'{p}{s}' not in FORBIDDEN]
        self.cursor = 0

    def single(self):
        while self.cursor < len(self.combos):
            item = self.combos[self.cursor]
            self.cursor += 1
            if (item[0], item[1], item[2]) in self.used:
                continue
            self.used.add((item[0], item[1], item[2]))
            return item
        raise RuntimeError('组合用尽')

    def double(self, same_state=True):
        while self.cursor < len(self.combos):
            name, part_a, state_a = self.single()
            for offset in range(2, 12):
                idx = (self.cursor + offset) % len(self.combos)
                name_b, part_b, state_b = self.combos[idx]
                if name_b != name or part_b == part_a:
                    continue
                if same_state and state_b != state_a:
                    continue
                if not same_state and state_b == state_a:
                    continue
                self.used.add((name_b, part_b, state_b))
                text = (f'{part_a}{state_a}，{part_b}也{state_a}' if same_state
                        else f'{part_a}{state_a}，{part_b}{state_b}')
                return name, text
        raise RuntimeError('双项组合用尽')


def main():
    ART.mkdir(parents=True, exist_ok=True)
    bank = Bank()
    train = []
    for index in range(20):                                    # 单项 20
        name, part, state = bank.single()
        train.append(unit(f'v1_{index:02d}', name, f'{part}{state}'))
    subject_pairs = [(0, 1), (2, 3), (4, 0), (1, 2), (3, 4)]
    for pair_index in range(10):                               # 对照 20
        name_a, part, state = bank.single()
        name_b = PEOPLE[(PEOPLE.index(name_a) + 1) % len(PEOPLE)]
        text_a = f'{part}{state}'
        bank.used.add((name_a, part, state))
        bank.used.add((name_b, part, state))
        train.append(unit(f'v2_{pair_index:02d}a', name_a, text_a))
        train.append(unit(f'v2_{pair_index:02d}b', name_b, text_a))
    for index in range(40):                                    # 双项 40
        name, text = bank.double(same_state=(index % 2 == 0))
        train.append(unit(f'v3_{index:02d}', name, text))
    FC.check_units(train)
    keys = [(u['fact']['name'], u['fact']['text']) for u in train]
    assert len(set(keys)) == len(keys), '训练集重复事实'

    confirm = []
    for index in range(20):                                    # 新确认：双项 20
        name, text = bank.double(same_state=(index % 2 == 0))
        confirm.append(unit(f'c1_{index:02d}', name, text))
    for index in range(10):                                    # 新确认：带无关背景的单项 10
        name, part, state = bank.single()
        confirm.append(unit(f'c2_{index:02d}', name, f'{part}{state}', header=BUSY))
    for index in range(5):                                     # 新确认：最小对照 10（5 对）
        name, part, state = bank.single()
        other = PEOPLE[(PEOPLE.index(name) + 2) % len(PEOPLE)]
        confirm.append(unit(f'c3_{index:02d}a', name, f'{part}{state}'))
        confirm.append(unit(f'c3_{index:02d}b', other, f'{part}{state}'))
    FC.check_units(confirm)

    def dump(path, rows):
        path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n',
                        encoding='utf-8')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(path.name, len(rows), digest)
        return digest

    digests = {'train': dump(ART / 'boundary2-train80.jsonl', train),
               'confirm': dump(ART / 'boundary2-confirm40.jsonl', confirm)}
    (ART / 'boundary2-manifest.json').write_text(json.dumps({
        'train': {'single': 20, 'contrast': 20, 'double_same_state': 20,
                  'double_diff_state': 20},
        'confirm': {'double': 20, 'single_busy_visible': 10, 'contrast': 10},  # 5 对
        'files': digests,
        'forbidden': sorted(FORBIDDEN),
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
