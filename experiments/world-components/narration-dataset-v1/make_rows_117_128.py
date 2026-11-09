"""Rows 117-128: twelve more fabricated narration-dataset rows.

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
        "index": 117,
        "hero": "秦既明",
        "scene": "报刊库",
        "people": {
            "秦既明": {
                "位置": "报刊库", "精神值": 48,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "他查了六年", "查到了反而不知道交给谁"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清十月十七日那三天的闭馆通告", "状态": "未完成"}]},
            },
            "温照": {
                "位置": "报刊库", "精神值": 53,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["沉默寡言", "合订本他一箱一箱搬", "写下来的东西要留三份"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温照"],
        "hidden": {"方望舒": "装订间"},
        "items": {},
        "changes": {
            "秦既明": {"完成任务": ["查清十年前那场火灾是谁放的火",
                              "查清十月十七日那三天的闭馆通告"],
                     "新增小任务": [{"目标": "把查到的事分三份写清楚存起来",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
            "温照": {"精神值": 58},
        },
        "time": "24 分钟",
    },
    {
        "index": 118,
        "hero": "方既白",
        "scene": "借阅台",
        "people": {
            "方既白": {
                "位置": "借阅台", "精神值": 56,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["谨慎", "借书先看扉页", "不是它说自己是的那个东西就不借"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "程既明": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["不爱欠人情", "卡片上的字写得慢", "答应天天等"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": [{"目标": "查清这一批里还有几本换过书名", "状态": "未完成"}]},
            },
        },
        "also_present": ["程既明"],
        "hidden": {"秦既明": "报刊库"},
        "items": {},
        "changes": {
            "程既明": {"解除个性": ["答应天天等", "卡片上的字写得慢"],
                     "新增个性": ["把查到的事都写在本子上"]},
            "方既白": {"精神值": 60},
        },
        "time": "11 分钟",
    },
    {
        "index": 119,
        "hero": "周含章",
        "scene": "长桌区",
        "people": {
            "周含章": {
                "位置": "长桌区", "精神值": 52,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["执着", "簿子她按年份排", "查不到就不肯一人收手"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清那半年四次换门卫的交接记录", "状态": "未完成"}]},
            },
            "柏含章": {
                "位置": "长桌区", "精神值": 50,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["护短", "签字是他一个个抄下来的", "签字总得有个去处"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"方既白": "借阅台"},
        "items": {},
        "changes": {
            "周含章": {"完成任务": ["查清那半年四次换门卫的交接记录"]},
            "柏含章": {"位置": "报刊库"},
        },
        "time": "13 分钟",
    },
    {
        "index": 120,
        "hero": "苏既明",
        "scene": "水槽前",
        "people": {
            "苏既明": {
                "位置": "水槽前", "精神值": 53,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "管子坏了他自己紧", "手蹭破了也不说"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "秦暮": {
                "位置": "水槽前", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "抹布归她管", "手破了就要包"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦暮"],
        "hidden": {"周含章": "长桌区"},
        "items": {},
        "changes": {
            "苏既明": {"精神值": 58,
                     "新增外貌": ["右手手背上包着一小块布条"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 121,
        "hero": "温既明",
        "scene": "报刊架后",
        "people": {
            "温既明": {
                "位置": "报刊架后", "精神值": 51,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "报夹上刻的年份他一眼看得见", "新夹子太新他要查"],
                "任务": {"大任务": {"目标": "查到九八年三月那一期的原件去向", "状态": "未完成"},
                       "小任务": []},
            },
            "叶既明": {
                "位置": "报刊架后", "精神值": 49,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["嘴硬", "架子上有几只旧夹他数得清", "刻痕浅就要对着灯看"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶既明"],
        "hidden": {"苏既明": "水槽前"},
        "items": {"报夹": {"位置": "报刊架后", "外貌": ["木夹断了一半", "夹口磨得发亮"]},
                  "合订本": {"位置": "报刊架后", "外貌": ["封皮被翻过来压在底下"]}},
        "changes": {
            "报夹": {"解除外貌": ["木夹断了一半"], "新增外貌": ["换成了一副新的铜夹"]},
            "合订本": {"新增外貌": ["封皮重新翻正了，书名朝外"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 122,
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
            "韩照": {
                "位置": "古籍库", "精神值": 52,
                "外貌": ["戴着一副圆框眼镜", "围巾洗得发白"],
                "个性": ["执着", "刀背刮过的地方他要指出来", "原本才肯信"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["韩照"],
        "hidden": {"温既明": "报刊架后"},
        "items": {},
        "changes": {
            "叶暮": {"新增小任务": [{"目标": "找出这一本的原本放在柜子哪一格",
                                "属于大任务": "替死去的搭档报仇",
                                "状态": "未完成"},
                             {"目标": "把被刀背刮掉的那个字补出来",
                                "属于大任务": "替死去的搭档报仇",
                                "状态": "未完成"}]},
            "古籍库": {"新增外貌": ["木架上多了一盏带罩的油灯"]},
        },
        "time": "19 分钟",
    },
    {
        "index": 123,
        "hero": "顾既明",
        "scene": "地下书库",
        "people": {
            "顾既明": {
                "位置": "地下书库", "精神值": 55,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "湿了的书他当天就要摊开", "那晚的事他不肯说"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "周书言": {
                "位置": "地下书库", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "坏掉的书她一册一册记", "少了的将来还能去找"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "把这一箱里坏掉的册子逐本记下来", "状态": "未完成"}]},
            },
        },
        "also_present": ["周书言"],
        "hidden": {"叶暮": "古籍库"},
        "items": {},
        "changes": {
            "顾既明": {"精神值": 41},
            "周书言": {"完成任务": ["把这一箱里坏掉的册子逐本记下来"]},
            "地下书库": {"新增外貌": ["除湿机停了，屋里安静得能听见灯管"]},
        },
        "time": "21 分钟",
    },
    {
        "index": 124,
        "hero": "苏望舒",
        "scene": "报刊阅览室",
        "people": {
            "苏望舒": {
                "位置": "报刊阅览室", "精神值": 52,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["讲究次序", "裁口直不直她一眼看得出来", "透过来能认的字她抄下来"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把被裁掉那一列的日期认出来", "状态": "未完成"}]},
            },
            "秦照": {
                "位置": "报刊阅览室", "精神值": 48,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["执着", "三指宽的口子他要量准", "抄下来的东西一定留着"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦照"],
        "hidden": {"顾既明": "地下书库"},
        "items": {},
        "changes": {
            "苏望舒": {"完成任务": ["把被裁掉那一列的日期认出来"]},
            "报刊阅览室": {"新增外貌": ["只开了一半的灯，另一半说是省电"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 125,
        "hero": "叶含章",
        "scene": "古籍库",
        "people": {
            "叶含章": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "削过的字她一眼看得出来", "猜的不算数"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "用原本把削掉的字校出来", "状态": "未完成"}]},
            },
            "温照": {
                "位置": "古籍库", "精神值": 54,
                "外貌": ["袖口沾了墨", "围巾洗得发白"],
                "个性": ["沉默寡言", "原本在柜子里他去取", "抄下来的纸他随身带着"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温照"],
        "hidden": {"苏望舒": "报刊阅览室"},
        "items": {"校样": {"位置": "古籍库", "外貌": ["纸边被削过，削得笔直", "第九页边上重新描过字"]}},
        "changes": {
            "叶含章": {"完成任务": ["用原本把削掉的字校出来"]},
            "校样": {"解除外貌": ["第九页边上重新描过字"],
                    "新增外貌": ["第九页补回了两行字，笔迹跟原本一致"]},
            "古籍库": {"新增外貌": ["柜子最里面那格空了，原本取了出来"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 126,
        "hero": "沈照",
        "scene": "东侧回廊",
        "people": {
            "沈照": {
                "位置": "东侧回廊", "精神值": 50,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "名单上十一个人他问到底", "问法不对就换个问法"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "把当班名单上十一个人一个个问到", "状态": "未完成"}]},
            },
            "温暮": {
                "位置": "东侧回廊", "精神值": 49,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "每一个人说了什么她都记", "记错一个字要重记"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "周书言": {
                "位置": "东侧回廊", "精神值": 53,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["心软", "第十一个人是她舅舅", "当面问才肯信"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "当面问舅舅那晚他到底在不在馆里", "状态": "未完成"}]},
            },
        },
        "also_present": ["温暮", "周书言"],
        "hidden": {"叶含章": "古籍库"},
        "items": {},
        "changes": {
            "温暮": {"解除个性": ["记错一个字要重记"],
                    "新增个性": ["把名单上的回答按人记在本子上"]},
            "周书言": {"解除个性": ["当面问才肯信"],
                     "新增个性": ["不敢再确定舅舅说的是真话"]},
            "沈照": {"新增外貌": ["名单的边角已经被翻得起了毛"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 127,
        "hero": "方望舒",
        "scene": "装订间",
        "people": {
            "方望舒": {
                "位置": "装订间", "精神值": 49,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["沉默寡言", "二十多年没数错过一次", "刀不快就磨到快"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"沈照": "东侧回廊", "温暮": "东侧回廊"},
        "items": {},
        "changes": {
            "方望舒": {"解除个性": ["刀不快就磨到快"],
                     "新增个性": ["决定把柜子里那盒旧刀具重新挑一把"]},
        },
        "time": "25 分钟",
    },
    {
        "index": 128,
        "hero": "秦既白",
        "scene": "后门",
        "people": {
            "秦既白": {
                "位置": "后门", "精神值": 52,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["谨慎", "后门他值了六年夜班", "门闩多年不插今天插上了"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "查清站在门口那半个钟头的人是谁", "状态": "未完成"}]},
            },
            "黎照": {
                "位置": "后门", "精神值": 51,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "见过三个拿着纸来找他的人", "不肯让人一个人待在后门"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"方望舒": "装订间"},
        "items": {},
        "changes": {
            "黎照": {"位置": "馆外街道"},
            "秦既白": {"完成任务": ["查清站在门口那半个钟头的人是谁"]},
        },
        "time": "8 分钟",
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
