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


def check(row, text):
    reasons = []
    loc = row["input"].split("地点=")[1].splitlines()[0]
    for p in PEOPLE:
        if p in text:
            reasons.append(f"person:{p}")
    for p in PLACES:
        if p in text and p != loc:
            reasons.append(f"place:{p}")
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
    if not (10 <= len(text) <= 48):
        reasons.append(f"length:{len(text)}")
    grams = [text[i:i + 4] for i in range(max(0, len(text) - 3))]
    if grams and max(grams.count(g) for g in set(grams)) >= 2:
        reasons.append("repetition")
    return {"ok": not reasons, "reasons": reasons}
