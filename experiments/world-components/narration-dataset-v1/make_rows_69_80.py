"""Rows 69-80: twelve more fabricated narration-dataset rows.

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
        "index": 69,
        "hero": "沈望舒",
        "scene": "报刊架后",
        "people": {
            "沈望舒": {
                "位置": "报刊架后", "精神值": 58,
                "外貌": ["袖口沾了墨", "头发用一根木簪别着"],
                "个性": ["谨慎", "她在报刊室做剪报", "缺了几期非要数清"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "秦望舒": {
                "位置": "报刊架后", "精神值": 46,
                "外貌": ["戴着一副圆框眼镜", "鞋面有一层土"],
                "个性": ["执着", "他把每一期报都按年月排过", "数不清不回家"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "数清那一年的报缺了几期", "状态": "未完成"}]},
            },
        },
        "also_present": ["秦望舒"],
        "hidden": {"顾照": "馆外街道"},
        "items": {},
        "changes": {
            "秦望舒": {"精神值": 38,
                     "完成任务": ["数清那一年的报缺了几期"]},
            "沈望舒": {"新增个性": ["答应陪秦望舒把剩下的几摞也数完"]},
            "报刊架后": {"新增外貌": ["空出来的架子上留着报纸压出的印子"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 70,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 56,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["讲究次序", "换过封皮的书她一本一本记", "记到第三十七张没停"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "温砚": {
                "位置": "借阅台", "精神值": 52,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["心软", "在借阅台站了三年", "见不得卡片堆歪"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把换过封皮的书逐本登记", "状态": "未完成"}]},
            },
            "苏含章": {
                "位置": "借阅台", "精神值": 49,
                "外貌": ["衣角被雨打湿过", "外套袖口磨破了"],
                "个性": ["嘴硬", "她只管还书这一头", "排在后面也不催"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温砚", "苏含章"],
        "hidden": {"柏既明": "庭院石阶"},
        "items": {},
        "changes": {
            "温砚": {"完成任务": ["把换过封皮的书逐本登记"]},
            "叶含章": {"新增外貌": ["右手食指上沾了一点印泥"]},
            "借阅台": {"新增外貌": ["台角多了一摞卡片，堆得有点歪"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 71,
        "hero": "韩照",
        "scene": "古籍库",
        "people": {
            "韩照": {
                "位置": "古籍库", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["执着", "校样他一本一本对", "削过的字他一眼看得出来"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "黎书言": {
                "位置": "古籍库", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["谨慎", "她管着两把钥匙里的一把", "数错了就重数"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "数清校样里被削过的页", "状态": "未完成"}]},
            },
        },
        "also_present": ["黎书言"],
        "hidden": {"叶含章": "借阅台"},
        "items": {"校样": {"位置": "古籍库", "外貌": ["纸边被削过，削得笔直"]}},
        "changes": {
            "黎书言": {"新增外貌": ["右手手腕上有一道新划的白印"]},
            "校样": {"新增外貌": ["第九页边上被削掉的字重新描过"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 72,
        "hero": "苏含章",
        "scene": "地下书库",
        "people": {
            "苏含章": {
                "位置": "地下书库", "精神值": 53,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "机器坏了他自己拆", "灰不清干净不装回去"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "柏照": {
                "位置": "地下书库", "精神值": 45,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["心软", "这屋里的书他一本一本地数过", "见不得架子敞着"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"韩照": "古籍库"},
        "items": {},
        "changes": {
            "柏照": {"位置": "装订间", "精神值": 51},
            "苏含章": {"新增个性": ["答应把除湿机修好再走"]},
            "地下书库": {"新增外貌": ["除湿机侧板卸下来靠在地上，螺丝摆成一排"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 73,
        "hero": "叶照",
        "scene": "装订间",
        "people": {
            "叶照": {
                "位置": "装订间", "精神值": 47,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "裁剩的纸边她都捆起来留着", "记东西写在本上不靠脑子"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"柏照": "地下书库", "苏含章": "配电间"},
        "items": {},
        "changes": {
            "叶照": {"新增小任务": [{"目标": "把柜子最下一层那七捆纸边清点一遍",
                                  "属于大任务": "找到父亲留下的那只铁皮匣子",
                                  "状态": "未完成"}]},
            "装订间": {"新增外貌": ["胶锅底结了一层冷掉的浆糊"]},
        },
        "time": "21 分钟",
    },
    {
        "index": 74,
        "hero": "方既白",
        "scene": "天台",
        "people": {
            "方既白": {
                "位置": "天台", "精神值": 60,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "兄长走失那年她十六岁", "听见有人跑过去就要问清楚"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "叶暮": {
                "位置": "天台", "精神值": 52,
                "外貌": ["围巾洗得发白", "鞋面有一层土"],
                "个性": ["沉默寡言", "那晚他在装订间，门是从外面锁的", "一直以为是自己记错"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶暮"],
        "hidden": {"苏含章": "地下书库"},
        "items": {},
        "changes": {
            "叶暮": {"解除个性": ["一直以为是自己记错"],
                     "新增个性": ["确定那晚门是从外面锁的"]},
        },
        "time": "8 分钟",
    },
    {
        "index": 75,
        "hero": "周书言",
        "scene": "缩微胶片室",
        "people": {
            "周书言": {
                "位置": "缩微胶片室", "精神值": 54,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["执着", "她一卷一卷地看胶片", "页码对不上就停"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "温既明": {
                "位置": "缩微胶片室", "精神值": 50,
                "外貌": ["外套袖口磨破了", "手指上沾了铅笔灰"],
                "个性": ["记性好", "胶卷的号他闭着眼能报出来", "少一页就要去调原本"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把十七号胶卷和原本对一遍", "状态": "未完成"}],},
            },
            "秦望舒": {
                "位置": "缩微胶片室", "精神值": 48,
                "外貌": ["鞋面有一层土", "围巾洗得发白"],
                "个性": ["嘴硬", "他数报数了十六年", "不认自己数错"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温既明", "秦望舒"],
        "hidden": {"方既白": "天台"},
        "items": {},
        "changes": {
            "温既明": {"完成任务": ["把十七号胶卷和原本对一遍"]},
            "周书言": {"新增小任务": [{"目标": "查清印厂那批样张被谁搬走了",
                                  "属于大任务": "把走失的兄长从外地找回来",
                                  "状态": "未完成"}]},
        },
        "time": "17 分钟",
    },
    {
        "index": 76,
        "hero": "顾照",
        "scene": "馆外街道",
        "people": {
            "顾照": {
                "位置": "馆外街道", "精神值": 55,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["谨慎", "他记日子从不用本子", "差一天也要查清"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清后门那把锁换锁的真实日期", "状态": "未完成"}]},
            },
            "柏清和": {
                "位置": "二层走廊", "精神值": 52,
                "外貌": ["头发用一根木簪别着", "戴着一副圆框眼镜"],
                "个性": ["记性好", "信封里的纸她随身带着", "口风紧"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["柏清和"],
        "hidden": {"周书言": "缩微胶片室"},
        "items": {"路灯": {"位置": "馆外街道", "外貌": ["街口那一盏不亮了"]}},
        "changes": {
            "顾照": {"完成任务": ["查清后门那把锁换锁的真实日期"]},
            "柏清和": {"位置": "馆外街道"},
            "路灯": {"新增外貌": ["灯罩里积了水，亮起来是花的"]},
        },
        "time": "9 分钟",
    },
    {
        "index": 77,
        "hero": "秦照",
        "scene": "二层走廊",
        "people": {
            "秦照": {
                "位置": "二层走廊", "精神值": 52,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["执着", "地板第几块会响他心里有数", "拆开看才肯信"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "叶既明": {
                "位置": "二层走廊", "精神值": 47,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["嘴硬", "那晚他从这层跑下去过", "地板缝里抠出过东西"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清这一层地板是什么时候换的", "状态": "未完成"}]},
            },
        },
        "also_present": ["叶既明"],
        "hidden": {"顾照": "馆外街道"},
        "items": {},
        "changes": {
            "叶既明": {"精神值": 41},
            "秦照": {"精神值": 58},
            "二层走廊": {"新增外貌": ["第三块地板被撬开过，钉子换成了新的"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 78,
        "hero": "柏既明",
        "scene": "庭院石阶",
        "people": {
            "柏既明": {
                "位置": "庭院石阶", "精神值": 56,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["护短", "石阶的沟是他父亲那辈冲出来的", "答应的事一定做到"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
            "黎既白": {
                "位置": "庭院石阶", "精神值": 58,
                "外貌": ["指节上有旧伤", "围巾洗得发白"],
                "个性": ["心软", "她冬天在石阶上滑过一跤", "把手套留给了别人"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎既白"],
        "hidden": {"秦照": "二层走廊"},
        "items": {},
        "changes": {
            "黎既白": {"精神值": 52},
        },
        "time": "10 分钟",
    },
    {
        "index": 79,
        "hero": "沈照",
        "scene": "报刊阅览室",
        "people": {
            "沈照": {
                "位置": "报刊阅览室", "精神值": 49,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "名单上十一个人他问了九个", "两行字的报道他不放过"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "温暮": {
                "位置": "报刊阅览室", "精神值": 55,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "她替沈照记每一个人说了什么", "记错一个字要重记"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "秦书言": {
                "位置": "报刊阅览室", "精神值": 46,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "母亲那晚也在馆里", "把重排的事说了出来"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "找出印厂那批样张的下落", "状态": "未完成"}]},
            },
        },
        "also_present": ["温暮", "秦书言"],
        "hidden": {"柏既明": "庭院石阶"},
        "items": {},
        "changes": {
            "秦书言": {"解除个性": ["心软"],
                     "新增个性": ["把印厂的事说出去，不再等人先开口"]},
            "温暮": {"解除个性": ["记错一个字要重记"],
                    "新增个性": ["抄下来的东西先给沈照看一遍"]},
            "沈照": {"精神值": 43},
        },
        "time": "14 分钟",
    },
    {
        "index": 80,
        "hero": "周既白",
        "scene": "配电间",
        "people": {
            "周既白": {
                "位置": "配电间", "精神值": 51,
                "外貌": ["鞋面有一层土", "围巾洗得发白"],
                "个性": ["好奇心重", "她说查就查到底", "碰东西先用手背试温度"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清三楼走廊那一路线是什么时候接上的", "状态": "未完成"}]},
            },
            "江既白": {
                "位置": "配电间", "精神值": 54,
                "外貌": ["外套袖口磨破了", "戴着一副圆框眼镜"],
                "个性": ["讲究次序", "线路图在她脑子里过三遍", "闸刀合过几次她要数"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清三楼走廊那一路线是什么时候接上的",
                                "状态": "未完成"}]},
            },
        },
        "also_present": ["江既白"],
        "hidden": {"沈照": "报刊阅览室"},
        "items": {},
        "changes": {
            "江既白": {"新增外貌": ["手掌上蹭了一道黑印"],
                     "完成任务": ["查清三楼走廊那一路线是什么时候接上的"]},
            "周既白": {"精神值": 45},
            "配电间": {"新增外貌": ["配电箱门上有一道新磨的划痕"]},
        },
        "time": "12 分钟",
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
