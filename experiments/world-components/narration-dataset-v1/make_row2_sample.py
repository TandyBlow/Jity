"""Row 2: a second fabricated narration-dataset row, same row format, new round.

World: 30 characters, 28 locations (the newspaper room is split into fine
sub-locations), 201 items. Everything is invented; no database read.

Round: the protagonist is already standing behind the newspaper racks. Two
other people are in the same fine sub-location; a fourth person sits at the
long table in the same parent room but a different sub-location, so she is
NOT part of the scene and does not enter the row.

Change kinds covered here that row 1 did not have:
  - 解除个性 (a grudge entry removed) together with 新增个性 (a new promise)
  - 解除外貌 on an item
  - a finer split of one parent location, exercising the visibility rule
"""

import io
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rows_common import build_result  # noqa: E402

SEED = 20261110
OUT_DIR = "experiments/world-components/narration-dataset-v1"

SURNAMES = "沈林周叶顾韩陆程苏谢秦唐方江黎温季柏岑"
GIVEN = ["砚", "知微", "行舟", "青", "闻雪", "远", "照", "望舒", "临", "既明",
         "怀瑾", "执", "云舟", "书言", "停云", "寄北", "含章", "叙白", "清和", "暮"]

LOCATIONS = [
    ("一层门厅", None, "地砖被脚步磨得发白，正对大门挂着一面停摆的钟。"),
    ("借阅台", "一层门厅", "硬木台面，边角包着铜皮，抽屉上着锁。"),
    ("还书处", "一层门厅", "铁皮还书箱敞着口，旁边堆着没上架的书车。"),
    ("一层走廊", None, "走廊很窄，两侧墙上贴满发黄的告示。"),
    ("值班室", "一层走廊", "一张行军床、一部内线电话，窗户糊着报纸。"),
    ("茶水间", "一层走廊", "水壶底结着厚水垢，窗台上排着搪瓷杯。"),
    ("二层走廊", None, "地板踩上去会响，尽头那盏灯长期不亮。"),
    ("报刊阅览室", "二层走廊", "旧报纸的味道压过一切，长条桌一直排到窗前。"),
    ("长桌区", "报刊阅览室", "三张长条桌并排，桌面上留着没人擦掉的茶渍。"),
    ("报刊架后", "报刊阅览室", "两排铁架夹出一条窄道，报纸按年月用木夹夹住。"),
    ("窗边", "报刊阅览室", "窗台宽得能坐人，玻璃上有一道从没补过的裂缝。"),
    ("二层西侧书架", "二层走廊", "书架高到天花板，索书号标签翘起了边。"),
    ("报刊库", "二层走廊", "合订本按年份排在铁柜里，抽屉很涩。"),
    ("三层走廊", None, "这一层没有窗，墙皮受潮鼓起。"),
    ("古籍库", "三层走廊", "双层库门，内层包着铁皮，钥匙由两人分管。"),
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

ITEM_NOUNS = ["合订本", "报夹", "放大镜", "裁纸刀", "浆糊瓶", "书车", "梯凳",
              "台灯", "灯罩", "窗栓", "门牌", "钥匙串", "水壶", "茶杯", "抹布",
              "纸箱", "麻绳", "牛皮纸", "封套", "印章", "印泥", "订书机", "剪刀",
              "胶水", "雨伞", "外套", "手套", "口罩", "手电", "电池", "钟", "挂历",
              "花名册", "值日表", "便签盒", "笔筒", "图钉", "尺子", "镊子", "墨水瓶"]

ITEM_LOOKS = ["边角磨圆了", "表面有一层薄灰", "漆皮翘起", "木头被手汗浸得发亮",
              "铁皮上有锈斑", "布面褪成了浅色", "纸页卷边", "还留着上一任的笔迹"]

ROOTS = ["找到被族人藏起来的那本族谱原本", "查清十年前那场火灾是谁放的火",
         "替死去的搭档报仇", "找到父亲留下的那只铁皮匣子",
         "弄清母亲改名换姓之前到底是谁", "拿到能证明兄长清白的原始记录"]

SUBTASKS = ["翻看十年前的值班记录", "核对还书箱里的借阅单存根", "查访当年的门卫",
            "翻检古籍库的出入签字", "比对三份互相矛盾的登记簿", "找到知情的老装订工",
            "把受潮的旧刊挑出来晾干", "在缩微胶片里找那一天的报纸",
            "问清配电间那晚跳闸的时间", "找出被人撕掉的那一页"]

APPEARANCES = ["袖口沾了墨", "头发用一根木簪别着", "鞋面有一层土",
               "围巾洗得发白", "指节上有旧伤", "衣角被雨打湿过", "戴着一副圆框眼镜"]

PERSONALITIES = ["谨慎", "好奇心重", "沉默寡言", "护短", "讲究次序", "记仇", "心软"]


def build_world(rng):
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
            "个性": [rng.choice(PERSONALITIES)],
            "任务": {
                "大任务": {"目标": ROOTS[index % len(ROOTS)], "状态": "未完成"},
                "小任务": [{"目标": goal, "状态": "未完成"}
                        for goal in rng.sample(SUBTASKS, rng.choice((0, 1, 2)))],
            },
        }

    items, used_labels = {}, set()
    for index in range(200):
        base = rng.choice(ITEM_NOUNS)
        label = base if base not in used_labels else f"{base}{index}"
        used_labels.add(label)
        items[label] = {"位置": rng.choice(leaves), "外貌": [rng.choice(ITEM_LOOKS)]}
    return locations, characters, items


def main():
    rng = random.Random(SEED)
    locations, characters, items = build_world(rng)

    hero = "周叙白"
    helper = "沈含章"
    ally = "顾知微"
    bystander = "叶照"
    extra = {
        hero: (62, ["袖口沾了墨", "戴着一副圆框眼镜"], ROOTS[3]),
        helper: (58, ["头发用一根木簪别着", "围巾洗得发白"], ROOTS[0]),
        ally: (54, ["指节上有旧伤", "衣角被雨打湿过"], ROOTS[2]),
        bystander: (70, ["鞋面有一层土"], ROOTS[4]),
    }
    for name, (sanity, looks, root) in extra.items():
        characters[name] = {
            "位置": "二层走廊",
            "精神值": sanity,
            "外貌": list(looks),
            "个性": ["谨慎"],
            "任务": {"大任务": {"目标": root, "状态": "未完成"}, "小任务": []},
        }

    # scene placement: hero, helper and ally share the narrow aisle behind the
    # newspaper racks; the bystander sits at the long table (same parent room,
    # different fine location) and stays out of the scene
    characters[hero]["位置"] = "报刊架后"
    characters[helper]["位置"] = "报刊架后"
    characters[ally]["位置"] = "报刊架后"
    characters[bystander]["位置"] = "长桌区"
    for name, entry in characters.items():
        if name not in (hero, helper, ally, bystander) and entry["位置"] in ("报刊架后", "长桌区", "窗边"):
            entry["位置"] = "二层西侧书架"

    characters[hero]["个性"] = [
        "不爱欠人情",
        f"和{helper}共事多年，信得过他的记性",
        f"和{ally}因为那批旧报纸闹过一回，至今没和解",
        "父亲当年是这家馆的古籍修复工，他从小在装订间长大",
    ]
    characters[helper]["个性"] = [
        "记性好",
        "在这个报刊阅览室做了十八年管理员，闭着眼也知道哪一年的报纸在哪一档",
        f"和{hero}共事多年，信得过他",
        f"欠{ally}一次人情，一直想还",
    ]
    characters[ally]["个性"] = [
        "嘴硬",
        "那台缩微阅读机是她父亲留下的，她不肯让人随便碰",
        f"和{hero}因为那批旧报纸闹过一回，见面就绕开",
        "认定十年前那场火灾不是意外",
    ]

    items["长桌区墨水瓶"] = {"位置": "长桌区", "外貌": ["瓶口结着一层干墨"]}
    items["报架放大镜"] = {"位置": "报刊架后", "外貌": ["镜片有一道裂纹", "黄铜柄磨得发亮"]}
    items["缩微阅读机"] = {"位置": "缩微胶片室", "外貌": ["镜头盖用胶布粘着"]}

    before = {"地点": json.loads(json.dumps(locations, ensure_ascii=False)),
              "人物": json.loads(json.dumps(characters, ensure_ascii=False)),
              "物品": json.loads(json.dumps(items, ensure_ascii=False))}
    after = json.loads(json.dumps(before, ensure_ascii=False))

    # --- the round ---
    after["物品"]["报架放大镜"]["外貌"] = ["镜片换过了", "黄铜柄磨得发亮"]

    root = before["人物"][helper]["任务"]["大任务"]["目标"]
    # the achieved subtask must already exist in the previous state
    before["人物"][helper]["任务"]["小任务"] = [
        {"目标": "在缩微胶片里找那一天的报纸", "状态": "未完成"},
        {"目标": "核对还书箱里的借阅单存根", "状态": "未完成"},
    ]
    after["人物"][helper] = json.loads(json.dumps(before["人物"][helper], ensure_ascii=False))
    after["人物"][helper]["任务"]["小任务"] = [
        {"目标": "在缩微胶片里找那一天的报纸", "状态": "已完成"},
        {"目标": "核对还书箱里的借阅单存根", "状态": "未完成"},
        {"目标": "找出被人撕掉的那一页", "状态": "未完成"},
    ]

    after["人物"][ally]["个性"].remove("和" + hero + "因为那批旧报纸闹过一回，见面就绕开")
    after["人物"][ally]["个性"].append("答应替" + hero + "查那批旧报纸，只是还没想好怎么开口")

    # both of them walk out of the aisle before the round ends (the target text
    # has them leave); the recorded positions follow the text
    after["人物"][helper]["位置"] = "长桌区"
    after["人物"][ally]["位置"] = "二层走廊"

    delta = {
        "时间推进": "2 分钟",
        "变化": {
            "报架放大镜": {"新增外貌": ["镜片换过了"], "解除外貌": ["镜片有一道裂纹"]},
            helper: {
                "位置": "长桌区",
                "完成任务": ["在缩微胶片里找那一天的报纸"],
                "新增小任务": [{"目标": "找出被人撕掉的那一页",
                             "属于大任务": root, "状态": "未完成"}],
            },
            ally: {
                "位置": "二层走廊",
                "解除个性": ["和" + hero + "因为那批旧报纸闹过一回，见面就绕开"],
                "新增个性": ["答应替" + hero + "查那批旧报纸，只是还没想好怎么开口"],
            },
        },
    }

    text = "\n\n".join([
        "两分钟过去了。",
        f"铁架夹出的这条窄道里几乎没有风。{helper}把放大镜递过来的时候，"
        f"镜片是新的，黄铜柄还是旧的那副，磨得发亮。「换过了。」他说，"
        f"「上一块裂得太厉害，看不出字。」",
        "地上散着几页没夹住的报纸，被他用脚尖拨到一边。",
        f"他这条线还没有结果。他把下一步写在本子上：找出被人撕掉的那一页。",
        f"{ally}站在窄道另一头，看了一会儿才走过来。她和{hero}因为那批旧报纸闹过一回，"
        f"见面总是绕开。这一次她没绕，只说了半句：「那批报纸……我替你查。」"
        "话没说完又停住，像是还没想好接下来该怎么说。",
    ])
    hand_written = f"{OUT_DIR}/narratives/row-0002.txt"
    text = (io.open(hand_written, encoding="utf-8").read().strip()
            if os.path.exists(hand_written) else generated)

    full = {"上回合状态": before, "本回合变化": delta, "本回合状态": after,
            "视角": f"主角视角（{hero}）；只表达已结算的世界事实", "叙事": text}

    # Visibility rule: only people in the same FINE location as the protagonist
    # after the round enter the row. The bystander sits at the long table,
    # inside the same parent room, and stays out.
    scene = after["人物"][hero]["位置"]
    scene_people = {name for name, entry in after["人物"].items() if entry["位置"] == scene}
    changed_people = {name for name in delta["变化"] if name in after["人物"]}
    touched_people = scene_people | changed_people
    touched_locations = {scene}
    for name in touched_people:
        for state in (before, after):
            where = state["人物"][name]["位置"]
            if where in before["地点"]:
                touched_locations.add(where)
                parent = before["地点"][where]["位于"]
                if parent:
                    touched_locations.add(parent)
    touched_items = {"报架放大镜"}

    def scope(state):
        locations_view = {}
        for name in sorted(touched_locations):
            entry = dict(state["地点"][name])
            locations_view[name] = entry
        return {
            "地点": locations_view,
            "人物": {name: state["人物"][name] for name in sorted(touched_people)},
            "物品": {name: state["物品"][name] for name in sorted(touched_items)},
        }

    scoped = {"上回合状态": scope(before), "本回合变化": delta,
              "本回合状态": build_result(after, delta["变化"]),
              "视角": f"主角视角（{hero}）；只表达已结算的世界事实", "叙事": text}

    for filename, row in (("row-0002-scene.jsonl", scoped), ("row-0002-full.jsonl", full)):
        path = f"{OUT_DIR}/{filename}"
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{path}: {len(io.open(path, encoding='utf-8').read())} chars")

    print(f"world: {len(characters)} characters, {len(locations)} locations, {len(items)} items")
    print(f"scene people: {sorted(touched_people)}; excluded (different fine location): {bystander}")
    print(text)


if __name__ == "__main__":
    main()
