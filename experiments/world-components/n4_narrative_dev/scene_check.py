# Deterministic checker for scene sentences (environment + POV interiority).
# Shared by validate_scene_corpus.py and train_scene.py.

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent

PEOPLE, PLACES, FURNITURE = set(), set(), set()
for w in ("world.json", "holdout_world.json"):
    world = json.loads((HERE / w).read_text(encoding="utf-8"))
    for ch in world["characters"].values():
        PEOPLE.add(ch["name"])
    for loc in world["locations"].values():
        PLACES.add(loc["name"])
        FURNITURE.update(loc.get("features", []))
        for s in loc.get("sublocations", []):
            FURNITURE.add(s["name"])
            FURNITURE.update(s.get("features", []))

NUM = re.compile(r"[0-9０-９]+(分钟|小时|秒|点|刻|步)"
                 r"|[一二三四五六七八九十百千]+(分钟|小时|刻钟)")
BAD_WORDS = ["任务", "goal", "resultText", "taskId", "攻略", "提示"]
# scene sentences must not narrate events; these are action verbs
ACTION_VERBS = ["推开", "走进", "回到", "坐到", "拿起", "放下", "搬",
                "拖", "擦掉", "系紧", "敲响", "扶正", "翻出", "换好",
                "送到", "挂到", "清开", "开口", "问"]
SCENE_TOKENS = ["雨", "雾", "雪", "风", "光", "灯", "炭", "潮", "浪",
                "水", "冰", "石", "纸", "铜", "木", "草", "汽", "声"]


AGENT_NOUNS = ["风", "雨", "雪", "雾", "浪", "光", "灯", "潮", "汽", "水"]
PASSIVE_AGENTS = ["风", "雪", "雨", "雾", "浪", "鞋底", "石墙",
                  "浪沫", "蒸汽", "潮气", "撞", "水", "光"]


def bad_ba_construction(text):
    """把-sentences: the agent must be a weather/light noun (风把雪吹开 ok,
    木门把木门挡在外面 not). Reject if the 把-agent is not one of them."""
    for i, ch in enumerate(text):
        if ch != "把" or i == 0:
            continue
        agent = text[max(0, i - 3):i]
        if not any(a in agent for a in AGENT_NOUNS):
            return True
    return False


def bad_bei_construction(text):
    """被-sentences: the agent after 被 must be a scene force."""
    for i, ch in enumerate(text):
        if ch != "被" or i + 3 > len(text):
            continue
        agent = text[i + 1:i + 6]
        if not any(a in agent for a in PASSIVE_AGENTS):
            return True
    return False


def repeated_noun(text):
    """Any 2-character span used twice reads as stutter (木门…木门), except
    Chinese reduplication such as 一阵一阵 / 一片一片."""
    for j in range(max(0, len(text) - 1)):
        g = text[j:j + 2]
        if len(g) < 2:
            continue
        pos = [i for i in range(len(text) - 1) if text[i:i + 2] == g]
        if len(pos) < 2:
            continue
        redup = any(text[i:i + 4] == g + g for i in pos)
        if not redup:
            return True
    return False


def check(row, text):
    reasons = []
    loc = row["input"].split("地点=")[1].splitlines()[0]
    scene = row["input"].split("场景=")[1].splitlines()[0]
    for p in PEOPLE:
        if p in text:
            reasons.append(f"person:{p}")
    for p in PLACES:
        if p in text and p != loc:
            reasons.append(f"place:{p}")
    if "雪" in scene and "雨" in text:
        reasons.append("weather-mismatch")
    if "雨" in scene and "雪" in text:
        reasons.append("weather-mismatch")
    if NUM.search(text):
        reasons.append("has-duration")
    for w in BAD_WORDS:
        if w in text:
            reasons.append(f"task-word:{w}")
    for v in ACTION_VERBS:
        if v in text:
            reasons.append(f"event-verb:{v}")
    if not any(t in text for t in SCENE_TOKENS):
        reasons.append("no-scene-token")
    if bad_ba_construction(text):
        reasons.append("bad-ba-agent")
    if bad_bei_construction(text):
        reasons.append("bad-bei-agent")
    if repeated_noun(text):
        reasons.append("repeated-noun")
    if not (10 <= len(text) <= 48):
        reasons.append(f"length:{len(text)}")
    grams = [text[i:i + 4] for i in range(max(0, len(text) - 3))]
    if grams and max(grams.count(g) for g in set(grams)) >= 2:
        reasons.append("repetition")
    return {"ok": not reasons, "reasons": reasons}
