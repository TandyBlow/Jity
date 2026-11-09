"""One fabricated full-state row at production scale, with appearances.

World: 30 characters, 25 locations, 200 items. Every location, item and
character has an appearance record; the round changes one of each, plus a
position, a subtask achievement, a sanity drop and a personality addition.

Goals are long-horizon (find a hidden thing / uncover the truth / avenge),
with short subtasks under each.

The row keeps the whole world in both states, as requested. Time advance and
the explicit change list are kept; see the report for what they add over a
plain diff.
"""

import io
import json
import random

SEED = 20261109
OUT_DIR = "experiments/world-components/narration-dataset-v1"

SURNAMES = "沈林周叶顾韩陆程苏谢秦唐方江黎温季柏岑"
GIVEN = ["砚", "知微", "行舟", "青", "闻雪", "远", "照", "望舒", "临", "既明",
         "怀瑾", "执", "云舟", "书言", "停云", "寄北", "含章", "叙白", "清和", "暮"]

LOCATIONS = [
    ("一层门厅", None, "地砖被来往的脚步磨得发白，正对大门挂着一面停摆的钟。"),
    ("借阅台", "一层门厅", "台面是硬木的，边角用铜皮包着，抽屉上着锁。"),
    ("还书处", "一层门厅", "铁皮还书箱敞着口，旁边堆着没来得及上架的书车。"),
    ("一层走廊", None, "走廊很窄，两侧墙上贴满发黄的告示。"),
    ("值班室", "一层走廊", "一张行军床、一部内线电话，窗户糊着报纸。"),
    ("茶水间", "一层走廊", "水壶底结着厚厚的水垢，窗台上排着搪瓷杯。"),
    ("二层走廊", None, "地板踩上去会响，尽头的一盏灯长期不亮。"),
    ("二层西侧书架", "二层走廊", "书架高到天花板，索书号标签翘起了边。"),
    ("二层东侧书架", "二层走廊", "书架间留出的过道只容一人侧身。"),
    ("报刊阅览室", "二层走廊", "长条桌上摊着没归位的报纸，空气里有旧纸的味道。"),
    ("三层走廊", None, "这一层没有窗，墙皮受潮鼓起。"),
    ("古籍库", "三层走廊", "库门是双层的，内层包着铁皮，钥匙由两人分管。"),
    ("缩微胶片室", "三层走廊", "机器蒙着防尘布，胶片盒按卷号码在铁架上。"),
    ("地下书库", None, "除湿机日夜响着，书脊上有一层薄霉。"),
    ("旧刊堆放区", "地下书库", "旧报捆成垛，麻绳勒出的印子还在。"),
    ("装订间", "地下书库", "裁纸刀和胶锅都还留着，碎纸屑没扫。"),
    ("庭院", None, "石板缝里长着青苔，中间一棵老槐树。"),
    ("东侧回廊", "庭院", "回廊的灯坏了一盏，晚上走过去要摸墙。"),
    ("西侧回廊", "庭院", "廊柱上的漆起皮，露出里面的木头。"),
    ("庭院石阶", "庭院", "石阶被雨水冲出浅浅的沟。"),
    ("馆外街道", None, "路灯昏黄，对面是一排关了门的铺子。"),
    ("门卫岗亭", "馆外街道", "岗亭里放着一台老式电暖器，玻璃上贴着值班表。"),
    ("后门", "馆外街道", "铁门上了两道锁，门轴上挂着油壶。"),
    ("配电间", None, "配电箱的漆掉了一半，空气里有轻微的焦味。"),
    ("天台", None, "地面铺着防水卷材，角落里堆着废弃的灯架。"),
]

ITEM_NOUNS = ["借阅单", "还书箱", "登记簿", "索书号标签", "书车", "梯凳", "手推车",
              "灯罩", "台灯", "窗栓", "门牌", "钥匙串", "水壶", "茶杯", "抹布",
              "纸箱", "麻绳", "牛皮纸", "封套", "印章", "印泥", "订书机", "剪刀",
              "胶水", "雨伞", "外套", "手套", "口罩", "手电", "电池", "钟", "挂历",
              "花名册", "值日表", "便签盒", "笔筒", "图钉", "尺子", "放大镜", "镊子"]

ITEM_LOOKS = ["边角磨圆了", "表面有一层薄灰", "漆皮翘起", "木头被手汗浸得发亮",
              "铁皮上有锈斑", "布面褪成了浅色", "纸页卷边", "还留着上一任的笔迹"]

ROOTS = ["找到被族人藏起来的那本族谱原本", "查清十年前那场火灾是谁放的火",
         "替死去的搭档报仇", "找到父亲留下的那只铁皮匣子",
         "弄清母亲改名换姓之前到底是谁", "拿到能证明兄长清白的原始记录"]

SUBTASKS = ["翻看十年前的值班记录", "核对还书箱里的借阅单存根", "查访当年的门卫",
            "翻检古籍库的出入签字", "比对三份互相矛盾的登记簿", "找到知情的老装订工",
            "把受潮的旧刊挑出来晾干", "在缩微胶片里找那一天的报纸",
            "问清配电间那晚跳闸的时间", "找出被人撕掉的那一页"]

APPEARANCES = ["穿灰布外套", "袖口沾了墨", "头发用一根木簪别着", "鞋面有一层土",
               "围巾洗得发白", "指节上有旧伤", "衣角被雨打湿过", "戴着一副圆框眼镜"]

PERSONALITIES = ["谨慎", "好奇心重", "沉默寡言", "护短", "讲究次序", "记仇", "心软"]


def main():
    rng = random.Random(SEED)

    locations = {name: {"位于": parent, "外貌": [look]} for name, parent, look in LOCATIONS}
    rooms = [name for name, parent, _ in LOCATIONS if parent is None]
    leaves = [name for name, _, _ in LOCATIONS if locations[name]["位于"] is not None]

    names, used = [], set()
    while len(names) < 30:
        name = rng.choice(SURNAMES) + rng.choice(GIVEN)
        if name not in used:
            used.add(name)
            names.append(name)

    characters = {}
    for index, name in enumerate(names):
        characters[name] = {
            "位置": rng.choice(rooms),
            "精神值": rng.choice((35, 42, 50, 58, 62, 70, 75, 80)),
            "外貌": rng.sample(APPEARANCES, 2),
            "人格": [rng.choice(PERSONALITIES)],
            "任务": {
                "大任务": {"目标": ROOTS[index % len(ROOTS)], "状态": "未完成"},
                "小任务": [{"目标": goal, "状态": "未完成"}
                        for goal in rng.sample(SUBTASKS, rng.choice((0, 1, 2, 3)))],
            },
        }

    items, used_labels = {}, set()
    for index in range(200):
        base = rng.choice(ITEM_NOUNS)
        label = base if base not in used_labels else f"{base}{index}"
        used_labels.add(label)
        items[label] = {"位置": rng.choice(leaves), "外貌": [rng.choice(ITEM_LOOKS)]}

    items["天台灯架"] = {"位置": "天台", "外貌": ["铁皮灯罩里积着雨水"]}
    before = {"地点": locations, "人物": characters, "物品": items}
    after = json.loads(json.dumps(before, ensure_ascii=False))

    mover, doer, changer = names[0], names[1], names[2]
    characters[doer]["位置"] = "借阅台"
    characters[doer]["任务"]["小任务"][0]["目标"] = "核对还书箱里的借阅单存根"
    from_room = before["人物"][mover]["位置"]
    to_room = "天台" if from_room != "天台" else "庭院"
    after["人物"][mover]["位置"] = to_room
    after["人物"][mover]["外貌"].append("肩头落了一层灰")
    after["地点"][to_room]["外貌"].append("水洼里积着刚落的雨")
    item_here = "天台灯架"
    after["物品"][item_here]["外貌"].append("轮子锈死了，推不动")

    goal = before["人物"][doer]["任务"]["小任务"][0]["目标"]
    root = before["人物"][doer]["任务"]["大任务"]["目标"]
    after["人物"][doer]["任务"]["小任务"][0]["状态"] = "已完成"

    before["人物"][changer]["精神值"] = 45
    after["人物"][changer]["精神值"] = 40
    after["人物"][changer]["人格"].append("对火光和烟味格外警觉")

    delta = {
        "时间推进": "3 分钟",
        "变化": {
            mover: {"位置": to_room, "新增外貌": ["肩头落了一层灰"]},
            doer: {"完成任务": [{"小任务": goal, "属于大任务": root}]},
            changer: {"精神值": 40, "新增人格": ["对火光和烟味格外警觉"]},
            to_room: {"新增外貌": ["水洼里积着刚落的雨"]},
            item_here: {"新增外貌": ["轮子锈死了，推不动"]},
        },
    }

    text = (
        f"三分钟过去了。{mover}从{from_room}走上{to_room}，肩头落了一层灰。"
        f"{to_room}的水洼里积着刚落的雨，{item_here}的轮子锈死了，推不动。"
        f"{doer}翻完了{goal}，「{root}」还没有结果。"
        f"{changer}的精神值从45降到40，心里多了一条「对火光和烟味格外警觉」。"
    )

    row = {"上回合状态": before, "本回合变化": delta, "本回合状态": after,
           "视角": mover, "叙事": text}

    path = f"{OUT_DIR}/row-full-appearance.jsonl"
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{path}: {len(io.open(path, encoding='utf-8').read())} chars")
    print(f"world: {len(characters)} characters, {len(locations)} locations, {len(items)} items")
    print(text)


if __name__ == "__main__":
    main()
