# -*- coding: utf-8 -*-
"""Build the independent-review calibration batch.

The free-day fixture is generated from the committed world file, so the
`上回合状态` is the real initial state, not a hand-written approximation. The
texts are copied verbatim from the reports they are named after; nothing is
rewritten to make a check fire.
"""
import json
import io
import os

ROOT = "D:/others/Jity/.local/parallel-local-game"
WT = ROOT + "/worktrees/01-input"
OUT = WT + "/experiments/narration-quality/review"
WORLD = WT + "/frontend/public/worlds/dragon-raja-free-day.world.json"

world = json.load(io.open(WORLD, encoding="utf-8"))
initial = world["initial"]
loc_name = {key: value["name"] for key, value in initial["locations"].items()}
char_name = {key: value["name"] for key, value in initial["characters"].items()}
item_name = {key: value["name"] for key, value in initial["items"].items()}


def place_block(key):
    value = initial["locations"][key]
    parent = value.get("parentLocationId")
    return {
        "位于": loc_name[parent] if parent else None,
        "外貌": [value["initialAppearance"]],
    }


def person_block(key):
    value = initial["characters"][key]
    container = value["initialPosition"]["containerId"]
    place = loc_name.get(container, char_name.get(container, container))
    big = [task for task in value["tasks"].values() if not task.get("parentTaskId")]
    small = [task for task in value["tasks"].values() if task.get("parentTaskId")]
    tasks = {
        "大任务": {"目标": big[0]["goal"], "状态": "未完成" if big[0]["status"] == "pending" else "已完成"} if big else None,
        "小任务": [
            {"目标": task["goal"], "状态": "未完成" if task["status"] == "pending" else "已完成"}
            for task in small
        ],
    }
    return {
        "位置": place,
        "精神值": value["initialSanity"],
        "外貌": [value["initialAppearance"]],
        "个性": [value["initialPersonality"]],
        "任务": tasks,
    }


def item_block(key):
    value = initial["items"][key]
    container = value["initialPosition"]["containerId"]
    place = loc_name.get(container, char_name.get(container, container))
    return {"位置": place, "外貌": [value["initialAppearance"]]}


def base_state():
    return {
        "视角": "主角视角（路明非）；只表达已结算的世界事实",
        "上回合状态": {
            "地点": {name: place_block(key) for key, name in [
                ("campus", "campus"), ("west", "west"), ("lane", "lane"), ("shed", "shed"),
                ("yard", "yard"), ("west_arcade", "west_arcade"), ("aid", "aid"), ("rest", "rest"),
            ]},
            "人物": {
                char_name["lu"]: person_block("lu"),
                char_name["nono"]: person_block("nono"),
                char_name["fingel"]: person_block("fingel"),
            },
            "物品": {
                item_name["rules"]: item_block("rules"),
                item_name["map"]: item_block("map"),
                item_name["goggles_lu"]: item_block("goggles_lu"),
                item_name["pistol_nono"]: item_block("pistol_nono"),
            },
        },
        "本回合变化": {"时间推进": "2 分钟", "变化": {}},
    }


opening = base_state()

# Free-day task point: 路明非 and 诺诺 moved to 西回廊; 路明非 completed
# task_nono_lu, gained one personality line and sanity 43 -> 48.
task_state = json.loads(json.dumps(opening))
task_state["上回合状态"]["人物"][char_name["lu"]]["位置"] = "西回廊"
task_state["上回合状态"]["人物"][char_name["nono"]]["位置"] = "西回廊"
task_state["上回合状态"]["地点"]["西回廊"] = place_block("west_arcade")
task_state["本回合变化"] = {
    "时间推进": "3 分钟",
    "变化": {
        char_name["lu"]: {
            "精神值": 48,
            "新增个性": ["不再等别人替他决定，愿意先迈出一步"],
            "任务": {
                "大任务": {"目标": task_state["上回合状态"]["人物"][char_name["lu"]]["任务"]["大任务"]["目标"], "状态": "未完成"},
                "小任务": [
                    {"目标": "向诺诺问清当前红蓝两方局势和自己是否可以保持中立", "状态": "已完成"},
                ] + task_state["上回合状态"]["人物"][char_name["lu"]]["任务"]["小任务"][1:],
            },
        },
    },
}
task_state["上回合状态"]["人物"]["林亦舟"] = {
    "位置": "西回廊", "精神值": 29,
    "外貌": ["蓝色识别带沾着灰，左脚踝在鞋帮上方肿起；背靠第三根廊柱坐着，演习枪已经放到右手碰不到的地面。说话正常，没法独自站稳"],
    "个性": ["蓝方低年级队员，怕被看成拖累"],
    "任务": {"大任务": {"目标": "在不加重脚踝伤势的情况下到达演习医护处置室", "状态": "未完成"}, "小任务": []},
}
task_state["本回合状态"] = {
    char_name["lu"]: {
        "精神值": 48,
        "个性": task_state["上回合状态"]["人物"][char_name["lu"]]["个性"] + ["不再等别人替他决定，愿意先迈出一步"],
        "任务": task_state["本回合变化"]["变化"][char_name["lu"]]["任务"],
    },
}

# Move point: 路明非 and 诺诺 to 西回廊, 芬格尔 器材棚 -> 中央庭院.
move_state = json.loads(json.dumps(opening))
for name, target in [(char_name["lu"], "西回廊"), (char_name["nono"], "西回廊"), (char_name["fingel"], "中央庭院")]:
    move_state["本回合变化"]["变化"][name] = {"位置": target}
move_state["上回合状态"]["地点"]["西回廊"] = place_block("west_arcade")
move_state["上回合状态"]["地点"]["中央庭院"] = place_block("yard")
move_state["本回合状态"] = {name: {"位置": target} for name, target in [
    (char_name["lu"], "西回廊"), (char_name["nono"], "西回廊"), (char_name["fingel"], "中央庭院")]}

# Small corridor scene for 02's 1.5B root run, transcribed from its prompt.
corridor = {
    "视角": "主角视角（周宁）；只表达已结算的世界事实",
    "上回合状态": {
        "地点": {
            "走廊": {"位于": None, "外貌": ["明亮的走廊，通往门厅。"]},
            "门厅": {"位于": "走廊", "外貌": ["门厅的灯还亮着。"]},
        },
        "人物": {
            "林川": {
                "位置": "走廊", "精神值": 10, "外貌": ["穿灰衣"],
                "个性": ["谨慎", "恪守职责"],
                "任务": {"大任务": {"目标": "留在走廊守门，不碰盒子", "状态": "未完成"}, "小任务": []},
            },
            "周宁": {
                "位置": "走廊", "精神值": 10, "外貌": ["穿蓝衣"], "个性": ["好奇"],
                "任务": {"大任务": None, "小任务": []},
            },
        },
        "物品": {"盒子": {"位置": "走廊", "外貌": ["盒盖关闭"]}},
    },
    "本回合变化": {"时间推进": "", "变化": {}},
}

# Small scene for rule anchors: one move, one sanity change, one task.
rule_scene = {
    "视角": "主角视角（温执）；只表达已结算的世界事实",
    "上回合状态": {
        "地点": {
            "一层门厅": {"位于": None, "外貌": ["地砖被脚步磨得发白。"]},
            "借阅台": {"位于": "一层门厅", "外貌": ["硬木台面，边角包着铜皮。"]},
            "还书处": {"位于": "一层门厅", "外貌": ["铁皮还书箱敞着口。"]},
        },
        "人物": {
            "温执": {
                "位置": "借阅台", "精神值": 51, "外貌": ["戴着一副圆框眼镜"], "个性": ["不爱欠人情"],
                "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                        "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "未完成"}]},
            },
            "黎知微": {
                "位置": "还书处", "精神值": 63, "外貌": ["袖口沾了墨"], "个性": ["讲究次序"],
                "任务": {"大任务": {"目标": "把走失的妹妹从外地找回来", "状态": "未完成"}, "小任务": []},
            },
        },
        "物品": {"铁皮还书箱": {"位置": "还书处", "外貌": ["箱底锈穿了一个洞"]}},
    },
    "本回合变化": {
        "时间推进": "4 分钟",
        "变化": {
            "温执": {"位置": "还书处", "精神值": 47, "任务": {
                "大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "已完成"}]}},
            "黎知微": {"新增个性": ["答应替温执留一只没登记过的旧箱"]},
            "铁皮还书箱": {"解除外貌": ["箱底锈穿了一个洞"], "新增外貌": ["箱底垫了一块木板"]},
        },
    },
    "本回合状态": {
        "温执": {"位置": "还书处", "精神值": 47,
                 "任务": {"大任务": {"目标": "查清十年前那场火灾是谁放的火", "状态": "未完成"},
                          "小任务": [{"目标": "比对三份互相矛盾的登记簿", "状态": "已完成"}]}},
        "黎知微": {"个性": ["讲究次序", "答应替温执留一只没登记过的旧箱"]},
        "铁皮还书箱": {"外貌": ["箱底垫了一块木板"]},
    },
}

genders = {
    "路明非": {"gender": "male", "source": "world/character text: 「不愿替他」", "confidence": "world-text"},
    "诺诺": {"gender": "female", "source": "world/character text: 「不能显示她」", "confidence": "world-text"},
    "楚子航": {"gender": "male", "source": "world/character text: 「楚子航补上他」", "confidence": "world-text"},
    "沈澄": {"gender": "female", "source": "world/character text: 「和她」", "confidence": "world-text"},
    "林亦舟": {"gender": "male", "source": "05 character-gender-evidence: 「已离开他的手」", "confidence": "world-text"},
    "周宁": {"gender": "female", "source": "08 report humanReviewFindings: product review 2026-11-10 recorded 周宁 narrated as 他 as an error", "confidence": "recorded-review"},
}


def completed_tasks(state, person_name, goal):
    raw = state["上回合状态"]["人物"][person_name]["任务"]
    return {
        "大任务": raw["大任务"],
        "小任务": [
            {"目标": task["目标"], "状态": "已完成" if task["目标"] == goal else task["状态"]}
            for task in raw["小任务"]
        ],
    }


# Point matching 04's program-mode sample: 路明非/诺诺 moved into 器材棚,
# 芬格尔 left for 中央庭院, the goggles moved to his forehead, the cage lock
# was opened, and two tasks completed.
program_state = json.loads(json.dumps(opening))
program_state["上回合状态"]["人物"][char_name["lu"]]["位置"] = "西侧服务巷"
program_state["上回合状态"]["人物"][char_name["nono"]]["位置"] = "西侧服务巷"
program_state["上回合状态"]["人物"][char_name["fingel"]]["位置"] = "器材棚"
program_state["上回合状态"]["人物"]["秦越"] = {
    "位置": "器材棚", "精神值": 61, "外貌": ["灰色器材背心套在校服外，胸前挂着领用牌"],
    "个性": ["按登记发器材"], "任务": {"大任务": {"目标": "让演习器材可追溯地发放，并优先保证伤员搬运", "状态": "未完成"}, "小任务": []},
}
program_state["上回合状态"]["地点"]["器材笼"] = {"位于": "器材棚", "外貌": ["铁笼里堆着担架、折叠梯和安全绳。"]}
program_state["上回合状态"]["地点"]["中央庭院"] = place_block("yard")
program_state["上回合状态"]["物品"]["器材笼的挂锁"] = {"位置": "器材棚", "外貌": ["锁舌扣在笼门上。"]}
program_state["上回合状态"]["物品"]["折叠担架"] = {"位置": "器材笼", "外貌": ["帆布面磨得发白。"]}
program_state["上回合状态"]["物品"]["演习弹药箱"] = {"位置": "器材棚", "外貌": ["箱盖开着，箱内两只已装填的通用短枪弹匣各有8发弗里嘉演习弹。"]}
program_state["本回合变化"] = {
    "时间推进": "2 分钟",
    "变化": {
        char_name["lu"]: {
            "位置": "器材棚",
            "新增外貌": ["护目镜推到额头上，镜带压住一撮头发"],
            "新增个性": ["开口还是先绕一句玩笑，但已经把护目镜当成要用的东西，不再只是挂在胸前给别人看"],
            "任务": completed_tasks(program_state, char_name["lu"], "把胸前护目镜戴好并确认镜片没有裂纹"),
        },
        char_name["nono"]: {
            "位置": "器材棚",
            "任务": completed_tasks(program_state, char_name["nono"], "问清路明非的参赛意愿并说明三条接近钟楼的路线"),
        },
        char_name["fingel"]: {"位置": "中央庭院"},
        "器材笼的挂锁": {"新增外貌": ["锁舌挂在笼门上，笼门开着"]},
    },
}
program_state["本回合状态"] = {
    char_name["lu"]: {
        "位置": "器材棚",
        "外貌": program_state["上回合状态"]["人物"][char_name["lu"]]["外貌"] + ["护目镜推到额头上，镜带压住一撮头发"],
        "个性": program_state["上回合状态"]["人物"][char_name["lu"]]["个性"] + ["开口还是先绕一句玩笑，但已经把护目镜当成要用的东西，不再只是挂在胸前给别人看"],
        "任务": program_state["本回合变化"]["变化"][char_name["lu"]]["任务"],
    },
    char_name["nono"]: {"位置": "器材棚", "任务": program_state["本回合变化"]["变化"][char_name["nono"]]["任务"]},
    char_name["fingel"]: {"位置": "中央庭院"},
    "器材笼的挂锁": {"外貌": ["锁舌挂在笼门上，笼门开着"]},
}

PROGRAM_TEXT = "\n\n".join([
    "两分钟过去了。",
    "路明非站在器材棚。",
    "诺诺离开西侧服务巷，走进器材棚。",
    "芬格尔从器材棚进入中央庭院。",
    "路明非身上，护目镜已经推到额头上，镜带压住一撮头发，右手还搭在颈后的镜带上。",
    "器材笼的挂锁已经打开，锁舌挂在笼门上，笼里那副折叠担架被拖到了门口。",
    "路明非把「把胸前护目镜戴好并确认镜片没有裂纹」这件事做完了。",
    "路明非还有下一件事要做：向秦越报明护目镜已经领到手，再问清担架放在哪一侧。",
    "诺诺完成了「问清路明非的参赛意愿并说明三条接近钟楼的路线」。",
    "路明非身上多了一点变化：开口还是先绕一句玩笑，但已经把护目镜当成要用的东西，不再只是挂在胸前给别人看。",
    "路明非喉咙紧了一下。",
    "路明非把护目镜推到额头上，问秦越担架放在哪一侧；秦越说担架已经在器材笼门口，先报用途再登记。",
    "开盖演习弹药箱在器材棚，箱内两只已装填的通用短枪弹匣各有8发弗里嘉演习弹。",
    "路明非在原地站了一会儿。",
])


anchors = []

# ------------------------------------------- Qwen3 1.7B product-case arms (02)
arms_scene = {
    "视角": "主角视角（路明非）",
    "上回合状态": {
        "地点": {"西侧服务巷": {"位于": "西侧器材区", "外貌": ["巷口的黄黑绳已放下，进入即算踏入演习区。右墙贴着赛区图，器材棚门敞开；巷子尽头的低墙挡住庭院视线，墙角留下新鲜的演习弹红痕。"]},
                 "西侧器材区": {"位于": "卡塞尔学院演习区", "外貌": ["器材棚、服务巷和西侧集结点围成一条后勤线；从服务巷可到庭院西口，也能绕进检修通道。"]}},
        "人物": {
            "路明非": {"位置": "西侧服务巷", "精神值": 43,
                       "外貌": ["校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带"],
                       "个性": ["听见远处枪声会下意识缩肩", "习惯先用一句玩笑替自己解围"],
                       "任务": {"大任务": {"目标": "作出参赛选择", "状态": "未完成"}, "小任务": []}},
            "诺诺": {"位置": "西侧服务巷", "精神值": 58,
                     "外貌": ["红发用发圈束在脑后，红色识别带缠在左臂；右袖的红痕是扶过弹着石墙时蹭上的，身上没有本场命中标记，手里的短枪枪口压向地面"],
                     "个性": ["看人时比听解释更有耐心"], "任务": {"大任务": {"目标": "保障旗台行动", "状态": "未完成"}, "小任务": []}},
        },
        "物品": {"路明非的护目镜": {"位置": "路明非", "外貌": ["镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前"]},
                 "赛区路线图": {"位置": "西侧服务巷", "外貌": ["图上画出庭院、东西回廊、跨溪小桥、钟楼与白线撤离路"]},
                 "演习规则牌": {"位置": "西侧服务巷", "外貌": ["牌面写明：使用弗里嘉演习弹；护目镜必须戴好；医护白线禁射；退出者不得返场；15:45停赛"]}},
    },
    "本回合变化": {"变化": {}},
    "本回合状态": {"人物": {}, "物品": {}},
}
anchors += [
    {
        "id": "neg/qwen3-arm-scene",
        "source": "results/02-narration/real-qwen3-free-day-arms.json free-day-root::scene, auto-accepted=true",
        "input": arms_scene,
        "text": "路明非盯着墙上的赛区图，手指摩挲着镜片边缘。巷口的黄黑绳已放，空气中还残留着硝烟味。他摸了摸胸前的护目镜，镜片无裂纹，镜带松着。远处传来枪声，他下意识缩肩，但没说出口。诺诺在入口处，红发束在脑后，短枪枪口压向地面。他没说话，只是低头整理衣襟，膝盖沾了灰。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.sound_added", "fact.trait_as_event"], "style": [],
                   "notes": "A conditional trait (hearing gunfire, shrinking the shoulders) is turned into a current gunshot plus a current shrug."},
    },
    {
        "id": "neg/qwen3-arm-prose",
        "source": "results/02-narration/real-qwen3-free-day-arms.json free-day-root::prose, auto-accepted=true",
        "input": arms_scene,
        "text": "路明非望着远处的钟楼，风穿过巷子，带来一丝凉意。诺诺的红发在阳光下闪烁，她手中的短枪压在地面，枪口微微抬起。远处传来演习规则牌的声音，提醒着他们必须遵守规则。路明非注意到诺诺的红痕，那是她扶过弹着石墙时蹭上的，身上没有本场命中标记。空气中弥漫着演习弹的气味，路明非感受到脚下地面的温度，仿佛能触摸到那片被弹片击中的痕迹。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.state_contradiction", "fact.object_speaks", "fact.past_added"], "style": [],
                   "notes": "The rule sign speaks, the held pistol lies on the ground with its muzzle up, and a fragment hit is invented."},
    },
    {
        "id": "neg/qwen3-arm-beats",
        "source": "results/02-narration/real-qwen3-free-day-arms.json free-day-root::beats, rejected",
        "input": arms_scene,
        "text": "光从巷口斜斜洒来，映着诺诺发圈上的红光，右袖的红痕在光下泛着暗色。路明非伸手摸了摸手背，指尖触到那道浅浅的红痕，忽然想起刚才被弹片击中时，自己也摸到了类似的东西。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.past_added", "fact.body_mark_added"], "style": [],
                   "notes": "An invented fragment hit remembered as past; the protagonist has no such mark in the settled appearance."},
    },
]


# -------------------------------------------------- 1.5B accepted counterexample
box_scene = {
    "视角": "主角视角（周宁）",
    "上回合状态": {
        "地点": {"走廊": {"位于": None, "外貌": ["明亮的走廊，通往门厅。"]}},
        "人物": {"林川": {"位置": "走廊", "精神值": 10, "外貌": ["穿灰衣"],
                          "任务": {"大任务": {"目标": "留在走廊守门，不碰盒子", "状态": "未完成"}, "小任务": []}},
                 "周宁": {"位置": "走廊", "精神值": 10, "外貌": ["穿蓝衣"], "任务": {"大任务": {"目标": "无", "状态": "未完成"}, "小任务": []}}},
        "物品": {"盒子": {"位置": "走廊", "外貌": ["盒盖关闭"]}},
    },
    "本回合变化": {"时间推进": "2 分钟", "变化": {}},
    "本回合状态": {"人物": {}, "物品": {}},
}
anchors += [
    {
        "id": "neg/1.5b-accepted-elapsed",
        "source": "results/quality/beat-qwen25-1.5b-instruct.json run elapsed-two-minutes, accepted=true by the old gate",
        "input": box_scene,
        "text": "光从盒子缝隙中透出，映在走廊的每一面墙壁上。声音是轻柔的铃声，偶尔几下脚步声在走廊尽头渐行渐远。周宁的手指轻轻触碰盒盖，盒子缓缓开启，映入眼帘的是一块精致的古董，上面雕刻着精美的图案。\n\n约两分钟过去了。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.event_added", "fact.sound_added", "fact.sound_added"], "style": [],
                   "notes": "Closed box opens, two sounds and a new object appear; the time is stated, so this is a pure invention case."},
    },
    {
        "id": "neg/1.5b-root-closed-box",
        "source": "results/quality/beat-qwen25-1.5b-instruct.json run root-scene, rejected for length only",
        "input": box_scene,
        "text": "走廊明亮，周宁看着林川站在那里，林川的手按在盒盖上，盒子静静地悬在空中。周宁的心跳加速，盒子缓缓打开，里面是一张纸条。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.time_missing", "fact.object_added", "fact.event_added"], "style": [],
                   "notes": "A closed box opens and holds a note that was never settled."},
    },
]

# ------------------------------------------------------- 08 counterexamples
gaze_scene = {
    "视角": "主角视角（周宁）",
    "上回合状态": {
        "地点": {"走廊": {"位于": None, "外貌": ["明亮的走廊，通往门厅。"]},
                 "门厅": {"位于": None, "外貌": ["门厅里的灯亮着。"]}},
        "人物": {"周宁": {"位置": "走廊", "精神值": 10, "外貌": ["穿蓝衣"]},
                 "林川": {"位置": "门厅", "精神值": 10, "外貌": ["穿灰衣"]}},
        "物品": {"盒子": {"位置": "走廊", "外貌": ["盒盖关闭"]}},
    },
    "本回合变化": {"时间推进": "2 分钟", "变化": {}},
    "本回合状态": {"人物": {}, "物品": {}},
}
route_scene = {
    "视角": "主角视角（林川）",
    "上回合状态": {
        "地点": {"库房": {"位于": None, "外貌": ["库房里堆着木箱。"]},
                 "平台": {"位于": None, "外貌": ["平台边上有栏杆。"]},
                 "楼梯间": {"位于": None, "外貌": ["窄楼梯拐角堆着沙袋。"]}},
        "人物": {"林川": {"位置": "库房", "精神值": 40, "外貌": ["穿灰衣"]}},
        "物品": {},
    },
    "本回合变化": {"时间推进": "2 分钟", "变化": {"林川": {"位置": "平台"}}},
    "本回合状态": {"林川": {"位置": "平台"}},
}
anchors += [
    {
        "id": "neg/08-gaze-is-not-movement",
        "source": "worktrees/08-runtime/.local/candidate-model/run-qwen25-1.5b-dev-r3.json point continuation-elapsed; the shared grader flagged movement_without_fact on the gaze",
        "input": gaze_scene,
        "text": "两分钟过去。周宁的视线在门厅与走廊之间来回扫动，偶尔停顿在那扇门上，似乎在等待门厅那边的人迈出步伐。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [], "notes": "The subject is the gaze, not the body: no movement fact is needed."},
    },
    {
        "id": "neg/wrong-source-floor",
        "source": "08-runtime limitation: the unseen-world move point paraphrases 库房→平台 as 从楼梯间走来 and the shared grader missed the wrong source",
        "input": route_scene,
        "text": "两分钟过去，林川从楼梯间走来，停在平台边上。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.wrong_source"], "style": [], "notes": "The origin is a known place and differs from the settled origin; the destination alone does not make the move right."},
    },
]



def add(case):
    anchors.append(case)


def from_report(path, *keys):
    data = json.load(io.open(path, encoding="utf-8"))
    value = data
    for key in keys:
        value = value[key]
    return value


# ---------------------------------------------------------------- negatives
add({
    "id": "neg/08-dev-root",
    "source": "results/quality/team-08-runtime.json realRuns[6].text0 (accepted by the old grader)",
    "input": corridor,
    "text": from_report(ROOT + "/results/quality/team-08-runtime.json", "realRuns")[6]["text0"],
    "options": {"genders": {name: entry["gender"] for name, entry in genders.items()}, "minChars": 60, "targetChars": 200},
    "expect": {
        "fact": ["fact.sound_added"],
        "review": ["review.pronoun", "review.micro_action"],
        "notes": "「脚步声」 in a corridor whose only settled state is an empty hallway; 「林川站在他身后」 leaves 他 ambiguous, so the pronoun is a review item, not a machine gender verdict. The 2-minute advance is not stated either.",
    },
})

add({
    "id": "neg/08-dev-continuation",
    "source": "results/quality/team-08-runtime.json realRuns[6].textContinuation",
    "input": dict(corridor, **{"本回合变化": {"时间推进": "2 分钟", "变化": {}}}),
    "text": from_report(ROOT + "/results/quality/team-08-runtime.json", "realRuns")[6]["textContinuation"],
    "options": {
        "genders": {name: entry["gender"] for name, entry in genders.items()},
        "priorTexts": [from_report(ROOT + "/results/quality/team-08-runtime.json", "realRuns")[6]["text0"]],
        "minChars": 60, "targetChars": 200,
    },
    "expect": {
        "fact": ["fact.sound_added"],
        "style": ["style.repeated_opening"],
        "review": ["review.pronoun"],
        "notes": "Unfounded footsteps; verbatim opening repeated from the previous turn; 他 for 周宁; the 2-minute advance is stated twice.",
    },
})

add({
    "id": "neg/08-free-day-gun",
    "source": "results/quality/team-08-runtime.json realRuns[1].text (accepted, 275 chars)",
    "input": opening,
    "text": from_report(ROOT + "/results/quality/team-08-runtime.json", "realRuns")[1]["text"],
    "options": {"genders": {name: entry["gender"] for name, entry in genders.items()}, "minChars": 60, "targetChars": 200},
    "expect": {
        "fact": ["fact.item_misattribution"],
        "notes": "路明非's settled appearance says 右手还空着; the prose puts a gun in that hand.",
    },
})

add({
    "id": "neg/08-free-day-board",
    "source": "results/quality/team-08-runtime.json realRuns[2].text (accepted, 204 chars)",
    "input": opening,
    "text": from_report(ROOT + "/results/quality/team-08-runtime.json", "realRuns")[2]["text"],
    "options": {"genders": {name: entry["gender"] for name, entry in genders.items()}, "minChars": 60, "targetChars": 200},
    "expect": {
        "fact": ["fact.time_missing", "fact.body_mark_added"],
        "notes": "The rule sign in his palm is now review-level polish; the hard errors are the missing time and 诺诺's red mark moved onto 路明非's arm.",
    },
})

add({
    "id": "neg/02-1.5b-root",
    "source": "results/02-narration/real-model-1.5b.json runs[0].text (rejected by 02's grader, kept for the narrative defects)",
    "input": corridor,
    "text": from_report(ROOT + "/results/02-narration/real-model-1.5b.json", "runs")[0]["text"],
    "options": {"genders": {name: entry["gender"] for name, entry in genders.items()}, "minChars": 60, "targetChars": 200},
    "expect": {
        "fact": ["fact.event_added"],
        "review": ["review.micro_action"],
        "notes": "「她把门推开一条缝」 invents a door; no time is stated (2-minute point); dialogue invents a past light.",
    },
})

add({
    "id": "neg/02-free-day-task-accepted",
    "source": "results/quality/browser-09.json run 02-narration::free-day-task::mwakurt9 (accepted=true)",
    "input": task_state,
    "text": "「站住！」林亦舟叫道。\n\n路明非把「向诺诺问清当前红蓝两方局势和自己是否可以保持中立」这件事做完了。\n\n路明非不再等别人替他决定，愿意先迈出一步。。\n\n路明非的精神值从43变成了48。\n\n约三分钟过去了。",
    "options": {"genders": {name: entry["gender"] for name, entry in genders.items()}, "minChars": 60, "targetChars": 200},
    "expect": {
        "fact": [],
        "style": ["style.status_panel", "style.field_sentence", "style.punctuation"],
        "review": ["review.speech_act"],
        "notes": "Every settled fact is present, so the fact count is zero — but the text is a field recital, not narration. This is the accepted-by-machine case the product review rejected.",
    },
})

# ---------------------------------------------------------- synthetic rules
add({
    "id": "neg/wrong-sanity-number",
    "source": "synthetic: settled 51 -> 47, prose says 53",
    "input": rule_scene,
    "text": "温执走进还书处，站了四分钟。温执的精神值从 51 掉到 53。温执办完了「比对三份互相矛盾的登记簿」，说箱底已经垫了木板。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": ["fact.wrong_number"], "notes": "53 is neither the settled 51 nor 47."},
})

add({
    "id": "neg/reversed-move",
    "source": "synthetic: settled 温执 借阅台 -> 还书处; prose reverses it",
    "input": rule_scene,
    "text": "四分钟过去，温执从还书处走回借阅台；温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": ["fact.direction_reversed"], "notes": "Origin/destination order is reversed."},
})

add({
    "id": "neg/invented-past",
    "source": "synthetic: no past event in the settled input",
    "input": rule_scene,
    "text": "四分钟过去，温执走进还书处，忽然说起小时候从树上掉下来摔断腿的事。温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": ["fact.past_added"], "notes": "「小时候…」 has no basis in the input."},
})

add({
    "id": "neg/promise",
    "source": "synthetic: no promise settled",
    "input": rule_scene,
    "text": "四分钟过去，温执走进还书处。温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47。黎知微答应替温执留一只没登记过的旧箱，又保证明天一定把三份登记簿都找出来。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": ["fact.promise_added"], "notes": "保证 is a promise with no settled basis."},
})

add({
    "id": "neg/viewpoint-interiority",
    "source": "synthetic: 黎知微 is not the viewpoint",
    "input": rule_scene,
    "text": "四分钟过去，温执走进还书处。黎知微心里明白他不会就此罢休，却只是把箱底垫好。温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": ["fact.viewpoint_interiority"], "notes": "黎知微's interior state is not visible to 温执."},
})

add({
    "id": "neg/item-scene-held",
    "source": "synthetic: 铁皮还书箱 is settled in 还书处",
    "input": rule_scene,
    "text": "四分钟过去，温执走进还书处，把铁皮还书箱抱在怀里，低头看箱底那块木板。温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": [], "style": [], "notes": "A scene object written as carried is allowed polish: the object's settled position does not change, so this is review-level, not a fact error."},
})

add({
    "id": "neg/gender-single-person",
    "source": "synthetic: 周宁 is the only person in the scene and the registry says female",
    "input": {
        "视角": "主角视角（周宁）；只表达已结算的世界事实",
        "上回合状态": {
            "地点": {"走廊": {"位于": None, "外貌": ["明亮的走廊，通往门厅。"]}},
            "人物": {"周宁": {"位置": "走廊", "精神值": 10, "外貌": ["穿蓝衣"], "个性": ["好奇"], "任务": {"小任务": []}}},
            "物品": {"盒子": {"位置": "走廊", "外貌": ["盒盖关闭"]}},
        },
        "本回合变化": {"时间推进": "2 分钟", "变化": {}},
    },
    "text": "两分钟过去。他站在走廊里，看着脚边的盒子，没有动。",
    "options": {"genders": {"周宁": "female"}, "minChars": 1},
    "expect": {"fact": ["fact.gender"], "notes": "Only 周宁 is in the scene, so 他 cannot be anyone else."},
})


add({
    "id": "pos/04-program-free-day-move",
    "source": "results/quality/team-04-settlement.json firstProse.programMode.sample (program realization, not a model)",
    "input": program_state,
    "text": PROGRAM_TEXT,
    "options": {"genders": {name: entry["gender"] for name, entry in genders.items()}, "minChars": 60, "targetChars": 200},
    "expect": {"fact": ["fact.event_added"], "style": ["style.status_panel"], "notes": "Program text: the panel realization is a style failure; the stretcher dragged to the door and the new next-task line are additions the point did not settle."},
})

# ---------------------------------------------------------------- positives
add({
    "id": "pos/paraphrase-move",
    "source": "synthetic: same settled move, natural paraphrase",
    "input": rule_scene,
    "text": "四分钟过去了。温执从借阅台走到还书处，在铁皮箱边停下。温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47，箱底也已经垫了一块木板。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": [], "notes": "Direction preserved, time stated, task and item change stated."},
})

add({
    "id": "pos/negated-event",
    "source": "synthetic: negated verb must not be an event",
    "input": rule_scene,
    "text": "四分钟过去，温执走进还书处。他没有打开铁皮还书箱，只蹲下看了看箱底。温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": [], "notes": "「没有打开」 is not an assertion that the box was opened."},
})

add({
    "id": "pos/licensed-appearance",
    "source": "synthetic: settled appearance quoted, no invention",
    "input": rule_scene,
    "text": "四分钟过去，温执走进还书处。铁皮还书箱的箱底垫了一块木板，边角还新；他戴着圆框眼镜，站在箱边看了一会儿。温执办完了「比对三份互相矛盾的登记簿」，精神值从 51 降到 47。黎知微答应替温执留一只没登记过的旧箱。",
    "options": {"genders": {}, "minChars": 1},
    "expect": {"fact": [], "notes": "The board under the box is the settled appearance change; the glasses are settled appearance."},
})


anchors += [
    {
        "id": "neg/wrong-place-outer",
        "source": "02 req-02-06 class: a person inside a sub-place written at the outer place",
        "input": {"视角": "主角视角（方既白）", "上回合状态": {"地点": {"天台": {"位于": None, "外貌": ["地面铺着防水卷材。"]}, "天台楼梯间": {"位于": "天台", "外貌": ["楼梯间窄，灯泡坏了。"]}}, "人物": {"方既白": {"位置": "天台楼梯间", "精神值": 53, "外貌": ["头发用一根木簪别着"], "个性": ["心软"], "任务": {"大任务": {"目标": "找回兄长", "状态": "未完成"}, "小任务": []}}, "黎含英": {"位置": "天台楼梯间", "精神值": 55, "外貌": ["围巾洗得发白"], "个性": ["沉默寡言"], "任务": {"大任务": {"目标": "赎回医书", "状态": "未完成"}, "小任务": []}}}, "物品": {}}, "本回合变化": {"时间推进": "6 分钟", "变化": {}}, "本回合状态": {"人物": {}, "物品": {}}},
        "text": "六分钟过去。方既白还在天台，手指按在墙边没有移开。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.wrong_place"], "style": [],
                   "notes": "Settled in 天台楼梯间; the prose puts her at the outer 天台."},
    },
    {
        "id": "pos/wrong-place-same",
        "source": "same scene, correct place claim",
        "input": {"视角": "主角视角（方既白）", "上回合状态": {"地点": {"天台": {"位于": None, "外貌": ["地面铺着防水卷材。"]}, "天台楼梯间": {"位于": "天台", "外貌": ["楼梯间窄，灯泡坏了。"]}}, "人物": {"方既白": {"位置": "天台楼梯间", "精神值": 53, "外貌": ["头发用一根木簪别着"], "个性": ["心软"], "任务": {"大任务": {"目标": "找回兄长", "状态": "未完成"}, "小任务": []}}, "黎含英": {"位置": "天台楼梯间", "精神值": 55, "外貌": ["围巾洗得发白"], "个性": ["沉默寡言"], "任务": {"大任务": {"目标": "赎回医书", "状态": "未完成"}, "小任务": []}}}, "物品": {}}, "本回合变化": {"时间推进": "6 分钟", "变化": {}}, "本回合状态": {"人物": {}, "物品": {}}},
        "text": "六分钟过去。方既白在楼梯间里，手指按在墙边没有移开。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [],
                   "notes": "Shortened sub-place name stays inside the settled place; no flag."},
    },
]


anchors += [
    {
        "id": "neg/09-smoke-prose",
        "source": "results/02-narration/smoke-probe-05b.json free-day-root::prose, 0.5B narration model, old gate accepted",
        "input": arms_scene,
        "text": "西侧服务巷的灯亮着，空气中带着纸屑和空气的味道。\n\n路明非站在东侧的服务台前，手里拿着一只盒子。\n\n「这个盒子。」他说。\n\n诺诺站在他身后，看着他拿。\n\n「你拿的是什么。」\n\n「演习用的背心。」\n\n诺诺凑近看。「这是新的吗？」\n\n「是新买的。」路明非说，「胸袋里放着一支枪，肩上没有。」\n\n诺诺没说话。她把盒子推过去，放在台子边上。\n\n「我来拿。」她说，「你先坐这儿。」\n\n路明非没有立刻走开。「站住。」\n\n诺诺停下。「站住。」\n\n他站着没走。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.item_misattribution"], "style": [],
                   "notes": "An empty hand holds an invented box; the wrong place (东侧服务台) is not covered yet."},
    },
    {
        "id": "neg/09-smoke-scene",
        "source": "results/02-narration/smoke-probe-05b.json free-day-root::scene, 0.5B narration model, old gate accepted",
        "input": arms_scene,
        "text": "「哨声响了。」\n\n路明非把枪放在桌上，对着空场。\n\n诺诺站在旁边，手里紧着一条布条。「有伤员吗？」\n\n「没有。」\n\n诺诺没再问。她转过头看着他，脸上闪过一丝复杂。\n\n「我猜你们在做什么。」她说。\n\n「都在做什么。」\n\n「都在做一件事。」\n\n路明非把枪收好，背在背后。\n\n回廊上响起了脚步声。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.item_misattribution", "fact.sound_added"], "style": [],
                   "notes": "An empty hand handles a gun twice; a corridor footstep has no move fact."},
    },
]

anchors += [
    {
        "id": "neg/10turn-program-fallback",
        "source": "results/product/evidence/09-product-10turn.json turn 1, source=program, the settlement failed and no time advance was committed",
        "input": arms_scene,
        "text": "一分钟过去，路明非还在西侧服务巷。\n\n西侧服务巷里，巷口的黄黑绳已放下，进入即算踏入演习区。\n\n身边还有诺诺，红发用发圈束在脑后，红色识别带缠在左臂。\n\n路明非：本组结算未能确认新的结果。\n\n路明非在原地站了一会儿。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.time_added"], "style": ["style.meta"],
                   "notes": "A minute passes with no settled advance, and the settlement failure line is shown as prose. The standing micro-action must stay unflagged."},
    },
    {
        "id": "neg/10turn-ellipsis",
        "source": "results/product/evidence/09-product-10turn.json turn 2, shown text is a single ellipsis after a timeout",
        "input": arms_scene,
        "text": "…",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": ["style.placeholder"],
                   "notes": "No words were shown; this is a placeholder, not a scene."},
    },
    {
        "id": "pos/allowed-micro-action",
        "source": "allowed polish: a posture change that alters no settled state",
        "input": arms_scene,
        "text": "路明非在原地站了一会儿。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [],
                   "notes": "Standing still changes no settled state; it must not be rejected as a new event."},
    },
    {
        "id": "pos/allowed-dialogue",
        "source": "allowed polish: short dialogue with no settled content",
        "input": arms_scene,
        "text": "「走吧。」诺诺说。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [],
                   "notes": "Dialogue wording is allowed; only invented content needs reading."},
    },
]

anchors += [
    {
        "id": "neg/qwen3b-move-prose",
        "source": "results/02-narration/real-qwen3-free-day-arms.json move-direction::prose, auto-accepted",
        "input": {"视角": "主角视角（周宁）", "上回合状态": {"地点": {"走廊": {"位于": None, "外貌": ["明亮的走廊，通往门厅。"]}, "门厅": {"位于": None, "外貌": []}}, "人物": {"周宁": {"位置": "走廊", "精神值": 10, "外貌": ["穿蓝衣"], "个性": ["好奇"], "任务": {"大任务": None, "小任务": []}}, "林川": {"位置": "走廊", "精神值": 40, "外貌": ["穿灰衣"], "个性": ["寡言"], "任务": {"大任务": None, "小任务": []}}}, "物品": {"盒子": {"位置": "走廊", "外貌": ["盒盖关闭"]}}}, "本回合变化": {"变化": {"林川": {"位置": "门厅"}}}, "本回合状态": {"人物": {}, "物品": {}}},
        "text": "周宁看着盒盖紧闭的盒子，听见远处传来林川的脚步声，从走廊走到门厅。空气中弥漫着淡淡的木香，混合着一丝若有若无的潮湿。他靠在墙上，手指无意识地摩挲着盒子边缘，耳边是林川低声交谈的声音。远处传来轻微的响动，像是风拂过树叶，又像是某种未知的声响。周宁没有动，只是静静等待。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [],
                   "notes": "Allowed polish (leaning, touching the lid) plus an invented conversation, which is review-level speech, not a fact error."},
    },
    {
        "id": "pos/qwen3b-elapsed-prose",
        "source": "results/02-narration/real-qwen3-free-day-arms.json elapsed-two-minutes::prose, auto-accepted; 10 called it the cleanest arm",
        "input": {"视角": "主角视角（周宁）", "上回合状态": {"地点": {"走廊": {"位于": None, "外貌": ["明亮的走廊，通往门厅。"]}, "门厅": {"位于": None, "外貌": []}}, "人物": {"周宁": {"位置": "走廊", "精神值": 10, "外貌": ["穿蓝衣"], "个性": ["好奇"], "任务": {"大任务": None, "小任务": []}}}, "物品": {"盒子": {"位置": "走廊", "外貌": ["盒盖关闭"]}}}, "本回合变化": {"时间推进": "2 分钟", "变化": {}}, "本回合状态": {"人物": {}, "物品": {}}},
        "text": "周宁盯着前方的盒子，盒盖依旧紧闭。走廊里只有风声，吹动着他的衣角。他没有说话，只是盯着那块木头，仿佛在等待什么。两分钟过去，他依旧站在原地，手中只握着自己的物品，没有移动。空气中有一丝潮湿的气味，混着淡淡的木香。他没有拿起盒子，也没有放下它。此刻，他只看见盒子，听见风声，和自己。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [],
                   "notes": "Time is stated and nothing contradicts the state; the ungrounded held object is a review item, so the text is not fact-broken but not proven clean either."},
    },
]

anchors += [
    {
        "id": "neg/qwen3-clean-prose",
        "source": "results/02-narration/real-qwen3-free-day-arms-clean.json free-day-root::prose (accepted, 15:35Z)",
        "input": arms_scene,
        "text": "路明非盯着手中的演习规则牌，镜片上映着墙上的赛区图。诺诺的红发在风中飘动，她手中的短枪枪口压向地面，红痕在左臂清晰可见。路明非的护目镜挂在胸前，镜带松着，镜片无裂纹。他看着诺诺的识别带，没有说话。空气中弥漫着演习弹的硝烟味，路明非的手指轻轻摩挲着规则牌边缘。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.state_contradiction"], "style": [],
                   "notes": "诺诺's red mark is settled on the right sleeve and written on the left arm. Holding the lane's rule sign is polish."},
    },
    {
        "id": "neg/qwen3-clean-scene",
        "source": "results/02-narration/real-qwen3-free-day-arms-clean.json free-day-root::scene (accepted, 15:35Z)",
        "input": arms_scene,
        "text": "路明非蹲在服务巷的墙角，手指摩挲着护目镜边缘。远处枪声未歇，他缩肩的姿势被风揉碎，混着灰土味的空气里，有金属摩擦的声响。诺诺的短枪枪口仍压向地面，红发在风中晃动，像一团未燃的火。他摸到胸前的护目镜，镜片无裂纹，镜带松着，未戴在眼前。墙角的演习弹痕还在，新鲜的，像未愈合的伤口。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.sound_added", "fact.trait_as_event"], "style": [],
                   "notes": "Gunshot and metal sound have no source; the conditional shrink is written as now."},
    },
    {
        "id": "neg/qwen3-clean-beats",
        "source": "results/02-narration/real-qwen3-free-day-arms-clean.json free-day-root::beats (rejected, 15:35Z)",
        "input": arms_scene,
        "text": "路明非看见光在墙角闪烁，像碎银般散落。他摸到右臂上红痕，指尖触到发圈的金属扣。忽然，一片碎屑落在手背，是弹片刮过皮肤的痕迹。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.body_mark_added", "fact.past_added"], "style": [],
                   "notes": "A red mark on the protagonist's arm and a fragment hit he never had."},
    },
]


anchors += [
    {
        "id": "neg/09-smoke-beats",
        "source": "results/02-narration/smoke-probe-05b-beats.json free-day-root::beats (0.5B narration model, accepted)",
        "input": arms_scene,
        "text": "西侧服务巷的巷口传来一声闷响，立刻让诺诺停下脚步。\n\n路明非抬头看。巷子里没人应声。\n\n「有人？」他问。\n\n「没。」诺诺说，「门是开着的。」\n\n「开了多久。」\n\n「不知道。」诺诺把袖子往上捋了捋，「可声音传进来。」\n\n路明非把绳子收好，放在地上，把手掌贴在墙上，回过头看了看巷口那道光。\n\n远处有声音，比街上的更近。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.item_misattribution", "fact.sound_added"], "style": [],
                   "notes": "An empty hand puts away a rope that was never settled, and a muffled sound starts the scene."},
    },
]


anchors += [
    {
        "id": "neg/lora-scene",
        "source": "results/02-narration/real-lora-free-day-arms.json free-day-root::scene (1.5B v2 template, rejected, 513 chars)",
        "input": arms_scene,
        "text": "西侧服务巷里，路明非站在巷口。他把胸前的护目镜摘下来，挂在脖子上的小钩子上，又重新挂回了胸口。镜片是干净的，没有裂纹，他很满意地笑了笑。诺诺从后门走了进来，手里拿着一个装着短枪的袋子。「你先走吧。」他说。「我先走。」「现在怎么走？「从这儿绕过去。」路明非把头伸出去，「右手边是正门，左手边是服务巷。要过这儿时，记得往墙根儿退两步。墙后面有人在等你。」「你是第九个了？」诺诺问。「第九个。」他把手里的东西递过去，「这个是短枪，别对准人。」「我知道。」「还有别的？」「没有了。」路明非说。他把那张纸条从口袋里抽出来，塞进衣兜。「你什么时候想好啦？」诺诺问。「今天。」他说，「明天我去找你们队长。」「为什么是我？」「因为我的腿不听使唤。」他笑了一下，声音有些轻。「那你笑得出来。」「能笑就得撑住。」路明非把纸条重新插回口袋，然后往前走了一步。「诺诺，你刚才说的那句‘我不会替别人跑’，我记下了。」诺诺停了下来。「什么意思？」「意思是，你不能替我跑。」他解释道，「你要是能跑，早就跑了。」诺诺看了他一会儿，没有再说话。她把短枪插回袋子，走到门口，又回头。「那你明天还来吗？」路明非问。「来。」她说，「明天你在哪儿见着了就往哪儿走吧。」",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.object_added"], "style": [],
                   "notes": "The only hard fact is the invented note prop; the 12 dialogue turns and the next-day promise are review-level, which is why the gate must hold rather than accept."},
    },
]


anchors += [
    {
        "id": "neg/qwen3-160-prose",
        "source": "results/02-narration/real-qwen3-free-day-160.json free-day-root-160::prose (accepted, 101 chars)",
        "input": arms_scene,
        "text": "路明非望着远处的钟楼，护目镜在胸前晃动。诺诺的红发在风中飘动，枪口压向地面。演习规则牌在手中转着，他听见了风声，也听见了脚步声。路明非的护目镜无裂纹，镜带松着，他看见了诺诺的红痕，也看见了她手里的短枪。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.sound_added"], "style": [],
                   "notes": "A footstep with no mover; the rule sign in hand and the unseen clock tower stay review."},
    },
    {
        "id": "neg/qwen3-closed-prose",
        "source": "results/02-narration/real-qwen3-free-day-closedlist.json free-day-root-160::prose (accepted, 109 chars)",
        "input": arms_scene,
        "text": "路明非握着演习规则牌，看着诺诺手里的短枪压向地面。她发圈松散，红痕在左臂蜿蜒，护目镜松着带，挂在胸前。西侧服务巷的黄黑绳已放下，器材棚门敞开。钟楼旗台外廊的风声在耳边响起，路明非的演习背心前襟完好，肩上没有阵营识别带。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.state_contradiction"], "style": [],
                   "notes": "The red mark moves to the left arm in the next sentence; the pronoun still refers to 诺诺."},
    },
]


b01_input = {'视角': '主角视角（温执）；只表达已结算的世界事实',
 '上回合状态': {'地点': {'一层门厅': {'位于': None, '外貌': ['地砖被脚步磨得发白，正对大门挂着一面停摆的钟。']},
                  '借阅台': {'位于': '一层门厅', '外貌': ['硬木台面，边角包着铜皮，抽屉上着锁。']},
                  '还书处': {'位于': '一层门厅', '外貌': ['铁皮还书箱敞着口，旁边堆着没上架的书车。']}},
           '人物': {'温执': {'位置': '借阅台',
                         '精神值': 51,
                         '外貌': ['戴着一副圆框眼镜', '指节上有旧伤'],
                         '个性': ['不爱欠人情', '在还书处帮过工，知道哪只箱子漏底', '认定十年前那场火灾不是意外'],
                         '任务': {'大任务': {'目标': '查清十年前那场火灾是谁放的火', '状态': '未完成'}, '小任务': [{'目标': '比对三份互相矛盾的登记簿', '状态': '未完成'}]}},
                  '黎知微': {'位置': '还书处',
                          '精神值': 63,
                          '外貌': ['袖口沾了墨', '衣角被雨打湿过'],
                          '个性': ['讲究次序', '管着还书处那串钥匙', '记得每个常来的人借过什么'],
                          '任务': {'大任务': {'目标': '把走失的妹妹从外地找回来', '状态': '未完成'}, '小任务': []}}},
           '物品': {'铁皮还书箱': {'位置': '还书处', '外貌': ['箱底锈穿了一个洞']}}},
 '本回合变化': {'时间推进': '4 分钟',
           '变化': {'温执': {'位置': '还书处', '新增外貌': ['袖口沾了墨']}, '黎知微': {'新增个性': ['答应替温执留一只没登记过的旧箱']}, '铁皮还书箱': {'解除外貌': ['箱底锈穿了一个洞'], '新增外貌': ['箱底垫了一块木板']}}},
 '本回合状态': {'温执': {'位置': '还书处', '外貌': ['戴着一副圆框眼镜', '指节上有旧伤', '袖口沾了墨']},
           '黎知微': {'个性': ['讲究次序', '管着还书处那串钥匙', '记得每个常来的人借过什么', '答应替温执留一只没登记过的旧箱']},
           '铁皮还书箱': {'外貌': ['箱底垫了一块木板']}}}
anchors += [
    {
        "id": "neg/b01-stale-look",
        "source": "12-best-of-n b01 raw.jsonl seed 43 (frozen checker ec7ffc0e already rejected it; 01 gap review)",
        "input": b01_input,
        "text": "温执站在还书处，箱底垫了一块木板，箱底锈穿了一个洞。他戴着一副圆框眼镜，指节上还有旧伤，袖口沾了墨。他似乎在为十年前那场火灾的真相而努力。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.state_contradiction"], "style": ["style.appearance_recital"], "review": [],
                   "notes": "The look removed this turn (箱底锈穿了一个洞) is narrated as current; the appearance is also recited."},
    },
    {
        "id": "neg/b01-trait-owner",
        "source": "12-best-of-n b01 raw.jsonl seed 61",
        "input": b01_input,
        "text": "温执站在还书处，他戴着一副圆框眼镜，指节上还有旧伤。袖口沾了墨，这是他日常工作的痕迹。他注意到箱底垫了一块木板，这可能是为了防止箱子漏底。温执的个性是讲究次序，他知道哪只箱子漏底，认定十年前那场火灾不是意外。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.trait_misattribution"], "style": ["style.appearance_recital"], "review": [],
                   "notes": "讲究次序 belongs to 黎知微; the sentence gives it to 温执 with 温执的个性是…."},
    },
    {
        "id": "neg/b01-first-person",
        "source": "12-best-of-n b01 raw.jsonl seed 97",
        "input": b01_input,
        "text": "我站在还书处，箱底垫着一块木板，箱底锈穿了一个洞。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.state_contradiction"], "style": ["style.perspective"], "review": [],
                   "notes": "First-person prose for a named third-person viewpoint, plus the removed look again."},
    },
]



anchors += [
    {
        "id": "neg/q3-new-scene",
        "source": "results/02-narration/real-qwen3-free-day-arms-clean.json scene arm (accepted, 122 chars)",
        "input": {'视角': '主角视角（路明非）',
 '上回合状态': {'人物': {'路明非': {'位置': '西侧服务巷/slot_wall',
                          '精神值': 43,
                          '外貌': ['校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。听见远处枪声会下意识缩肩'],
                          '个性': ['习惯先用一句玩笑替自己解围，真见到有人受伤又很难装作没看见。认识诺诺和室友芬格尔，对楚子航有同校旧识的熟悉感，却还没答应加入任何一方；很想证明自己不是只能被别人保护的人'],
                          '任务': {'大任务': {'目标': '在自由一日结束前作出自己的参赛选择，并完成一次能由在场人确认的有效行动后安全离场', '状态': '未完成'},
                                 '小任务': [{'目标': '向诺诺问清当前红蓝两方局势和自己是否可以保持中立', '状态': '未完成'},
                                         {'目标': '在进入交火区前拿到可用的护目镜与演习装备', '状态': '未完成'},
                                         {'目标': '把胸前护目镜戴好并确认镜片没有裂纹', '状态': '未完成'},
                                         {'目标': '在庭院正路、西回廊和地下检修通道之间选择一条有掩护的路线', '状态': '未完成'},
                                         {'目标': '得到至少一名在场者明确同意的协作，不替他人擅自承诺', '状态': '未完成'},
                                         {'目标': '读过服务巷规则牌，知道医护白线内禁止交火', '状态': '已完成'}]}},
                  '诺诺': {'位置': '西侧服务巷/slot_entry',
                         '精神值': 58,
                         '外貌': ['红发用发圈束在脑后，红色识别带缠在左臂；右袖的红痕是扶过弹着石墙时蹭上的，身上没有本场命中标记，手里的短枪枪口压向地面'],
                         '个性': ['看人时比听解释更有耐心，开玩笑尖锐却会在危险前把人拉住。属于凯撒的红方，愿意给路明非提示，但不愿替他选阵营；知道西回廊有蓝方伤员，尚不知道伤势是否真实'],
                         '任务': {'大任务': {'目标': '让红方的旗台行动有可执行的掩护，而不把路明非当诱饵', '状态': '未完成'},
                                '小任务': [{'目标': '问清路明非的参赛意愿并说明三条接近钟楼的路线', '状态': '未完成'},
                                        {'目标': '把故障短讯机恢复到能与凯撒联络的状态', '状态': '未完成'},
                                        {'目标': '确认西回廊的蓝方伤员是否需要真正的医护帮助', '状态': '未完成'},
                                        {'目标': '与凯撒约定可被双方看见的进攻信号，再决定何时离开服务巷', '状态': '未完成'}]}}},
           '地点': {'西侧服务巷': {'位于': '西侧器材区', '外貌': ['巷口的黄黑绳已放下，进入即算踏入演习区。右墙贴着赛区图，器材棚门敞开；巷子尽头的低墙挡住庭院视线，墙角留下新鲜的演习弹红痕']},
                  '西侧器材区': {'位于': '卡塞尔学院演习区', '外貌': ['器材棚', '服务巷和西侧集结点围成一条后勤线；从服务巷可到庭院西口，也能绕进检修通道。运送伤员可沿白线到医护附楼，不必穿越庭院']}},
           '物品': {'路明非的护目镜': {'位置': '路明非', '外貌': ['镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前']},
                  '路明非的演习背心': {'位置': '路明非', '外貌': ['背心前襟完好，没有演习弹痕；胸袋能放一只弹匣，肩上没有阵营识别带']},
                  '诺诺的演习短枪': {'位置': '诺诺', '外貌': ['枪上有黄色演习标记，弹匣内剩3发弗里嘉演习弹，保险合上，枪口向下']},
                  '赛区路线图': {'位置': '西侧服务巷', '外貌': ['图上画出庭院', '东西回廊', '跨溪小桥', '钟楼与白线撤离路；地下检修通道用虚线标注，未标门闩状态']}}},
 '本回合变化': {'变化': {}}},
        "text": "路明非盯着墙上的赛区图，右手空着，护目镜挂在胸前。巷口的黄黑绳已放，风穿过服务巷，带起几片干叶。诺诺在入口处，红发束在脑后，短枪枪口压向地面。他听见远处枪声，缩肩。空气中混着机油和铁锈味，墙角的演习弹痕迹新鲜。他摸了摸胸前的护目镜，镜片无裂纹。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.sound_added", "fact.trait_as_event"], "style": [], "forbid": [],
                   "notes": "The gunshot exists only inside the settled habit; the scene still turns it into a current event."},
    },
]

anchors += [
    {
        "id": "neg/q3-repair-prose",
        "source": "results/02-narration/real-qwen3-free-day-sentence-repair.json prose arm (rejected, 97 chars)",
        "input": {'视角': '主角视角（路明非）',
 '上回合状态': {'人物': {'路明非': {'位置': '西侧服务巷/slot_wall',
                          '精神值': 43,
                          '外貌': ['校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。听见远处枪声会下意识缩肩'],
                          '个性': ['习惯先用一句玩笑替自己解围，真见到有人受伤又很难装作没看见。认识诺诺和室友芬格尔，对楚子航有同校旧识的熟悉感，却还没答应加入任何一方；很想证明自己不是只能被别人保护的人'],
                          '任务': {'大任务': {'目标': '在自由一日结束前作出自己的参赛选择，并完成一次能由在场人确认的有效行动后安全离场', '状态': '未完成'},
                                 '小任务': [{'目标': '向诺诺问清当前红蓝两方局势和自己是否可以保持中立', '状态': '未完成'},
                                         {'目标': '在进入交火区前拿到可用的护目镜与演习装备', '状态': '未完成'},
                                         {'目标': '把胸前护目镜戴好并确认镜片没有裂纹', '状态': '未完成'},
                                         {'目标': '在庭院正路、西回廊和地下检修通道之间选择一条有掩护的路线', '状态': '未完成'},
                                         {'目标': '得到至少一名在场者明确同意的协作，不替他人擅自承诺', '状态': '未完成'},
                                         {'目标': '读过服务巷规则牌，知道医护白线内禁止交火', '状态': '已完成'}]}},
                  '诺诺': {'位置': '西侧服务巷/slot_entry',
                         '精神值': 58,
                         '外貌': ['红发用发圈束在脑后，红色识别带缠在左臂；右袖的红痕是扶过弹着石墙时蹭上的，身上没有本场命中标记，手里的短枪枪口压向地面'],
                         '个性': ['看人时比听解释更有耐心，开玩笑尖锐却会在危险前把人拉住。属于凯撒的红方，愿意给路明非提示，但不愿替他选阵营；知道西回廊有蓝方伤员，尚不知道伤势是否真实'],
                         '任务': {'大任务': {'目标': '让红方的旗台行动有可执行的掩护，而不把路明非当诱饵', '状态': '未完成'},
                                '小任务': [{'目标': '问清路明非的参赛意愿并说明三条接近钟楼的路线', '状态': '未完成'},
                                        {'目标': '把故障短讯机恢复到能与凯撒联络的状态', '状态': '未完成'},
                                        {'目标': '确认西回廊的蓝方伤员是否需要真正的医护帮助', '状态': '未完成'},
                                        {'目标': '与凯撒约定可被双方看见的进攻信号，再决定何时离开服务巷', '状态': '未完成'}]}}},
           '地点': {'西侧服务巷': {'位于': '西侧器材区', '外貌': ['巷口的黄黑绳已放下，进入即算踏入演习区。右墙贴着赛区图，器材棚门敞开；巷子尽头的低墙挡住庭院视线，墙角留下新鲜的演习弹红痕']},
                  '西侧器材区': {'位于': '卡塞尔学院演习区', '外貌': ['器材棚', '服务巷和西侧集结点围成一条后勤线；从服务巷可到庭院西口，也能绕进检修通道。运送伤员可沿白线到医护附楼，不必穿越庭院']}},
           '物品': {'路明非的护目镜': {'位置': '路明非', '外貌': ['镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前']},
                  '路明非的演习背心': {'位置': '路明非', '外貌': ['背心前襟完好，没有演习弹痕；胸袋能放一只弹匣，肩上没有阵营识别带']},
                  '诺诺的演习短枪': {'位置': '诺诺', '外貌': ['枪上有黄色演习标记，弹匣内剩3发弗里嘉演习弹，保险合上，枪口向下']},
                  '赛区路线图': {'位置': '西侧服务巷', '外貌': ['图上画出庭院', '东西回廊', '跨溪小桥', '钟楼与白线撤离路；地下检修通道用虚线标注，未标门闩状态']}}},
 '本回合变化': {'变化': {}}},
        "text": "路明非盯着演习规则牌，发圈在脑后晃动。诺诺靠在墙边，发丝垂落。西侧服务巷的黄黑绳已放下，路明非的护目镜无裂纹，演习背心前襟完好。他摸了摸衣袋，里面装着几片药片。风声轻拂，钟楼旗台外廊的风铃轻响。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.sound_added", "fact.item_misattribution"], "style": [], "forbid": [],
                   "notes": "The wind chime is invented; the hair tie belongs to 诺诺, not 路明非."},
    },
]

anchors += [
    {
        "id": "pos/q3-quiet-beats",
        "source": "results/02-narration/real-qwen3-free-day-beats-quiet.json beats arm (rejected for length, fact-clean)",
        "input": {'视角': '主角视角（路明非）',
 '上回合状态': {'人物': {'路明非': {'位置': '西侧服务巷/slot_wall',
                          '精神值': 43,
                          '外貌': ['校服领口松着，膝盖沾了灰；护目镜挂在胸前，右手还空着，身上没有红蓝识别带。听见远处枪声会下意识缩肩'],
                          '个性': ['习惯先用一句玩笑替自己解围，真见到有人受伤又很难装作没看见。认识诺诺和室友芬格尔，对楚子航有同校旧识的熟悉感，却还没答应加入任何一方；很想证明自己不是只能被别人保护的人'],
                          '任务': {'大任务': {'目标': '在自由一日结束前作出自己的参赛选择，并完成一次能由在场人确认的有效行动后安全离场', '状态': '未完成'},
                                 '小任务': [{'目标': '向诺诺问清当前红蓝两方局势和自己是否可以保持中立', '状态': '未完成'},
                                         {'目标': '在进入交火区前拿到可用的护目镜与演习装备', '状态': '未完成'},
                                         {'目标': '把胸前护目镜戴好并确认镜片没有裂纹', '状态': '未完成'},
                                         {'目标': '在庭院正路、西回廊和地下检修通道之间选择一条有掩护的路线', '状态': '未完成'},
                                         {'目标': '得到至少一名在场者明确同意的协作，不替他人擅自承诺', '状态': '未完成'},
                                         {'目标': '读过服务巷规则牌，知道医护白线内禁止交火', '状态': '已完成'}]}},
                  '诺诺': {'位置': '西侧服务巷/slot_entry',
                         '精神值': 58,
                         '外貌': ['红发用发圈束在脑后，红色识别带缠在左臂；右袖的红痕是扶过弹着石墙时蹭上的，身上没有本场命中标记，手里的短枪枪口压向地面'],
                         '个性': ['看人时比听解释更有耐心，开玩笑尖锐却会在危险前把人拉住。属于凯撒的红方，愿意给路明非提示，但不愿替他选阵营；知道西回廊有蓝方伤员，尚不知道伤势是否真实'],
                         '任务': {'大任务': {'目标': '让红方的旗台行动有可执行的掩护，而不把路明非当诱饵', '状态': '未完成'},
                                '小任务': [{'目标': '问清路明非的参赛意愿并说明三条接近钟楼的路线', '状态': '未完成'},
                                        {'目标': '把故障短讯机恢复到能与凯撒联络的状态', '状态': '未完成'},
                                        {'目标': '确认西回廊的蓝方伤员是否需要真正的医护帮助', '状态': '未完成'},
                                        {'目标': '与凯撒约定可被双方看见的进攻信号，再决定何时离开服务巷', '状态': '未完成'}]}}},
           '地点': {'西侧服务巷': {'位于': '西侧器材区', '外貌': ['巷口的黄黑绳已放下，进入即算踏入演习区。右墙贴着赛区图，器材棚门敞开；巷子尽头的低墙挡住庭院视线，墙角留下新鲜的演习弹红痕']},
                  '西侧器材区': {'位于': '卡塞尔学院演习区', '外貌': ['器材棚', '服务巷和西侧集结点围成一条后勤线；从服务巷可到庭院西口，也能绕进检修通道。运送伤员可沿白线到医护附楼，不必穿越庭院']}},
           '物品': {'路明非的护目镜': {'位置': '路明非', '外貌': ['镜片无裂纹，镜带松着，现挂在胸前而非戴在眼前']},
                  '路明非的演习背心': {'位置': '路明非', '外貌': ['背心前襟完好，没有演习弹痕；胸袋能放一只弹匣，肩上没有阵营识别带']},
                  '诺诺的演习短枪': {'位置': '诺诺', '外貌': ['枪上有黄色演习标记，弹匣内剩3发弗里嘉演习弹，保险合上，枪口向下']},
                  '赛区路线图': {'位置': '西侧服务巷', '外貌': ['图上画出庭院', '东西回廊', '跨溪小桥', '钟楼与白线撤离路；地下检修通道用虚线标注，未标门闩状态']}}},
 '本回合变化': {'变化': {}}},
        "text": "红发女子左臂缠着红色识别带，右袖红痕未褪。演习规则牌在她掌心，护目镜紧贴双眼。她指尖抵着墙，指尖沾着泥渍。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [], "forbid": ["fact.sound_added", "fact.state_contradiction", "fact.item_misattribution"],
                   "notes": "A 53-char beat that keeps the settled band, mark and map; short but fact-clean."},
    },
]


anchors += [
    {
        "id": "neg/slot-substitution",
        "source": "constructed from frozen-row-0012: 温执's cuff is settled with ink",
        "input": b01_input,
        "text": "温执站在还书处，袖口沾着泥。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.state_contradiction"], "style": [], "review": [],
                   "notes": "袖口 is settled with 墨; 泥 changes the same slot."},
    },
]


rows_q3 = {row["id"]: row for row in map(json.loads, io.open(WT + "/.local/narration-quality/batch-q3-new2.jsonl", encoding="utf-8"))}
anchors.append(
    {
        "id": "neg/q3-ext-prose",
        "source": "02 Qwen3-1.7B free-day extended run (78 chars, rejected by 02); goggles settled hanging, text says 摘下",
        "input": rows_q3["q3-ext"]["input"],
        "text": rows_q3["q3-ext"]["text"],
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.item_misattribution", "fact.state_contradiction"], "style": [], "review": [],
                   "notes": "发圈 belongs to 诺诺; 摘下护目镜 implies they were worn, but they hang on the chest."},
    },
)


# ------------------------------------------------- 82-char static inventory
rows_move = {row["id"]: row for row in map(json.loads, io.open(WT + "/.local/narration-quality/batch-q3-all.jsonl", encoding="utf-8"))}
state_list_input = json.loads(json.dumps(rows_move["real-qwen3-free-day-160::free-day-root-160::prose"]["input"]))
state_list_input["本回合变化"] = {"变化": {"路明非": {"位置": "中央庭院"}}}
anchors.append(
    {
        "id": "neg/state-list-82",
        "source": "02 Qwen3-1.7B free-day move arm, 82 chars accepted by 02's own flag; a static inventory, not prose",
        "input": state_list_input,
        "text": "路明非在中央庭院的石阶上，护目镜无裂纹，演习背心前襟完好。诺诺在西侧服务巷，红发用发圈束在脑后。演习规则牌在手心，赛区路线图在脚边。风穿过庭院，带着潮湿的泥土气息。",
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": ["style.state_recital"], "review": [],
                   "notes": "A change point rendered as 6 current-state clauses; accepted flags do not make this prose."},
    },
)


rows_spine = {row["id"]: row for row in map(json.loads, io.open(WT + "/.local/narration-quality/batch-q3-spine.jsonl", encoding="utf-8"))}
anchors.append(
    {
        "id": "neg/q3-spine-handchain",
        "source": "02 Qwen3-1.7B spine-root-2 run (144 chars, accepted by 02): invents a silver bracelet with scratches",
        "input": rows_spine["q3-spine"]["input"],
        "text": rows_spine["q3-spine"]["text"],
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.object_added"], "style": [], "review": [],
                   "notes": "银质手链 is worn and described, but it is neither in the settled look nor handled from a settled object."},
    },
)


rows_cont = {row["id"]: row for row in map(json.loads, io.open(WT + "/.local/narration-quality/batch-q3-cont.jsonl", encoding="utf-8"))}
anchors.append(
    {
        "id": "neg/q3-cont-laughter-past",
        "source": "02 Qwen3-1.7B continuation run (162 chars, rejected by 02): children's laughter and a war memory",
        "input": rows_cont["q3-cont-1"]["input"],
        "text": rows_cont["q3-cont-1"]["text"],
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.past_added", "fact.sound_added"], "style": [], "review": [],
                   "notes": "孩童的笑声 has no child in the scene; 曾经被战火灼伤 is an unsettled past event."},
    },
)
anchors.append(
    {
        "id": "neg/q3-cont-hair",
        "source": "02 Qwen3-1.7B continuation runs 2/3 (156/134 chars): 诺诺's tied hair hangs loose",
        "input": rows_cont["q3-cont-2"]["input"],
        "text": rows_cont["q3-cont-2"]["text"],
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": ["fact.state_contradiction"], "style": [], "review": [],
                   "notes": "Red hair is settled 束在脑后; 红发垂落 is a state change."},
    },
)


rows_cont4 = {row["id"]: row for row in map(json.loads, io.open(WT + "/.local/narration-quality/batch-q3-cont4.jsonl", encoding="utf-8"))}
anchors.append(
    {
        "id": "pos/q3-cont4-lane",
        "source": "02 Qwen3-1.7B continuation-4 run (117 chars, accepted by 02): the viewpoint looks at the lane he is in",
        "input": rows_cont4["q3-cont-4"]["input"],
        "text": rows_cont4["q3-cont-4"]["text"],
        "options": {"genders": {}, "minChars": 1},
        "expect": {"fact": [], "style": [], "review": [], "forbid": ["review.unseen_entity"],
                   "notes": "路明非 is at 西侧服务巷/slot_wall; looking at 西侧服务巷 is not an unseen place."},
    },
)


rows_gender = {row["id"]: row for row in map(json.loads, io.open(WT + "/.local/narration-quality/batch-q3-all.jsonl", encoding="utf-8"))}
anchors.append(
    {
        "id": "neg/zhouning-pronoun",
        "source": "02 q3 1.5B run: 周宁 (female, recorded by the 2026-11-10 product review) is narrated as 他 eleven times",
        "input": rows_gender["real-model-1.5b::elapsed-two-minutes"]["input"],
        "text": rows_gender["real-model-1.5b::elapsed-two-minutes"]["text"],
        "options": {"minChars": 1},
        "expect": {"fact": ["fact.gender"], "style": [], "review": [],
                   "notes": "A single-person scene; 他 cannot be anyone but 周宁."},
    },
)
anchors.append(
    {
        "id": "pos/nono-pronoun",
        "source": "02 Qwen3 free-day-calibrated run: 诺诺's hair band, then 他 = the male viewpoint",
        "input": rows_gender["real-qwen3-free-day-calibrated::free-day-root-160::prose"]["input"],
        "text": rows_gender["real-qwen3-free-day-calibrated::free-day-root-160::prose"]["text"],
        "options": {"minChars": 1},
        "expect": {"fact": [], "style": [], "review": [],
                   "forbid": ["fact.gender"],
                   "notes": "The male viewpoint is visible; 他 must not be blamed on 诺诺."},
    },
)

os.makedirs(OUT, exist_ok=True)
batch = {
    "version": "narration-quality-anchors-v1",
    "createdAt": "2026-11-10",
    "world": "frontend/public/worlds/dragon-raja-free-day.world.json",
    "genders": genders,
    "cases": anchors,
}
io.open(OUT + "/anchors.json", "w", encoding="utf-8", newline="\n").write(
    json.dumps(batch, ensure_ascii=False, indent=2) + "\n")
print("anchors", len(anchors))
