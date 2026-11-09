"""Rows 189-200: twelve more fabricated narration-dataset rows.

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
        "index": 189,
        "hero": "秦照",
        "scene": "报刊阅览室",
        "people": {
            "秦照": {
                "位置": "报刊阅览室", "精神值": 49,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["执着", "对不完就不回去", "写完了才敢说查完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清那二十二页是谁修过边", "状态": "未完成"}]},
            },
            "沈既明": {
                "位置": "报刊阅览室", "精神值": 52,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["护短", "一个人坐到天亮他不放心", "问到最后要问到自己头上"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["沈既明"],
        "hidden": {"叶望舒": "古籍库"},
        "items": {},
        "changes": {
            "秦照": {"完成任务": ["查清十年前那场火灾是谁放的火",
                              "查清那二十二页是谁修过边"]},
        },
        "time": "34 分钟",
    },
    {
        "index": 190,
        "hero": "叶望舒",
        "scene": "古籍库",
        "people": {
            "叶望舒": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["讲究次序", "削口都在哪一边她要数", "想出来就用"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "把三十七页削过的字逐页校出来", "状态": "未完成"}]},
            },
            "顾既白": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "原本才肯信", "想到的办法当场就用"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既白"],
        "hidden": {"秦照": "报刊阅览室"},
        "items": {},
        "changes": {
            "叶望舒": {"新增个性": ["削口在哪一边，先数清楚再动手"]},
            "顾既白": {"新增个性": ["一页画一个方框，方框对着削口"],
                     "精神值": 44},
        },
        "time": "23 分钟",
    },
    {
        "index": 191,
        "hero": "温暮",
        "scene": "缩微胶片室",
        "people": {
            "温暮": {
                "位置": "缩微胶片室", "精神值": 50,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "标签贴了几层她看得出", "接缝她要看两遍"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清这一卷胶片为什么换过三次标签", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"叶望舒": "古籍库", "顾既白": "古籍库"},
        "items": {"胶片盒": {"位置": "缩微胶片室",
                         "外貌": ["卷号是三零九", "盒盖贴着一张新标签", "标签下面是另一张旧标签"]}},
        "changes": {
            "胶片盒": {"解除外貌": ["盒盖贴着一张新标签", "标签下面是另一张旧标签"],
                     "新增外貌": ["盒盖上三层标签都被揭开，边角翘着"]},
        },
        "time": "25 分钟",
    },
    {
        "index": 192,
        "hero": "周书言",
        "scene": "庭院",
        "people": {
            "周书言": {
                "位置": "庭院", "精神值": 51,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["心软", "树根底下有东西她要挖", "挖出来以前先不动"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "黎既白": {
                "位置": "庭院", "精神值": 50,
                "外貌": ["指节上有旧伤", "衣角被雨打湿过"],
                "个性": ["心软", "石缝里的苔她要留着", "埋着的东西她不乱动"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "柏书言": {
                "位置": "庭院", "精神值": 49,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "昨天看过的地方他记得清", "埋东西的人还在院里他就走"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎既白"],
        "hidden": {"温暮": "缩微胶片室"},
        "items": {},
        "changes": {
            "柏书言": {"位置": "地下书库"},
            "周书言": {"新增外貌": ["袖口沾了湿土"]},
            "黎既白": {"精神值": 43},
        },
        "time": "17 分钟",
    },
    {
        "index": 193,
        "hero": "韩照",
        "scene": "装订间",
        "people": {
            "韩照": {
                "位置": "装订间", "精神值": 48,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "开过刃的刀他要挑出来", "刀柄上的字他要念出声"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "试出柜子里七把刀哪把最合手", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"周书言": "庭院", "黎既白": "庭院"},
        "items": {},
        "changes": {
            "韩照": {"新增外貌": ["手指上沾了磨刀的石粉", "袖口上有一道新划的细口",
                              "右手虎口上贴着一小块胶布"]},
        },
        "time": "22 分钟",
    },
    {
        "index": 194,
        "hero": "江既白",
        "scene": "配电间",
        "people": {
            "江既白": {
                "位置": "配电间", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["谨慎", "线槽走向他要量", "数过的束数他记得住"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清被拿走的那一束线接到哪儿", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"韩照": "装订间"},
        "items": {},
        "changes": {
            "江既白": {"精神值": 31},
        },
        "time": "19 分钟",
    },
    {
        "index": 195,
        "hero": "温砚",
        "scene": "报刊架后",
        "people": {
            "温砚": {
                "位置": "报刊架后", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["讲究次序", "七七年到八六年他一年一年数", "单子他要带出去"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "数清七七年到八六年缺的报", "状态": "未完成"}]},
            },
            "周书言": {
                "位置": "报刊架后", "精神值": 52,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["心软", "十月十七那一期她要问", "两张单子要一起送"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "查清每年十月缺的那一期是不是同一版", "状态": "未完成"}]},
            },
            "苏望舒": {
                "位置": "报刊架后", "精神值": 53,
                "外貌": ["头发用一根木簪别着", "戴着一副圆框眼镜"],
                "个性": ["心软", "八七年往后归她数", "窄道里她总能挤出办法"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "数清八七年到九八年缺的报", "状态": "未完成"}]},
            },
        },
        "also_present": ["周书言", "苏望舒"],
        "hidden": {"江既白": "配电间"},
        "items": {},
        "changes": {
            "温砚": {"完成任务": ["数清七七年到八六年缺的报"]},
            "苏望舒": {"完成任务": ["数清八七年到九八年缺的报"]},
            "报刊架后": {"新增外貌": ["中间两排架子被推开了半尺"]},
        },
        "time": "24 分钟",
    },
    {
        "index": 196,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "卡片写过几次她要数", "描字的时候不下班"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "把借书卡上三层字描出来", "状态": "未完成"}]},
            },
            "方望舒": {
                "位置": "借阅台", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "念日期她一个字不差", "说要留下就留下"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方望舒"],
        "hidden": {"温砚": "报刊架后"},
        "items": {},
        "changes": {
            "叶含章": {"完成任务": ["把借书卡上三层字描出来"],
                     "解除个性": ["描字的时候不下班"],
                     "新增个性": ["描完一个字就念一遍给人听"]},
            "借阅台": {"新增外貌": ["铜灯今天亮得早"]},
        },
        "time": "21 分钟",
    },
    {
        "index": 197,
        "hero": "柏照",
        "scene": "地下书库",
        "people": {
            "柏照": {
                "位置": "地下书库", "精神值": 47,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["心软", "潮气往上走他要摸墙", "拆墙的事他不肯轻说"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清最里面那面墙后面是什么", "状态": "未完成"}]},
            },
            "苏含章": {
                "位置": "地下书库", "精神值": 50,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "搬书要记账", "除湿机坏了他自己修"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "把靠墙那两排书搬到别的架子", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"叶含章": "借阅台"},
        "items": {},
        "changes": {
            "地下书库": {"解除外貌": ["除湿机日夜响着，书脊上有一层薄霉。"],
                     "新增外貌": ["除湿机重新开了，书脊上的薄霉没退"]},
        },
        "time": "27 分钟",
    },
    {
        "index": 198,
        "hero": "沈照",
        "scene": "东侧回廊",
        "people": {
            "沈照": {
                "位置": "东侧回廊", "精神值": 49,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "问不到底就不算问完", "问到自己头上也不躲"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "把当班名单上十一个人一个个问到", "状态": "未完成"}]},
            },
            "温暮": {
                "位置": "东侧回廊", "精神值": 52,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "空白值班表的事她要写清", "怕也要问"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温暮"],
        "hidden": {"柏照": "地下书库"},
        "items": {},
        "changes": {
            "沈照": {"精神值": 57},
            "温暮": {"精神值": 44},
        },
        "time": "15 分钟",
    },
    {
        "index": 199,
        "hero": "方既白",
        "scene": "天台",
        "people": {
            "方既白": {
                "位置": "天台", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "登记表的边角她要收着", "三个名字里第二个是她哥"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "叶暮": {
                "位置": "天台", "精神值": 51,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["沉默寡言", "数格子的人他看得出来", "纸上的印子他也要看"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"沈照": "东侧回廊"},
        "items": {},
        "changes": {
            "方既白": {"新增小任务": [{"目标": "问清那第三个人的名字是谁",
                                "属于大任务": "把走失的兄长从外地找回来",
                                "状态": "未完成"}]},
            "叶暮": {"位置": "天台楼梯间"},
        },
        "time": "13 分钟",
    },
    {
        "index": 200,
        "hero": "叶望舒",
        "scene": "古籍库",
        "people": {
            "叶望舒": {
                "位置": "古籍库", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["讲究次序", "偏旁少一点她也看得出", "换了灯芯要记在册子上"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "把三十七页削过的字逐页校出来", "状态": "未完成"}]},
            },
            "顾既白": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "原本才肯信", "差一笔也算差"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既白"],
        "hidden": {"方既白": "天台"},
        "items": {},
        "changes": {
            "叶望舒": {"完成任务": ["把三十七页削过的字逐页校出来"],
                     "新增小任务": [{"目标": "把清单另写一份锁在柜子里",
                                  "属于大任务": "弄清母亲改名换姓之前到底是谁",
                                  "状态": "未完成"}],
                     "解除个性": ["换了灯芯要记在册子上"]},
            "顾既白": {"新增外貌": ["上衣口袋里塞着一张折得很整齐的纸"]},
        },
        "time": "29 分钟",
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
