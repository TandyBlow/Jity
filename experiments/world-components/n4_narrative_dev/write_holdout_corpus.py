# Build the 12-case new-world holdout (zero-shot evaluation, no training).
# World: n4w-snow-pass (云关驿 / 风口岭 / 雪溪 / 望雪台).
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/write_holdout_corpus.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
WORLD = json.loads((HERE / "holdout_world.json").read_text(encoding="utf-8"))
OUT = HERE / "holdout_corpus.jsonl"


def moved(fid, eid, frm, to, at):
    return {"factId": fid, "kind": "moved", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "from": frm, "to": to,
            "at": at, "source": {"field": "positionSet"}}


def outcome(fid, eid, task_id, at):
    t = WORLD["tasks"][task_id]
    return {"factId": fid, "kind": "outcome", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "taskId": task_id,
            "goal": t["goal"], "resultText": t["resultText"], "at": at,
            "source": {"field": "tasksAchieved", "taskId": task_id}}


def sanity(fid, eid, frm, to, at):
    return {"factId": fid, "kind": "sanity_changed", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "from": frm, "to": to,
            "at": at, "source": {"field": "sanitySet"}}


def appearance(fid, eid, text, at):
    return {"factId": fid, "kind": "appearance_changed", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "text": text, "at": at,
            "source": {"field": "appearanceChanges"}}


def personality(fid, eid, text, at):
    return {"factId": fid, "kind": "personality_changed", "entityId": eid,
            "name": WORLD["characters"][eid]["name"], "text": text, "at": at,
            "source": {"field": "personalityChanges"}}


def no_change(fid):
    return {"factId": fid, "kind": "no_change", "entityId": None,
            "name": None, "scope": "全局", "source": {"noChange": True}}


def time(fid, amount):
    return {"factId": fid, "kind": "time", "entityId": None, "name": None,
            "amount": amount, "unit": "minute",
            "source": {"timeAdvance": True}}


CASES = [
    dict(id="n4w-01", path=["loc_inn", "loc_inn_hall"], time="傍晚",
         weather="雪，屋檐挂冰凌", wind="低（石墙挡风）", light="炭火",
         atmosphere="门里透出炭火味",
         present=["char_lu"], visible=["item_charcoal", "item_tea",
                                       "item_fur"],
         facts=[moved("f0", "char_lu", "风口岭", "云关驿", "云关驿"),
                time("f1", 6)],
         narrative="云关驿的屋檐挂满冰凌，陆行从风口岭下来，推开结霜的木门。大堂里的炭火味扑到脸上，他把皮袄领口拢了拢，站在门边听了一会儿风雪。"),
    dict(id="n4w-02", path=["loc_inn", "loc_inn_hall"], time="傍晚",
         weather="雪", wind="低（石墙挡风）", light="炭火",
         atmosphere="炭盆刚添过，铜壶冒白汽",
         present=["char_lu", "char_qi"],
         visible=["item_charcoal", "item_tea"],
         facts=[outcome("f0", "char_qi", "task_fire", "云关驿"),
                appearance("f1", "char_qi", "围裙上沾了炭灰", "云关驿"),
                time("f2", 8)],
         narrative="祁婶蹲在炭盆边，把最后一块炭添进去，火苗重新窜起来。她围裙上沾着炭灰，手背被热气烘得发红；陆行在长桌旁坐下，铜壶里的水正好响了。"),
    dict(id="n4w-03", path=["loc_pass", "loc_pass_shed"], time="夜",
         weather="风，雪粒", wind="高（山口横风）", light="马灯",
         atmosphere="旧马棚里黑得很快",
         present=["char_lu", "char_aluo"],
         visible=["item_lantern", "item_bell"],
         facts=[outcome("f0", "char_aluo", "task_lamp", "风口岭"),
                appearance("f1", "char_aluo", "手指沾了灯油", "风口岭"),
                time("f2", 7)],
         narrative="旧马棚里黑得很快，阿洛把马灯从门板上取下来，划亮火折子点上。灯罩里那点火光晃了两下，她手指沾了灯油，在围裙上擦了擦；风从破门板缝里钻进来。"),
    dict(id="n4w-04", path=["loc_tower", "loc_tower_top"], time="黄昏",
         weather="雪，风", wind="高（台顶直风）", light="灰白天色",
         atmosphere="铃绳被风吹得乱响",
         present=["char_lu", "char_shi"],
         visible=["item_bell", "item_rope"],
         facts=[moved("f0", "char_shi", "云关驿", "望雪台", "望雪台"),
                outcome("f1", "char_shi", "task_bell", "望雪台"),
                time("f2", 9)],
         narrative="石青从驿里出来，沿着木梯上到望雪台，把铜铃挂回铃架。风把铃绳吹得乱响，他伸手按住铃舌；台下的驿道只剩一条灰白的线。"),
    dict(id="n4w-05", path=["loc_inn", "loc_inn_room"], time="夜",
         weather="风，窗纸轻响", wind="低（石墙挡风）", light="油灯",
         atmosphere="客房里只有油灯的光",
         present=["char_lu"], visible=["item_map", "item_fur"],
         facts=[moved("f0", "char_lu", "风口岭", "云关驿", "云关驿"),
                outcome("f1", "char_lu", "task_map", "云关驿"),
                sanity("f2", "char_lu", 8, 10, "云关驿"),
                time("f3", 10)],
         narrative="陆行推开客房的门，油灯还亮着。他掀开枕头，从底下抽出那张卷了边的旧地图；纸页带着潮气，他把它摊在床沿，胸口那点没着落的感觉才慢慢定下来。"),
    dict(id="n4w-06", path=["loc_brook", "loc_brook_bridge"], time="清晨",
         weather="雪，溪面结冰", wind="中（溪谷风）", light="灰白",
         atmosphere="冰面反着灰白的光",
         present=["char_lu"], visible=["item_fur"],
         facts=[moved("f0", "char_lu", "云关驿", "雪溪", "雪溪"),
                appearance("f1", "char_lu", "外袍下摆结了一层薄冰", "雪溪"),
                time("f2", 8)],
         narrative="雪溪的石桥下只剩一线黑水，陆行踩着冰碴走到桥中央。风从溪面卷上来，外袍下摆很快结了一层薄冰；他扶住桥栏，听见冰面在脚下轻轻响。"),
    dict(id="n4w-07", path=["loc_pass", "loc_pass_gate"], time="清晨",
         weather="雪，横风", wind="高（山口横风）", light="灰白",
         atmosphere="经幡被风吹得笔直",
         present=["char_lu", "char_aluo"],
         visible=["item_snowstaff", "item_fur"],
         facts=[moved("f0", "char_aluo", "云关驿", "风口岭", "风口岭"),
                moved("f1", "char_lu", "云关驿", "风口岭", "风口岭"),
                personality("f2", "char_lu", "开始愿意先开口", "风口岭"),
                time("f3", 6)],
         narrative="风把隘口的经幡吹得笔直，陆行和阿洛一前一后走到石堆旁。陆行本来想像往常那样把话咽回去，却先问了一句雪杖还撑不撑得住；阿洛把杖尖在石头上磕了磕，说还硬着。"),
    dict(id="n4w-08", path=["loc_pass", "loc_pass_shed"], time="午后",
         weather="风，雪粒", wind="高（山口横风）", light="门缝的光",
         atmosphere="干草堆在角落里",
         present=["char_lu"], visible=["item_lantern", "item_bell"],
         facts=[no_change("f0"), time("f1", 7)],
         narrative="旧马棚里堆着干草，风从门缝里吹进来，草屑在光里打转。陆行靠在门框上等了一会儿，马灯没有亮，铜铃也没有响；棚里什么也没有再发生。"),
    dict(id="n4w-09", path=["loc_pass", "loc_pass_shed"], time="夜",
         weather="风，雪", wind="高（山口横风）", light="马灯",
         atmosphere="药味混着干草味",
         present=["char_lu"], visible=["item_medicine", "item_lantern"],
         facts=[outcome("f0", "char_lu", "task_medicine", "风口岭"),
                sanity("f1", "char_lu", 10, 8, "风口岭"),
                time("f2", 9)],
         narrative="陆行把油纸包着的药粉送到马棚，放在干草边的木箱上。回来时风更硬了，他缩着肩走回驿里；胸口那点发紧的感觉没有散，手指也冻得不听使唤。"),
    dict(id="n4w-10", path=["loc_inn", "loc_inn_hall"], time="夜",
         weather="雪", wind="低（石墙挡风）", light="炭火",
         atmosphere="门一开，雪沫被风卷进来",
         present=["char_lu", "char_shi"],
         visible=["item_rope", "item_charcoal"],
         facts=[moved("f0", "char_shi", "望雪台", "云关驿", "云关驿"),
                appearance("f1", "char_shi", "肩上落了一层雪", "云关驿"),
                time("f2", 7)],
         narrative="石青从望雪台下来，推门进驿时，肩上落了一层雪。他把绳梯靠在门边，抖了抖灰棉袍；陆行看见他眉毛上也结着霜，炭盆的火光在门内晃。"),
    dict(id="n4w-11", path=["loc_inn", "loc_inn_hall"], time="傍晚",
         weather="雪停", wind="低（石墙挡风）", light="炭火",
         atmosphere="屋檐不再滴水",
         present=["char_lu"], visible=["item_tea", "item_charcoal"],
         facts=[no_change("f0"), time("f1", 8)],
         narrative="雪停在傍晚，云关驿的屋檐不再滴水。陆行坐在长桌旁，铜壶里的水已经凉了；门外没有人来，炭盆里的火也只剩下一点暗红。"),
    dict(id="n4w-12", path=["loc_pass", "loc_pass_gate"], time="清晨",
         weather="雪，横风", wind="高（山口横风）", light="灰白",
         atmosphere="驿道被雪埋了一半",
         present=["char_lu", "char_aluo"],
         visible=["item_snowstaff", "item_bell"],
         facts=[moved("f0", "char_aluo", "云关驿", "风口岭", "风口岭"),
                outcome("f1", "char_aluo", "task_snow", "风口岭"),
                time("f2", 9)],
         narrative="阿洛从驿里出来，沿着驿道往风口岭走，把积雪一锹一锹清到路边。雪沫被风吹起来，粘在她的帽檐上；等她直起腰，驿道的石面终于露出一点灰。"),
]


def build(c):
    chars = []
    for eid in c["present"]:
        ch = WORLD["characters"][eid]
        chars.append({"entityId": eid, "name": ch["name"],
                      "personality": ch["personality"],
                      "appearance": ch["appearance"],
                      "inventory": ch["inventory"], "use": "read"})
    root = c["path"][0]
    return {
        "worldId": WORLD["worldId"], "id": c["id"],
        "title": c["id"], "facts": c["facts"],
        "sceneBrief": {"locationId": root, "time": c["time"],
                       "weather": c["weather"], "present": c["present"],
                       "props": [WORLD["items"][x]["name"] for x in c["visible"]],
                       "atmosphere": c["atmosphere"]},
        "perspective": {"type": "protagonist", "entityId": "char_lu",
                        "at": WORLD["locations"][root]["name"]},
        "narrative": c["narrative"], "annotations": [],
        "sceneState": {"locationId": root, "locationPath": c["path"],
                       "time": c["time"], "weather": c["weather"],
                       "wind": c["wind"], "light": c["light"],
                       "present": c["present"],
                       "visibleItems": c["visible"],
                       "atmosphere": c["atmosphere"]},
        "grounding": [], "timeNarrative": "vague",
        "characterContext": chars, "personalityUse": [],
        "contract": "n4-narrative-v0", "split": "holdout",
        "reviewStatus": "frozen-holdout",
    }


def main():
    rows = [build(c) for c in CASES]
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {len(rows)} holdout cases -> {OUT}")


if __name__ == "__main__":
    main()
