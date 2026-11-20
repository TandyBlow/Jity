"""Rows 45-56: twelve more fabricated narration-dataset rows.

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
        "index": 45,
        "hero": "方既明",
        "scene": "水槽前",
        "people": {
            "方既明": {
                "位置": "水槽前", "精神值": 58,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["沉默寡言", "他管着茶水间的热水", "修东西不爱叫人帮忙"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "温既白": {
                "位置": "水槽前", "精神值": 56,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["讲究次序", "茶水间的水槽堵过多少回她数得清", "认死理"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把水槽下水口的茶垢刷干净", "状态": "未完成"}]},
            },
        },
        "also_present": ["温既白"],
        "hidden": {"周含章": "报刊库"},
        "items": {},
        "changes": {
            "温既白": {"完成任务": ["把水槽下水口的茶垢刷干净"]},
            "方既明": {"精神值": 54},
            "水槽前": {"新增外貌": ["下水口边上积了一圈洗不掉的茶垢"]},
        },
        "time": "8 分钟",
    },
    {
        "index": 46,
        "hero": "叶既白",
        "scene": "二层西侧书架",
        "people": {
            "叶既白": {
                "位置": "二层西侧书架", "精神值": 53,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["谨慎", "西侧书架的书她按灰量记位置", "认定那本书是被人拿走的"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": []},
            },
            "顾既白": {
                "位置": "二层西侧书架", "精神值": 57,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["嘴硬", "他搬书搬了十年", "手背上的口子从来不管"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既白"],
        "hidden": {"方既明": "水槽前"},
        "items": {},
        "changes": {
            "顾既白": {"新增外貌": ["右手手背上有一道书架划的新口子"]},
            "叶既白": {"解除个性": ["认定那本书是被人拿走的"],
                     "新增个性": ["拿不准那本书是自己记错了位置"]},
        },
        "time": "9 分钟",
    },
    {
        "index": 47,
        "hero": "秦照",
        "scene": "旧刊堆放区",
        "people": {
            "秦照": {
                "位置": "旧刊堆放区", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["执着", "旧刊垛是他一垛一垛解开的", "见不得纸烂在绳子里"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "沈暮": {
                "位置": "旧刊堆放区", "精神值": 61,
                "外貌": ["衣角被雨打湿过", "围巾洗得发白"],
                "个性": ["记性好", "她认得出十年前的封面色", "发现对不上就要记下来"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["沈暮"],
        "hidden": {"叶既白": "二层西侧书架"},
        "items": {},
        "changes": {
            "沈暮": {"精神值": 52,
                     "新增小任务": [{"目标": "数清这一垛里有多少张是后贴的封面",
                                  "属于大任务": "查明族谱被谁抄走了一份",
                                  "状态": "未完成"}]},
            "秦照": {"新增个性": ["答应陪沈暮把这垛解到底"]},
        },
        "time": "17 分钟",
    },
    {
        "index": 48,
        "hero": "周既白",
        "scene": "庭院",
        "people": {
            "周既白": {
                "位置": "庭院", "精神值": 49,
                "外貌": ["鞋面有一层土", "头发用一根木簪别着"],
                "个性": ["心软", "她扫院子扫了三年", "见不得地上有落叶"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "温照": {
                "位置": "庭院", "精神值": 55,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "他在院子里挖过两回地", "埋着的东西他不肯乱动"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "把老槐树根底下埋着的东西挖出来", "状态": "未完成"}]},
            },
        },
        "also_present": ["温照"],
        "hidden": {"沈暮": "旧刊堆放区"},
        "items": {},
        "changes": {
            "温照": {"完成任务": ["把老槐树根底下埋着的东西挖出来"]},
            "周既白": {"精神值": 56},
            "庭院": {"新增外貌": ["老槐树的叶子落了一半，扫过的地方下午又被填满"]},
        },
        "time": "11 分钟",
    },
    {
        "index": 49,
        "hero": "柏既明",
        "scene": "庭院石阶",
        "people": {
            "柏既明": {
                "位置": "庭院石阶", "精神值": 51,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "石阶的沟是他父亲那辈冲出来的", "见不得人蹲着干活不说话"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
            "黎既白": {
                "位置": "庭院", "精神值": 58,
                "外貌": ["指节上有旧伤", "衣角被雨打湿过"],
                "个性": ["心软", "她冬天在石阶上滑过一跤", "做事不肯半途走"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎既白"],
        "hidden": {"温照": "庭院"},
        "items": {},
        "changes": {
            "黎既白": {"位置": "庭院石阶"},
            "柏既明": {"新增个性": ["答应明天带一副手套来"]},
        },
        "time": "7 分钟",
    },
    {
        "index": 50,
        "hero": "顾望舒",
        "scene": "后门",
        "people": {
            "顾望舒": {
                "位置": "后门", "精神值": 54,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["讲究次序", "后门那把钥匙她配过三把", "查不到底不肯收手"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清九八年秋天为什么换后门的锁", "状态": "未完成"}]},
            },
            "秦既白": {
                "位置": "后门", "精神值": 47,
                "外貌": ["鞋面有一层土", "袖口沾了机油"],
                "个性": ["谨慎", "他在后门这间屋里值了六年夜班", "听见门响就要看清是谁"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦既白"],
        "hidden": {"秦照": "旧刊堆放区"},
        "items": {},
        "changes": {
            "秦既白": {"解除外貌": ["袖口沾了机油"]},
            "顾望舒": {"完成任务": ["查清九八年秋天为什么换后门的锁"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 51,
        "hero": "温书言",
        "scene": "配电间",
        "people": {
            "温书言": {
                "位置": "配电间", "精神值": 62,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["执着", "线路图是他一笔一笔描的", "以为这间屋子他全知道"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "方照": {
                "位置": "配电间", "精神值": 56,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["沉默寡言", "她跟着老师傅学过接电", "不该碰的线她一根不碰"],
                "任务": {"大任务": {"目标": "把被典当出去的那套医书赎回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方照"],
        "hidden": {"秦既白": "后门"},
        "items": {},
        "changes": {
            "温书言": {"精神值": 45},
            "方照": {"新增个性": ["决定把那条后加的线画进线路图"]},
            "配电间": {"新增外貌": ["配电箱门上有一道新的划痕"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 52,
        "hero": "黎暮",
        "scene": "三层走廊",
        "people": {
            "黎暮": {
                "位置": "三层走廊", "精神值": 50,
                "外貌": ["指节上有旧伤", "围巾洗得发白"],
                "个性": ["好奇心重", "墙皮鼓起来的地方她一块块摸过", "不肯把看见的事说出去"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"韩既明": "古籍库", "顾望舒": "后门"},
        "items": {},
        "changes": {
            "黎暮": {"新增外貌": ["鞋面上落了一层磨墙的灰"]},
            "三层走廊": {"新增外貌": ["走廊尽头那盏台灯只亮了一半，墙皮被磨开一道缝"]},
        },
        "time": "24 分钟",
    },
    {
        "index": 53,
        "hero": "苏既白",
        "scene": "二层走廊",
        "people": {
            "苏既白": {
                "位置": "二层走廊", "精神值": 52,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["不爱欠人情", "走廊上第几块地板会响他心里有数", "对不上账就不算完"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "核对那半年值班表的交接次数", "状态": "未完成"}]},
            },
            "柏清和": {
                "位置": "二层走廊", "精神值": 57,
                "外貌": ["戴着一副圆框眼镜", "头发用一根木簪别着"],
                "个性": ["记性好", "还书箱的存根她按日子排", "发现缺口就一定要补齐"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "数清那半年少了多少张借阅单存根", "状态": "未完成"}]},
            },
        },
        "also_present": ["柏清和"],
        "hidden": {"黎暮": "三层走廊"},
        "items": {},
        "changes": {
            "苏既白": {"完成任务": ["核对那半年值班表的交接次数"]},
            "柏清和": {"完成任务": ["数清那半年少了多少张借阅单存根"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 54,
        "hero": "顾书言",
        "scene": "门卫岗亭",
        "people": {
            "顾书言": {
                "位置": "门卫岗亭", "精神值": 53,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["谨慎", "岗亭里的东西他一件件数过", "看字先看笔迹"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "方书言": {
                "位置": "门卫岗亭", "精神值": 48,
                "外貌": ["围巾洗得发白", "衣角被雨打湿过"],
                "个性": ["嘴硬", "她在岗亭坐了六年", "冷也不肯多穿一件"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方书言"],
        "hidden": {"苏既白": "二层走廊"},
        "items": {"电暖器": {"位置": "门卫岗亭", "外貌": ["铁皮壳上有一块烤黄的印子"]}},
        "changes": {
            "方书言": {"精神值": 55},
            "电暖器": {"新增外貌": ["铁皮壳上又烤黄了一块"]},
            "顾书言": {"新增小任务": [{"目标": "问清中间那半个月是谁替的班",
                                  "属于大任务": "找到父亲留下的那只铁皮匣子",
                                  "状态": "未完成"}]},
        },
        "time": "9 分钟",
    },
    {
        "index": 55,
        "hero": "叶既明",
        "scene": "报刊阅览室",
        "people": {
            "叶既明": {
                "位置": "报刊阅览室", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["讲究次序", "他管阅览室的镇纸", "见不得人在报上折角"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "秦书言": {
                "位置": "报刊阅览室", "精神值": 54,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["心软", "母亲那晚也在馆里", "从不说家里的事"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "韩望舒": {
                "位置": "报刊阅览室", "精神值": 46,
                "外貌": ["指节上有旧伤", "外套袖口磨破了"],
                "个性": ["嘴硬", "父亲那晚当班", "认定说了也没用"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "问清那天夜里上二楼的人是谁", "状态": "未完成"}]},
            },
        },
        "also_present": ["秦书言", "韩望舒"],
        "hidden": {"顾书言": "门卫岗亭"},
        "items": {},
        "changes": {
            "秦书言": {"解除个性": ["从不说家里的事"],
                     "新增个性": ["把母亲那晚当班的事说了出来"]},
            "韩望舒": {"解除个性": ["认定说了也没用"],
                     "新增个性": ["想找个人把父亲那晚的事说清楚"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 56,
        "hero": "周含章",
        "scene": "报刊库",
        "people": {
            "周含章": {
                "位置": "报刊库", "精神值": 57,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["执着", "她查了十年的值班记录", "记下的东西不肯改"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查出九八年十月十七日那晚的值班人名字",
                                "状态": "未完成"}]},
            },
            "柏含章": {
                "位置": "报刊库", "精神值": 55,
                "外貌": ["鞋面有一层土", "袖口沾了墨"],
                "个性": ["护短", "父亲当年在馆里管书", "见过的人记得住脸"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["柏含章"],
        "hidden": {"叶既明": "报刊阅览室"},
        "items": {},
        "changes": {
            "周含章": {"完成任务": ["查出九八年十月十七日那晚的值班人名字"],
                     "解除个性": ["执着"],
                     "新增个性": ["查到了名字，反而不知道该做什么"]},
            "柏含章": {"新增个性": ["答应陪周含章把那本簿子送去复印"]},
        },
        "time": "15 分钟",
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
