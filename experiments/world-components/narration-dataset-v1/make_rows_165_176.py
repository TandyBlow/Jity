"""Rows 165-176: twelve more fabricated narration-dataset rows.

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
        "index": 165,
        "hero": "秦照",
        "scene": "报刊阅览室",
        "people": {
            "秦照": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["执着", "修过的纸边他一眼看得出来", "问之前先把东西收好"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清那二十二页是谁修过边", "状态": "未完成"}]},
            },
            "温暮": {
                "位置": "报刊阅览室", "精神值": 52,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "刀口和印刷的边她分得清", "问之前先想好问什么"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温暮"],
        "hidden": {"叶照": "装订间"},
        "items": {},
        "changes": {
            "秦照": {"完成任务": ["查清那二十二页是谁修过边"]},
            "报刊阅览室": {"新增外貌": ["长桌上三本簿子摞齐，压着镇纸", "靠窗那一排椅子摆得整整齐齐"]},
        },
        "time": "17 分钟",
    },
    {
        "index": 166,
        "hero": "柏书言",
        "scene": "报刊库",
        "people": {
            "柏书言": {
                "位置": "报刊库", "精神值": 48,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "六年在等有人来问", "空位上的灰他摸得出新旧"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
            "苏既明": {
                "位置": "报刊库", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "鞋面有一层土"],
                "个性": ["谨慎", "钥匙有几把他记得清", "话不能说得太快"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏既明"],
        "hidden": {"秦照": "报刊阅览室"},
        "items": {},
        "changes": {
            "柏书言": {"精神值": 40,
                     "新增个性": ["决定不再等，直接去问馆长那把钥匙"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 167,
        "hero": "温暮",
        "scene": "东侧回廊",
        "people": {
            "温暮": {
                "位置": "东侧回廊", "精神值": 51,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "黑也要摸墙过去", "记的时候一个字不差"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "周书言": {
                "位置": "东侧回廊", "精神值": 47,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["心软", "想听他自己说", "不肯让人陪着去"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "当面问舅舅那晚他到底在不在馆里", "状态": "未完成"}]},
            },
        },
        "also_present": ["周书言"],
        "hidden": {"柏书言": "报刊库"},
        "items": {},
        "changes": {
            "周书言": {"解除个性": ["不肯让人陪着去"],
                     "新增个性": ["决定明天当面问舅舅，问完就写下来"]},
            "温暮": {"解除个性": ["记的时候一个字不差"],
                    "新增个性": ["记的时候先记他说不出来的那部分"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 168,
        "hero": "叶望舒",
        "scene": "古籍库",
        "people": {
            "叶望舒": {
                "位置": "古籍库", "精神值": 49,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["讲究次序", "空出来的格她要摸一遍", "封蜡她认得"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清那一格原本被谁借走", "状态": "未完成"}]},
            },
            "顾既白": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "柜子最里头他也要摸一遍", "蜡是从哪儿掉的他要问"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既白"],
        "hidden": {"温暮": "东侧回廊"},
        "items": {"封条": {"位置": "古籍库", "外貌": ["蜡印完整，压着一个篆字"]}},
        "changes": {
            "封条": {"新增外貌": ["蜡印缺了一小块，缺口是新的"]},
            "古籍库": {"新增外貌": ["柜子最上面那一格空着，格底有一小块蜡"]},
            "顾既白": {"新增个性": ["摸到的东西一定要指给人看"]},
        },
        "time": "22 分钟",
    },
    {
        "index": 169,
        "hero": "秦既明",
        "scene": "报刊库",
        "people": {
            "秦既明": {
                "位置": "报刊库", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "查了六年", "查到了就给该知道的人"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清十月十七日那三天的闭馆通告", "状态": "未完成"}]},
            },
            "温照": {
                "位置": "报刊库", "精神值": 53,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["沉默寡言", "箱子盖他一定盖严", "写下来的东西要留三份"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温照"],
        "hidden": {"叶望舒": "古籍库"},
        "items": {},
        "changes": {
            "秦既明": {"完成任务": ["查清十年前那场火灾是谁放的火"]},
        },
        "time": "27 分钟",
    },
    {
        "index": 170,
        "hero": "叶含章",
        "scene": "借阅台",
        "people": {
            "叶含章": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "外套袖口磨破了"],
                "个性": ["谨慎", "四十年才回来的书不外借", "卡片边缘磨圆了她要记"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查清那本借了四十年的书是谁还回来的", "状态": "未完成"}]},
            },
            "方望舒": {
                "位置": "借阅台", "精神值": 49,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "天黑了也敢去", "要走的人她想去看看"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"秦既明": "报刊库"},
        "items": {},
        "changes": {
            "叶含章": {"完成任务": ["查清那本借了四十年的书是谁还回来的"]},
            "方望舒": {"位置": "馆外街道"},
        },
        "time": "11 分钟",
    },
    {
        "index": 171,
        "hero": "温暮",
        "scene": "缩微胶片室",
        "people": {
            "温暮": {
                "位置": "缩微胶片室", "精神值": 50,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "标签贴了几层她看得出", "胶片没重绕就是没动过内容"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清这一卷胶片为什么换过三次标签", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"叶含章": "借阅台", "方望舒": "馆外街道"},
        "items": {},
        "changes": {
            "温暮": {"解除个性": ["胶片没重绕就是没动过内容"]},
        },
        "time": "26 分钟",
    },
    {
        "index": 172,
        "hero": "周书言",
        "scene": "庭院石阶",
        "people": {
            "周书言": {
                "位置": "庭院石阶", "精神值": 52,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["心软", "沟她要一级一级抠", "登记簿上的字她记得"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "查清登记簿上三月那个名字是不是她哥", "状态": "未完成"}]},
            },
            "黎既白": {
                "位置": "庭院石阶", "精神值": 49,
                "外貌": ["指节上有旧伤", "衣角被雨打湿过"],
                "个性": ["心软", "她五月才来", "手套舍不得用新的"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎既白"],
        "hidden": {"温暮": "缩微胶片室"},
        "items": {},
        "changes": {
            "周书言": {"完成任务": ["查清登记簿上三月那个名字是不是她哥"],
                     "新增小任务": [{"目标": "找出五月以后登记簿上是谁替她哥签的字",
                                  "属于大任务": "把走失的兄长从外地找回来",
                                  "状态": "未完成"},
                                {"目标": "问清黎既白五月来的时候见过谁",
                                  "属于大任务": "把走失的兄长从外地找回来",
                                  "状态": "未完成"}]},
        },
        "time": "18 分钟",
    },
    {
        "index": 173,
        "hero": "柏照",
        "scene": "地下书库",
        "people": {
            "柏照": {
                "位置": "地下书库", "精神值": 47,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["心软", "那一套他数过十一册", "加加减减他记得住"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "把那一套医书剩下几册点清", "状态": "未完成"}]},
            },
            "苏含章": {
                "位置": "地下书库", "精神值": 50,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "扫帚他不肯借人", "空位上的灰他摸得出"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "查清少掉的五册是谁搬走的", "状态": "未完成"}]},
            },
            "韩照": {
                "位置": "地下书库", "精神值": 51,
                "外貌": ["指节上有旧伤", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "霉味他闻得出新旧", "书脊上的薄霉他看得清"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏含章", "韩照"],
        "hidden": {"周书言": "庭院石阶"},
        "items": {},
        "changes": {
            "柏照": {"精神值": 39,
                     "完成任务": ["把那一套医书剩下几册点清"]},
            "苏含章": {"完成任务": ["查清少掉的五册是谁搬走的"]},
            "地下书库": {"新增外貌": ["第三排架子上的书脊都覆着一层薄霉"]},
        },
        "time": "24 分钟",
    },
    {
        "index": 174,
        "hero": "方既白",
        "scene": "天台",
        "people": {
            "方既白": {
                "位置": "天台", "精神值": 48,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "站一会儿就站两个钟头", "冷也不肯下去"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "叶暮": {
                "位置": "天台", "精神值": 51,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["沉默寡言", "后门那本簿子他翻过", "三月以后还有一次"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"柏照": "地下书库"},
        "items": {},
        "changes": {
            "叶暮": {"位置": "天台楼梯间"},
            "方既白": {"精神值": 43,
                     "新增外貌": ["手指冻得发红，指尖有点僵"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 175,
        "hero": "温既明",
        "scene": "报刊架后",
        "people": {
            "温既明": {
                "位置": "报刊架后", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "空出来的位置他要数", "门没关就要去看"],
                "任务": {"大任务": {"目标": "查到九八年三月那一期的原件去向", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"方既白": "天台楼梯间"},
        "items": {},
        "changes": {
            "报刊架后": {"新增外貌": ["窗开了一条缝，报页被风吹得轻响"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 176,
        "hero": "韩照",
        "scene": "装订间",
        "people": {
            "韩照": {
                "位置": "装订间", "精神值": 48,
                "外貌": ["指节上有旧伤", "袖口沾了墨"],
                "个性": ["沉默寡言", "十捆纸边他一捆捆捆好", "刀背的印他认得"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清十捆纸边里哪几捆被人翻过", "状态": "未完成"}]},
            },
            "叶照": {
                "位置": "装订间", "精神值": 49,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["心软", "刀用过又放回去她看得出来", "纸边的记号她一个个对"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶照"],
        "hidden": {"温既明": "报刊架后", "方既白": "天台楼梯间"},
        "items": {},
        "changes": {
            "韩照": {"完成任务": ["查清十捆纸边里哪几捆被人翻过"]},
            "叶照": {"新增外貌": ["围裙前襟上沾了一点胶"]},
        },
        "time": "19 分钟",
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
