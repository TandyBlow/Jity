# N4 narrative development corpus v0 (review draft, 2026-11-02).
#
# The user asked N4 to stop being a state verbalizer and become a narrator:
# scene, behaviour and (viewpoint) psychology under the committed facts. This
# generator writes a 12-case REVIEW corpus for that target. It is NOT a
# training set and NOT a holdout:
#   - the world family "n4n-fog-harbor" is newly authored for this draft;
#   - no old C/B row is reused; full isolation checks still run before any
#     training use;
#   - the "outcome" kind and qualitative sanity expression are PROPOSED
#     contract pieces, not yet implemented by N1/N5. The corpus is for the
#     user's review of the target writing and boundaries first.
#
# The corpus intentionally forbids: task titles / quest-log wording, stat
# labels and numbers for sanity/appearance/personality, new named entities,
# items or locations, other characters' inner states, new world-changing
# events, and dialogue that creates commitments. Generic scene props listed
# in the brief may be used; the protagonist's interiority is allowed.
#
# Usage: python experiments/world-components/n4_narrative_dev/write_corpus.py
# Output: world.json, corpus.jsonl, review-checklist.json and
#         design/world-engine-reports/components/n4-narrative-dev.md

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
DOC = REPO / "design" / "world-engine-reports" / "components" / "n4-narrative-dev.md"

from state_data import WORLD_STATE as WORLD, SCENES, PERSONALITY_USE


def F(fid, kind, eid, name, **kw):
    d = {"factId": fid, "kind": kind, "entityId": eid, "name": name}
    d.update(kw)
    return d


def moved(fid, eid, name, frm, to):
    return F(fid, "moved", eid, name, **{"from": frm, "to": to, "at": to,
                                        "source": {"field": "positionSet"}})


def outcome(fid, eid, name, task_id, at):
    t = WORLD["tasks"][task_id]
    return F(fid, "outcome", eid, name, taskId=task_id, goal=t["goal"],
             resultText=t["resultText"], at=at,
             source={"field": "tasksAchieved", "taskId": task_id})


def sanity(fid, eid, name, lo, hi, at):
    return F(fid, "sanity_changed", eid, name, **{"from": lo, "to": hi,
                                                 "at": at,
                                                 "source": {"field": "sanitySet"}})


def appearance(fid, eid, name, text, at):
    return F(fid, "appearance_changed", eid, name, text=text, at=at,
             source={"field": "appearanceChanges"})


def personality(fid, eid, name, text, at):
    return F(fid, "personality_changed", eid, name, text=text, at=at,
             source={"field": "personalityChanges"})


def timef(fid, amount, unit="minute"):
    return F(fid, "time", None, None, amount=amount, unit=unit,
             source={"timeAdvance": True})


def noch(fid):
    return F(fid, "no_change", None, None, scope="全局",
             source={"noChange": True})


def A(text, covers, elaboration):
    return {"text": text, "covers": covers, "elaboration": elaboration}


CASES = [
    {
        "id": "n4n-01", "title": "塔顶的灯芯",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮生巷", "旧灯塔"),
            outcome("f1", "char_shen", "沈砚", "task_lamp", "旧灯塔"),
            sanity("f2", "char_shen", "沈砚", 10, 12, "旧灯塔"),
            timef("f3", 8),
        ],
        "sceneBrief": {
            "locationId": "loc_lighthouse", "location": "旧灯塔·塔顶",
            "time": "夜", "weather": "雾，海风",
            "present": ["char_shen"],
            "props": ["油布包", "铜灯罩", "备用灯芯", "石阶", "火苗"],
            "atmosphere": "风硬，铜灯罩嗡嗡响",
            "allowedElaboration": ["weather", "sensory", "gesture",
                                   "interiority"],
            "hiddenMotivation": ["task_lamp"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "旧灯塔"},
        "narrative": "雾从石阶底下漫上来，沈砚把油布包往怀里按了按，一层一层"
                     "登上旧灯塔。塔顶的风比巷子里硬，吹得铜灯罩嗡嗡作响；他"
                     "换好备用灯芯，火苗重新站稳，胸口那口一直提着的气才慢慢"
                     "落回去。过了一会儿，他才像从黑暗里走出来。",
        "annotations": [
            A("雾从石阶底下漫上来，沈砚把油布包往怀里按了按，一层一层登上旧灯塔。",
              ["f0"], ["weather", "sensory", "gesture"]),
            A("塔顶的风比巷子里硬，吹得铜灯罩嗡嗡作响；他换好备用灯芯，火苗重新"
              "站稳，胸口那口一直提着的气才慢慢落回去。",
              ["f1", "f2"], ["sensory", "interiority"]),
            A("过了一会儿，他才像从黑暗里走出来。",
              ["f3"], ["time", "interiority"]),
        ],
    },
    {
        "id": "n4n-02", "title": "浅滩上的系泊绳",
        "facts": [
            moved("f0", "char_shen", "沈砚", "旧灯塔", "潮渡"),
            outcome("f1", "char_shen", "沈砚", "task_rope", "潮渡"),
            appearance("f2", "char_shen", "沈砚", "外袍下摆结了一层盐霜", "潮渡"),
            timef("f3", 12),
        ],
        "sceneBrief": {
            "locationId": "loc_ferry", "location": "潮渡·浅滩",
            "time": "黎明", "weather": "低潮，海风，湿冷",
            "present": ["char_shen"],
            "props": ["系泊绳", "木桩", "浅滩", "石阶", "外袍"],
            "atmosphere": "黑水退去，泥滩反着冷光",
            "allowedElaboration": ["weather", "sensory", "gesture", "visual"],
            "hiddenMotivation": ["task_rope"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "潮渡"},
        "narrative": "天刚亮，潮渡的黑水退到木桩以下，露出一截被潮水舔白的浅滩。"
                     "沈砚踩着湿滑的石阶下去，把陷在泥里的系泊绳一寸一寸拖回岸"
                     "上；等他直起腰，外袍下摆已经结了一层白花花的盐霜。等他把绳子"
                     "拖回木桩边，手指已经被海风吹得发僵。",
        "annotations": [
            A("天刚亮，潮渡的黑水退到木桩以下，露出一截被潮水舔白的浅滩。",
              [], ["scene", "weather", "sensory"]),
            A("沈砚踩着湿滑的石阶下去，把陷在泥里的系泊绳一寸一寸拖回岸上；"
              "等他直起腰，外袍下摆已经结了一层白花花的盐霜。",
              ["f0", "f1", "f2"], ["behavior", "sensory", "visual"]),
            A("等他把绳子拖回木桩边，手指已经被海风吹得发僵。",
              ["f3"], ["time", "sensory"]),
        ],
    },
    {
        "id": "n4n-03", "title": "雾里的渡船",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮生巷", "潮渡"),
            moved("f1", "char_gu", "顾行舟", "河心", "潮渡"),
            timef("f2", 6),
        ],
        "sceneBrief": {
            "locationId": "loc_ferry", "location": "潮渡",
            "time": "黄昏", "weather": "雾，河面低",
            "present": ["char_shen", "char_gu"],
            "props": ["渡船", "缆绳", "船灯", "木桩", "石阶"],
            "atmosphere": "雾压低河面，船灯只剩一团黄",
            "allowedElaboration": ["weather", "scene", "sensory", "behavior"],
            "hiddenMotivation": ["task_wait"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "潮渡"},
        "narrative": "雾把河面压得很低，潮渡的木桩只剩一截影子。沈砚在石阶尽头"
                     "站了一会儿，才听见船灯从雾里透出来；顾行舟把渡船靠上木桩，"
                     "缆绳在他手里绕了两圈，船身轻轻一磕，水面上的灯影就碎了。"
                     "雾没有散，船总算到了。",
        "annotations": [
            A("雾把河面压得很低，潮渡的木桩只剩一截影子。",
              [], ["weather", "scene"]),
            A("沈砚在石阶尽头站了一会儿，才听见船灯从雾里透出来；",
              ["f0"], ["behavior", "sensory"]),
            A("顾行舟把渡船靠上木桩，缆绳在他手里绕了两圈，船身轻轻一磕，水面"
              "上的灯影就碎了。",
              ["f1"], ["behavior", "sensory"]),
            A("雾没有散，船总算到了。",
              ["f2"], ["time", "weather"]),
        ],
    },
    {
        "id": "n4n-04", "title": "潮汐簿的缺页",
        "facts": [
            outcome("f0", "char_shen", "沈砚", "task_log", "潮汐档案馆"),
            timef("f1", 20),
            moved("f2", "char_atang", "阿棠", "早市", "潮汐档案馆"),
            outcome("f3", "char_atang", "阿棠", "task_paper", "潮汐档案馆"),
        ],
        "sceneBrief": {
            "locationId": "loc_archive", "location": "潮汐档案馆",
            "time": "午后", "weather": "雨",
            "present": ["char_shen", "char_atang"],
            "props": ["潮汐簿", "干纸", "墨", "天窗", "铜灯", "门槛"],
            "atmosphere": "雨点敲天窗，屋里只有笔尖和雨声",
            "allowedElaboration": ["weather", "scene", "sensory", "behavior"],
            "hiddenMotivation": ["task_log", "task_paper"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "潮汐档案馆"},
        "narrative": "雨点密密地敲着档案馆的天窗，沈砚把潮汐簿摊在灯下，缺页的"
                     "边缘毛糙得像被咬过。他照着旧墨迹补完最后一个字，阿棠正好"
                     "推门进来，把一叠干纸放在桌角，鞋底在门槛上蹭了两下。屋里"
                     "只有笔尖和雨声，纸页终于接上了。",
        "annotations": [
            A("雨点密密地敲着档案馆的天窗，沈砚把潮汐簿摊在灯下，缺页的边缘"
              "毛糙得像被咬过。",
              [], ["weather", "scene", "sensory"]),
            A("他照着旧墨迹补完最后一个字，",
              ["f0"], ["behavior"]),
            A("阿棠正好推门进来，把一叠干纸放在桌角，鞋底在门槛上蹭了两下。",
              ["f2", "f3"], ["behavior"]),
            A("屋里只有笔尖和雨声，纸页终于接上了。",
              ["f1"], ["time", "sensory"]),
        ],
    },
    {
        "id": "n4n-05", "title": "雾堤上的钟",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮汐档案馆", "雾堤"),
            outcome("f1", "char_shen", "沈砚", "task_bell", "雾堤"),
            sanity("f2", "char_shen", "沈砚", 12, 9, "雾堤"),
            timef("f3", 4),
        ],
        "sceneBrief": {
            "locationId": "loc_seawall", "location": "雾堤",
            "time": "夜", "weather": "大雾，浪高",
            "present": ["char_shen"],
            "props": ["雾警钟", "钟绳", "铁链", "石阶"],
            "atmosphere": "浪头撞石壁，白沫翻上堤面",
            "allowedElaboration": ["weather", "scene", "sensory", "gesture",
                                   "interiority"],
            "hiddenMotivation": ["task_bell"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "雾堤"},
        "narrative": "雾堤上的石阶被浪花打湿，沈砚摸着冰冷的铁链往上走，鞋底几"
                     "次打滑。他抓住钟绳，把雾警钟一下一下敲响；钟声撞进雾里，"
                     "又被海风撕碎。他的后背全是冷汗，手指抖得几乎握不"
                     "住绳子——直到钟声散尽，他才发觉自己一直屏着呼吸。",
        "annotations": [
            A("雾堤上的石阶被浪花打湿，沈砚摸着冰冷的铁链往上走，鞋底几次"
              "打滑。",
              ["f0"], ["weather", "scene", "sensory", "behavior"]),
            A("他抓住钟绳，把雾警钟一下一下敲响；钟声撞进雾里，又被海风撕碎。",
              ["f1"], ["behavior", "sensory"]),
            A("他的后背全是冷汗，手指抖得几乎握不住绳子——直到钟声"
              "散尽，他才发觉自己一直屏着呼吸。",
              ["f2", "f3"], ["time", "interiority"]),
        ],
    },
    {
        "id": "n4n-06", "title": "抽屉底层的钥匙",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮汐档案馆", "潮生巷"),
            outcome("f1", "char_shen", "沈砚", "task_key", "潮生巷"),
            sanity("f2", "char_shen", "沈砚", 9, 11, "潮生巷"),
            timef("f3", 3),
        ],
        "sceneBrief": {
            "locationId": "loc_alley", "location": "潮生巷·屋内",
            "time": "夜", "weather": "雨",
            "present": ["char_shen"],
            "props": ["抽屉", "旧纸", "备用钥匙", "蜡烛", "木板", "床沿",
                      "桌子"],
            "atmosphere": "雨声不停，屋里只有一点烛光",
            "allowedElaboration": ["weather", "scene", "sensory", "gesture",
                                   "interiority"],
            "hiddenMotivation": ["task_key"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "潮生巷"},
        "narrative": "潮生巷的雨还没停，沈砚摸黑进了屋，点亮桌角的蜡烛。抽屉最"
                     "底层压着一层旧纸，他一张张掀开，终于摸到那把冰凉的备用钥"
                     "匙；铜齿磕在木板上，发出很轻的一声。他攥着钥匙坐"
                     "到床沿，才发现肩膀一直绷得发酸。",
        "annotations": [
            A("潮生巷的雨还没停，沈砚摸黑进了屋，点亮桌角的蜡烛。",
              ["f0"], ["weather", "scene", "behavior"]),
            A("抽屉最底层压着一层旧纸，他一张张掀开，终于摸到那把冰凉的备用"
              "钥匙；铜齿磕在木板上，发出很轻的一声。",
              ["f1"], ["behavior", "sensory"]),
            A("他攥着钥匙坐到床沿，才发现肩膀一直绷得发酸。",
              ["f2", "f3"], ["time", "interiority"]),
        ],
    },
    {
        "id": "n4n-07", "title": "档案馆的雨声",
        "facts": [
            noch("f0"),
            timef("f1", 15),
        ],
        "sceneBrief": {
            "locationId": "loc_archive", "location": "潮汐档案馆",
            "time": "夜", "weather": "雨渐匀",
            "present": ["char_shen"],
            "props": ["潮汐簿", "冷茶", "灯", "灯芯", "门"],
            "atmosphere": "雨声、灯芯、凉茶；没有脚步",
            "allowedElaboration": ["weather", "scene", "sensory", "interiority"],
            "hiddenMotivation": [],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "潮汐档案馆"},
        "narrative": "档案馆的雨声渐渐匀了，灯芯烧出一小截黑灰。沈砚把潮汐簿合"
                     "上，又翻开，指尖停在同一行字上；桌上的茶早就凉了，杯口凝"
                     "着一圈水汽。门外一直没有脚步声，他也就没有起身。",
        "annotations": [
            A("档案馆的雨声渐渐匀了，灯芯烧出一小截黑灰。",
              [], ["weather", "scene"]),
            A("沈砚把潮汐簿合上，又翻开，指尖停在同一行字上；桌上的茶早就凉了，"
              "杯口凝着一圈水汽。",
              ["f0"], ["behavior", "sensory"]),
            A("门外一直没有脚步声，他也就没有起身。",
              ["f0", "f1"], ["time", "interiority"]),
        ],
    },
    {
        "id": "n4n-08", "title": "早市的鱼鳞",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮生巷", "早市"),
            outcome("f1", "char_atang", "阿棠", "task_fish", "早市"),
            appearance("f2", "char_shen", "沈砚", "衣摆沾了鱼鳞和泥水", "早市"),
            timef("f3", 5),
        ],
        "sceneBrief": {
            "locationId": "loc_market", "location": "早市",
            "time": "清晨", "weather": "潮湿，白汽",
            "present": ["char_shen", "char_atang"],
            "props": ["帆布棚", "鱼筐", "案板", "银鳞鱼", "石板", "外袍"],
            "atmosphere": "白汽、鱼鳞、泥水、嘈杂",
            "allowedElaboration": ["scene", "sensory", "behavior", "visual"],
            "hiddenMotivation": ["task_fish"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "早市"},
        "narrative": "早市的帆布棚下全是白汽，鱼鳞在石板上闪成一片碎光。沈砚从"
                     "人缝里挤过去，正看见阿棠抱着一筐银鳞鱼往案板上送，鱼尾拍"
                     "得筐沿啪啪响；他往旁边让了一步，衣摆还是沾上了鱼鳞和泥水。"
                     "白汽还没有散，他低头看了一眼衣摆，又往前走了。",
        "annotations": [
            A("早市的帆布棚下全是白汽，鱼鳞在石板上闪成一片碎光。",
              [], ["scene", "sensory"]),
            A("沈砚从人缝里挤过去，正看见阿棠抱着一筐银鳞鱼往案板上送，鱼尾"
              "拍得筐沿啪啪响；他往旁边让了一步，衣摆还是沾上了鱼鳞和泥水。",
              ["f0", "f1", "f2"], ["behavior", "sensory", "visual"]),
            A("白汽还没有散，他低头看了一眼衣摆，又往前走了。",
              ["f3"], ["time", "behavior"]),
        ],
    },
    {
        "id": "n4n-09", "title": "灯塔上的那句话",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮渡", "旧灯塔"),
            personality("f1", "char_shen", "沈砚", "不再把话咽回去", "旧灯塔"),
            outcome("f2", "char_ye", "叶知微", "task_wipe", "旧灯塔"),
            timef("f3", 7),
        ],
        "sceneBrief": {
            "locationId": "loc_lighthouse", "location": "旧灯塔·旋梯",
            "time": "傍晚", "weather": "海风",
            "present": ["char_shen", "char_ye"],
            "props": ["旋梯", "擦铜油", "抹布", "铜框", "灯罩", "油壶", "灯芯"],
            "atmosphere": "擦铜油味，海光从窄窗照进来",
            "allowedElaboration": ["scene", "sensory", "behavior"],
            "hiddenMotivation": ["task_wipe", "task_lamp"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "旧灯塔"},
        "narrative": "旧灯塔的旋梯里有股擦铜油的味道。叶知微正踮着脚擦灯罩，抹布"
                     "在铜框上转出一圈亮光；沈砚站在门口，本来想好的客气话到了"
                     "嘴边，却没有像往常那样咽回去，而是直接问她灯芯还够不够用。"
                     "灯罩被擦得透亮，他的话也比平时多了一句。",
        "annotations": [
            A("旧灯塔的旋梯里有股擦铜油的味道。",
              [], ["scene", "sensory"]),
            A("叶知微正踮着脚擦灯罩，抹布在铜框上转出一圈亮光；",
              ["f2"], ["behavior", "sensory"]),
            A("沈砚站在门口，本来想好的客气话到了嘴边，却没有像往常那样咽回去，"
              "而是直接问她灯芯还够不够用。",
              ["f0", "f1"], ["behavior"]),
            A("灯罩被擦得透亮，他的话也比平时多了一句。",
              ["f1", "f3"], ["time"]),
        ],
    },
    {
        "id": "n4n-10", "title": "雨里的潮生巷",
        "facts": [
            moved("f0", "char_shen", "沈砚", "旧灯塔", "潮生巷"),
            sanity("f1", "char_shen", "沈砚", 11, 12, "潮生巷"),
            timef("f2", 6),
        ],
        "sceneBrief": {
            "locationId": "loc_alley", "location": "潮生巷",
            "time": "夜", "weather": "雨渐小",
            "present": ["char_shen"],
            "props": ["纸灯笼", "湿石板", "油纸伞", "水洼", "墙根"],
            "atmosphere": "灯笼光落在湿石板上，巷子很静",
            "allowedElaboration": ["weather", "scene", "sensory", "behavior",
                                   "interiority"],
            "hiddenMotivation": [],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "潮生巷"},
        "narrative": "雨势小了些，潮生巷的纸灯笼一盏接一盏亮着，光落在湿石板上，"
                     "像一层薄薄的金箔。沈砚收了伞，沿着墙根慢慢往回走；鞋底踩"
                     "过水洼，凉气从裤脚钻上来，他却觉得胸口比出门时松了一点。"
                     "巷子不长，他走得比平时慢。",
        "annotations": [
            A("雨势小了些，潮生巷的纸灯笼一盏接一盏亮着，光落在湿石板上，像"
              "一层薄薄的金箔。",
              [], ["weather", "scene", "sensory"]),
            A("沈砚收了伞，沿着墙根慢慢往回走；鞋底踩过水洼，凉气从裤脚钻"
              "上来，他却觉得胸口比出门时松了一点。",
              ["f0", "f1"], ["behavior", "sensory", "interiority"]),
            A("巷子不长，他走得比平时慢。",
              ["f2"], ["time", "behavior"]),
        ],
    },
    {
        "id": "n4n-11", "title": "雾堤上的警示灯",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮渡", "雾堤"),
            outcome("f1", "char_han", "韩渡", "task_bell_rope", "雾堤"),
            outcome("f2", "char_shen", "沈砚", "task_warnlamp", "雾堤"),
            timef("f3", 4),
            sanity("f4", "char_shen", "沈砚", 12, 10, "雾堤"),
        ],
        "sceneBrief": {
            "locationId": "loc_seawall", "location": "雾堤",
            "time": "夜", "weather": "雾，风横，浪高",
            "present": ["char_shen", "char_han"],
            "props": ["钟架", "钟绳", "警示灯", "铁皮", "石壁", "火苗"],
            "atmosphere": "浪撞石壁，白沫翻上堤面",
            "allowedElaboration": ["weather", "scene", "sensory", "behavior",
                                   "interiority"],
            "hiddenMotivation": ["task_bell_rope", "task_warnlamp"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "雾堤"},
        "narrative": "雾堤上的风比潮渡更横，浪头撞在石壁上，碎成一片白沫。韩渡"
                     "蹲在钟架下，把松脱的钟绳重新系紧；沈砚扶正被风吹歪的警示"
                     "灯，灯罩里的火苗晃了两下，才勉强稳住。他的掌心被"
                     "铁皮冰得发麻，心里那点没来由的慌却越压越重。",
        "annotations": [
            A("雾堤上的风比潮渡更横，浪头撞在石壁上，碎成一片白沫。",
              [], ["weather", "scene", "sensory"]),
            A("韩渡蹲在钟架下，把松脱的钟绳重新系紧；",
              ["f1"], ["behavior"]),
            A("沈砚扶正被风吹歪的警示灯，灯罩里的火苗晃了两下，才勉强稳住。",
              ["f0", "f2"], ["behavior", "sensory"]),
            A("他的掌心被铁皮冰得发麻，心里那点没来由的慌却越压越重。",
              ["f3", "f4"], ["time", "interiority"]),
        ],
    },
    {
        "id": "n4n-12", "title": "潮渡的船灯",
        "facts": [
            moved("f0", "char_shen", "沈砚", "潮生巷", "潮渡"),
            moved("f1", "char_gu", "顾行舟", "河心", "潮渡"),
            timef("f2", 9),
            personality("f3", "char_shen", "沈砚", "开始愿意等", "潮渡"),
        ],
        "sceneBrief": {
            "locationId": "loc_ferry", "location": "潮渡",
            "time": "夜", "weather": "雾",
            "present": ["char_shen", "char_gu"],
            "props": ["船灯", "木桩", "渡船", "缆绳"],
            "atmosphere": "雾重，船灯只剩一团黄",
            "allowedElaboration": ["weather", "scene", "behavior", "sensory"],
            "hiddenMotivation": ["task_wait"],
        },
        "perspective": {"type": "protagonist", "entityId": "char_shen",
                        "at": "潮渡"},
        "narrative": "潮渡的雾到夜里更重，船灯只剩一团模糊的黄。沈砚靠在木桩上，"
                     "没有像从前那样来回踱步；顾行舟的渡船从河心慢慢靠过来，船"
                     "头切开水面，缆绳甩上木桩时发出一声闷响。他一直没"
                     "有催，等船停稳，才向前走了一步。",
        "annotations": [
            A("潮渡的雾到夜里更重，船灯只剩一团模糊的黄。",
              [], ["weather", "scene"]),
            A("沈砚靠在木桩上，没有像从前那样来回踱步；",
              ["f0", "f3"], ["behavior"]),
            A("顾行舟的渡船从河心慢慢靠过来，船头切开水面，缆绳甩上木桩时"
              "发出一声闷响。",
              ["f1"], ["behavior", "sensory"]),
            A("他一直没有催，等船停稳，才向前走了一步。",
              ["f2", "f3"], ["time", "behavior"]),
        ],
    },
]


def check_case(c):
    facts = {f["factId"] for f in c["facts"]}
    covered = set()
    narrative = c["narrative"]
    for a in c["annotations"]:
        if a["text"] not in narrative:
            raise SystemExit(f"{c['id']}: annotation text not in narrative: "
                             f"{a['text'][:40]}")
        covered.update(a["covers"])
    time_facts = {f["factId"] for f in c["facts"] if f["kind"] == "time"}
    required = facts - time_facts
    if covered != required:
        raise SystemExit(f"{c['id']}: coverage mismatch "
                         f"missing={required - covered} extra={covered - required}")
    present_ids = set(c["sceneState"]["present"])
    ctx_ids = {x["entityId"] for x in c.get("characterContext", [])}
    if present_ids - ctx_ids:
        raise SystemExit(f"{c['id']}: present characters missing from "
                         f"characterContext: {present_ids - ctx_ids}")
    if "任务" in narrative or "目标" in narrative or "理智" in narrative \
            or "精神值" in narrative or "外貌" in narrative \
            or "个性" in narrative or "位置" in narrative:
        raise SystemExit(f"{c['id']}: forbidden stat/task wording")
    if "完成了任务" in narrative or "任务达成" in narrative:
        raise SystemExit(f"{c['id']}: task-label wording")
    for g in c["grounding"]:
        if g["detail"] not in narrative:
            raise SystemExit(f"{c['id']}: grounding detail not in narrative: "
                             f"{g['detail']}")


def main() -> int:
    for c in CASES:
        c.update(SCENES[c["id"]])
        time_facts = {f["factId"] for f in c["facts"] if f["kind"] == "time"}
        c["timeNarrative"] = ("vague" if c["id"] in ("n4n-01", "n4n-02")
                              else "omitted")
        for a in c["annotations"]:
            if any(fid in time_facts for fid in a["covers"]):
                a["covers"] = [fid for fid in a["covers"]
                               if fid not in time_facts]
                a["elaboration"] = [e for e in a["elaboration"]
                                    if e != "time"]
                if not any(e.startswith("time-") for e in a["elaboration"]):
                    a["elaboration"].append("time-" + c["timeNarrative"])
        c["characterContext"] = [
            {"entityId": eid,
             "name": WORLD["characters"][eid]["name"],
             "personality": WORLD["characters"][eid]["personality"],
             "appearance": WORLD["characters"][eid]["appearance"],
             "inventory": WORLD["characters"][eid].get("inventory", []),
             "use": "read"}
            for eid in c["sceneState"]["present"]]
        c["personalityUse"] = PERSONALITY_USE.get(c["id"], [])
        check_case(c)
    world_path = HERE / "world.json"
    corpus_path = HERE / "corpus.jsonl"
    review_path = HERE / "review-checklist.json"
    world_path.write_text(json.dumps(WORLD, ensure_ascii=False, indent=1)
                          + "\n", encoding="utf-8", newline="\n")
    corpus_path.write_text("".join(
        json.dumps({"worldId": WORLD["worldId"], **c,
                    "contract": "n4-narrative-v0",
                    "split": "dev-review",
                    "reviewStatus": "approved"}, ensure_ascii=False) + "\n"
        for c in CASES), encoding="utf-8", newline="\n")
    review = {c["id"]: {"verdict": "pass", "issues": [],
                        "notes": "用户审阅通过（2026-11-02）"}
              for c in CASES}
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=1)
                           + "\n", encoding="utf-8", newline="\n")
    _write_review_md(world_path, corpus_path)
    print(f"wrote {len(CASES)} cases -> {corpus_path}")
    print(f"review sheet -> {DOC}")
    return 0


def _fact_line(f):
    kind = f["kind"]
    if kind == "moved":
        return f"{f['from']} → {f['to']}（at {f['at']}）"
    if kind == "outcome":
        return (f"surface=“{f['resultText']}”；hidden goal=“{f['goal']}”"
                f"（{f['taskId']}）")
    if kind == "sanity_changed":
        return f"{f['from']} → {f['to']}（内部数值，叙事不打印）"
    if kind == "time":
        return (f"{f['amount']} {f['unit']}（内部；叙事不写具体时长，"
                f"可省略/模糊）")
    if kind == "appearance_changed":
        return f"内部文本=“{f['text']}”；叙事用可见细节"
    if kind == "personality_changed":
        return f"内部文本=“{f['text']}”；叙事用行为表现"
    if kind == "no_change":
        return f"scope={f.get('scope')}"
    return json.dumps(f, ensure_ascii=False)


def _write_review_md(world_path, corpus_path):
    world = json.loads(world_path.read_text(encoding="utf-8"))
    cases = [json.loads(l) for l in
             corpus_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def locname(x):
        if x in world["locations"]:
            return world["locations"][x]["name"]
        for loc in world["locations"].values():
            for sub in loc.get("sublocations", []):
                if sub["id"] == x:
                    return sub["name"]
        return x

    def itemname(x):
        return world["items"].get(x, {}).get("name", x)

    def charname(x):
        return world["characters"].get(x, {}).get("name", x)
    lines = [
        "# N4 叙事开发语料 v0（已审通过）",
        "",
        "日期：2026-11-02。目标：N4 不再逐条复述状态，而是在**已提交事实**"
        "的约束下写场景、行为与视角人物心理。",
        "",
        "这是一份 **12 例已审通过的叙事开发集**，不是训练集，也不是留出集；"
        "世界族 `n4n-fog-harbor` 为本稿新写，不复用旧 C/B 行。"
        "`outcome` 类型与“用心理/行为表达理智变化”是**提议中的契约**，"
        "当前 N1/N5 尚未实现；先请审文字与边界，再改契约。",
        "",
        "## 允许 / 禁止",
        "",
        "| 允许 | 禁止 |",
        "| --- | --- |",
        "| 与地点/天气/道具 brief 一致的环境细节 | 新增具名人物、物品、地点 |",
        "| 与事实一致的动作、表情、姿态 | 新增会改变世界状态的事件/任务/目标 |",
        "| 视角人物（沈砚）的心理 | 其他角色的内心（只能写可见行为） |",
        "| 连接、节奏、感官细节 | 任务标题/quest log 措辞；理智/外貌/个性/位置的"
        "数值面板 |",
        "| brief/物品表列出的道具；角色个性可读取 | 产生承诺的具体对话 |",
        "",
        "任务 `goal` 只作隐藏动机，不能出现在正文；表面只写 `resultText`。"
        "理智变化用心理/生理反应表达，不打印数值。外貌/个性变化用可见细节"
        "与行为表达，不打印字段名。",
        "",
        "本稿把每个具体名词都绑定到世界状态/场景状态/物品表；身体部位（手、"
        "肩、后背等）属于人物自身，不再单列；比喻（如“金箔”）标注为 "
        "`narrative.simile`，不作世界事实。场景可覆盖物品位置（`itemOverrides`），"
        "默认位置见物品表。",
        "",
        "## 世界",
        "",
    ]
    lines += ["### 地点", ""]
    for lid, loc in world["locations"].items():
        lines.append(f"- **{loc['name']}**（{lid}）：{loc['appearance']}")
        lines.append(f"  - 小地点：" + "；".join(
            f"{s['name']}（level {s['level']}，{s['appearance']}）"
            for s in loc.get("sublocations", [])))
        lines.append(f"  - 特征：{', '.join(loc.get('features', []))}；"
                     f"风：{loc.get('windExposure', '-')}")
    lines += ["", "### 物品", ""]
    for iid, it in world["items"].items():
        pos = json.dumps(it.get("position"), ensure_ascii=False)
        after = ("；after=" + json.dumps(it["afterPosition"],
                                         ensure_ascii=False)
                 if it.get("afterPosition") else "")
        state = ("；state=" + json.dumps(it["state"], ensure_ascii=False)
                 if it.get("state") else "")
        lines.append(f"- **{it['name']}**（{iid}）：{it['appearance']}；"
                     f"position={pos}{after}{state}")
    lines += ["", "### 人物", ""]
    for cid, ch in world["characters"].items():
        lines.append(f"- **{ch['name']}**（{cid}）：{ch['appearance']}；"
                     f"性格：{ch['personality']}；"
                     f"inventory={', '.join(ch.get('inventory', [])) or '无'}")
    lines += ["", "### 任务（隐藏动机，不可打印）", ""]
    for tid, t in world["tasks"].items():
        lines.append(f"- `{tid}`：{t['goal']}（owner {t['owner']}；"
                     f"surface resultText=“{t['resultText']}”）")
    lines += ["", "## 审阅方式", "",
              "每例检查：事实是否全覆盖；有无任务标题；有无新增具名实体/物品/"
              "地点；有无他人内心；有无新增世界事件；场景/行为/心理是否自然；"
              "视角是否一致；有无数值面板。结论写回 `review-checklist.json`。",
              ""]
    for c in cases:
        lines += [f"## {c['id']} · {c['title']}", "",
                  "**Facts**", "",
                  "| factId | kind | 主体 | 内容 |",
                  "| --- | --- | --- | --- |"]
        for f in c["facts"]:
            lines.append(f"| {f['factId']} | {f['kind']} | "
                         f"{f.get('name') or '-'} | {_fact_line(f)} |")
        ss = c["sceneState"]
        brief = c["sceneBrief"]
        path = " → ".join(locname(x) for x in ss["locationPath"])
        lines += ["", "**Scene state**", "",
                  f"- 地点路径：{path}",
                  f"- 时间：{ss['time']}；天气：{ss['weather']}；"
                  f"风：{ss['wind']}；光：{ss['light']}"
                  + (f"；水：{ss['water']}" if ss.get("water") else ""),
                  f"- 在场：{', '.join(charname(x) for x in ss['present'])}；"
                  f"可见物品：{', '.join(itemname(x) for x in ss['visibleItems']) or '无'}",
                  f"- 氛围：{ss['atmosphere']}",
                  f"- 时间事实：内部；叙事={c['timeNarrative']}"
                  "（不写具体时长）",
                  (f"- 场景物品覆盖："
                   + "；".join(f"{itemname(k)} → {json.dumps(v, ensure_ascii=False)}"
                              for k, v in ss.get("itemOverrides", {}).items())
                   if ss.get("itemOverrides") else "- 场景物品覆盖：无"),
                  f"- 隐藏动机：{', '.join(brief['hiddenMotivation']) or '无'}",
                  "", "**Character context（读取；不要求体现）**", "",
                  "| 角色 | 个性（读取） | 外貌（读取） | inventory |",
                  "| --- | --- | --- | --- |"]
        for cc in c["characterContext"]:
            lines.append(f"| {cc['name']} | {cc['personality']} | "
                         f"{cc['appearance']} | "
                         f"{', '.join(cc['inventory']) or '无'} |")
        lines += ["", "本场使用（可无；只影响可见行为，不写他人内心）：", ""]
        for u in c["personalityUse"]:
            lines.append(f"- {u}")
        lines += ["", "**Grounding（每个具体名词 → 状态）**", "",
                  "| 细节 | 状态来源 | 值 |",
                  "| --- | --- | --- |"]
        for g in c["grounding"]:
            lines.append(f"| {g['detail']} | {g['source']} | {g['value']} |")
        lines += ["", "**Narrative**", "", "> " + c["narrative"], "",
                  "**Annotations**", "",
                  "| 文本 | covers | 允许的展开 |",
                  "| --- | --- | --- |"]
        for a in c["annotations"]:
            lines.append(f"| {a['text']} | {', '.join(a['covers']) or '—'} | "
                         f"{', '.join(a['elaboration'])} |")
        lines += ["", "**Review**", "",
                  "- [ ] 事实全覆盖",
                  "- [ ] 无任务标题/quest 措辞",
                  "- [ ] 无新增具名实体/物品/地点",
                  "- [ ] 无他人内心（仅可见行为）",
                  "- [ ] 无新增世界事件/承诺性对话",
                  "- [ ] 场景/行为/心理自然",
                  "- [ ] 视角一致",
                  "- [ ] 无理智/外貌/个性/位置数值面板",
                  "- [ ] 每个具体名词都有状态依据（Grounding 表）",
                  "- [ ] 时间不出现具体时长（可模糊/省略）",
                  "- [ ] 角色个性已读取（不要求体现）",
                  ""]
    lines += ["## 已知缺口（先记录，不在审阅稿里假装完成）", "",
              "1. 当前 N1 没有 `outcome`/`resultText`，任务完成只有 `goal`；"
              "本稿假定上游提供结果文本。",
              "2. 当前 N5 的 G1 对理智/外貌/个性使用字段/数值式匹配；"
              "G3 要求精确时间值。本稿把时间事实留内部、正文只模糊或省略，"
              "用心理/行为/视觉表达；G1/G3 都需要新的语义/人工核对口径。",
              "3. 本稿未跑模型、未训练、未做完整 B 冻结池隔离；"
              "训练前须重新跑隔离与预登记。",
              "4. 对话暂不纳入（避免模型替角色做出承诺）；如需对话，"
              "另立契约。",
              "5. 当前 N4 renderer 仍只读事实行；`characterContext` 与"
              "“时间模糊/省略”是提议的 N4 输入/评测口径，尚未接线。",
              ""]
    DOC.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    raise SystemExit(main())
