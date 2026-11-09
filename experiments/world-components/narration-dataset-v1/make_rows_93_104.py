"""Rows 93-104: twelve more fabricated narration-dataset rows.

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
        "index": 93,
        "hero": "秦既明",
        "scene": "报刊阅览室",
        "people": {
            "秦既明": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "他把三份登记簿对了一夜", "对上了才肯说"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "把后门那十一次签字对出来", "状态": "未完成"}]},
            },
            "叶照": {
                "位置": "报刊阅览室", "精神值": 49,
                "外貌": ["指节上有旧伤", "围巾洗得发白"],
                "个性": ["沉默寡言", "父亲那半年在门房", "看见笔画的起头就知道是谁写的"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶照"],
        "hidden": {"方既明": "门卫岗亭"},
        "items": {},
        "changes": {
            "秦既明": {"完成任务": ["把后门那十一次签字对出来"]},
            "叶照": {"精神值": 42},
            "报刊阅览室": {"新增外貌": ["桌角放着一盏没开的台灯"]},
        },
        "time": "21 分钟",
    },
    {
        "index": 94,
        "hero": "沈清和",
        "scene": "装订间",
        "people": {
            "沈清和": {
                "位置": "装订间", "精神值": 52,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "她在这馆里六年，只会搬书", "要学就学到底"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "苏望舒": {
                "位置": "装订间", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["讲究次序", "包边的手艺她学了十一年", "教人只示范三遍"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把这批散线的书都包一遍", "状态": "未完成"}]},
            },
        },
        "also_present": ["苏望舒"],
        "hidden": {"秦既明": "报刊阅览室"},
        "items": {},
        "changes": {
            "沈清和": {"新增外貌": ["手心上全是浆糊", "袖口沾了浆糊的干痕"],
                     "新增个性": ["决定每天来学半个钟头包边"]},
            "苏望舒": {"新增个性": ["答应明天让沈清和上第四本"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 95,
        "hero": "周既白",
        "scene": "地下书库",
        "people": {
            "周既白": {
                "位置": "地下书库", "精神值": 48,
                "外貌": ["外套袖口磨破了", "围巾洗得发白"],
                "个性": ["谨慎", "封皮和内容对不上她一眼看得出来", "拆了才肯下结论"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "柏书言": {
                "位置": "地下书库", "精神值": 53,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["护短", "这一排架子归他管", "不拆永远是猜的"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "拆开第七本往后那几本换过封皮的书", "状态": "未完成"}]},
            },
        },
        "also_present": ["柏书言"],
        "hidden": {"沈清和": "装订间"},
        "items": {},
        "changes": {
            "柏书言": {"解除外貌": ["指节上有旧伤", "袖口沾了墨"]},
            "周既白": {"精神值": 44},
            "地下书库": {"新增外貌": ["最里面那排架子照不到，两盏灯只开了一半"]},
        },
        "time": "19 分钟",
    },
    {
        "index": 96,
        "hero": "黎书言",
        "scene": "报刊架后",
        "people": {
            "黎书言": {
                "位置": "报刊架后", "精神值": 51,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["心软", "合订本她按年排", "看见装反的封皮就要翻过来"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
            "温既明": {
                "位置": "报刊架后", "精神值": 47,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["记性好", "七九年的报只剩一本", "装反的东西他一眼看见"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "查清七九年那本报为什么装反了封皮", "状态": "未完成"}]},
            },
            "苏望舒": {
                "位置": "报刊架后", "精神值": 56,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["不爱欠人情", "窄道里她总能挤出办法", "传书传得比谁都快"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温既明", "苏望舒"],
        "hidden": {"周既白": "地下书库"},
        "items": {},
        "changes": {
            "黎书言": {"新增外貌": ["手背上压出一道红印", "袖口沾了合订本的灰"]},
            "温既明": {"新增个性": ["决定把那一本单独放一个架子"]},
            "苏望舒": {"精神值": 61},
        },
        "time": "11 分钟",
    },
    {
        "index": 97,
        "hero": "方既白",
        "scene": "庭院",
        "people": {
            "方既白": {
                "位置": "庭院", "精神值": 46,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "她在这馆里待了三年", "想走又不敢走"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "沈叙白": {
                "位置": "庭院", "精神值": 49,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["护短", "他手里一直压着一张纸", "怕人走了就再也不回来"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清三月以后那次签字是不是同一个人的手", "状态": "未完成"}]},
            },
            "秦照": {
                "位置": "庭院", "精神值": 52,
                "外貌": ["袖口沾了墨", "围巾洗得发白"],
                "个性": ["执着", "她扫院子扫了三年", "话不多，记得住日子"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["沈叙白", "秦照"],
        "hidden": {"黎书言": "报刊架后"},
        "items": {},
        "changes": {
            "方既白": {"解除个性": ["想走又不敢走"],
                     "新增个性": ["决定把三月以后那次签字查清再走"]},
            "沈叙白": {"新增外貌": ["袖口上沾了一点炉灰"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 98,
        "hero": "韩照",
        "scene": "报刊库",
        "people": {
            "韩照": {
                "位置": "报刊库", "精神值": 49,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["沉默寡言", "报刊库的合订本他一册一册数", "窗子关着就不开"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"方既白": "庭院", "沈叙白": "庭院"},
        "items": {"搪瓷杯": {"位置": "报刊库", "外貌": ["杯口有个缺口", "杯底剩了一点水"]}},
        "changes": {
            "报刊库": {"新增外貌": ["墙角的水泥地返潮，颜色比别处深"]},
            "搪瓷杯": {"解除外貌": ["杯底剩了一点水"], "新增外貌": ["杯底干了，桌面上留了一圈印子"]},
        },
        "time": "17 分钟",
    },
    {
        "index": 99,
        "hero": "叶望舒",
        "scene": "借阅台",
        "people": {
            "叶望舒": {
                "位置": "借阅台", "精神值": 54,
                "外貌": ["袖口沾了墨", "头发用一根木簪别着"],
                "个性": ["讲究次序", "还回来的书她要先看卡片", "借了四十年的书也要登记"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "查清那本借了四十年的书是谁还回来的", "状态": "未完成"}]},
            },
            "程既明": {
                "位置": "借阅台", "精神值": 51,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["谨慎", "还书箱每天早上一开他就看", "看见陌生的字要抄下来"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["程既明"],
        "hidden": {"韩照": "报刊库"},
        "items": {},
        "changes": {
            "叶望舒": {"完成任务": ["查清那本借了四十年的书是谁还回来的"]},
            "程既明": {"新增外貌": ["指节上沾了一点印泥"]},
            "借阅台": {"新增外貌": ["铜灯换了个新罩子，光比从前亮"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 100,
        "hero": "温暮",
        "scene": "借阅台",
        "people": {
            "温暮": {
                "位置": "二层走廊", "精神值": 53,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "她抱着本子走路", "话不多，问得准"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "柏清和": {
                "位置": "借阅台", "精神值": 55,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["心软", "存根她按日子排", "替人跑一趟不嫌远"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "查清换过号的那几本书被谁借走过", "状态": "未完成"}]},
            },
        },
        "also_present": [],
        "hidden": {"叶望舒": "报刊阅览室"},
        "items": {},
        "changes": {
            "温暮": {"位置": "借阅台"},
            "柏清和": {"位置": "长桌区"},
        },
        "time": "4 分钟",
    },
    {
        "index": 101,
        "hero": "顾照",
        "scene": "配电间",
        "people": {
            "顾照": {
                "位置": "配电间", "精神值": 58,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["谨慎", "闸刀响不响他听得出来", "没告诉过他的配电处他一定要找"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "找出馆里另一处配电的地方", "状态": "未完成"}]},
            },
            "苏既白": {
                "位置": "配电间", "精神值": 54,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["执着", "线路图他描过三遍", "墙里有声音他就贴上去听"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏既白"],
        "hidden": {"温暮": "借阅台"},
        "items": {},
        "changes": {
            "顾照": {"精神值": 57},
        },
        "time": "8 分钟",
    },
    {
        "index": 102,
        "hero": "韩照",
        "scene": "古籍库",
        "people": {
            "韩照": {
                "位置": "古籍库", "精神值": 52,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["执着", "三本对一遍才肯下结论", "缺字的地方他补"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "把三本缺页的书对照补字", "状态": "未完成"}]},
            },
            "周书言": {
                "位置": "古籍库", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["记性好", "她那一本的第十一页是完整的", "念出来不差分毫"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "把三本缺页的书对照补字", "状态": "未完成"}]},
            },
            "温照": {
                "位置": "古籍库", "精神值": 55,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["沉默寡言", "他那一本不缺页但连着不通", "少了半句就要说出来"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "把三本缺页的书对照补字", "状态": "未完成"}]},
            },
        },
        "also_present": ["周书言", "温照"],
        "hidden": {"顾照": "配电间"},
        "items": {},
        "changes": {
            "韩照": {"完成任务": ["把三本缺页的书对照补字"]},
            "周书言": {"完成任务": ["把三本缺页的书对照补字"]},
            "温照": {"完成任务": ["把三本缺页的书对照补字"]},
        },
        "time": "23 分钟",
    },
    {
        "index": 103,
        "hero": "苏既白",
        "scene": "水槽前",
        "people": {
            "苏既白": {
                "位置": "水槽前", "精神值": 53,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "管子坏了他自己紧", "紧不住就等报修"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "方望舒": {
                "位置": "水槽前", "精神值": 51,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["嘴硬", "漏一次她擦一次", "不肯等人来修"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["方望舒"],
        "hidden": {"韩照": "古籍库"},
        "items": {},
        "changes": {
            "方望舒": {"解除个性": ["不肯等人来修"],
                     "新增个性": ["决定明天去报修换管子"]},
            "水槽前": {"新增外貌": ["地砖上有一摊水，一直没干"]},
        },
        "time": "9 分钟",
    },
    {
        "index": 104,
        "hero": "方既明",
        "scene": "门卫岗亭",
        "people": {
            "方既明": {
                "位置": "门卫岗亭", "精神值": 52,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["谨慎", "值班表他揭下来看", "问不到就不算完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清十月十七日那一格的字是谁写的", "状态": "未完成"}],},
            },
            "秦照": {
                "位置": "门卫岗亭", "精神值": 50,
                "外貌": ["袖口沾了墨", "围巾洗得发白"],
                "个性": ["心软", "她记得住日子", "看着人一个人硬撑就难受"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦照"],
        "hidden": {"苏既白": "水槽前"},
        "items": {"值班表": {"位置": "门卫岗亭", "外貌": ["被暖器烤得卷了边", "玻璃上结着雾"]}},
        "changes": {
            "方既明": {"完成任务": ["查清十月十七日那一格的字是谁写的"],
                     "新增小任务": [{"目标": "找到写那一格字的人当面问",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}],
                     "新增个性": ["学会先问一个人不在哪儿"]},
            "秦照": {"精神值": 55},
            "值班表": {"解除外貌": ["被暖器烤得卷了边"], "新增外貌": ["重新压平了，四个角用胶带粘住"]},
        },
        "time": "14 分钟",
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
