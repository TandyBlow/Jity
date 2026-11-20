"""Build one fabricated narration-dataset row at production scale.

World: 30 characters, 25 locations, 200 items. One round: three characters
change. The script writes two forms of the same row:

  row-big-full.jsonl    before/after carry every entity (what a naive
                        "previous state + delta + current state" row is)
  row-big-scoped.jsonl  before/after carry only the entities this round
                        touches, plus the protagonist

and prints both sizes so the cost of the full form is visible.

Everything here is invented. No database read, no committed point.
"""

import io
import json
import random

SEED = 20261108
OUT_DIR = "experiments/world-components/narration-dataset-v1"

SURNAMES = "沈林周叶顾韩陆程苏谢秦唐方江黎温季柏岑"
GIVEN = ["砚", "知微", "行舟", "青", "闻雪", "远", "照", "望舒", "临", "既明",
         "долг", "怀瑾", "执", "云舟", "书言", "停云", "寄北", "含章", "叙白", "清和"]

LOCATIONS = [
    ("一层门厅", None), ("借阅台", "一层门厅"), ("还书处", "一层门厅"),
    ("一层走廊", None), ("值班室", "一层走廊"), ("茶水间", "一层走廊"),
    ("二层走廊", None), ("二层西侧书架", "二层走廊"), ("二层东侧书架", "二层走廊"),
    ("报刊阅览室", "二层走廊"), ("三层走廊", None), ("古籍库", "三层走廊"),
    ("缩微胶片室", "三层走廊"), ("地下书库", None), ("旧刊堆放区", "地下书库"),
    ("装订间", "地下书库"), ("庭院", None), ("东侧回廊", "庭院"),
    ("西侧回廊", "庭院"), ("庭院石阶", "庭院"), ("馆外街道", None),
    ("门卫岗亭", "馆外街道"), ("后门", "馆外街道"), ("配电间", None),
    ("天台", None),
]

ITEM_NOUNS = ["借阅单", "还书箱", "登记簿", "索书号标签", "书车", "梯凳", "手推车",
              "灯罩", "台灯", "窗栓", "门牌", "钥匙串", "水壶", "茶杯", "抹布",
              "纸箱", "麻绳", "牛皮纸", "封套", "印章", "印泥", "订书机", "剪刀",
              "胶水", "雨伞", "外套", "手套", "口罩", "手电", "电池", "钟", "挂历",
              "花名册", "值日表", "便签盒", "笔筒", "图钉", "尺子", "放大镜", "镊子"]

TASK_ROOTS = ["在闭馆前补齐今天缺失的借阅记录", "把地下一层受潮的旧刊挑出来",
              "核实三层古籍库的出入登记", "把二层的散书按索书号归位",
              "在交班前清点还书箱", "查清昨夜值班室里响动的原因",
              "把庭院的积水排掉", "核对本周逾期通知的名单",
              "把缩微胶片按卷号重新排架", "在天亮前修好配电间的跳闸"]

SUBTASKS = ["核对还书箱", "查阅值班登记", "翻看借阅单存根", "清点书车",
            "登记新到的期刊", "检查窗栓", "擦拭灯罩", "整理东侧书架",
            "整理西侧书架", "重排索书号标签", "打开除湿机", "检查排水沟",
            "记录跳闸时间", "核对出入签字", "把散书搬回书库"]


def main():
    rng = random.Random(SEED)

    locations = {name: parent for name, parent in LOCATIONS}
    leaves = [name for name in locations if any(p == name for p in locations.values())]
    rooms = [name for name in locations if locations[name] is None]

    # names are unique; the projection below keys people by name
    names = []
    used = set()
    while len(names) < 30:
        surname = rng.choice(SURNAMES)
        given = rng.choice(GIVEN).replace("долг", "重")
        name = surname + given
        if name not in used:
            used.add(name)
            names.append(name)

    characters = {}
    for index, name in enumerate(names):
        home = rng.choice(rooms)
        root = TASK_ROOTS[index % len(TASK_ROOTS)]
        subs = rng.sample(SUBTASKS, rng.choice((0, 1, 2, 3)))
        characters[name] = {
            "位置": home,
            "精神值": rng.choice((35, 42, 50, 58, 62, 70, 75, 80)),
            "任务": {
                "大任务": {"目标": root, "状态": "未完成"},
                "小任务": [{"目标": goal, "状态": "未完成"} for goal in subs],
            },
            "人格": [rng.choice(("谨慎", "好奇心重", "沉默寡言", "护短", "讲究次序"))],
        }

    items = {}
    for index in range(200):
        base = rng.choice(ITEM_NOUNS)
        label = base if base not in items else f"{base}{index}"
        items[label] = {"位置": rng.choice(leaves + rooms)}

    before = {"地点": locations, "人物": characters, "物品": items}
    after = json.loads(json.dumps(before, ensure_ascii=False))

    mover, doer, changer = names[0], names[1], names[2]
    from_room = before["人物"][mover]["位置"]
    to_room = rng.choice([room for room in rooms if room != from_room])
    after["人物"][mover]["位置"] = to_room

    goal = before["人物"][doer]["任务"]["小任务"][0]["目标"]
    after["人物"][doer]["任务"]["小任务"][0]["状态"] = "已完成"

    before["人物"][changer]["精神值"] = 58
    after["人物"][changer]["精神值"] = 51
    after["人物"][changer]["人格"].append("经历了停电后格外留心线路")

    delta = {
        "时间推进": "1 分钟",
        "变化": {
            mover: {"位置": to_room},
            doer: {"完成任务": [{"小任务": goal, "属于大任务": before["人物"][doer]["任务"]["大任务"]["目标"]}]},
            changer: {"精神值": 51, "新增人格": ["经历了停电后格外留心线路"]},
        },
    }

    text = (
        f"一分钟过去了。{mover}从{from_room}走到了{to_room}。"
        f"{doer}完成了「{goal}」，大任务「{before['人物'][doer]['任务']['大任务']['目标']}」还没有完成。"
        f"{changer}的精神值从58降到51，心里多了一条「经历了停电后格外留心线路」。"
    )

    full = {"上回合状态": before, "本回合变化": delta, "本回合状态": after,
            "视角": mover, "叙事": text}

    touched = set(delta["变化"]) | {mover}
    touched_locations = {from_room, to_room}
    for name in touched:
        touched_locations.add(after["人物"][name]["位置"])
    for label, item in items.items():
        if item["位置"] in touched_locations:
            touched_locations.add(item["位置"])

    def scope(state):
        return {
            "地点": {name: parent for name, parent in state["地点"].items() if name in touched_locations},
            "人物": {name: state["人物"][name] for name in touched},
            "物品": {label: item for label, item in state["物品"].items() if item["位置"] in touched_locations},
        }

    scoped = {"上回合状态": scope(before), "本回合变化": delta, "本回合状态": scope(after),
              "视角": mover, "叙事": text}

    for filename, row in (("row-big-full.jsonl", full), ("row-big-scoped.jsonl", scoped)):
        path = f"{OUT_DIR}/{filename}"
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        size = len(io.open(path, encoding="utf-8").read())
        print(f"{filename}: {size} chars")

    print(f"world: {len(characters)} characters, {len(locations)} locations, {len(items)} items")
    print(f"scoped keeps: {len(scoped['上回合状态']['人物'])} characters, "
          f"{len(scoped['上回合状态']['地点'])} locations, {len(scoped['上回合状态']['物品'])} items")
    print(text)


if __name__ == "__main__":
    main()
