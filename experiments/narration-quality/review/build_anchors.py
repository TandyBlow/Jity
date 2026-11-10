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
        "fact": ["fact.item_misattribution"],
        "notes": "演习规则牌 is settled in the lane; the prose puts it in his palm.",
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
    "expect": {"fact": ["fact.item_misattribution"], "notes": "A scene object written as carried."},
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
