"""Rows 177-188: twelve more fabricated narration-dataset rows.

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
        "index": 177,
        "hero": "秦既明",
        "scene": "报刊库",
        "people": {
            "秦既明": {
                "位置": "报刊库", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "查了六年", "写下来的东西一行都不省"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清十月十七日那三天的闭馆通告", "状态": "未完成"}]},
            },
            "温照": {
                "位置": "报刊库", "精神值": 53,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["沉默寡言", "写下来的东西要留三份", "寄出去的那份他要亲自投"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温照"],
        "hidden": {"韩照": "旧刊堆放区"},
        "items": {},
        "changes": {
            "秦既明": {"完成任务": ["查清十年前那场火灾是谁放的火",
                              "查清十月十七日那三天的闭馆通告"]},
            "温照": {"新增小任务": [{"目标": "把写好的那份送到报馆去",
                                "属于大任务": "找回被典当出去的那套医书",
                                "状态": "未完成"}]},
        },
        "time": "26 分钟",
    },
    {
        "index": 178,
        "hero": "江既白",
        "scene": "配电间",
        "people": {
            "江既白": {
                "位置": "配电间", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["谨慎", "螺丝他一颗一颗拧", "划痕的方向他要看"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"秦既明": "报刊库", "温照": "报刊库"},
        "items": {},
        "changes": {
            "江既白": {"新增外貌": ["手指上沾了一点黑", "袖口蹭了一道灰"]},
        },
        "time": "21 分钟",
    },
    {
        "index": 179,
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
                "位置": "水槽前", "精神值": 49,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "旧管子她按尺寸分", "写两份才放心"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "把库房剩下的旧管子按尺寸分开", "状态": "未完成"}]},
            },
        },
        "also_present": ["黎既白"],
        "hidden": {"江既白": "配电间"},
        "items": {},
        "changes": {
            "苏既白": {"完成任务": ["把水槽底下那一截锈管换掉"],
                     "精神值": 58},
            "黎既白": {"完成任务": ["把库房剩下的旧管子按尺寸分开"],
                     "精神值": 55},
            "水槽前": {"新增外貌": ["水槽底下那一截换成了新管子，接头上留着扳手压出的痕"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 180,
        "hero": "叶望舒",
        "scene": "古籍库",
        "people": {
            "叶望舒": {
                "位置": "古籍库", "精神值": 48,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["讲究次序", "封蜡她认得", "印碎了一半她也要认出来"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "认出封蜡上那个篆字是哪一半", "状态": "未完成"}]},
            },
            "顾既白": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "揭过封条的人他不放过", "篆字他一个也不认识"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既白"],
        "hidden": {"苏既白": "水槽前"},
        "items": {"封条": {"位置": "古籍库", "外貌": ["蜡印完整，压着一个篆字", "贴在柜门内侧"]}},
        "changes": {
            "封条": {"解除外貌": ["蜡印完整，压着一个篆字"],
                    "新增外貌": ["蜡印缺了一小块，缺口是新的"]},
            "叶望舒": {"完成任务": ["认出封蜡上那个篆字是哪一半"]},
        },
        "time": "23 分钟",
    },
    {
        "index": 181,
        "hero": "周既白",
        "scene": "二层西侧书架",
        "people": {
            "周既白": {
                "位置": "二层西侧书架", "精神值": 49,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["执着", "空了的位置她不填", "两个人核快一半"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "按那张纸上的索书号把十一本找齐", "状态": "未完成"}]},
            },
            "柏清和": {
                "位置": "二层西侧书架", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["心软", "书他一本本归位", "夹纸的人他知道不简单"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["柏清和"],
        "hidden": {"叶望舒": "古籍库"},
        "items": {},
        "changes": {
            "周既白": {"完成任务": ["按那张纸上的索书号把十一本找齐"],
                     "新增个性": ["决定这一排自己一排一排核"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 182,
        "hero": "温暮",
        "scene": "二层走廊",
        "people": {
            "温暮": {
                "位置": "二层走廊", "精神值": 51,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "抄本和原本分开看", "先对完再说"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "把抄本和原本对一遍", "状态": "未完成"}]},
            },
            "柏清和": {
                "位置": "二层走廊", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["心软", "原本他带在身上三个月", "抄错的地方他自己也不知道"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"周既白": "二层西侧书架"},
        "items": {},
        "changes": {
            "柏清和": {"位置": "长桌区"},
            "温暮": {"精神值": 46},
        },
        "time": "8 分钟",
    },
    {
        "index": 183,
        "hero": "秦暮",
        "scene": "报刊阅览室",
        "people": {
            "秦暮": {
                "位置": "报刊阅览室", "精神值": 52,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "后补的页她一眼看得出来", "手抖过的字她要重认"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把三本簿子缺的页数对出来", "状态": "未完成"}]},
            },
            "温知微": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "纸的白她比得出来", "挤在一起的字她要看清"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温知微"],
        "hidden": {"温暮": "二层走廊"},
        "items": {},
        "changes": {
            "秦暮": {"完成任务": ["把三本簿子缺的页数对出来"],
                     "解除个性": ["手抖过的字她要重认", "后补的页她一眼看得出来"],
                     "新增个性": ["补页的人当时有人在等，这件事她记住了"]},
        },
        "time": "19 分钟",
    },
    {
        "index": 184,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "还书箱每天早上都要翻", "墨没干的字她不敢碰"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清那张纸条是谁放进去的", "状态": "未完成"}]},
            },
            "秦暮": {
                "位置": "借阅台", "精神值": 53,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["记性好", "笔帽没盖的人她记得", "队尾那个人她记住了"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦暮"],
        "hidden": {"秦既明": "报刊库"},
        "items": {},
        "changes": {
            "叶含章": {"完成任务": ["查清那张纸条是谁放进去的"]},
            "借阅台": {"新增外貌": ["台面上那张纸条的墨还没干透"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 185,
        "hero": "周书言",
        "scene": "庭院石阶",
        "people": {
            "周书言": {
                "位置": "庭院石阶", "精神值": 51,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["心软", "沟她要一级一级抠", "多带一副手套"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "黎既白": {
                "位置": "庭院石阶", "精神值": 50,
                "外貌": ["指节上有旧伤", "衣角被雨打湿过"],
                "个性": ["心软", "存水结冰要滑人", "手套舍不得用新的"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "柏书言": {
                "位置": "庭院石阶", "精神值": 47,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "沟的坡度他看得出", "最上面那一级他自己弄"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "查清最上面那一级的沟是谁后挖的", "状态": "未完成"}]},
            },
        },
        "also_present": ["黎既白", "柏书言"],
        "hidden": {"叶含章": "借阅台"},
        "items": {},
        "changes": {
            "柏书言": {"完成任务": ["查清最上面那一级的沟是谁后挖的"],
                     "精神值": 52},
            "周书言": {"新增外貌": ["手套上沾了一层湿泥"]},
        },
        "time": "22 分钟",
    },
    {
        "index": 186,
        "hero": "秦既白",
        "scene": "后门",
        "people": {
            "秦既白": {
                "位置": "后门", "精神值": 52,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["谨慎", "后门他值了六年夜班", "铜锈的方向他要看"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "查清站在门后锁门的人是谁", "状态": "未完成"}]},
            },
            "黎照": {
                "位置": "后门", "精神值": 50,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "见过三个拿着纸来找他的人", "不肯让人一个人待在后门"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"周书言": "庭院石阶"},
        "items": {},
        "changes": {
            "秦既白": {"精神值": 34},
            "后门": {"新增外貌": ["门锁的锁孔边蹭掉了一小块漆"]},
        },
        "time": "17 分钟",
    },
    {
        "index": 187,
        "hero": "韩照",
        "scene": "旧刊堆放区",
        "people": {
            "韩照": {
                "位置": "旧刊堆放区", "精神值": 48,
                "外貌": ["指节上有旧伤", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "绳结的打法他一眼看得出来", "剪过的地方他要量"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"秦既白": "后门"},
        "items": {"报捆": {"位置": "旧刊堆放区", "外貌": ["麻绳勒出的印子很深", "绳结是右撇子打的"]}},
        "changes": {
            "报捆": {"解除外貌": ["绳结是右撇子打的"],
                    "新增外貌": ["绳结是左撇子打的，绳头压在下面绕了两圈"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 188,
        "hero": "柏书言",
        "scene": "报刊库",
        "people": {
            "柏书言": {
                "位置": "报刊库", "精神值": 49,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "六年在等有人来问", "抄过一遍的东西他记得"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "查清那一批封面是从哪本书上撕的", "状态": "未完成"}]},
            },
            "苏既明": {
                "位置": "报刊库", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "鞋面有一层土"],
                "个性": ["谨慎", "扉页上的印子他要对", "查完了就该有个说法"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清那批封面的来路", "状态": "未完成"}]},
            },
        },
        "also_present": ["苏既明"],
        "hidden": {"韩照": "旧刊堆放区"},
        "items": {},
        "changes": {
            "柏书言": {"完成任务": ["查清那一批封面是从哪本书上撕的"],
                     "新增小任务": [{"目标": "把抄下来的那份签字交出去",
                                  "属于大任务": "替死去的搭档报仇",
                                  "状态": "未完成"}]},
            "苏既明": {"完成任务": ["查清那批封面的来路"]},
        },
        "time": "24 分钟",
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
