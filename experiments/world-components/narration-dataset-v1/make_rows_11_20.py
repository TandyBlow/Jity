"""Rows 11-20: ten more fabricated narration-dataset rows.

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
        "index": 11,
        "hero": "唐既明",
        "scene": "值班室",
        "people": {
            "唐既明": {
                "位置": "值班室", "精神值": 44,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["沉默寡言", "在这间值班室值了十一年夜班",
                       "那晚跳闸的时候他就在楼下"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "问清配电间那晚跳闸的时间", "状态": "未完成"}]},
            },
            "谢停云": {
                "位置": "值班室", "精神值": 57,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["固执", "母亲改名换姓的事是她自己翻出来的",
                       "每月都来问同一件事，从不解释"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["谢停云"],
        "hidden": {"柏青": "一层走廊"},
        "items": {"内线电话": {"位置": "值班室",
                            "外貌": ["听筒线打过结", "漆掉了一半"]}},
        "changes": {
            "唐既明": {"完成任务": ["问清配电间那晚跳闸的时间"],
                     "新增小任务": [{"目标": "翻看十年前的值班记录",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
            "内线电话": {"解除外貌": ["听筒线打过结"], "新增外貌": ["听筒线换过新的"]},
            "值班室": {"新增外貌": ["窗上的报纸被撕掉一块"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 12,
        "hero": "温执",
        "scene": "还书处",
        "people": {
            "温执": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["不爱欠人情", "在还书处帮过工，知道哪只箱子漏底",
                       "认定十年前那场火灾不是意外"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "未完成"}]},
            },
            "黎知微": {
                "位置": "还书处", "精神值": 63,
                "外貌": ["袖口沾了墨", "衣角被雨打湿过"],
                "个性": ["讲究次序", "管着还书处那串钥匙",
                       "记得每个常来的人借过什么"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎知微"],
        "hidden": {"唐既明": "值班室"},
        "items": {"铁皮还书箱": {"位置": "还书处", "外貌": ["箱底锈穿了一个洞"]}},
        "changes": {
            "温执": {"位置": "还书处", "新增外貌": ["袖口沾了墨"]},
            "黎知微": {"新增个性": ["答应替温执留一只没登记过的旧箱"]},
            "铁皮还书箱": {"解除外貌": ["箱底锈穿了一个洞"], "新增外貌": ["箱底垫了一块木板"]},
        },
        "time": "4 分钟",
    },
    {
        "index": 13,
        "hero": "柏青",
        "scene": "报刊库",
        "people": {
            "柏青": {
                "位置": "报刊库", "精神值": 49,
                "外貌": ["头发用一根木簪别着", "袖口沾了墨"],
                "个性": ["嘴硬", "母亲改名换姓的事他从别人嘴里听过半句",
                       "从不认自己记错事"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "翻看十年前的值班记录", "状态": "未完成"}]},
            },
            "苏清和": {
                "位置": "报刊库", "精神值": 58,
                "外貌": ["围巾洗得发白", "鞋面有一层土"],
                "个性": ["心软", "被典当行的人糊弄过一次，从此不信嘴上的话",
                       "见过柏青为一份合订本跟人红过脸"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏清和"],
        "hidden": {"谢停云": "二层走廊"},
        "items": {"铁柜": {"位置": "报刊库", "外貌": ["抽屉很涩，拉开要使劲"]}},
        "changes": {
            "柏青": {"解除个性": ["从不认自己记错事"],
                     "新增个性": ["承认自己可能记错了那一年的日期"]},
            "铁柜": {"解除外貌": ["抽屉很涩，拉开要使劲"], "新增外貌": ["抽屉上了蜡，拉起来顺了"]},
        },
        "time": "9 分钟",
    },
    {
        "index": 14,
        "hero": "温照",
        "scene": "长桌区",
        "people": {
            "温照": {
                "位置": "长桌区", "精神值": 66,
                "外貌": ["戴着一副圆框眼镜", "头发用一根木簪别着"],
                "个性": ["好奇心重", "在这家馆做剪报，做了七年",
                       "不爱坐窗边，说光刺眼"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": [{"目标": "找出被人撕掉的那一页", "状态": "未完成"}]},
            },
            "方既明": {
                "位置": "长桌区", "精神值": 52,
                "外貌": ["袖口沾了墨", "围巾洗得发白"],
                "个性": ["沉默寡言", "哪一年的旧报堆在哪个角，他闭着眼能报出来",
                       "和温照共事多年，从没红过脸"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方既明"],
        "hidden": {"柏青": "报刊架后"},
        "items": {},
        "changes": {
            "长桌区": {"新增外貌": ["靠窗那张桌子的茶渍被擦掉了"]},
        },
        "time": "7 分钟",
    },
    {
        "index": 15,
        "hero": "苏既明",
        "scene": "地下书库",
        "people": {
            "苏既明": {
                "位置": "地下书库", "精神值": 48,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["护短", "在地下库熬了三个通宵", "认死理，认定的事九头牛拉不回"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "方既明": {
                "位置": "地下书库", "精神值": 53,
                "外貌": ["袖口沾了墨", "围巾洗得发白"],
                "个性": ["记性好", "哪一年的旧报堆在哪个角，他闭着眼能报出来",
                       "和苏既明吵过一次，吵完还是留下来"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "把受潮的旧刊挑出来晾干", "状态": "未完成"}]},
            },
        },
        "also_present": ["方既明"],
        "hidden": {"黎知微": "旧刊堆放区"},
        "items": {},
        "changes": {
            "苏既明": {"精神值": 58,
                     "新增个性": ["和方既明说开了，答应把剩下的挑完"]},
            "方既明": {"完成任务": ["把受潮的旧刊挑出来晾干"]},
        },
        "time": "25 分钟",
    },
    {
        "index": 16,
        "hero": "黎远",
        "scene": "门卫岗亭",
        "people": {
            "黎远": {
                "位置": "门卫岗亭", "精神值": 59,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["谨慎", "在这座岗亭坐了六年", "认得每一个夜里进出门的人"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查访当年的门卫", "状态": "未完成"}]},
            },
            "韩清和": {
                "位置": "门卫岗亭", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["嘴硬", "妹妹走失那年她十九岁", "每回走都从后门绕"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"苏清和": "一层门厅"},
        "items": {},
        "changes": {
            "黎远": {"新增小任务": [{"目标": "比对三份互相矛盾的登记簿",
                                  "属于大任务": "拿到能证明兄长清白的原始记录",
                                  "状态": "未完成"}],
                     "新增外貌": ["袖口沾了墨"]},
            "韩清和": {"位置": "馆外街道"},
        },
        "time": "6 分钟",
    },
    {
        "index": 17,
        "hero": "韩暮",
        "scene": "配电间",
        "people": {
            "韩暮": {
                "位置": "配电间", "精神值": 61,
                "外貌": ["手指关节发黄", "鞋面有一层土"],
                "个性": ["讲究次序", "在馆里管了十二年电路", "闻不得焦味"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "未完成"}]},
            },
            "叶照": {
                "位置": "配电间", "精神值": 64,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["记性好", "他父亲也是馆里的人", "和韩暮一起值过夜班"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶照"],
        "hidden": {"柏青": "一层走廊"},
        "items": {},
        "changes": {
            "韩暮": {"精神值": 50, "新增外貌": ["手背烫红了一块"]},
            "配电间": {"新增外貌": ["绝缘手套挂在门后，指头处磨穿了一个洞"]},
        },
        "time": "3 分钟",
    },
    {
        "index": 18,
        "hero": "程砚",
        "scene": "东侧回廊",
        "people": {
            "程砚": {
                "位置": "东侧回廊", "精神值": 55,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["好奇心重", "父亲当年是这家馆的古籍修复工", "记东西只写不记"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "翻看十年前的值班记录", "状态": "未完成"}]},
            },
            "江停云": {
                "位置": "东侧回廊", "精神值": 60,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["心软", "妹妹走失那年她十九岁，此后再没搬过家",
                       "陪程砚查了三年，从没催过她"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["江停云"],
        "hidden": {"温照": "长桌区"},
        "items": {},
        "changes": {
            "程砚": {"解除外貌": ["戴着一副圆框眼镜"],
                     "新增外貌": ["换了副细框眼镜"],
                     "完成任务": ["翻看十年前的值班记录"],
                     "新增小任务": [{"目标": "查访当年的门卫",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
        },
        "time": "11 分钟",
    },
    {
        "index": 19,
        "hero": "江暮",
        "scene": "馆外街道",
        "people": {
            "江暮": {
                "位置": "后门", "精神值": 57,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "从后门进出惯了，不想让人看见",
                       "认定十年前那场火灾不是意外"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查访当年的门卫", "状态": "未完成"}]},
            },
            "秦砚": {
                "位置": "馆外街道", "精神值": 46,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["嘴硬", "搭档死在十年前那场火灾里", "和后门的锁匠熟"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦砚"],
        "hidden": {"黎远": "门卫岗亭"},
        "items": {},
        "changes": {
            "江暮": {"位置": "馆外街道"},
            "秦砚": {"新增个性": ["答应替江暮留一把后门的新钥匙"]},
            "后门": {"新增外貌": ["铁门上多了一道新划痕"]},
        },
        "time": "5 分钟",
    },
    {
        "index": 20,
        "hero": "叶清和",
        "scene": "一层门厅",
        "people": {
            "叶清和": {
                "位置": "一层门厅", "精神值": 50,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["谨慎", "在这家馆做前台，做了四年", "和柏暮是旧识，见面只谈公事"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "柏暮": {
                "位置": "一层门厅", "精神值": 62,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["记性好", "他父亲也是馆里的人", "认定有些东西是被故意弄丢的"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "找出被人撕掉的那一页", "状态": "未完成"}]},
            },
        },
        "also_present": ["柏暮"],
        "hidden": {"韩清和": "门卫岗亭"},
        "items": {"挂钟": {"位置": "一层门厅", "外貌": ["指针停在九点十分"]}},
        "changes": {
            "柏暮": {"完成任务": ["找出被人撕掉的那一页"],
                     "新增个性": ["认定那一页是被人故意撕掉的"]},
            "挂钟": {"解除外貌": ["指针停在九点十分"], "新增外貌": ["换过电池，指针动了"]},
        },
        "time": "13 分钟",
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
