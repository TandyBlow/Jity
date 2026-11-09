"""Rows 3-10: eight more fabricated narration-dataset rows.

Each row is its own fabricated world (34 characters, 28 locations, ~200
items): the protagonist differs, so they cannot be consecutive rounds of one
world. The location inventory is shared, including the fine sub-locations
that decide visibility.

Every row is checked before it is written:
  * the declared change list is applied to the after state;
  * the before/after diff is computed independently and compared with the
    declared list, so a change that silently appears in the state but not in
    the delta (or the reverse) fails the run;
  * the row keeps only the changed entities plus whoever stands in the
    protagonist's fine location at the end of the round;
  * the target narrative is read from narratives/row-00NN.txt.
"""

import io
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rows_common import build_result  # noqa: E402

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
    ("茶水间", None, "水壶底结着厚水垢，窗台上排着搪瓷杯。"),
    ("窗边", "茶水间", "窗玻璃上总蒙着一层雾，擦干净也看不清庭院。"),
    ("水槽前", "茶水间", "水槽的下水口常堵，水下得很慢。"),
    ("二层走廊", None, "地板踩上去会响，尽头那盏灯长期不亮。"),
    ("报刊阅览室", "二层走廊", "旧报纸的味道压过一切，长条桌一直排到窗前。"),
    ("长桌区", "报刊阅览室", "三张长条桌并排，桌面上留着没人擦掉的茶渍。"),
    ("报刊架后", "报刊阅览室", "两排铁架夹出一条窄道，报纸按年月用木夹夹住。"),
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
    ("庭院石阶", "庭院", "石阶被雨水冲出浅浅的沟。"),
    ("馆外街道", None, "路灯昏黄，对面是一排关了门的铺子。"),
    ("门卫岗亭", "馆外街道", "岗亭里放着一台老式电暖器，玻璃上贴着值班表。"),
    ("后门", "馆外街道", "铁门上了两道锁，门轴上挂着油壶。"),
    ("配电间", None, "配电箱的漆掉了一半，空气里有轻微的焦味。"),
    ("天台", None, "地面铺着防水卷材，角落里堆着废弃的灯架。"),
    ("天台楼梯间", "天台", "楼梯间窄，灯泡坏了，按两下才亮。"),
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
         "弄清母亲改名换姓之前到底是谁", "拿到能证明兄长清白的原始记录",
         "找回被典当出去的那套医书", "把走失的妹妹从外地找回来"]

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


def flat_tasks(character):
    tasks = {character["任务"]["大任务"]["目标"]: character["任务"]["大任务"]["状态"]}
    for task in character["任务"]["小任务"]:
        tasks[task["目标"]] = task["状态"]
    return tasks


def apply_ops(character, ops, label):
    for op, value in ops.items():
        if op == "位置":
            character["位置"] = value
        elif op == "精神值":
            character["精神值"] = value
        elif op == "新增外貌":
            character["外貌"].extend(value)
        elif op == "解除外貌":
            for entry in value:
                if entry not in character["外貌"]:
                    raise SystemExit(f"{label}: 解除外貌 {entry!r} not present")
                character["外貌"].remove(entry)
        elif op == "新增个性":
            character["个性"].extend(value)
        elif op == "解除个性":
            for entry in value:
                if entry not in character["个性"]:
                    raise SystemExit(f"{label}: 解除个性 {entry!r} not present")
                character["个性"].remove(entry)
        elif op == "新增小任务":
            for task in value:
                character["任务"]["小任务"].append({"目标": task["目标"], "状态": task["状态"]})
        elif op == "完成任务":
            for goal in value:
                hit = False
                if character["任务"]["大任务"]["目标"] == goal:
                    character["任务"]["大任务"]["状态"] = "已完成"
                    hit = True
                for task in character["任务"]["小任务"]:
                    if task["目标"] == goal:
                        task["状态"] = "已完成"
                        hit = True
                if not hit:
                    raise SystemExit(f"{label}: 完成任务 {goal!r} not in the task tree")
        else:
            raise SystemExit(f"{label}: unknown op {op!r}")


def diff_ops(before_character, after_character):
    ops = {}
    if before_character["位置"] != after_character["位置"]:
        ops["位置"] = after_character["位置"]
    if before_character["精神值"] != after_character["精神值"]:
        ops["精神值"] = after_character["精神值"]
    for field, add_key, drop_key in (("外貌", "新增外貌", "解除外貌"), ("个性", "新增个性", "解除个性")):
        pre = list(before_character[field])
        post = list(after_character[field])
        added, removed = [], []
        for entry in post:
            if entry in pre:
                pre.remove(entry)
            else:
                added.append(entry)
        for entry in pre:
            removed.append(entry)
        if added:
            ops[add_key] = added
        if removed:
            ops[drop_key] = list(reversed(removed))
    pre_tasks, post_tasks = flat_tasks(before_character), flat_tasks(after_character)
    achieved = [goal for goal, status in post_tasks.items()
                if status == "已完成" and pre_tasks.get(goal) == "未完成"]
    added_tasks = [goal for goal in post_tasks if goal not in pre_tasks]
    if achieved:
        ops["完成任务"] = achieved
    if added_tasks:
        ops["新增小任务"] = added_tasks
    return ops


ROWS = [
    {
        "index": 3,
        "hero": "陆停云",
        "scene": "借阅台",
        "people": {
            "陆停云": {
                "位置": "借阅台", "精神值": 66,
                "外貌": ["头发用一根木簪别着", "袖口沾了墨"],
                "个性": ["讲究次序",
                       "在这家馆做了九年值班员，闭着眼也摸得到抽屉的锁",
                       "和韩叙白认识得早，替他把过几次关"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾当晚的值班人是谁", "状态": "未完成"},
                       "小任务": [{"目标": "核对还书箱里的借阅单存根", "状态": "未完成"},
                                {"目标": "比对三份互相矛盾的登记簿", "状态": "未完成"}]},
            },
            "韩叙白": {
                "位置": "借阅台", "精神值": 58,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["执着",
                       "和陆停云认识得早，信得过她办事的次序",
                       "认定十年前那场火灾不是意外，一直在查"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查访当年的门卫", "状态": "未完成"}]},
            },
        },
        "also_present": ["韩叙白"],
        "hidden": {"李青": "还书处"},
        "items": {"台面印章": {"位置": "借阅台", "外貌": ["印泥结成了块", "铜柄磨得发亮"]}},
        "locations": {},
        "changes": {
            "陆停云": {"完成任务": ["核对还书箱里的借阅单存根"]},
            "韩叙白": {"新增小任务": [{"目标": "翻看十年前的值班记录",
                                   "属于大任务": "查清十年前那场火灾是谁放的火",
                                   "状态": "未完成"}]},
            "台面印章": {"解除外貌": ["印泥结成了块"], "新增外貌": ["印泥换过新的"]},
        },
        "time": "5 分钟",
    },
    {
        "index": 4,
        "hero": "江叙白",
        "scene": "二层西侧书架",
        "people": {
            "江叙白": {
                "位置": "二层西侧书架", "精神值": 58,
                "外貌": ["指节上有旧伤", "围巾洗得发白"],
                "个性": ["沉默寡言",
                       "记得那一页写过什么，但记不清写在哪一边",
                       "兄长十年前的案子毁了他半个家"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "翻检古籍库的出入签字", "状态": "未完成"}]},
            },
            "苏停云": {
                "位置": "二层西侧书架", "精神值": 62,
                "外貌": ["鞋面有一层土", "衣角被雨打湿过"],
                "个性": ["心软",
                       "被典当行的人糊弄过一次，从此不信嘴上的话",
                       "和江叙白不算熟，见过他在闭馆后还留在库里"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏停云"],
        "hidden": {"陆停云": "报刊库"},
        "items": {},
        "changes": {
            "江叙白": {"精神值": 49,
                     "新增个性": ["开始怀疑自己记错了那一页"],
                     "新增外貌": ["指节被纸边划破"]},
            "二层西侧书架": {"新增外貌": ["顶格的书脊上落了一层灰"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 5,
        "hero": "苏照",
        "scene": "水槽前",
        "people": {
            "苏照": {
                "位置": "窗边", "精神值": 55,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["好奇心重",
                       "母亲改名换姓的事是她自己翻出来的，没跟任何人说过",
                       "喝水只喝烫的"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "柏含章": {
                "位置": "水槽前", "精神值": 47,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["嘴硬",
                       "搭档死在十年前那场火灾里，他一直记着那天的风向",
                       "和苏照不熟，只觉得她问话问得太细"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "找出被人撕掉的那一页", "状态": "未完成"}]},
            },
        },
        "also_present": ["柏含章"],
        "hidden": {"秦望舒": "长桌区"},
        "items": {},
        "changes": {
            "苏照": {"位置": "水槽前"},
            "水槽前": {"新增外貌": ["水槽里积着昨天的茶渣"]},
            "柏含章": {"新增外貌": ["袖口湿了一片"],
                     "新增个性": ["答应替苏照留一把档案室的钥匙"]},
        },
        "time": "3 分钟",
    },
    {
        "index": 6,
        "hero": "程含章",
        "scene": "庭院石阶",
        "people": {
            "程含章": {
                "位置": "庭院石阶", "精神值": 52,
                "外貌": ["衣角被雨打湿过", "戴着一副圆框眼镜"],
                "个性": ["谨慎",
                       "父亲当年是这家馆的夜班门卫，火灾后被人指为失职",
                       "从不把话说完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "翻看十年前的值班记录", "状态": "未完成"}]},
            },
            "顾停云": {
                "位置": "庭院石阶", "精神值": 60,
                "外貌": ["鞋面有一层土", "袖口沾了墨"],
                "个性": ["心软",
                       "妹妹走失那年她十九岁，此后再没搬过家",
                       "陪程含章查了三年，从没催过他"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾停云"],
        "hidden": {"江叙白": "西侧回廊"},
        "items": {},
        "locations": {},
        "changes": {
            "程含章": {"完成任务": ["查清十年前那场火灾是谁放的火", "翻看十年前的值班记录"],
                     "新增个性": ["确认父亲那晚不在场"],
                     "精神值": 60},
        },
        "time": "8 分钟",
    },
    {
        "index": 7,
        "hero": "叶既明",
        "scene": "缩微胶片室",
        "people": {
            "叶既明": {
                "位置": "缩微胶片室", "精神值": 64,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["护短",
                       "这台阅读机是他父亲留下的，从前不肯让人碰",
                       "和沈叙白在同一个班组待过两年"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": [{"目标": "找出被人撕掉的那一页", "状态": "未完成"}]},
            },
            "沈叙白": {
                "位置": "缩微胶片室", "精神值": 50,
                "外貌": ["指节上有旧伤", "围巾洗得发白"],
                "个性": ["执着",
                       "兄长十年前的案子毁了他半个家",
                       "和叶既明共过事，知道他嘴上硬、心里松"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "在缩微胶片里找那一天的报纸", "状态": "未完成"}]},
            },
        },
        "also_present": ["沈叙白"],
        "hidden": {"苏照": "三层走廊"},
        "items": {"缩微阅读机": {"位置": "缩微胶片室", "外貌": ["镜头盖用胶布粘着"]}},
        "locations": {},
        "changes": {
            "叶既明": {"解除个性": ["这台阅读机是他父亲留下的，从前不肯让人碰"],
                     "新增个性": ["答应让沈叙白用一次阅读机"]},
            "沈叙白": {"完成任务": ["在缩微胶片里找那一天的报纸"]},
            "缩微阅读机": {"解除外貌": ["镜头盖用胶布粘着"], "新增外貌": ["镜头盖换过了"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 8,
        "hero": "黎含章",
        "scene": "装订间",
        "people": {
            "黎含章": {
                "位置": "装订间", "精神值": 41,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["沉默寡言",
                       "在这间装订间干了二十六年，只肯用手工裁纸",
                       "那套医书是她替人典当出去的，一直没敢说"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"程含章": "旧刊堆放区", "顾停云": "地下书库"},
        "items": {},
        "locations": {},
        "changes": {},
        "time": "20 分钟",
    },
    {
        "index": 9,
        "hero": "方叙白",
        "scene": "旧刊堆放区",
        "people": {
            "方叙白": {
                "位置": "旧刊堆放区", "精神值": 62,
                "外貌": ["鞋面有一层土", "袖口沾了墨"],
                "个性": ["护短",
                       "在地下库熬了三个通宵，谁都劝不动",
                       "认死理，认定的事九头牛拉不回"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "韩既明": {
                "位置": "旧刊堆放区", "精神值": 57,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["记性好",
                       "哪一年的旧报堆在哪个角，他闭着眼也能报出来",
                       "和方叙白共事多年，从没跟他红过脸"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "把受潮的旧刊挑出来晾干", "状态": "未完成"}]},
            },
            "沈知微": {
                "位置": "装订间", "精神值": 68,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["讲究次序",
                       "隔壁装订间的账归她管",
                       "从不进堆放区，说那里的灰呛人"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["韩既明"],
        "hidden": {"沈知微": "装订间"},
        "items": {"捆报麻绳": {"位置": "旧刊堆放区", "外貌": ["被虫蛀过", "勒出的印子还在"]}},
        "locations": {},
        "changes": {
            "方叙白": {"精神值": 55},
            "韩既明": {"完成任务": ["把受潮的旧刊挑出来晾干"],
                     "新增小任务": [{"目标": "找出被人撕掉的那一页",
                                  "属于大任务": "找到被族人藏起来的那本族谱原本",
                                  "状态": "未完成"}]},
            "捆报麻绳": {"解除外貌": ["被虫蛀过"], "新增外貌": ["换成新的塑料绳"]},
        },
        "time": "6 分钟",
    },
    {
        "index": 10,
        "hero": "秦望舒",
        "scene": "古籍库",
        "people": {
            "秦望舒": {
                "位置": "古籍库", "精神值": 53,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["好奇心重",
                       "父亲当年是这家馆的古籍修复工，她从小在库里长大",
                       "记东西只写不记，本子攒了一抽屉"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "未完成"}]},
            },
            "柏暮": {
                "位置": "古籍库", "精神值": 65,
                "外貌": ["衣角被雨打湿过", "袖口沾了墨"],
                "个性": ["谨慎",
                       "母亲改名换姓的事，他从别人嘴里听过半句",
                       "管着库里的一把钥匙，另一把不在他手里"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "翻检古籍库的出入签字", "状态": "未完成"}]},
            },
        },
        "also_present": ["柏暮"],
        "hidden": {"黎含章": "三层走廊"},
        "items": {},
        "changes": {
            "秦望舒": {"解除外貌": ["戴着一副圆框眼镜"],
                     "新增外貌": ["换了副黑框眼镜"],
                     "新增小任务": [{"目标": "找出十年前十月以后那半年的出入签字",
                                  "属于大任务": "拿到能证明兄长清白的原始记录",
                                  "状态": "未完成"}]},
            "柏暮": {"完成任务": ["翻检古籍库的出入签字"]},
            "古籍库": {"新增外貌": ["门上贴的封条被撕开一角"]},
        },
        "time": "15 分钟",
    },
]


def main():
    written = []
    for spec in ROWS:
        rng = random.Random(20261100 + spec["index"])
        locations, characters, items = build_world(rng)

        for name, entry in spec["people"].items():
            characters[name] = json.loads(json.dumps(entry, ensure_ascii=False))
        for name, where in spec["hidden"].items():
            if name in characters:
                characters[name]["位置"] = where
            else:
                characters[name] = {
                    "位置": where, "精神值": 68,
                    "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                    "个性": ["讲究次序", "从不进堆放区，说那里的灰呛人"],
                    "任务": {"大任务": {"目标": ROOTS[7], "状态": "未完成"}, "小任务": []},
                }
        items.update(json.loads(json.dumps(spec["items"], ensure_ascii=False)))

        # nobody random may stand in the scene, or in a hidden person's spot
        kept = set(spec["people"]) | set(spec["hidden"])
        for name, entry in characters.items():
            if name in kept:
                continue
            if entry["位置"] == spec["scene"]:
                entry["位置"] = "地下书库" if spec["scene"] != "地下书库" else "庭院"

        before = {"地点": json.loads(json.dumps(locations, ensure_ascii=False)),
                  "人物": json.loads(json.dumps(characters, ensure_ascii=False)),
                  "物品": json.loads(json.dumps(items, ensure_ascii=False))}
        after = json.loads(json.dumps(before, ensure_ascii=False))

        for where, ops in spec.get("locations", {}).items():
            for op, value in ops.items():
                if op == "新增外貌":
                    after["地点"][where]["外貌"].extend(value)
                elif op == "解除外貌":
                    for entry in value:
                        after["地点"][where]["外貌"].remove(entry)
                else:
                    raise SystemExit(f"row {spec['index']}: unknown location op {op!r}")

        label = f"row {spec['index']}"
        for entity, ops in spec["changes"].items():
            target = None
            if entity in after["人物"]:
                target = after["人物"][entity]
            elif entity in after["物品"]:
                target = after["物品"][entity]
            if target is not None:
                apply_ops(target, ops, f"{label} {entity}")
            elif entity in after["地点"]:
                for op, value in ops.items():
                    if op == "新增外貌":
                        target = after["地点"][entity]
                        target["外貌"].extend(value)
                    else:
                        raise SystemExit(f"{label}: unknown location change {op!r}")
            else:
                raise SystemExit(f"{label}: unknown entity {entity!r}")

        # independent diff, entity by entity, and compare with the declaration
        declared = {}
        for entity, ops in spec["changes"].items():
            if entity in after["人物"]:
                declared[entity] = diff_ops(before["人物"][entity], after["人物"][entity])
            elif entity in after["物品"]:
                ops_out = {}
                pre, post = list(before["物品"][entity]["外貌"]), list(after["物品"][entity]["外貌"])
                added = [e for e in post if e not in pre]
                removed = [e for e in pre if e not in post]
                if added:
                    ops_out["新增外貌"] = added
                if removed:
                    ops_out["解除外貌"] = removed
                if before["物品"][entity]["位置"] != after["物品"][entity]["位置"]:
                    raise SystemExit(f"{label}: item moved, not supported")
                declared[entity] = ops_out
            else:
                pre, post = list(before["地点"][entity]["外貌"]), list(after["地点"][entity]["外貌"])
                ops_out = {}
                added = [e for e in post if e not in pre]
                removed = [e for e in pre if e not in post]
                if added:
                    ops_out["新增外貌"] = added
                if removed:
                    ops_out["解除外貌"] = removed
                declared[entity] = ops_out
        for entity, ops in declared.items():
            want = dict(spec["changes"][entity])
            if "新增小任务" in want:
                want["新增小任务"] = [task["目标"] for task in want["新增小任务"]]
            if "新增外貌" in want and entity in after["地点"]:
                pass
            if ops != want:
                raise SystemExit(f"{label}: delta mismatch on {entity}: declared {want} actual {ops}")

        delta = {"时间推进": spec["time"], "变化": json.loads(json.dumps(spec["changes"], ensure_ascii=False))}
        if not delta["变化"]:
            delta = {"时间推进": spec["time"], "变化": {}}

        scene = after["人物"][spec["hero"]]["位置"]
        if scene != spec["scene"]:
            raise SystemExit(f"{label}: hero not in the declared scene")
        scene_people = {name for name, entry in after["人物"].items() if entry["位置"] == scene}
        changed_people = {name for name in delta["变化"] if name in after["人物"]}
        for name in spec["also_present"]:
            if name not in scene_people:
                raise SystemExit(f"{label}: {name} declared present but is not in the scene")
        for name, where in spec["hidden"].items():
            if name in scene_people:
                raise SystemExit(f"{label}: {name} declared hidden but is in the scene")
        touched_people = scene_people | changed_people
        touched_locations = {scene}
        for name in touched_people | set(spec["changes"]):
            for state in (before, after):
                if name not in state["人物"]:
                    continue
                where = state["人物"][name]["位置"]
                if where in before["地点"]:
                    touched_locations.add(where)
                    parent = before["地点"][where]["位于"]
                    if parent:
                        touched_locations.add(parent)
        changed_items = [name for name in delta["变化"] if name in after["物品"]]

        def scope(state):
            return {
                "地点": {name: state["地点"][name] for name in sorted(touched_locations)},
                "人物": {name: state["人物"][name] for name in sorted(touched_people)},
                "物品": {name: state["物品"][name] for name in sorted(changed_items)},
            }

        narrative_path = f"{OUT_DIR}/narratives/row-{spec['index']:04d}.txt"
        if not os.path.exists(narrative_path):
            raise SystemExit(f"missing narrative {narrative_path}")
        text = io.open(narrative_path, encoding="utf-8").read().strip()

        row = {"上回合状态": scope(before), "本回合变化": delta,
               "本回合状态": build_result(after, delta["变化"]),
               "视角": f"主角视角（{spec['hero']}）；只表达已结算的世界事实", "叙事": text}
        path = f"{OUT_DIR}/row-{spec['index']:04d}-scene.jsonl"
        with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        written.append((path, list(touched_people), len(delta["变化"])))

    for path, people, changed in written:
        print(f"{path}: people={people} changed={changed} chars={len(io.open(path, encoding='utf-8').read())}")


if __name__ == "__main__":
    main()
