# Validate the verbalizer pairs: subject binding, result coverage, no
# numbers/task wording, no new named people or places.
# Run: python -X utf8 experiments/world-components/n4_narrative_dev/validate_verbalizer.py

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent

PEOPLE = set()
PLACES = set()
FURNITURE = set()
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
    for it in world["items"].values():
        FURNITURE.add(it["name"])

NUM = re.compile(r"[0-9０-９]+(分钟|小时|秒|点|刻|步)"
                 r"|[一二三四五六七八九十百千]+(分钟|小时|刻钟)")
BAD_WORDS = ["任务", "goal", "resultText", "taskId", "攻略", "提示",
             "完成了任务", "目标达成"]


def place_hit(text, place):
    if place in text:
        return True
    tail = place[-2:]
    return len(tail) == 2 and tail in text


def core_hit(text, phrase):
    chars = [c for c in phrase if "\u4e00" <= c <= "\u9fff"]
    if not chars:
        return 1.0
    return sum(1 for c in chars if c in text) / len(chars)


def check(row):
    t = row["target"]
    kind = row["kind"]
    sig = row["signature"]
    problems = []
    if kind == "no_change":
        if not any(k in t for k in ("没有", "什么", "再发生", "安静", "没有别的")):
            problems.append("no no-change wording")
    else:
        name = sig[1]
        if name not in t:
            problems.append(f"missing subject {name}")
        pov = re.search(r"视角=([^；]+)", row["input"]).group(1)
        for p in PEOPLE:
            if p in t and p not in (name, pov):
                problems.append(f"extra person {p}")
        for p in PLACES:
            if p in t and not place_hit(row["input"], p):
                problems.append(f"extra place {p}")
        if kind == "moved":
            if not place_hit(t, sig[3]):
                problems.append(f"missing destination {sig[3]}")
        elif kind == "outcome":
            hit = core_hit(t, sig[2])
            if hit < 0.5:
                problems.append(f"weak result coverage {hit:.2f}")
        elif kind in ("appearance", "personality"):
            hit = core_hit(t, sig[2])
            if hit < 0.4:
                problems.append(f"weak text coverage {hit:.2f}")
        elif kind == "sanity_changed":
            if not any(k in t for k in ("呼吸", "胸口", "手指", "心跳", "气")):
                problems.append("no bodily signal")
    if NUM.search(t):
        problems.append("has duration/number")
    for w in BAD_WORDS:
        if w in t:
            problems.append(f"has task word {w}")
    if len(t) > 42:
        problems.append(f"too long {len(t)}")
    return problems


def main():
    bad = 0
    for name in ("verbalizer_pairs.jsonl", "verbalizer_holdout.jsonl"):
        rows = [json.loads(l) for l in
                (HERE / name).read_text(encoding="utf-8").splitlines()
                if l.strip()]
        for r in rows:
            p = check(r)
            if p:
                bad += 1
                print(name, r["pairId"], p, "|", r["target"])
        print(name, len(rows), "rows")
    print("bad:", bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
