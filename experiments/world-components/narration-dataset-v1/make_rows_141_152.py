"""Rows 141-152: twelve more fabricated narration-dataset rows.

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
        "index": 141,
        "hero": "秦照",
        "scene": "报刊阅览室",
        "people": {
            "秦照": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["执着", "三本对完才说话", "被撕下来的纸他不肯丢"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "把三本簿子缺的页数对出来", "状态": "未完成"}]},
            },
            "温暮": {
                "位置": "报刊阅览室", "精神值": 53,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "簿子她一本本翻", "撕痕要看方向"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温暮"],
        "hidden": {"秦既明": "报刊库"},
        "items": {},
        "changes": {
            "秦照": {"完成任务": ["把三本簿子缺的页数对出来"]},
            "报刊阅览室": {"新增外貌": ["桌面擦过了，茶渍淡了一层", "桌角压着一张被撕下来的纸"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 142,
        "hero": "叶望舒",
        "scene": "古籍库",
        "people": {
            "叶望舒": {
                "位置": "古籍库", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "袖口沾了墨"],
                "个性": ["讲究次序", "字号大小她一比比得出来", "削过的地方她要数清"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "数清这一批校样里被削过的页", "状态": "未完成"}]},
            },
            "顾既白": {
                "位置": "古籍库", "精神值": 47,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["嘴硬", "搬书他一人顶两个", "削和写不是一个人他看得出来"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把削过的三十七页逐页登记", "状态": "未完成"}]},
            },
        },
        "also_present": ["顾既白"],
        "hidden": {"秦照": "报刊阅览室"},
        "items": {},
        "changes": {
            "顾既白": {"精神值": 41,
                     "新增小任务": [{"目标": "找出补字的人换过几次笔",
                                  "属于大任务": "查明族谱被谁抄走了一份",
                                  "状态": "未完成"}]},
            "叶望舒": {"完成任务": ["数清这一批校样里被削过的页"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 143,
        "hero": "方望舒",
        "scene": "装订间",
        "people": {
            "方望舒": {
                "位置": "装订间", "精神值": 48,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["沉默寡言", "二十多年没数错过一次", "刀不快就磨到快"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"叶望舒": "古籍库", "顾既白": "古籍库"},
        "items": {},
        "changes": {
            "方望舒": {"新增外貌": ["右手虎口上沾了磨刀的灰"]},
        },
        "time": "24 分钟",
    },
    {
        "index": 144,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 52,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "还书箱每天早上都要翻", "纸条上的地址她要记"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清那本借了四十年的书是谁还回来的", "状态": "未完成"}]},
            },
            "方望舒": {
                "位置": "借阅台", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "走之前不问清就不舒服", "一个人也敢去"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "秦暮": {
                "位置": "借阅台", "精神值": 55,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["记性好", "队尾那个人她记住了", "两个人一起走才安心"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "查清巷子里门牌十九那户住的是谁", "状态": "未完成"}]},
            },
        },
        "also_present": ["方望舒", "秦暮"],
        "hidden": {"韩照": "报刊库"},
        "items": {},
        "changes": {
            "叶含章": {"完成任务": ["查清那本借了四十年的书是谁还回来的"]},
            "秦暮": {"完成任务": ["查清巷子里门牌十九那户住的是谁"]},
            "借阅台": {"新增外貌": ["台面上留着一张写着地址的纸条"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 145,
        "hero": "柏书言",
        "scene": "报刊库",
        "people": {
            "柏书言": {
                "位置": "报刊库", "精神值": 51,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "封面的胶新不新他一摸就知道", "七本封面新的他数过"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "查清那一批封面是从哪本书上撕的", "状态": "未完成"}]},
            },
            "苏既明": {
                "位置": "报刊库", "精神值": 49,
                "外貌": ["戴着一副圆框眼镜", "鞋面有一层土"],
                "个性": ["谨慎", "夹在书里的纸他一张张抽", "书名对不上就要写下来"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏既明"],
        "hidden": {"叶含章": "借阅台"},
        "items": {"合订本": {"位置": "报刊库", "外貌": ["封面是新的，胶还亮着"]}},
        "changes": {
            "合订本": {"新增外貌": ["封面夹层里塞着两张旧封面的残页", "书脊上原来的书名被磨掉了"]},
            "柏书言": {"完成任务": ["查清那一批封面是从哪本书上撕的"]},
        },
        "time": "17 分钟",
    },
    {
        "index": 146,
        "hero": "周既白",
        "scene": "二层西侧书架",
        "people": {
            "周既白": {
                "位置": "二层西侧书架", "精神值": 50,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["执着", "夹在书里的纸她要翻到背面", "空了的位置她不填"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "按那张纸上的索书号把十一本找齐", "状态": "未完成"}]},
            },
            "柏清和": {
                "位置": "二层西侧书架", "精神值": 48,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["心软", "书他一本本归位", "夹纸的人他知道不简单"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["柏清和"],
        "hidden": {"柏书言": "报刊库"},
        "items": {},
        "changes": {
            "周既白": {"完成任务": ["按那张纸上的索书号把十一本找齐"],
                     "解除个性": ["空了的位置她不填"],
                     "新增个性": ["承认第七本是被她父亲借走的"]},
            "柏清和": {"精神值": 53},
        },
        "time": "16 分钟",
    },
    {
        "index": 147,
        "hero": "温暮",
        "scene": "长桌区",
        "people": {
            "温暮": {
                "位置": "二层走廊", "精神值": 52,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "抄本和原本她要分开看", "各走各的她也不怕"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "柏清和": {
                "位置": "借阅台", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["心软", "抄错一个字要重抄", "原本他放回原处"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把抄本和原本对一遍", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"周既白": "二层西侧书架"},
        "items": {},
        "changes": {
            "温暮": {"位置": "长桌区"},
            "柏清和": {"位置": "长桌区"},
        },
        "time": "5 分钟",
    },
    {
        "index": 148,
        "hero": "周既白",
        "scene": "配电间",
        "people": {
            "周既白": {
                "位置": "配电间", "精神值": 54,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["好奇心重", "铜丝绕闸刀这种手段她要记下来", "不肯说的事往往就是知道的事"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清这一路电是谁接的", "状态": "未完成"}]},
            },
            "江既白": {
                "位置": "配电间", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["谨慎", "闸刀拉过几次他要数", "断了又合上一定有原因"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["江既白"],
        "hidden": {"温暮": "长桌区"},
        "items": {},
        "changes": {
            "周既白": {"精神值": 46,
                     "完成任务": ["查清这一路电是谁接的"]},
            "配电间": {"新增外貌": ["箱底有一截剪断的铜丝"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 149,
        "hero": "方清和",
        "scene": "茶水间",
        "people": {
            "方清和": {
                "位置": "茶水间", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["记性好", "半年的登记簿她核完了", "代签的笔迹她不放过"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "核清那半年谁的名字是代签的", "状态": "未完成"}]},
            },
            "苏书言": {
                "位置": "茶水间", "精神值": 54,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["不爱欠人情", "烧了十年锅炉", "原本一动就没人认"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏书言"],
        "hidden": {"周既白": "配电间"},
        "items": {"水壶": {"位置": "茶水间", "外貌": ["壶底的水垢结得很厚"]}},
        "changes": {
            "茶水间": {"新增外貌": ["窗上的水汽结了一层，看不见院子"]},
            "水壶": {"新增外貌": ["壶嘴边上磕掉了一小块"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 150,
        "hero": "周书言",
        "scene": "报刊架后",
        "people": {
            "周书言": {
                "位置": "报刊架后", "精神值": 50,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["心软", "合订本她按年排", "装反的封皮就要翻过来"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "温砚": {
                "位置": "报刊架后", "精神值": 52,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["讲究次序", "传书传得比谁都快", "装反的东西他一眼看见"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "查清七九年那本报为什么装反了封皮", "状态": "未完成"}]},
            },
            "苏望舒": {
                "位置": "报刊架后", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "戴着一副圆框眼镜"],
                "个性": ["心软", "窄道里她总能挤出办法", "排成一列往外传"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "秦照": {
                "位置": "报刊架后", "精神值": 48,
                "外貌": ["外套袖口磨破了", "衣角被雨打湿过"],
                "个性": ["执着", "他站最外面", "每一本都要看一眼"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温砚", "苏望舒", "秦照"],
        "hidden": {"方清和": "茶水间"},
        "items": {},
        "changes": {
            "温砚": {"完成任务": ["查清七九年那本报为什么装反了封皮"]},
            "周书言": {"新增外貌": ["手背上压出一道红印"]},
            "苏望舒": {"精神值": 60},
        },
        "time": "13 分钟",
    },
    {
        "index": 151,
        "hero": "叶暮",
        "scene": "古籍库",
        "people": {
            "叶暮": {
                "位置": "古籍库", "精神值": 47,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "拆过的书她一眼认得出来", "油灯要挪近才看得清"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"周书言": "报刊架后", "温砚": "报刊架后"},
        "items": {},
        "changes": {
            "叶暮": {"新增个性": ["决定把这一本原样留着不动"]},
        },
        "time": "22 分钟",
    },
    {
        "index": 152,
        "hero": "秦既明",
        "scene": "报刊库",
        "people": {
            "秦既明": {
                "位置": "报刊库", "精神值": 49,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "查了六年", "查到了要给该知道的人"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清十月十七日那三天的闭馆通告", "状态": "未完成"}]},
            },
            "温照": {
                "位置": "报刊库", "精神值": 52,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["沉默寡言", "写下来的东西要留三份", "箱子盖他一定盖严"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温照"],
        "hidden": {"叶暮": "古籍库"},
        "items": {},
        "changes": {
            "秦既明": {"完成任务": ["查清十年前那场火灾是谁放的火",
                              "查清十月十七日那三天的闭馆通告"]},
            "温照": {"精神值": 58},
        },
        "time": "25 分钟",
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
