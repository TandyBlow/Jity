"""Rows 105-116: twelve more fabricated narration-dataset rows.

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
        "index": 105,
        "hero": "周书言",
        "scene": "报刊阅览室",
        "people": {
            "周书言": {
                "位置": "报刊阅览室", "精神值": 53,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "三本对完才肯说话", "缺的页要一页页补"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "把三本缺页的登记簿对完", "状态": "未完成"}]},
            },
            "温砚": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["讲究次序", "簿子他按年份排", "缺字的地方他记着"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "把三本缺页的登记簿对完", "状态": "未完成"}]},
            },
            "苏望舒": {
                "位置": "报刊阅览室", "精神值": 56,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["心软", "问了三个月没问出结果", "答应的事不肯半途撂下"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温砚", "苏望舒"],
        "hidden": {"叶含章": "东侧回廊"},
        "items": {},
        "changes": {
            "周书言": {"完成任务": ["把三本缺页的登记簿对完"]},
            "温砚": {"完成任务": ["把三本缺页的登记簿对完"]},
            "苏望舒": {"新增外貌": ["手背上沾了一点水"]},
        },
        "time": "22 分钟",
    },
    {
        "index": 106,
        "hero": "叶照",
        "scene": "缩微胶片室",
        "people": {
            "叶照": {
                "位置": "缩微胶片室", "精神值": 47,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "胶卷盒她按年份排", "记错的地方她要改回来"],
                "任务": {"大任务": {"目标": "查到九八年三月那一期的原件去向", "状态": "未完成"},
                       "小任务": [{"目标": "把装错盒的胶卷全部核对一遍", "状态": "未完成"}]},
            },
            "沈叙白": {
                "位置": "缩微胶片室", "精神值": 52,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["谨慎", "胶片室他管了九年", "盒子上的字和片子对不上就要查"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["沈叙白"],
        "hidden": {"周书言": "报刊阅览室"},
        "items": {},
        "changes": {
            "叶照": {"完成任务": ["查到九八年三月那一期的原件去向",
                              "把装错盒的胶卷全部核对一遍"],
                     "解除个性": ["记错的地方她要改回来"],
                     "新增个性": ["明白自己十一年来没记错"]},
            "沈叙白": {"精神值": 46},
        },
        "time": "26 分钟",
    },
    {
        "index": 107,
        "hero": "韩暮",
        "scene": "配电间",
        "people": {
            "韩暮": {
                "位置": "配电间", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "闸刀响不响他听得出来", "图上有没人敢动的线他要找"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清后加的那条线是谁接的", "状态": "未完成"}]},
            },
            "方既明": {
                "位置": "配电间", "精神值": 58,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "他师父画的线路图", "九八年以后的事他不肯多说"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方既明"],
        "hidden": {"叶照": "缩微胶片室"},
        "items": {},
        "changes": {
            "韩暮": {"精神值": 47},
            "方既明": {"精神值": 44},
            "配电间": {"新增外貌": ["箱子里那根后加的线，胶布已经发脆翘边"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 108,
        "hero": "韩照",
        "scene": "报刊库",
        "people": {
            "韩照": {
                "位置": "报刊库", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["沉默寡言", "合订本他一册一册数", "空着的位置他不肯填"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"韩暮": "配电间", "方既明": "配电间"},
        "items": {"纸条": {"位置": "报刊库", "外貌": ["写着三个日子，字很工整", "角上一块水痕把最后一个字泡糊了"]}},
        "changes": {
            "纸条": {"解除外貌": ["角上一块水痕把最后一个字泡糊了"],
                    "新增外貌": ["水痕干了，最后一个日子认出来是二十日"]},
            "报刊库": {"新增外貌": ["铁柜第三层空着，空出来的位置比别处干净"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 109,
        "hero": "温暮",
        "scene": "借阅台",
        "people": {
            "温暮": {
                "位置": "二层走廊", "精神值": 52,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "本子她抱着走", "父亲的事她一直没问出口"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清那半年少了十九次登记的两个人是谁", "状态": "未完成"}]},
            },
            "沈照": {
                "位置": "二层走廊", "精神值": 49,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["嘴硬", "地板第几块会响他心里有数", "查不到名字就不算完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"韩照": "报刊库", "沈照": "二层走廊"},
        "items": {},
        "changes": {
            "温暮": {"位置": "借阅台",
                     "完成任务": ["查清那半年少了十九次登记的两个人是谁"]},
            "沈照": {"新增小任务": [{"目标": "查清登记簿上被刮掉的那个名字",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
        },
        "time": "12 分钟",
    },
    {
        "index": 110,
        "hero": "柏清和",
        "scene": "古籍库",
        "people": {
            "柏清和": {
                "位置": "古籍库", "精神值": 54,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["讲究次序", "散线的书她都要重缝", "剪断的地方她要查"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
            "韩照": {
                "位置": "古籍库", "精神值": 48,
                "外貌": ["袖口沾了墨", "围巾洗得发白"],
                "个性": ["沉默寡言", "他父亲也修过这样的书", "针穿两遍才穿对"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清这个月剪断的三本书是谁剪的", "状态": "未完成"}]},
            },
        },
        "also_present": ["韩照"],
        "hidden": {"温暮": "借阅台"},
        "items": {},
        "changes": {
            "柏清和": {"新增个性": ["决定跟着韩照学重缝"]},
            "古籍库": {"新增外貌": ["桌上摆着三本散了线的书，线都断在三处"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 111,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "还回来的书她先翻扉页", "四十年才回来的书不外借"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清那本借了四十年的书是谁还回来的", "状态": "未完成"}]},
            },
            "温砚": {
                "位置": "借阅台", "精神值": 53,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["好奇心重", "还书箱每天早上一开他就看", "陌生人排队他记得住"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": []},
            },
            "苏望舒": {
                "位置": "借阅台", "精神值": 57,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["心软", "她在台前排过三年队", "看见人转身走就要问一句"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "秦照": {
                "位置": "借阅台", "精神值": 46,
                "外貌": ["指节上有旧伤", "衣角被雨打湿过"],
                "个性": ["执着", "他排在最末一位", "看见纸条就要抄下来"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温砚", "苏望舒"],
        "hidden": {"柏清和": "古籍库"},
        "items": {},
        "changes": {
            "秦照": {"位置": "报刊阅览室"},
            "温砚": {"新增外貌": ["袖口上沾了一点印泥"]},
            "借阅台": {"新增外貌": ["台面最里边压着一本四十年前借出的书"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 112,
        "hero": "周既白",
        "scene": "地下书库",
        "people": {
            "周既白": {
                "位置": "地下书库", "精神值": 49,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["谨慎", "封皮和内容对不上她一眼看得出来", "胶浸过的纸她摸得出来"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清这一排有几本换过封皮", "状态": "未完成"}]},
            },
            "柏书言": {
                "位置": "地下书库", "精神值": 52,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "这一排架子归他管", "换过封皮的书一本本翻"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["柏书言"],
        "hidden": {"叶含章": "借阅台"},
        "items": {},
        "changes": {
            "周既白": {"解除外貌": ["围巾洗得发白"]},
            "地下书库": {"新增外貌": ["架子最下面几本的封皮是从别的书上撕下来的，背面留着半行旧书名"]},
        },
        "time": "17 分钟",
    },
    {
        "index": 113,
        "hero": "黎书言",
        "scene": "装订间",
        "people": {
            "黎书言": {
                "位置": "装订间", "精神值": 50,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "裁剩的纸边她捆起来留着", "记东西写在本上"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"周既白": "地下书库", "柏书言": "地下书库"},
        "items": {},
        "changes": {
            "黎书言": {"新增小任务": [{"目标": "查清柜子里那捆纸上系的小牌子写的年份",
                                  "属于大任务": "找回被典当出去的那套医书",
                                  "状态": "未完成"}],
                     "解除个性": ["记东西写在本上"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 114,
        "hero": "秦照",
        "scene": "庭院",
        "people": {
            "秦照": {
                "位置": "庭院", "精神值": 48,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["执着", "树根的动静他最先发现", "木片上的刻痕他收着"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "方既白": {
                "位置": "庭院", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "她扫院子扫了三年", "捡回来的东西她不肯扔"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方既白"],
        "hidden": {"黎书言": "装订间"},
        "items": {},
        "changes": {
            "秦照": {"新增小任务": [{"目标": "查清那一根被锯走的树枝上的刻字",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
            "方既白": {"新增小任务": [{"目标": "把树干背面那行刻字拓下来",
                                  "属于大任务": "把走失的兄长从外地找回来",
                                  "状态": "未完成"}]},
            "庭院": {"新增外貌": ["地上只剩一层木屑，扫过的痕迹很清楚"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 115,
        "hero": "苏既白",
        "scene": "水槽前",
        "people": {
            "苏既白": {
                "位置": "水槽前", "精神值": 54,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "管子坏了他自己紧", "紧住了就不再多说"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "把水槽底下那一截锈管换掉", "状态": "未完成"}]},
            },
            "方望舒": {
                "位置": "水槽前", "精神值": 53,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "抹布归她管", "漏一次她擦一次"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方望舒"],
        "hidden": {"秦照": "庭院"},
        "items": {},
        "changes": {
            "苏既白": {"精神值": 59,
                     "完成任务": ["把水槽底下那一截锈管换掉"]},
            "方望舒": {"新增外貌": ["手指上沾了一点铁锈"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 116,
        "hero": "温照",
        "scene": "古籍库",
        "people": {
            "温照": {
                "位置": "东侧回廊", "精神值": 51,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "封条他一张张按平", "底下还有一层的他要掀开看"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "用灯照出旧封条上的日期", "状态": "未完成"}]},
            },
            "叶含章": {
                "位置": "东侧回廊", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "小手电她随身带着", "查不出来就写不可考"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"苏既白": "水槽前", "叶含章": "东侧回廊"},
        "items": {},
        "changes": {
            "温照": {"位置": "古籍库",
                     "完成任务": ["用灯照出旧封条上的日期"],
                     "新增个性": ["决定把旧封条也留着"]},
            "东侧回廊": {"新增外貌": ["新封条底下还有一层发黄的旧纸"]},
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
