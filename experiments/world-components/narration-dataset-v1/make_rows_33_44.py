"""Rows 33-44: twelve more fabricated narration-dataset rows.

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
        "index": 33,
        "hero": "沈叙白",
        "scene": "缩微胶片室",
        "people": {
            "沈叙白": {
                "位置": "缩微胶片室", "精神值": 51,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["谨慎", "管缩微胶片室管了九年", "不喜欢别人自己摇机器"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
            "闻照": {
                "位置": "缩微胶片室", "精神值": 49,
                "外貌": ["戴着一副圆框眼镜", "鞋面有一层土"],
                "个性": ["执着", "父亲当年也在馆里当班", "认定那场火灾不是意外",
                       "从不肯在别人面前把话说完"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "找出十月十七日那一夜的签字", "状态": "未完成"}]},
            },
        },
        "also_present": ["闻照"],
        "hidden": {"方清和": "茶水间"},
        "items": {"胶卷盒": {"位置": "缩微胶片室", "外貌": ["盖子扣不严，边上磕了一道"]}},
        "changes": {
            "闻照": {"完成任务": ["查清十年前那场火灾是谁放的火", "找出十月十七日那一夜的签字"],
                     "解除个性": ["从不肯在别人面前把话说完"],
                     "新增个性": ["知道了是谁放的火，反而一个字也不敢说出去"]},
            "沈叙白": {"精神值": 44},
            "胶卷盒": {"解除外貌": ["盖子扣不严，边上磕了一道"],
                    "新增外貌": ["换了个新盒盖，扣上时有一声脆响"]},
        },
        "time": "16 分钟",
    },
    {
        "index": 34,
        "hero": "方既白",
        "scene": "天台楼梯间",
        "people": {
            "方既白": {
                "位置": "天台楼梯间", "精神值": 68,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["心软", "兄长走失那年她十六岁", "看见刻在墙上的字会站很久"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
            "黎含英": {
                "位置": "天台", "精神值": 55,
                "外貌": ["围巾洗得发白", "袖口沾了墨"],
                "个性": ["沉默寡言", "在这座馆守了十一年楼梯", "记得每一级台阶哪块松"],
                "任务": {"大任务": {"目标": "把被典当出去的那套医书赎回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"沈叙白": "缩微胶片室"},
        "items": {},
        "changes": {
            "方既白": {"精神值": 53},
            "黎含英": {"位置": "天台楼梯间"},
            "天台楼梯间": {"新增外貌": ["墙上一行刻字的下半截被磨掉了"]},
        },
        "time": "6 分钟",
    },
    {
        "index": 35,
        "hero": "叶望舒",
        "scene": "报刊库",
        "people": {
            "叶望舒": {
                "位置": "报刊库", "精神值": 57,
                "外貌": ["袖口沾了墨", "戴着一副圆框眼镜"],
                "个性": ["讲究次序", "剪报册是她一本一本贴的", "不替人遮掩"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": [{"目标": "把剪报册里缺的那一页补回去", "状态": "未完成"}]},
            },
            "江既明": {
                "位置": "报刊库", "精神值": 46,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["嘴硬", "父亲当年是馆里的装订工", "从不认自己记错事"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["江既明"],
        "hidden": {"黎含英": "天台楼梯间"},
        "items": {"剪报册": {"位置": "报刊库", "外貌": ["中间缺了一页，书脊的线松了"]}},
        "changes": {
            "江既明": {"解除个性": ["从不认自己记错事"],
                     "新增个性": ["每天翻一遍自己撕掉的那一页，提醒自己做过什么"]},
            "叶望舒": {"解除个性": ["不替人遮掩"]},
            "剪报册": {"新增外貌": ["书脊重新缝过，线换成了新的"]},
        },
        "time": "11 分钟",
    },
    {
        "index": 36,
        "hero": "程书言",
        "scene": "借阅台",
        "people": {
            "程书言": {
                "位置": "借阅台", "精神值": 52,
                "外貌": ["戴着一副圆框眼镜", "袖口沾了墨"],
                "个性": ["不爱欠人情", "在借阅台站了四年", "记性差，靠纸条记事"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "温清和": {
                "位置": "借阅台", "精神值": 58,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["记性好", "按开本认书，不按书号", "认死理"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": [{"目标": "按开本把错架的书找回来", "状态": "未完成"}]},
            },
            "柏既白": {
                "位置": "借阅台", "精神值": 61,
                "外貌": ["外套袖口磨破了", "指节上有旧伤"],
                "个性": ["护短", "西边库房他跑了三年", "不爱在人多的台前说话"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "核清西边库房缺了哪几本", "状态": "未完成"}]},
            },
            "苏含章": {
                "位置": "借阅台", "精神值": 64,
                "外貌": ["衣角被雨打湿过", "鞋面有一层土"],
                "个性": ["好奇心重", "她只管还书这一头", "听人说话的时候不出声"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["温清和", "柏既白", "苏含章"],
        "hidden": {"方既白": "天台楼梯间"},
        "items": {},
        "changes": {
            "温清和": {"完成任务": ["按开本把错架的书找回来"]},
            "柏既白": {"完成任务": ["核清西边库房缺了哪几本"]},
            "程书言": {"精神值": 59},
            "借阅台": {"新增外貌": ["台面上多了一盏铜制的小灯"]},
        },
        "time": "13 分钟",
    },
    {
        "index": 37,
        "hero": "黎望舒",
        "scene": "古籍库",
        "people": {
            "黎望舒": {
                "位置": "古籍库", "精神值": 55,
                "外貌": ["头发用一根木簪别着", "袖口沾了墨"],
                "个性": ["讲究次序", "她管着两把钥匙里的一把", "拆过的书她一眼认得出来"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": [{"目标": "查清第七十二页为何从中间蛀", "状态": "未完成"}]},
            },
            "韩既明": {
                "位置": "古籍库", "精神值": 53,
                "外貌": ["围巾洗得发白", "戴着一副圆框眼镜"],
                "个性": ["嘴硬", "父亲当年是馆里的古籍修复工", "手上有活，嘴上一句不让人"],
                "任务": {"大任务": {"目标": "找到被族人藏起来的那本族谱原本", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["韩既明"],
        "hidden": {"江既明": "报刊库"},
        "items": {},
        "changes": {
            "韩既明": {"新增外貌": ["右手食指上有一道新割的口子"]},
            "黎望舒": {"完成任务": ["查清第七十二页为何从中间蛀"]},
            "古籍库": {"新增外貌": ["木架下层多了一盏带罩的油灯"]},
        },
        "time": "14 分钟",
    },
    {
        "index": 38,
        "hero": "叶停云",
        "scene": "装订间",
        "people": {
            "叶停云": {
                "位置": "装订间", "精神值": 48,
                "外貌": ["指节上有旧伤", "鞋面有一层土"],
                "个性": ["沉默寡言", "在这间装订间干了二十六年", "只肯用手工裁纸"],
                "任务": {"大任务": {"目标": "找回被典当出去的那套医书", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": [],
        "hidden": {"黎望舒": "古籍库"},
        "items": {},
        "changes": {
            "叶停云": {"新增外貌": ["右手虎口上磨出一块新茧"],
                     "新增个性": ["决定把那盒旧刀具重新磨一遍"]},
            "装订间": {"新增外貌": ["柜子深处那盒旧刀具被取了出来，盒盖上一层灰"]},
        },
        "time": "26 分钟",
    },
    {
        "index": 39,
        "hero": "周书言",
        "scene": "东侧回廊",
        "people": {
            "周书言": {
                "位置": "东侧回廊", "精神值": 60,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["心软", "她抄名单抄了半年", "不催人"],
                "任务": {"大任务": {"目标": "把走失的兄长从外地找回来", "状态": "未完成"},
                       "小任务": [{"目标": "把当班名单上十一个人一个个问到", "状态": "未完成"}]},
            },
            "沈照": {
                "位置": "东侧回廊", "精神值": 47,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["嘴硬", "父亲那晚也在馆里当班", "认定父亲的话不会有假"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "温暮": {
                "位置": "东侧回廊", "精神值": 52,
                "外貌": ["围巾洗得发白", "头发用一根木簪别着"],
                "个性": ["谨慎", "母亲那晚也在馆里", "从不说家里的事"],
                "任务": {"大任务": {"目标": "弄清母亲改名换姓之前到底是谁", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["沈照", "温暮"],
        "hidden": {"叶停云": "装订间"},
        "items": {},
        "changes": {
            "沈照": {"解除个性": ["认定父亲的话不会有假"],
                    "新增个性": ["开始怀疑父亲那晚说了假话"]},
            "温暮": {"解除个性": ["从不说家里的事"],
                    "新增个性": ["把母亲那晚当班的事说了出来"]},
            "周书言": {"精神值": 53},
        },
        "time": "7 分钟",
    },
    {
        "index": 40,
        "hero": "柏望舒",
        "scene": "地下书库",
        "people": {
            "柏望舒": {
                "位置": "地下书库", "精神值": 58,
                "外貌": ["外套袖口磨破了", "戴着一副圆框眼镜"],
                "个性": ["护短", "在地下库搬了七年箱子", "湿了的书一定要当天摊开"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
            "秦既明": {
                "位置": "地下书库", "精神值": 56,
                "外貌": ["鞋面有一层土", "围巾洗得发白"],
                "个性": ["执着", "她记东西只写不记", "见不得纸烂在地上"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["秦既明"],
        "hidden": {"周书言": "东侧回廊"},
        "items": {},
        "changes": {
            "柏望舒": {"精神值": 46},
            "秦既明": {"新增小任务": [{"目标": "把这一箱里坏掉的册子逐本记下来",
                                  "属于大任务": "查明族谱被谁抄走了一份",
                                  "状态": "未完成"}]},
            "地下书库": {"新增外貌": ["最里面那排架子的灯泡坏了，那一排照不到"]},
        },
        "time": "19 分钟",
    },
    {
        "index": 41,
        "hero": "苏书言",
        "scene": "茶水间",
        "people": {
            "苏书言": {
                "位置": "茶水间", "精神值": 54,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["不爱欠人情", "他烧了十年锅炉，顺带烧水", "见人总先问一句吃了没有"],
                "任务": {"大任务": {"目标": "找到父亲留下的那只铁皮匣子", "状态": "未完成"},
                       "小任务": []},
            },
            "方清和": {
                "位置": "茶水间", "精神值": 59,
                "外貌": ["头发用一根木簪别着", "衣角被雨打湿过"],
                "个性": ["记性好", "她管着半年的登记簿", "核不上的账不肯放过"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": [{"目标": "核清那半年谁的名字是代签的", "状态": "未完成"}]},
            },
        },
        "also_present": ["方清和"],
        "hidden": {"柏望舒": "地下书库"},
        "items": {},
        "changes": {
            "方清和": {"完成任务": ["核清那半年谁的名字是代签的"]},
            "苏书言": {"新增小任务": [{"目标": "问清当年谁替那三个人签的字",
                                  "属于大任务": "找到父亲留下的那只铁皮匣子",
                                  "状态": "未完成"}]},
            "茶水间": {"新增外貌": ["窗上的水汽结了一层，看不见院子"]},
        },
        "time": "9 分钟",
    },
    {
        "index": 42,
        "hero": "韩既白",
        "scene": "馆外街道",
        "people": {
            "韩既白": {
                "位置": "馆外街道", "精神值": 51,
                "外貌": ["围巾洗得发白", "鞋面有一层土"],
                "个性": ["谨慎", "她从库房的废纸堆里找东西", "不轻易把纸交出去"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "黎照": {
                "位置": "门卫岗亭", "精神值": 57,
                "外貌": ["外套袖口磨破了", "戴着一副圆框眼镜"],
                "个性": ["沉默寡言", "在这座岗亭坐了六年", "见过三个拿着纸来找他的人"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["黎照"],
        "hidden": {"苏书言": "茶水间"},
        "items": {"邮筒": {"位置": "馆外街道", "外貌": ["漆掉了一块，露出底下的铁"]}},
        "changes": {
            "黎照": {"位置": "馆外街道"},
            "韩既白": {"精神值": 58},
            "邮筒": {"新增外貌": ["投信口被雪水堵了一半"]},
        },
        "time": "5 分钟",
    },
    {
        "index": 43,
        "hero": "温既白",
        "scene": "长桌区",
        "people": {
            "温既白": {
                "位置": "长桌区", "精神值": 56,
                "外貌": ["袖口沾了墨", "指节上有旧伤"],
                "个性": ["讲究次序", "在长桌区做登记做了五年", "有用的东西不肯丢第二次"],
                "任务": {"大任务": {"目标": "把被典当出去的那套医书赎回来", "状态": "未完成"},
                       "小任务": []},
            },
            "叶清和": {
                "位置": "长桌区", "精神值": 50,
                "外貌": ["头发用一根木簪别着", "围巾洗得发白"],
                "个性": ["心软", "她那年值夜班", "说过的话不肯改口"],
                "任务": {"大任务": {"目标": "查明族谱被谁抄走了一份", "状态": "未完成"},
                       "小任务": [{"目标": "把去年写的那张纸条找回来", "状态": "未完成"}]},
            },
            "沈既白": {
                "位置": "长桌区", "精神值": 48,
                "外貌": ["戴着一副圆框眼镜", "衣角被雨打湿过"],
                "个性": ["执着", "他认定了那晚有人上过二楼", "说话不肯留余地"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                       "小任务": []},
            },
            "方暮": {
                "位置": "长桌区", "精神值": 62,
                "外貌": ["鞋面有一层土", "袖口沾了墨"],
                "个性": ["嘴硬", "她只管长桌区这一片", "见不得人在桌上留东西"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["叶清和", "沈既白", "方暮"],
        "hidden": {"黎照": "馆外街道"},
        "items": {},
        "changes": {
            "叶清和": {"完成任务": ["把去年写的那张纸条找回来"]},
            "沈既白": {"新增小任务": [{"目标": "问清那天夜里上二楼的人是谁",
                                  "属于大任务": "查清十年前那场火灾是谁放的火",
                                  "状态": "未完成"}]},
            "温既白": {"新增外貌": ["袖口那道墨痕洗过两回，还在"]},
        },
        "time": "10 分钟",
    },
    {
        "index": 44,
        "hero": "江既白",
        "scene": "值班室",
        "people": {
            "江既白": {
                "位置": "值班室", "精神值": 55,
                "外貌": ["外套袖口磨破了", "头发用一根木簪别着"],
                "个性": ["执着", "她核了半年的登记簿", "记下的东西一定送出去"],
                "任务": {"大任务": {"目标": "拿到能证明兄长清白的原始记录", "状态": "未完成"},
                       "小任务": [{"目标": "核清那半年为什么换了四次门卫", "状态": "未完成"}]},
            },
            "顾照": {
                "位置": "值班室", "精神值": 52,
                "外貌": ["鞋面有一层土", "围巾洗得发白"],
                "个性": ["谨慎", "炉子是他生的，一年烧四个月", "见过换门卫的那两次"],
                "任务": {"大任务": {"目标": "替死去的搭档报仇", "状态": "未完成"},
                       "小任务": []},
            },
        },
        "also_present": ["顾照"],
        "hidden": {"叶清和": "长桌区"},
        "items": {"登记簿": {"位置": "值班室", "外貌": ["封面中间一道折痕，按下去又弹起来"]}},
        "changes": {
            "江既白": {"完成任务": ["核清那半年为什么换了四次门卫"]},
            "顾照": {"新增个性": ["答应替江既白把那本簿子的原本守住"]},
            "登记簿": {"新增外貌": ["封面被手掌压平了一次，折痕浅了些"]},
        },
        "time": "12 分钟",
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
