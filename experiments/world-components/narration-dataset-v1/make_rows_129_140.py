"""Rows 129-140: twelve more fabricated narration-dataset rows.

Same row format, same visibility rule, same pre-write checks as rows 3-10.
The world builder and the change helpers are imported from make_rows_3_10 so
both batches use one implementation.

New coverage added here:
  * a round whose only change is the environment (row 14)
  * a protagonist who leaves the scene and an interlocutor who walks out of it
    (rows 16, 19)
  * sanity going up (row 15) as well as down (row 17)
  * relationships being withdrawn and offered inside 个性 (row 13)
"""

import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from make_rows_3_10 import apply_ops, build_world, diff_ops  # noqa: E402
from rows_common import build_result  # noqa: E402

OUT_DIR = "experiments/world-components/narration-dataset-v1"

ROWS = [
    {
        "index": 129,
        "hero": "温暮",
        "scene": "缩微胶片室",
        "people": {
            "温暮": {
                "位置": "缩微胶片室", "精神值": 52,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "字号和行距她一眼看得出来", "挤在一起的行她要量"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清重排的那一版是谁做的", "状态": "未完成"}]},
            },
            "叶既明": {
                "位置": "缩微胶片室", "精神值": 48,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["嘴硬", "胶片室他一天来两趟", "重排的记号他认得"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶既明"],
        "hidden": {"方既白": "庭院"},
        "items": {},
        "changes": {
            "温暮": {"完成任务": ["查清重排的那一版是谁做的"]},
            "叶既明": {"精神值": 41},
        },
        "time": "17 分钟",
    },
    {
        "index": 130,
        "hero": "韩照",
        "scene": "装订间",
        "people": {
            "韩照": {
                "位置": "装订间", "精神值": 49,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "裁剩的纸边他捆起来留着", "写下来的东西要标月份"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"温暮": "缩微胶片室", "叶既明": "缩微胶片室"},
        "items": {},
        "changes": {
            "韩照": {"新增小任务": [{"目标": "把柜子里那十捆纸边按月份重新排一遍",
                                "属于大任务": "查清十年前那场火灾是谁放的火",
                                "状态": "未完成"}]},
        },
        "time": "23 分钟",
    },
    {
        "index": 131,
        "hero": "秦暮",
        "scene": "报刊阅览室",
        "people": {
            "秦暮": {
                "位置": "报刊阅览室", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "三本簿子对完才说话", "空的地方要标出来"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把三本簿子缺的页数对出来", "状态": "未完成"}]},
            },
            "温知微": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "缺页的位置她按段记", "对不上就要重对"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "把三本簿子缺的页数对出来", "状态": "未完成"}]},
            },
            "沈既明": {
                "位置": "报刊阅览室", "精神值": 54,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["执着", "每段的头被抽掉他看得出来", "懂行的人才这么干"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温知微", "沈既明"],
        "hidden": {"韩照": "装订间"},
        "items": {},
        "changes": {
            "秦暮": {"完成任务": ["把三本簿子缺的页数对出来"]},
            "温知微": {"完成任务": ["把三本簿子缺的页数对出来"]},
            "报刊阅览室": {"新增外貌": ["靠窗那张长条桌空着"]},
        },
        "time": "19 分钟",
    },
    {
        "index": 132,
        "hero": "柏书言",
        "scene": "报刊库",
        "people": {
            "柏书言": {
                "位置": "报刊库", "精神值": 53,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "封面被翻过来的书他一本本翻正", "借书卡上的日期他记得"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "把这一排封面被翻过去的书都翻正", "状态": "未完成"}]},
            },
            "苏既明": {
                "位置": "报刊库", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "鞋面有一层土"],
                "个性": ["谨慎", "扉页上的水印他一眼看见", "借书卡他一张张看"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏既明"],
        "hidden": {"秦暮": "报刊阅览室"},
        "items": {"合订本": {"位置": "报刊库", "外貌": ["封面被翻过来压在底下", "扉页有一块水泡过的淡印"]}},
        "changes": {
            "合订本": {"解除外貌": ["封面被翻过来压在底下", "扉页有一块水泡过的淡印"]},
            "柏书言": {"完成任务": ["把这一排封面被翻过去的书都翻正"]},
            "苏既明": {"新增外貌": ["手指上沾了一点灰"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 133,
        "hero": "周既白",
        "scene": "二层走廊",
        "people": {
            "周既白": {
                "位置": "二层走廊", "精神值": 52,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["执着", "十九次不登记她要问到底", "写上去之前先问过人"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清那十九次不登记是谁写的字", "状态": "未完成"}]},
            },
            "江既白": {
                "位置": "二层走廊", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["谨慎", "一个人当班十九次不登记他不信", "先下楼再说"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"柏书言": "报刊库"},
        "items": {},
        "changes": {
            "江既白": {"位置": "借阅台",
                     "新增个性": ["决定先把那一年的借书卡取来再说"]},
            "周既白": {"精神值": 57},
        },
        "time": "11 分钟",
    },
    {
        "index": 134,
        "hero": "叶望舒",
        "scene": "古籍库",
        "people": {
            "叶望舒": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["讲究次序", "削过的字她一眼看得出来", "猜的不算数"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "数清这一批校样里被削过的页", "状态": "未完成"}]},
            },
            "顾既白": {
                "位置": "古籍库", "精神值": 48,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "刀削的边他一摸就知道", "数到第几页他记得住"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既白"],
        "hidden": {"周既白": "二层走廊"},
        "items": {},
        "changes": {
            "叶望舒": {"新增外貌": ["手指上沾了纸屑"]},
            "顾既白": {"新增外貌": ["右手食指上有一道纸边划的浅口"]},
            "古籍库": {"新增外貌": ["木架上摆着一盏挪近了的灯"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 135,
        "hero": "沈照",
        "scene": "东侧回廊",
        "people": {
            "沈照": {
                "位置": "东侧回廊", "精神值": 49,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "名单上十一个人他一个不落", "记下来的东西要留得住"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "问清第九个人那晚几点走、从哪个门走的", "状态": "未完成"}]},
            },
            "温暮": {
                "位置": "东侧回廊", "精神值": 53,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "每一个人说了什么她都记", "几点几分都要写清"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温暮"],
        "hidden": {"叶望舒": "古籍库"},
        "items": {},
        "changes": {
            "沈照": {"完成任务": ["问清第九个人那晚几点走、从哪个门走的"],
                     "解除个性": ["记下来的东西要留得住"]},
            "温暮": {"新增外貌": ["手指上沾了铅笔灰"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 136,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "袖口沾了墨"],
                "个性": ["谨慎", "四十年才回来的书不外借", "还书箱每天早上都要翻"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清那本借了四十年的书是谁还回来的", "状态": "未完成"}]},
            },
            "方望舒": {
                "位置": "借阅台", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "卡片堆歪了她要扶正", "排队的人她都记得住"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "查清那本借了四十年的书是谁还回来的",
                                "状态": "未完成"}]},
            },
            "程既明": {
                "位置": "借阅台", "精神值": 47,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["不爱欠人情", "跑一趟不嫌远", "追出去要追到底"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "秦暮": {
                "位置": "借阅台", "精神值": 54,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["记性好", "队尾那个人她看了一眼", "转身走的人她要记住"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方望舒", "秦暮"],
        "hidden": {"沈照": "东侧回廊"},
        "items": {"铜灯": {"位置": "借阅台", "外貌": ["灯罩旧了，光有点黄"]}},
        "changes": {
            "程既明": {"位置": "馆外街道"},
            "方望舒": {"完成任务": ["查清那本借了四十年的书是谁还回来的"]},
            "借阅台": {"新增外貌": ["台面最里边压着一本四十年前借出的书"]},
            "铜灯": {"解除外貌": ["灯罩旧了，光有点黄"], "新增外貌": ["灯罩换成了新的"]},

        },
        "time": "12 分钟",
    },
    {
        "index": 137,
        "hero": "苏既白",
        "scene": "水槽前",
        "people": {
            "苏既白": {
                "位置": "水槽前", "精神值": 52,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "管子坏了他自己紧", "拿东西要留条子"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "把水槽底下那一截锈管换掉", "状态": "未完成"}]},
            },
            "黎既白": {
                "位置": "水槽前", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "抹布归她管", "库房的东西不能随便拿"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎既白"],
        "hidden": {"叶含章": "借阅台"},
        "items": {},
        "changes": {
            "苏既白": {"精神值": 61,
                     "新增外貌": ["手掌上有一道扳手压出的红印"],
                     "新增个性": ["拿库房的东西都写条子压在库里"],
                     "完成任务": ["把水槽底下那一截锈管换掉"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 138,
        "hero": "温既明",
        "scene": "报刊架后",
        "people": {
            "温既明": {
                "位置": "报刊架后", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "空出来的位置他要记着", "新夹子太新也要查"],
                "任务": {"大任务": {"目标": "查到九八年三月那一期的原件去向", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"苏既白": "水槽前"},
        "items": {},
        "changes": {
            "报刊架后": {"新增外貌": ["架子上空出三个位置，木夹还挂着"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 139,
        "hero": "柏照",
        "scene": "地下书库",
        "people": {
            "柏照": {
                "位置": "地下书库", "精神值": 46,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["心软", "这屋里的书他一本一本数过", "明天的事不肯拖到后天"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "苏含章": {
                "位置": "地下书库", "精神值": 49,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "机器坏了他自己拆", "扫帚他不肯借人"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "把这两排架子上的灰扫干净", "状态": "未完成"}]},
            },
        },
        "also_present": ["苏含章"],
        "hidden": {"温既明": "报刊架后"},
        "items": {},
        "changes": {
            "柏照": {"精神值": 55},
            "苏含章": {"精神值": 56,
                     "完成任务": ["把这两排架子上的灰扫干净"]},
            "地下书库": {"新增外貌": ["两排架子盖上了布，布角落里还落着灰"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 140,
        "hero": "方既白",
        "scene": "庭院",
        "people": {
            "方既白": {
                "位置": "庭院", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "找了三年", "不扫叶子也来"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "秦照": {
                "位置": "庭院", "精神值": 52,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["执着", "树根底下挖出来的东西他记着", "每天带一壶水来"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦照"],
        "hidden": {"柏照": "地下书库"},
        "items": {},
        "changes": {
            "方既白": {"新增个性": ["决定不找那把配不上的钥匙了", "答应明天还在石阶上等"]},
            "秦照": {"新增个性": ["把树根底下挖出来的那把钥匙收进抽屉"]},
        },
        "time": "9 分钟",
    },
]
def main():
    written = []
    for spec in ROWS:
        rng = random.Random(20261200 + spec["index"])
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
                    "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                           "小任务": []},
                }
        items.update(json.loads(json.dumps(spec["items"], ensure_ascii=False)))

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

        label = f"row {spec['index']}"
        for entity, ops in spec["changes"].items():
            if entity in after["人物"]:
                apply_ops(after["人物"][entity], ops, f"{label} {entity}")
            elif entity in after["物品"]:
                target = after["物品"][entity]
                for op, value in ops.items():
                    if op == "新增外貌":
                        target["外貌"].extend(value)
                    elif op == "解除外貌":
                        for entry in value:
                            target["外貌"].remove(entry)
                    else:
                        raise SystemExit(f"{label}: unknown item op {op!r}")
            elif entity in after["地点"]:
                target = after["地点"][entity]
                for op, value in ops.items():
                    if op == "新增外貌":
                        target["外貌"].extend(value)
                    elif op == "解除外貌":
                        for entry in value:
                            target["外貌"].remove(entry)
                    else:
                        raise SystemExit(f"{label}: unknown location op {op!r}")
            else:
                raise SystemExit(f"{label}: unknown entity {entity!r}")

        # independent diff vs declaration
        for entity, ops in spec["changes"].items():
            if entity in after["人物"]:
                actual = diff_ops(before["人物"][entity], after["人物"][entity])
            else:
                kind = "物品" if entity in after["物品"] else "地点"
                pre = list(before[kind][entity]["外貌"])
                post = list(after[kind][entity]["外貌"])
                actual = {}
                added = [e for e in post if e not in pre]
                removed = [e for e in pre if e not in post]
                if added:
                    actual["新增外貌"] = added
                if removed:
                    actual["解除外貌"] = removed
            want = dict(ops)
            if "新增小任务" in want:
                want["新增小任务"] = [task["目标"] for task in want["新增小任务"]]
            if actual != want:
                raise SystemExit(f"{label}: delta mismatch on {entity}: declared {want} actual {actual}")

        delta = {"时间推进": spec["time"],
                 "变化": json.loads(json.dumps(spec["changes"], ensure_ascii=False))}

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
        written.append((path, sorted(touched_people), len(delta["变化"])))

    for path, people, changed in written:
        print(f"{path}: people={people} changed={changed} "
              f"chars={len(io.open(path, encoding='utf-8').read())}")


if __name__ == "__main__":
    main()
