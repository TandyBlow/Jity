"""Rows 57-68: twelve more fabricated narration-dataset rows.

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
        "index": 57,
        "hero": "温砚",
        "scene": "报刊架后",
        "people": {
            "温砚": {
                "位置": "报刊架后", "精神值": 55,
                "外貌": ["袖口沾了墨", "头发用一根木簪别着"],
                "个性": ["好奇心重", "她在报刊室做剪报，做了七年", "架子歪了就要修"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "黎含章": {
                "位置": "报刊架后", "精神值": 49,
                "外貌": ["戴着一副圆框眼镜", "围巾洗得发白"],
                "个性": ["沉默寡言", "旧报堆在哪他闭着眼能报出来", "架子的事他早说过一次"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "把歪了的报刊架调直", "状态": "未完成"}]},
            },
            "柏书言": {
                "位置": "报刊架后", "精神值": 60,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["嘴硬", "父亲当年是馆里的装订工", "答应了就不改口"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "沈含章": {
                "位置": "报刊架后", "精神值": 52,
                "外貌": ["袖口沾了墨", "外套袖口磨破了"],
                "个性": ["讲究次序", "他管着架子底下的砖", "垫不平就不算完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎含章", "柏书言", "沈含章"],
        "hidden": {"苏既白": "二层走廊"},
        "items": {"报夹": {"位置": "报刊架后", "外貌": ["木夹断了一半", "夹口磨得发亮"]}},
        "changes": {
            "黎含章": {"完成任务": ["把歪了的报刊架调直"]},
            "沈含章": {"新增个性": ["答应替黎含章找一块一样的砖"]},
            "柏书言": {"精神值": 64},
            "报夹": {"解除外貌": ["木夹断了一半"], "新增外貌": ["换了一副铜夹"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 58,
        "hero": "沈含章",
        "scene": "长桌区",
        "people": {
            "沈含章": {
                "位置": "长桌区", "精神值": 57,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["沉默寡言", "他收长桌区的报，收了九年", "收完最后一张才关灯"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"温砚": "报刊架后", "黎含章": "报刊架后"},
        "items": {},
        "changes": {
            "沈含章": {"精神值": 51},
            "长桌区": {"新增外貌": ["第二张长桌上的光退到地上，茶渍看得更清了"]},
        },
        "time": "8 分钟",
    },
    {
        "index": 59,
        "hero": "黎望舒",
        "scene": "缩微胶片室",
        "people": {
            "黎望舒": {
                "位置": "缩微胶片室", "精神值": 58,
                "外貌": ["头发用一根木簪别着", "袖口沾了墨"],
                "个性": ["谨慎", "两台机器哪台响得重她听得出来", "版面上的小字她一眼看得见"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "韩既明": {
                "位置": "缩微胶片室", "精神值": 63,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["执着", "父亲那晚在这间屋里值班", "认定父亲没说过真话以外的话"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": []},
            },
            "沈叙白": {
                "位置": "缩微胶片室", "精神值": 50,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["心软", "管胶片室管了九年", "见不得人一个人待着不说话"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["韩既明", "沈叙白"],
        "hidden": {"柏书言": "报刊架后"},
        "items": {},
        "changes": {
            "韩既明": {"精神值": 44},
            "沈叙白": {"精神值": 56},
            "缩微胶片室": {"新增外貌": ["两台机器的防尘布都收了起来，搭在椅背上"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 60,
        "hero": "叶既白",
        "scene": "三层走廊",
        "people": {
            "叶既白": {
                "位置": "三层走廊", "精神值": 54,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["讲究次序", "走廊上哪盏灯坏了她记得清", "换灯泡不肯等人扶"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": []},
            },
            "苏既明": {
                "位置": "三层走廊", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["嘴硬", "他这副眼镜是父亲配的", "十一年没换过"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏既明"],
        "hidden": {"沈含章": "长桌区"},
        "items": {},
        "changes": {
            "苏既明": {"解除外貌": ["戴着一副圆框眼镜"],
                     "新增外貌": ["换了一副金属细框的眼镜"]},
            "叶既白": {"精神值": 57},
        },
        "time": "9 分钟",
    },
    {
        "index": 61,
        "hero": "周既白",
        "scene": "庭院",
        "people": {
            "周既白": {
                "位置": "庭院", "精神值": 52,
                "外貌": ["鞋面有一层土", "头发用一根木簪别着"],
                "个性": ["心软", "她找了兄长三年", "落叶扫不完就不扫了"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "温照": {
                "位置": "庭院", "精神值": 57,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "他在院子里挖过两回地", "埋着的东西不肯乱动"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "周含章": {
                "位置": "庭院", "精神值": 48,
                "外貌": ["围巾洗得发白", "指节上有旧伤"],
                "个性": ["执着", "她查了十年的值班记录", "查到了反倒不知道该做什么"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温照", "周含章"],
        "hidden": {"苏既明": "三层走廊"},
        "items": {},
        "changes": {
            "周既白": {"解除个性": ["落叶扫不完就不扫了"],
                     "新增个性": ["决定明年春天再来扫一次"]},
            "温照": {"解除个性": ["埋着的东西不肯乱动"],
                    "新增个性": ["把挖出来的那把钥匙交了出去"]},
            "周含章": {"精神值": 55},
        },
        "time": "11 分钟",
    },
    {
        "index": 62,
        "hero": "柏清和",
        "scene": "报刊阅览室",
        "people": {
            "柏清和": {
                "位置": "报刊阅览室", "精神值": 56,
                "外貌": ["戴着一副圆框眼镜", "头发用一根木簪别着"],
                "个性": ["记性好", "她在这间屋子里看了六年报", "两个月份对不上就不放过"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
            "叶既明": {
                "位置": "报刊阅览室", "精神值": 53,
                "外貌": ["袖口沾了墨", "外套袖口磨破了"],
                "个性": ["讲究次序", "他管阅览室的镇纸", "见不得人在报上折角"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "秦书言": {
                "位置": "报刊阅览室", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "鞋面有一层土"],
                "个性": ["心软", "母亲那晚也在馆里", "把母亲的事说了出来"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "韩望舒": {
                "位置": "报刊阅览室", "精神值": 47,
                "外貌": ["指节上有旧伤", "围巾洗得发白"],
                "个性": ["嘴硬", "父亲那晚当班", "想找个人把父亲那晚的事说清楚"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶既明", "秦书言", "韩望舒"],
        "hidden": {"周既白": "庭院"},
        "items": {},
        "changes": {
            "叶既明": {"新增小任务": [{"目标": "把七八年的报和重排版逐份对照",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
            "秦书言": {"新增外貌": ["袖口沾了报上的油墨"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 63,
        "hero": "秦照",
        "scene": "旧刊堆放区",
        "people": {
            "秦照": {
                "位置": "旧刊堆放区", "精神值": 48,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["执着", "旧刊垛是他一垛一垛解开的", "缺角的地方要对得上"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"柏清和": "报刊阅览室"},
        "items": {"麻绳": {"位置": "旧刊堆放区", "外貌": ["勒出的印子还在", "绳头散开了一股"]}},
        "changes": {
            "旧刊堆放区": {"新增外貌": ["灯全亮了，纸垛的影子排得整整齐齐"]},
            "麻绳": {"解除外貌": ["绳头散开了一股"], "新增外貌": ["绳头重新编过，扎得很紧"]},
        },
        "time": "20 分钟",
    },
    {
        "index": 64,
        "hero": "方书言",
        "scene": "门卫岗亭",
        "people": {
            "方书言": {
                "位置": "门卫岗亭", "精神值": 49,
                "外貌": ["围巾洗得发白", "衣角被雨打湿过"],
                "个性": ["嘴硬", "她在岗亭坐了六年", "账上画钩的规矩她认得"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "查清中间半个月替班的人是谁", "状态": "未完成"}]},
            },
            "顾书言": {
                "位置": "门卫岗亭", "精神值": 51,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["谨慎", "岗亭里的东西他一件件数过", "看字先看笔迹"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾书言"],
        "hidden": {"秦照": "旧刊堆放区"},
        "items": {"电暖器": {"位置": "门卫岗亭", "外貌": ["铁皮壳上有两块烤黄的印子"]}},
        "changes": {
            "方书言": {"完成任务": ["查清中间半个月替班的人是谁"]},
            "顾书言": {"精神值": 57,
                     "新增个性": ["答应去查那十七个钩是谁画的"]},
            "电暖器": {"新增外貌": ["底下垫了一块砖，壳子不再烫地砖了"]},
        },
        "time": "11 分钟",
    },
    {
        "index": 65,
        "hero": "苏既白",
        "scene": "水槽前",
        "people": {
            "苏既白": {
                "位置": "水槽前", "精神值": 53,
                "外貌": ["袖口沾了墨", "鞋面有一层土"],
                "个性": ["沉默寡言", "水管坏了都是他自己修", "拧不紧就再拧一圈"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "秦暮": {
                "位置": "水槽前", "精神值": 58,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "水槽下面垫的抹布归她管", "水不放干不放心"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦暮"],
        "hidden": {"方书言": "门卫岗亭"},
        "items": {},
        "changes": {
            "苏既白": {"新增外貌": ["袖口湿了半截"]},
            "水槽前": {"新增外貌": ["水槽底下的抹布叠成了两层，压着一只扳手"]},
        },
        "time": "6 分钟",
    },
    {
        "index": 66,
        "hero": "叶望舒",
        "scene": "二层西侧书架",
        "people": {
            "叶望舒": {
                "位置": "二层西侧书架", "精神值": 55,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["谨慎", "书脊上的号和扉页的章她都要对一遍", "贴过的号她认得出来"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "把这一排书脊上的号全抄下来", "状态": "未完成"}]},
            },
            "顾既白": {
                "位置": "二层西侧书架", "精神值": 54,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["嘴硬", "他搬书搬了十年", "手背上的口子从来不管"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
            "温照": {
                "位置": "二层西侧书架", "精神值": 59,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["记性好", "他抄号抄得慢，抄得准", "对不上就回去重抄"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾既白", "温照"],
        "hidden": {"苏既白": "水槽前"},
        "items": {},
        "changes": {
            "叶望舒": {"完成任务": ["把这一排书脊上的号全抄下来"]},
            "顾既白": {"新增外貌": ["手背上那道口子结了痂"]},
            "温照": {"精神值": 51},
        },
        "time": "16 分钟",
    },
    {
        "index": 67,
        "hero": "秦既白",
        "scene": "后门",
        "people": {
            "秦既白": {
                "位置": "后门", "精神值": 50,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["谨慎", "他在后门值了六年夜班", "门闩多年不插，今天插上了"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
            "黎照": {
                "位置": "后门", "精神值": 53,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "见过三个拿着纸来找他的人", "不肯让人一个人待在后门"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"叶望舒": "二层西侧书架"},
        "items": {},
        "changes": {
            "黎照": {"位置": "馆外街道"},
            "秦既白": {"新增个性": ["决定夜里把后门的门闩插上"]},
            "后门": {"新增外貌": ["门轴上过油了，开的时候不响了"]},
        },
        "time": "7 分钟",
    },
    {
        "index": 68,
        "hero": "沈照",
        "scene": "东侧回廊",
        "people": {
            "沈照": {
                "位置": "东侧回廊", "精神值": 47,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "名单上十一个人他问了九个", "问不到就不算完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "把当班名单上十一个人一个个问到", "状态": "未完成"}]},
            },
            "温暮": {
                "位置": "东侧回廊", "精神值": 54,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "她替沈照记每一个人说了什么", "记错一个字就要重记"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "周书言": {
                "位置": "东侧回廊", "精神值": 56,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["心软", "她抄名单抄了半年", "第十一个人要自己去问"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "当面问舅舅那晚他到底在不在馆里", "状态": "未完成"}]},
            },
        },
        "also_present": ["温暮", "周书言"],
        "hidden": {"秦既白": "后门"},
        "items": {},
        "changes": {
            "周书言": {"完成任务": ["当面问舅舅那晚他到底在不在馆里"],
                     "新增小任务": [{"目标": "把舅舅的回答一字不差记下来",
                                  "属于大任务": "把走失的兄长从外地找回来",
                                  "状态": "未完成"}]},
            "温暮": {"新增外貌": ["手指上沾了铅笔灰"]},
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
