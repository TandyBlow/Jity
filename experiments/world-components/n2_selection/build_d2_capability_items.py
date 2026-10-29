# D2 capability items builder (D2 prep, review round 24).
#
# Builds the 8 N3 organisation capability samples pre-registered for D2
# (d1-ai-closure.md section 5): 4 time-placement items (G3) and 4
# two-person shared-event items (G1). The item shape matches the 16-item
# v2 dev set (viewpoint + facts), but the task is n3-plan: the fact list
# IS the selected set, and no must/target/omittable/forbidden labels and
# no hint notes exist. The organisation gold is annotated separately
# (annotation/d2-gold-*.*) and never embedded here.
#
# Surface texts below are hand-written by the implementer; everything
# structural (registries, fact fields, integrity rules) is program-built
# and asserted, following the N4 corpus construction discipline. Cast,
# places and texts are new source groups: they must not reuse B corpus
# strings (check_isolation_d2.py verifies against the frozen pool) and
# must not reuse the 16-item cast (裴行舟/沈拾/顾知白/陆停云/岑半夏...).

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

CHARS = {
    "char_600": "洛九针",
    "char_601": "孟潮生",
    "char_602": "温白山",
    "char_603": "桑晚照",
    "char_604": "阮听澜",
}
LOCS = {
    "loc_600": "潮音渡",
    "loc_601": "铁锚巷",
    "loc_602": "望火楼",
    "loc_603": "苇塘集",
    "loc_604": "老闸口",
}
TIME_UNITS = {"minute"}


def moved(fid, char, frm, to):
    return {"factId": fid, "kind": "moved", "entityId": char,
            "name": CHARS[char], "from": frm, "to": to, "at": to}


def positioned(fid, char, at):
    return {"factId": fid, "kind": "positioned_at", "entityId": char,
            "name": CHARS[char], "at": at}


def task(fid, char, goal, at):
    return {"factId": fid, "kind": "task_achieved", "entityId": char,
            "name": CHARS[char], "goal": goal, "at": at}


def appearance(fid, loc, text):
    return {"factId": fid, "kind": "appearance_changed", "entityId": loc,
            "name": LOCS[loc], "text": text, "at": LOCS[loc]}


def personality(fid, char, text, at):
    return {"factId": fid, "kind": "personality_changed", "entityId": char,
            "name": CHARS[char], "text": text, "at": at}


def sanity(fid, char, frm, to, at):
    return {"factId": fid, "kind": "sanity_changed", "entityId": char,
            "name": CHARS[char], "from": frm, "to": to, "at": at}


def time(fid, amount, unit="minute"):
    return {"factId": fid, "kind": "time", "amount": amount,
            "unit": unit, "at": None}


JOINT_LOCK = "合力把闸门绞上闸槽"
JOINT_CART = "合力把翻倒的药车扶正装好"
JOINT_BOAT = "合力把搁浅的渡船推回深水"
JOINT_PAPER = "合力把瞭望窗的破纸重新糊严"


def rule_at(loc):
    return f"你只知道自己在{loc}亲眼见到的，以及自己的行动与状态"


ITEMS = [
    {
        "itemId": "n3cap-01",
        "viewpoint": {"type": "protagonist", "entityId": "char_600",
                      "name": CHARS["char_600"], "at": "潮音渡",
                      "rule": rule_at("潮音渡")},
        "facts": [
            moved("f1", "char_600", "铁锚巷", "潮音渡"),
            task("f2", "char_600", "把三匹浸水的绸布拧干晾开", "潮音渡"),
            moved("f3", "char_601", "老闸口", "潮音渡"),
            time("f4", 8),
            sanity("f5", "char_601", 12, 10, "潮音渡"),
            appearance("f6", "loc_600", "渡口的石阶被水淹了最下面三级"),
        ],
    },
    {
        "itemId": "n3cap-02",
        "viewpoint": {"type": "protagonist", "entityId": "char_603",
                      "name": CHARS["char_603"], "at": "苇塘集",
                      "rule": rule_at("苇塘集")},
        "facts": [
            time("f1", 15),
            moved("f2", "char_603", "老闸口", "苇塘集"),
            task("f3", "char_603", "把晒场的陈皮翻了一遍", "苇塘集"),
            positioned("f4", "char_604", "苇塘集"),
            personality("f5", "char_604", "变得热络", "苇塘集"),
            appearance("f6", "loc_603", "集口的蓝布幌子换过一面新的"),
        ],
    },
    {
        "itemId": "n3cap-03",
        "viewpoint": {"type": "protagonist", "entityId": "char_602",
                      "name": CHARS["char_602"], "at": "望火楼",
                      "rule": rule_at("望火楼")},
        "facts": [
            positioned("f1", "char_602", "望火楼"),
            task("f2", "char_602", "把火盆里的隔夜炭灰清出去", "望火楼"),
            appearance("f3", "loc_602", "楼板上的响板换过三块新的"),
            moved("f4", "char_601", "老闸口", "望火楼"),
            task("f5", "char_601", "给瞭望窗糊上一层新纸", "望火楼"),
            time("f6", 12),
        ],
    },
    {
        "itemId": "n3cap-04",
        "viewpoint": {"type": "protagonist", "entityId": "char_604",
                      "name": CHARS["char_604"], "at": "潮音渡",
                      "rule": rule_at("潮音渡")},
        "facts": [
            moved("f1", "char_604", "苇塘集", "潮音渡"),
            task("f2", "char_604", "把船板缝里的青苔刮净", "潮音渡"),
            positioned("f3", "char_600", "潮音渡"),
            time("f4", 5),
            task("f5", "char_600", "把晾干的绸布叠好装箱", "潮音渡"),
            appearance("f6", "loc_600", "渡船的新桨架还没有上漆"),
            sanity("f7", "char_602", 13, 12, "潮音渡"),
        ],
    },
    {
        "itemId": "n3cap-05",
        "viewpoint": {"type": "protagonist", "entityId": "char_600",
                      "name": CHARS["char_600"], "at": "老闸口",
                      "rule": rule_at("老闸口")},
        "facts": [
            moved("f1", "char_600", "潮音渡", "老闸口"),
            task("f2", "char_600", JOINT_LOCK, "老闸口"),
            moved("f3", "char_601", "苇塘集", "老闸口"),
            task("f4", "char_601", JOINT_LOCK, "老闸口"),
            task("f5", "char_602", "给更梆上油", "老闸口"),
            appearance("f6", "loc_604", "闸槽里卡着的断桨被清了出去"),
        ],
    },
    {
        "itemId": "n3cap-06",
        "viewpoint": {"type": "protagonist", "entityId": "char_603",
                      "name": CHARS["char_603"], "at": "苇塘集",
                      "rule": rule_at("苇塘集")},
        "facts": [
            positioned("f1", "char_603", "苇塘集"),
            task("f2", "char_603", JOINT_CART, "苇塘集"),
            task("f3", "char_604", JOINT_CART, "苇塘集"),
            moved("f4", "char_604", "潮音渡", "苇塘集"),
            personality("f5", "char_602", "变得焦躁", "苇塘集"),
            appearance("f6", "loc_603", "药摊上两只竹匾摔裂了缝"),
        ],
    },
    {
        "itemId": "n3cap-07",
        "viewpoint": {"type": "protagonist", "entityId": "char_601",
                      "name": CHARS["char_601"], "at": "潮音渡",
                      "rule": rule_at("潮音渡")},
        "facts": [
            moved("f1", "char_601", "铁锚巷", "潮音渡"),
            task("f2", "char_601", JOINT_BOAT, "潮音渡"),
            task("f3", "char_604", JOINT_BOAT, "潮音渡"),
            task("f4", "char_602", JOINT_BOAT, "潮音渡"),
            sanity("f5", "char_604", 11, 13, "潮音渡"),
            appearance("f6", "loc_600", "船底的水线露出一截新漆"),
        ],
    },
    {
        "itemId": "n3cap-08",
        "viewpoint": {"type": "protagonist", "entityId": "char_602",
                      "name": CHARS["char_602"], "at": "望火楼",
                      "rule": rule_at("望火楼")},
        "facts": [
            moved("f1", "char_602", "苇塘集", "望火楼"),
            task("f2", "char_602", JOINT_PAPER, "望火楼"),
            task("f3", "char_600", JOINT_PAPER, "望火楼"),
            task("f4", "char_601", "给旗杆换一根新缆绳", "望火楼"),
            sanity("f5", "char_600", 12, 14, "望火楼"),
            appearance("f6", "loc_602", "旗杆顶端的旧绳还挂在钩上"),
        ],
    },
]


def check_items() -> list:
    problems = []
    time_items = [it["itemId"] for it in ITEMS[:4]]
    coevent_items = [it["itemId"] for it in ITEMS[4:]]
    if len(ITEMS) != 8 or len(time_items) != 4 or len(coevent_items) != 4:
        problems.append("item set must be 8 = 4 time + 4 co-event")
    seen_ids = set()
    for it in ITEMS:
        iid = it["itemId"]
        if iid in seen_ids:
            problems.append(f"{iid}: duplicate itemId")
        seen_ids.add(iid)
        vp = it["viewpoint"]
        if vp.get("entityId") not in CHARS or vp.get("at") not in LOCS.values():
            problems.append(f"{iid}: viewpoint entity/location not in registry")
        if vp.get("rule") != rule_at(vp["at"]):
            problems.append(f"{iid}: viewpoint rule text not the registered pattern")
        facts = it["facts"]
        want = [f"f{i}" for i in range(1, len(facts) + 1)]
        if [f["factId"] for f in facts] != want:
            problems.append(f"{iid}: factIds must be f1..fn in order")
        time_count = 0
        for f in facts:
            if f.get("at") is not None and f["at"] not in LOCS.values():
                problems.append(f"{iid}: {f['factId']} at unknown location {f.get('at')!r}")
            if f["kind"] == "moved":
                if f["from"] not in LOCS.values() or f["to"] not in LOCS.values():
                    problems.append(f"{iid}: {f['factId']} moved endpoint not in registry")
                if f["from"] == f["to"]:
                    problems.append(f"{iid}: {f['factId']} moved from == to")
            elif f["kind"] == "time":
                time_count += 1
                if f["unit"] not in TIME_UNITS or not isinstance(f["amount"], int):
                    problems.append(f"{iid}: {f['factId']} time unit/amount illegal")
            elif f["kind"] in ("task_achieved", "appearance_changed", "personality_changed"):
                if not isinstance(f.get(("goal" if f["kind"] == "task_achieved" else "text")), str) \
                        or len(f.get("goal", f.get("text", ""))) < 4:
                    problems.append(f"{iid}: {f['factId']} surface text too short")
            elif f["kind"] == "sanity_changed":
                if not (isinstance(f["from"], int) and isinstance(f["to"], int)
                        and 0 <= f["from"] <= 20 and 0 <= f["to"] <= 20 and f["from"] != f["to"]):
                    problems.append(f"{iid}: {f['factId']} sanity values illegal")
            elif f["kind"] == "positioned_at":
                pass
            else:
                problems.append(f"{iid}: unknown kind {f['kind']!r}")
        if iid in time_items and time_count != 1:
            problems.append(f"{iid}: time item must carry exactly one time fact, got {time_count}")
        if iid in coevent_items and time_count != 0:
            problems.append(f"{iid}: co-event item must not carry a time fact")
        goals = [f["goal"] for f in facts if f["kind"] == "task_achieved"]
        joint = {g for g in goals if goals.count(g) >= 2}
        if iid in coevent_items and not joint:
            problems.append(f"{iid}: co-event item lacks a shared goal string")
        if iid in time_items and joint:
            problems.append(f"{iid}: time item must not contain a shared goal string")
    return problems


def facts_hash(facts: list) -> str:
    canonical = json.dumps(facts, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    problems = check_items()
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        return 1
    out = HERE / "d2_capability_items.jsonl"
    lines = []
    for it in ITEMS:
        row = {
            "itemId": it["itemId"],
            "task": "n3-plan",
            "split": "dev",
            "batch": "d2",
            "viewpoint": it["viewpoint"],
            "facts": it["facts"],
            "hashes": {"facts": facts_hash(it["facts"])},
        }
        lines.append(json.dumps(row, ensure_ascii=False))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {out.name}: {len(ITEMS)} items")
    for it in ITEMS:
        kinds = [f["kind"] for f in it["facts"]]
        print(f"  {it['itemId']}: {len(kinds)} facts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
