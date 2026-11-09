"""Rows 21-32: twelve more fabricated narration-dataset rows.

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
        "index": 21,
        "hero": "温砚",
        "scene": "报刊架后",
        "people": {
            "温砚": {
                "位置": "报刊架后", "精神值": 58,
                "外貌": ["袖口沾了墨", "头发用一根木簪别着"],
                "个性": ["好奇心重", "在报刊室做剪报，做了七年",
                       "和黎含章共事多年，替他保管过不少东西"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "黎含章": {
                "位置": "报刊架后", "精神值": 51,
                "外貌": ["戴着一副圆框眼镜", "围巾洗得发白"],
                "个性": ["沉默寡言", "哪一年的旧报堆在哪，他闭着眼能报出来",
                       "和温砚共事多年，从没跟她红过脸"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "把受潮的旧刊挑出来晾干", "状态": "未完成"}]},
            },
            "柏书言": {
                "位置": "报刊架后", "精神值": 63,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["嘴硬", "父亲当年是馆里的装订工", "不轻易答应人，答应了就不改口"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎含章", "柏书言"],
        "hidden": {"叶暮": "长桌区"},
        "items": {"报夹": {"位置": "报刊架后", "外貌": ["木夹断了一半", "夹口磨得发亮"]}},
        "changes": {
            "黎含章": {"完成任务": ["把受潮的旧刊挑出来晾干"],
                     "新增小任务": [{"目标": "找出被人撕掉的那一页",
                                  "属于大任务": "找到被族人藏起来的那本族谱原本",
                                  "状态": "未完成"}]},
            "柏书言": {"新增个性": ["答应把撕掉那一页的字抄一份给温砚"]},
            "报夹": {"解除外貌": ["木夹断了一半"], "新增外貌": ["换了新的木夹"]},
        },
        "time": "9 分钟",
    },
    {
        "index": 22,
        "hero": "韩砚",
        "scene": "一层走廊",
        "people": {
            "韩砚": {
                "位置": "一层走廊", "精神值": 63,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["谨慎", "夜里守门守了六年", "认得每一个半夜进馆的人"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "查访当年的门卫", "状态": "未完成"}]},
            },
            "黎停云": {
                "位置": "一层走廊", "精神值": 54,
                "外貌": ["围巾洗得发白", "衣角被雨打湿过"],
                "个性": ["心软", "妹妹走失那年她十九岁", "从不在走廊里多说话"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"温砚": "报刊库"},
        "items": {},
        "changes": {
            "黎停云": {"位置": "值班室"},
            "韩砚": {"精神值": 56},
            "一层走廊": {"新增外貌": ["墙上的告示掉了一角"]},
        },
        "time": "4 分钟",
    },
    {
        "index": 23,
        "hero": "方望舒",
        "scene": "长桌区",
        "people": {
            "方望舒": {
                "位置": "长桌区", "精神值": 60,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["讲究次序", "在这家馆做登记，做了五年", "不喜欢别人翻她理好的东西"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
            "沈既明": {
                "位置": "长桌区", "精神值": 49,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["执着", "认定十年前那场火灾不是意外", "从不把话说完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "翻看十年前的值班记录", "状态": "未完成"}]},
            },
            "温知微": {
                "位置": "长桌区", "精神值": 66,
                "外貌": ["围巾洗得发白", "衣角被雨打湿过"],
                "个性": ["记性好", "他父亲也是馆里的人", "认死理"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "未完成"}]},
            },
        },
        "also_present": ["沈既明", "温知微"],
        "hidden": {"韩砚": "一层走廊"},
        "items": {},
        "changes": {
            "沈既明": {"新增小任务": [{"目标": "问清配电间那晚跳闸的时间",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
            "温知微": {"完成任务": ["比对三份互相矛盾的登记簿"]},
            "方望舒": {"新增外貌": ["袖口沾了墨"]},
        },
        "time": "12 分钟",
    },
    {
        "index": 24,
        "hero": "顾既明",
        "scene": "天台",
        "people": {
            "顾既明": {
                "位置": "天台", "精神值": 52,
                "外貌": ["鞋面有一层土", "外套袖口磨破了"],
                "个性": ["护短", "父亲当年是馆里的夜班门卫", "从不信口头的话"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "黎书言": {
                "位置": "天台", "精神值": 57,
                "外貌": ["头发用一根木簪别着", "袖口沾了墨"],
                "个性": ["心软", "在装订间帮过工，知道旧账放在哪", "答应的事从不改口"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "翻看十年前的值班记录", "状态": "未完成"}]},
            },
        },
        "also_present": ["黎书言"],
        "hidden": {"韩暮": "天台楼梯间"},
        "items": {},
        "changes": {
            "黎书言": {"完成任务": ["翻看十年前的值班记录"],
                     "新增个性": ["把那一夜的记录抄了一份带在身上"]},
            "顾既明": {"精神值": 61},
            "天台": {"新增外貌": ["角落那副灯架被人搬走了，地上留着四个锈印"]},
        },
        "time": "7 分钟",
    },
    {
        "index": 25,
        "hero": "秦停云",
        "scene": "报刊库",
        "people": {
            "秦停云": {
                "位置": "报刊库", "精神值": 55,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["谨慎", "管着报刊库的钥匙", "从不把钥匙借人过夜"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
            "江照": {
                "位置": "报刊库", "精神值": 47,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "母亲改名换姓的事他从别人嘴里听过半句", "从不认自己记错事"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "找出被人撕掉的那一页", "状态": "未完成"}]},
            },
        },
        "also_present": ["江照"],
        "hidden": {"温知微": "长桌区"},
        "items": {"铁柜": {"位置": "报刊库", "外貌": ["柜门关不严，缝里塞着一张纸"]}},
        "changes": {
            "江照": {"解除个性": ["从不认自己记错事"],
                     "新增个性": ["承认那一年的月份他一直记错"]},
            "秦停云": {"新增小任务": [{"目标": "找出十年前十月以后那半年的出入签字",
                                  "属于大任务": "拿到能证明兄长清白的原始记录",
                                  "状态": "未完成"}]},
            "铁柜": {"解除外貌": ["柜门关不严，缝里塞着一张纸"],
                    "新增外貌": ["柜门关严了，缝里的纸取了出来"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 26,
        "hero": "程既明",
        "scene": "一层门厅",
        "people": {
            "程既明": {
                "位置": "一层门厅", "精神值": 62,
                "外貌": ["鞋面有一层土", "戴着一副圆框眼镜"],
                "个性": ["不爱欠人情", "在这家馆做前台，做了四年", "和谁都能说上两句"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "叶书言": {
                "位置": "一层门厅", "精神值": 58,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["讲究次序", "他管着门厅的钥匙", "不喜欢人多的时候说话"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "查访当年的门卫", "状态": "未完成"}]},
            },
            "黎暮": {
                "位置": "一层门厅", "精神值": 45,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["沉默寡言", "从后门进出惯了", "认定十年前那场火灾不是意外"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
            "方含章": {
                "位置": "一层门厅", "精神值": 69,
                "外貌": ["袖口沾了墨", "衣角被雨打湿过"],
                "个性": ["好奇心重", "她只管告示牌那一面墙", "听人说话的时候不出声"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶书言", "黎暮", "方含章"],
        "hidden": {"秦停云": "报刊库"},
        "items": {"告示牌": {"位置": "一层门厅", "外貌": ["玻璃碎了一角"]}},
        "changes": {
            "叶书言": {"完成任务": ["查访当年的门卫"]},
            "黎暮": {"新增个性": ["答应把后门那把钥匙配一把给程既明"]},
            "告示牌": {"解除外貌": ["玻璃碎了一角"], "新增外貌": ["换了新玻璃"]},
        },
        "time": "6 分钟",
    },
    {
        "index": 27,
        "hero": "柏照",
        "scene": "地下书库",
        "people": {
            "柏照": {
                "位置": "地下书库", "精神值": 44,
                "外貌": ["围巾洗得发白", "鞋面有一层土"],
                "个性": ["心软", "在地下库待了十年", "闻不得霉味，却一直没走"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
            "温既明": {
                "位置": "地下书库", "精神值": 56,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["记性好", "哪一年的旧报堆在哪，他闭着眼能报出来", "认死理"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": [{"目标": "把受潮的旧刊挑出来晾干", "状态": "未完成"}]},
            },
        },
        "also_present": ["温既明"],
        "hidden": {"方含章": "一层门厅"},
        "items": {},
        "changes": {
            "温既明": {"完成任务": ["把受潮的旧刊挑出来晾干"],
                     "新增小任务": [{"目标": "找出被人撕掉的那一页",
                                  "属于大任务": "找到被族人藏起来的那本族谱原本",
                                  "状态": "未完成"}]},
            "柏照": {"新增个性": ["答应陪温既明把剩下两垛解完"]},
            "地下书库": {"新增外貌": ["除湿机的水桶满了，水漫到了地上"]},
        },
        "time": "15 分钟",
    },
    {
        "index": 28,
        "hero": "顾含章",
        "scene": "窗边",
        "people": {
            "顾含章": {
                "位置": "窗边", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "指节上有旧伤"],
                "个性": ["谨慎", "夜里值班，白天补觉", "话少，但记得住别人说过的话"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
            "苏暮": {
                "位置": "窗边", "精神值": 61,
                "外貌": ["袖口沾了墨", "围巾洗得发白"],
                "个性": ["嘴硬", "父亲当年是馆里的装订工", "不喝别人倒的水"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["苏暮"],
        "hidden": {"柏照": "地下书库"},
        "items": {},
        "changes": {
            "窗边": {"新增外貌": ["窗台上的搪瓷杯少了一只"]},
            "苏暮": {"新增个性": ["答应把那只杯子赔给顾含章"]},
            "顾含章": {"精神值": 57},
        },
        "time": "5 分钟",
    },
    {
        "index": 29,
        "hero": "韩照",
        "scene": "古籍库",
        "people": {
            "韩照": {
                "位置": "古籍库", "精神值": 53,
                "外貌": ["外套袖口磨破了", "戴着一副圆框眼镜"],
                "个性": ["执着", "父亲当年是馆里的古籍修复工", "记东西只写不记"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "翻检古籍库的出入签字", "状态": "未完成"}]},
            },
            "秦暮": {
                "位置": "古籍库", "精神值": 59,
                "外貌": ["鞋面有一层土", "衣角被雨打湿过"],
                "个性": ["讲究次序", "两把钥匙里她管着一把", "从不替人说情"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "找出十年前十月以后那半年的出入签字", "状态": "未完成"}]},
            },
        },
        "also_present": ["秦暮"],
        "hidden": {"顾含章": "窗边"},
        "items": {},
        "changes": {
            "秦暮": {"完成任务": ["找出十年前十月以后那半年的出入签字"],
                     "新增小任务": [{"目标": "核对那半年的签字是不是同一个人的笔迹",
                                  "属于大任务": "拿到能证明兄长清白的原始记录",
                                  "状态": "未完成"}]},
            "韩照": {"完成任务": ["翻检古籍库的出入签字"]},
            "古籍库": {"新增外貌": ["库门内侧的挂钩上挂着两把钥匙"]},
        },
        "time": "18 分钟",
    },
    {
        "index": 30,
        "hero": "沈清和",
        "scene": "馆外街道",
        "people": {
            "沈清和": {
                "位置": "馆外街道", "精神值": 49,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["沉默寡言", "从后门进出惯了，不想让人看见", "认定十年前那场火灾不是意外"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "柏砚": {
                "位置": "门卫岗亭", "精神值": 55,
                "外貌": ["外套袖口磨破了", "鞋面有一层土"],
                "个性": ["嘴硬", "在这座岗亭坐了六年", "和后门的锁匠熟"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["柏砚"],
        "hidden": {"韩照": "古籍库"},
        "items": {"门牌": {"位置": "馆外街道", "外貌": ["馆名的漆掉了一半"]}},
        "changes": {
            "柏砚": {"位置": "馆外街道"},
            "沈清和": {"新增小任务": [{"目标": "问清后门那把锁是哪一年换的",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
            "门牌": {"解除外貌": ["馆名的漆掉了一半"], "新增外貌": ["馆名重新描过"]},
        },
        "time": "3 分钟",
    },
    {
        "index": 31,
        "hero": "叶暮",
        "scene": "装订间",
        "people": {
            "叶暮": {
                "位置": "装订间", "精神值": 46,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["沉默寡言", "在这间装订间干了二十六年", "只肯用手工裁纸"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"沈清和": "馆外街道"},
        "items": {},
        "changes": {
            "叶暮": {"新增外貌": ["指节上贴了一块胶布"]},
            "装订间": {"新增外貌": ["胶锅里的浆糊熬开了，锅边糊了一圈"]},
        },
        "time": "22 分钟",
    },
    {
        "index": 32,
        "hero": "周望舒",
        "scene": "东侧回廊",
        "people": {
            "周望舒": {
                "位置": "东侧回廊", "精神值": 47,
                "外貌": ["戴着一副圆框眼镜", "指节上有旧伤"],
                "个性": ["护短", "妹妹走失那年他二十二岁", "陪人查案子，从不催"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "柏停云": {
                "位置": "东侧回廊", "精神值": 56,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["好奇心重", "父亲当年是馆里的夜班门卫", "认定那场火灾不是意外"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "问清配电间那晚跳闸的时间", "状态": "未完成"}]},
            },
        },
        "also_present": ["柏停云"],
        "hidden": {"叶暮": "装订间"},
        "items": {},
        "changes": {
            "周望舒": {"精神值": 55,
                     "新增个性": ["决定明年还在这家馆等下去"]},
            "柏停云": {"解除个性": ["认定那场火灾不是意外"],
                     "新增个性": ["不敢再确定那场火是不是意外"]},
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
