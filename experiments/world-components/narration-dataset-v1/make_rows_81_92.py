"""Rows 81-92: twelve more fabricated narration-dataset rows.

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
        "index": 81,
        "hero": "温砚",
        "scene": "报刊架后",
        "people": {
            "温砚": {
                "位置": "报刊架后", "精神值": 57,
                "外貌": ["袖口沾了墨", "头发用一根木簪别着"],
                "个性": ["好奇心重", "她在报刊室做剪报，做了七年", "号跳了就一定要问为什么"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "黎含章": {
                "位置": "报刊架后", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "围巾洗得发白"],
                "个性": ["沉默寡言", "报号跳到哪儿他闭着眼能报出来", "空着的位置不肯随便填"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": []},
            },
            "柏书言": {
                "位置": "报刊架后", "精神值": 61,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["嘴硬", "母亲那年在装订间连做了七天", "说出来的话不肯再收"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清三月中旬母亲为什么七天没回家", "状态": "未完成"}]},
            },
        },
        "also_present": ["黎含章", "柏书言"],
        "hidden": {"江既白": "二层西侧书架"},
        "items": {},
        "changes": {
            "柏书言": {"精神值": 55},
            "黎含章": {"新增个性": ["决定把空着的三个位置一直空着"]},
            "报刊架后": {"新增外貌": ["架子上空出三个位置，木夹还挂着"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 82,
        "hero": "苏望舒",
        "scene": "长桌区",
        "people": {
            "苏望舒": {
                "位置": "长桌区", "精神值": 54,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["讲究次序", "她看报先看墨色", "两层墨压着就不放过"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
            "沈既明": {
                "位置": "长桌区", "精神值": 48,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["执着", "他认定那版通告被人动过", "不问清不回家"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "找出重排版通告的原本", "状态": "未完成"}]},
            },
        },
        "also_present": ["沈既明"],
        "hidden": {"柏书言": "报刊架后"},
        "items": {"放大镜": {"位置": "长桌区", "外貌": ["镜片换过了", "手柄的漆掉了一块"]}},
        "changes": {
            "苏望舒": {"新增小任务": [{"目标": "把这一版重排的痕拍下来",
                                  "属于大任务": "查明族谱被谁抄走了一份",
                                  "状态": "未完成"}]},
            "放大镜": {"解除外貌": ["手柄的漆掉了一块"],
                    "新增外貌": ["手柄上缠了一圈胶布"]},
            "长桌区": {"新增外貌": ["窗玻璃上积了一层薄灰，没人擦"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 83,
        "hero": "温照",
        "scene": "古籍库",
        "people": {
            "温照": {
                "位置": "古籍库", "精神值": 52,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "单子在他怀里从来不折", "看见散线的书就蹲下去"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "叶含章": {
                "位置": "古籍库", "精神值": 49,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["谨慎", "断线的地方她先看断口", "看见借书卡就一张张抄"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清那十九张借书卡是谁写的", "状态": "未完成"}]},
            },
        },
        "also_present": ["叶含章"],
        "hidden": {"苏望舒": "长桌区"},
        "items": {},
        "changes": {
            "叶含章": {"新增外貌": ["手指上沾了纸灰"],
                     "完成任务": ["查清那十九张借书卡是谁写的"]},
            "温照": {"新增个性": ["答应把这一批散线的书都包一遍"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 84,
        "hero": "苏含章",
        "scene": "地下书库",
        "people": {
            "苏含章": {
                "位置": "地下书库", "精神值": 51,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["护短", "机器坏了他自己拆", "听见人跑不问清楚不踏实"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "柏照": {
                "位置": "地下书库", "精神值": 46,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["心软", "这屋里的书他一本一本地数过", "明天的事不肯拖到后天"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["柏照"],
        "hidden": {"温照": "古籍库"},
        "items": {},
        "changes": {
            "柏照": {"精神值": 41},
            "苏含章": {"新增个性": ["决定把那晚听见的脚步声说出去"]},
            "地下书库": {"新增外貌": ["两排架子盖上了布，布角落着灰"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 85,
        "hero": "叶暮",
        "scene": "装订间",
        "people": {
            "叶暮": {
                "位置": "装订间", "精神值": 48,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "在这间装订间干了二十六年", "刀不快就磨到快"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"苏含章": "地下书库", "柏照": "地下书库"},
        "items": {"裁纸刀": {"位置": "装订间", "外貌": ["刃口卷了两处", "刀柄磨得发亮"]}},
        "changes": {
            "叶暮": {"新增外貌": ["右手虎口上沾了磨刀的灰"]},
            "裁纸刀": {"解除外貌": ["刃口卷了两处"], "新增外貌": ["刃口磨出了一道直亮的线"]},
            "装订间": {"新增外貌": ["柜子底下摸出一块蒙着油布的油石"]},
        },
        "time": "23 分钟",
    },
    {
        "index": 86,
        "hero": "顾既明",
        "scene": "天台",
        "people": {
            "顾既明": {
                "位置": "天台", "精神值": 53,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "排水口堵了他自己掏", "睡不着的人爱往天台上跑"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "秦暮": {
                "位置": "天台", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["谨慎", "夜里的动静她记得住时间", "听见跑动不肯当没听见"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦暮"],
        "hidden": {"叶暮": "装订间"},
        "items": {},
        "changes": {
            "秦暮": {"新增小任务": [{"目标": "查清那一晚从楼上跑下来的人是谁",
                                  "属于大任务": "查明族谱被谁抄走了一份",
                                  "状态": "未完成"}]},
            "顾既明": {"精神值": 47},
            "天台": {"新增外貌": ["排水口周围积的泥被掏开，露出水泥地"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 87,
        "hero": "韩暮",
        "scene": "报刊阅览室",
        "people": {
            "韩暮": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["记性好", "裁口直不直她一眼看得出来", "透过来能认的字她抄下来"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "把被裁掉那一列的日子认出来", "状态": "未完成"}]},
            },
            "沈照": {
                "位置": "报刊阅览室", "精神值": 47,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "名单上十一个人他问了九个", "三指宽的口子他要量准"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["沈照"],
        "hidden": {"顾既明": "天台"},
        "items": {},
        "changes": {
            "韩暮": {"完成任务": ["把被裁掉那一列的日子认出来"]},
            "沈照": {"精神值": 52},
            "报刊阅览室": {"新增外貌": ["只开了一半的灯，另一半说是省电"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 88,
        "hero": "方既白",
        "scene": "借阅台",
        "people": {
            "方既白": {
                "位置": "借阅台", "精神值": 58,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["谨慎", "借书先看书脊再看扉页", "不是它说自己是的那个东西就不借"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "周望舒": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["心软", "柜台后面的事他一件件记", "答应了就天天等"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清这一批里还有几本换过书名", "状态": "未完成"}]},
            },
            "程既明": {
                "位置": "借阅台", "精神值": 60,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["不爱欠人情", "他在借阅台站了四年", "卡片上的字写得慢"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["周望舒", "程既明"],
        "hidden": {"韩暮": "报刊阅览室"},
        "items": {},
        "changes": {
            "周望舒": {"完成任务": ["查清这一批里还有几本换过书名"]},
            "程既明": {"新增外貌": ["右手食指上沾了一点印泥"]},
            "方既白": {"精神值": 62},
        },
        "time": "11 分钟",
    },
    {
        "index": 89,
        "hero": "周望舒",
        "scene": "东侧回廊",
        "people": {
            "周望舒": {
                "位置": "东侧回廊", "精神值": 52,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "封条背面的字她一张张看", "看见了就不肯当没看见"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "温暮": {
                "位置": "东侧回廊", "精神值": 54,
                "外貌": ["围巾洗得发白", "鞋面有一层土"],
                "个性": ["谨慎", "她记东西先记纸", "纸从哪儿裁下来的她要问"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清那张封条的纸是从哪本书上裁的", "状态": "未完成"}]},
            },
        },
        "also_present": ["温暮"],
        "hidden": {"方既白": "借阅台"},
        "items": {},
        "changes": {
            "周望舒": {"新增小任务": [{"目标": "把封条背面那个名字查出来",
                                  "属于大任务": "把走失的兄长从外地找回来",
                                  "状态": "未完成"}]},
            "温暮": {"新增外貌": ["手指上沾了铅笔灰"]},
            "东侧回廊": {"新增外貌": ["窗上贴了一年的封条掉下来一条"]},
        },
        "time": "9 分钟",
    },
    {
        "index": 90,
        "hero": "黎书言",
        "scene": "门卫岗亭",
        "people": {
            "黎书言": {
                "位置": "门卫岗亭", "精神值": 55,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["心软", "她在岗亭坐了六年", "表贴歪了就要扶正"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "顾既明": {
                "位置": "门卫岗亭", "精神值": 49,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "他认得几个人", "站在窗外看值班表的人他一定要问清"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既明"],
        "hidden": {"周望舒": "东侧回廊"},
        "items": {"值班表": {"位置": "门卫岗亭", "外貌": ["被暖器烤得卷了边", "贴得有点歪"]}},
        "changes": {
            "黎书言": {"解除个性": ["表贴歪了就要扶正"],
                     "新增个性": ["夜里把门从里面反锁"]},
            "值班表": {"解除外貌": ["贴得有点歪"], "新增外貌": ["重新贴正了，四个角都压实"]},
            "顾既明": {"新增小任务": [{"目标": "查清站在窗外看值班表的是谁",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
        },
        "time": "8 分钟",
    },
    {
        "index": 91,
        "hero": "柏望舒",
        "scene": "二层西侧书架",
        "people": {
            "柏望舒": {
                "位置": "二层西侧书架", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["执着", "书脊上的号他要一本本对", "空了的位置他不肯填"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
            "江既白": {
                "位置": "二层西侧书架", "精神值": 53,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["记性好", "夹在书里的纸他一眼看见", "抄下来的东西一定留着"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "按那张纸上的索书号把十一本找齐", "状态": "未完成"}]},
            },
        },
        "also_present": ["江既白"],
        "hidden": {"黎书言": "门卫岗亭"},
        "items": {},
        "changes": {
            "柏望舒": {"新增小任务": [{"目标": "查清第七本被谁拿走了",
                                  "属于大任务": "查明族谱被谁抄走了一份",
                                  "状态": "未完成"}]},
            "江既白": {"精神值": 57},
        },
        "time": "12 分钟",
    },
    {
        "index": 92,
        "hero": "周书言",
        "scene": "庭院",
        "people": {
            "周书言": {
                "位置": "庭院", "精神值": 56,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["执着", "树皮把字吃进去她也要认", "锯口新不新她先看木屑"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "温照": {
                "位置": "庭院", "精神值": 51,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "木屑潮不潮他一捻就知道", "树的事他不肯乱动"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "查清树干背面刻的名字是谁", "状态": "未完成"}]},
            },
        },
        "also_present": ["温照"],
        "hidden": {"柏望舒": "二层西侧书架", "江既白": "二层西侧书架"},
        "items": {},
        "changes": {
            "温照": {"完成任务": ["查清树干背面刻的名字是谁"]},
            "周书言": {"精神值": 49},
            "庭院": {"新增外貌": ["老槐树被锯掉一根枝，锯口还新"]},
        },
        "time": "11 分钟",
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
