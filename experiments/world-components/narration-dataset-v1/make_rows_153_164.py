"""Rows 153-164: twelve more fabricated narration-dataset rows.

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
        "index": 153,
        "hero": "温暮",
        "scene": "缩微胶片室",
        "people": {
            "温暮": {
                "位置": "缩微胶片室", "精神值": 51,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "字号和行距她一眼看得出来", "对不完就后天"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清重排的那一版是谁做的", "状态": "未完成"}]},
            },
            "叶既明": {
                "位置": "缩微胶片室", "精神值": 48,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["嘴硬", "胶片室他一天来两趟", "两头对着查他肯干"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶既明"],
        "hidden": {"周书言": "庭院"},
        "items": {},
        "changes": {
            "温暮": {"完成任务": ["查清重排的那一版是谁做的"]},
            "叶既明": {"新增外貌": ["袖口沾了胶片的灰"]},
        },
        "time": "19 分钟",
    },
    {
        "index": 154,
        "hero": "方既白",
        "scene": "天台",
        "people": {
            "方既白": {
                "位置": "天台", "精神值": 52,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "她找了三年", "站一会儿就站两个钟头"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "叶暮": {
                "位置": "天台", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["沉默寡言", "后门那本簿子他翻过", "三月以后还有一次"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶暮"],
        "hidden": {"温暮": "缩微胶片室"},
        "items": {},
        "changes": {
            "方既白": {"精神值": 61},
        },
        "time": "12 分钟",
    },
    {
        "index": 155,
        "hero": "沈照",
        "scene": "东侧回廊",
        "people": {
            "沈照": {
                "位置": "东侧回廊", "精神值": 49,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "名单他一个不落", "换一个问法再问一遍"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "把当班名单上十一个人一个个问到", "状态": "未完成"}]},
            },
            "温暮": {
                "位置": "东侧回廊", "精神值": 52,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "每一个人说了什么她都记", "换个问法也要记"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "把当班名单上十一个人一个个问到", "状态": "未完成"}]},
            },
            "周书言": {
                "位置": "东侧回廊", "精神值": 54,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["心软", "第十一个人是她舅舅", "当面问才肯信"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "当面问舅舅那晚他到底在不在馆里", "状态": "未完成"}]},
            },
        },
        "also_present": ["温暮"],
        "hidden": {"方既白": "天台"},
        "items": {},
        "changes": {
            "周书言": {"位置": "庭院"},
            "温暮": {"完成任务": ["把当班名单上十一个人一个个问到"]},
            "东侧回廊": {"新增外貌": ["窗台上的名单被吹起一角，压着一支铅笔"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 156,
        "hero": "温既明",
        "scene": "报刊架后",
        "people": {
            "温既明": {
                "位置": "报刊架后", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "旧夹上刻的年份他一眼看得见", "刻字也要看"],
                "任务": {"大任务": {"目标": "查到九八年三月那一期的原件去向", "状态": "未完成"},
                       "小任务": []},
            },
            "叶既明": {
                "位置": "报刊架后", "精神值": 48,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["嘴硬", "旧夹他一只只对灯看", "刻的字他记住了"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清旧夹上那个顾字是谁刻的", "状态": "未完成"}]},
            },
        },
        "also_present": ["叶既明"],
        "hidden": {"沈照": "东侧回廊"},
        "items": {"报夹": {"位置": "报刊架后", "外貌": ["木夹断了一半", "夹口磨得发亮"]}},
        "changes": {
            "报夹": {"解除外貌": ["木夹断了一半"]},
            "叶既明": {"完成任务": ["查清旧夹上那个顾字是谁刻的"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 157,
        "hero": "韩照",
        "scene": "装订间",
        "people": {
            "韩照": {
                "位置": "装订间", "精神值": 49,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "盒子里的刀他一把把试", "开过刃的他要记下来"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "试出柜子里七把刀哪把最合手", "状态": "未完成"}]},
            },
            "叶照": {
                "位置": "装订间", "精神值": 47,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["心软", "磨过的痕她认得出来", "老手磨的刀她一眼看得见"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶照"],
        "hidden": {"温既明": "报刊架后"},
        "items": {},
        "changes": {
            "韩照": {"新增外貌": ["右手拇指上沾了磨刀的灰", "袖口上有一道新划的细口",
                              "虎口上贴着一小块胶布"],
                     "完成任务": ["试出柜子里七把刀哪把最合手"]},
            "装订间": {"新增外貌": ["柜子上摊着七把刀，刃口都朝上"]},
        },
        "time": "21 分钟",
    },
    {
        "index": 158,
        "hero": "秦暮",
        "scene": "报刊阅览室",
        "people": {
            "秦暮": {
                "位置": "报刊阅览室", "精神值": 52,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "缺的页要标出来", "补不上就空着"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把三本簿子缺的页数对出来", "状态": "未完成"}]},
            },
            "温知微": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "借出去过的书她要抄底", "少了的将来还能找"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温知微"],
        "hidden": {"韩照": "装订间"},
        "items": {},
        "changes": {
            "温知微": {"新增个性": ["把借出去过的簿子都先抄一份底"]},
            "秦暮": {"解除个性": ["补不上就空着"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 159,
        "hero": "柏书言",
        "scene": "报刊库",
        "people": {
            "柏书言": {
                "位置": "报刊库", "精神值": 51,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "封面新不新他一摸就知道", "七本的来路他要查清"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "查清那一批封面是从哪本书上撕的", "状态": "未完成"}]},
            },
            "苏既明": {
                "位置": "报刊库", "精神值": 50,
                "外貌": ["戴着一副圆框眼镜", "鞋面有一层土"],
                "个性": ["谨慎", "书脊上的字他一个个认", "也不见了就要去看"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏既明"],
        "hidden": {"秦暮": "报刊阅览室"},
        "items": {"合订本": {"位置": "报刊库", "外貌": ["封面换过了，胶还亮着", "书脊上原来的书名被磨掉了"]}},
        "changes": {
            "柏书言": {"完成任务": ["查清那一批封面是从哪本书上撕的"]},
            "合订本": {"解除外貌": ["书脊上原来的书名被磨掉了"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 160,
        "hero": "周书言",
        "scene": "庭院石阶",
        "people": {
            "周书言": {
                "位置": "庭院石阶", "精神值": 51,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["心软", "石阶的沟她要一条条抠", "多带一副手套"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "黎既白": {
                "位置": "庭院石阶", "精神值": 48,
                "外貌": ["指节上有旧伤", "衣角被雨打湿过"],
                "个性": ["心软", "三月她才来", "弄不完就弄到下雪"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎既白"],
        "hidden": {"柏书言": "报刊库"},
        "items": {},
        "changes": {
            "周书言": {"精神值": 63},
        },
        "time": "11 分钟",
    },
    {
        "index": 161,
        "hero": "韩照",
        "scene": "报刊库",
        "people": {
            "韩照": {
                "位置": "报刊库", "精神值": 48,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["沉默寡言", "合订本他一箱一箱数", "返潮的地方他要看"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"周书言": "庭院石阶"},
        "items": {},
        "changes": {
            "报刊库": {"新增外貌": ["墙角的水泥地返潮更深了，一直深到柜子底下",
                            "窗台上那盆吊兰的叶子黄了一半"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 162,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "借书卡上的字她要认", "两本并排放着看"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清那两本旧书是谁还回来的", "状态": "未完成"}]},
            },
            "方望舒": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "两本压在一起她也翻得出来", "卡片堆歪了要扶正"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "查清那两本旧书是谁还回来的", "状态": "未完成"}]},
            },
            "秦暮": {
                "位置": "借阅台", "精神值": 53,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["记性好", "门牌十九她刚查过", "跟着走出去不嫌远"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方望舒", "秦暮"],
        "hidden": {"韩照": "报刊库"},
        "items": {},
        "changes": {
            "叶含章": {"完成任务": ["查清那两本旧书是谁还回来的"]},
            "方望舒": {"完成任务": ["查清那两本旧书是谁还回来的"]},
            "秦暮": {"新增外貌": ["手指上沾了门牌上的灰"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 163,
        "hero": "苏既白",
        "scene": "水槽前",
        "people": {
            "苏既白": {
                "位置": "水槽前", "精神值": 53,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "管子坏了他自己紧", "拿东西要留条子"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "方望舒": {
                "位置": "水槽前", "精神值": 52,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "抹布归她管", "新管子也要问来路"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方望舒"],
        "hidden": {"叶含章": "借阅台"},
        "items": {},
        "changes": {
            "苏既白": {"解除个性": ["拿东西要留条子"],
                     "新增小任务": [{"目标": "把库房里剩下那几截旧管子按尺寸分开",
                                  "属于大任务": "找回被典当出去的那套医书",
                                  "状态": "未完成"}]},
            "水槽前": {"新增外貌": ["水槽底下那一截换成了新管子"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 164,
        "hero": "温暮",
        "scene": "二层走廊",
        "people": {
            "温暮": {
                "位置": "二层走廊", "精神值": 51,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "抄本和原本分开看", "各走各的她也不怕"],
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
        "hidden": {"苏既白": "水槽前"},
        "items": {},
        "changes": {
            "柏清和": {"位置": "借阅台"},
            "温暮": {"完成任务": ["把抄本和原本对一遍"]},
        },
        "time": "7 分钟",
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
