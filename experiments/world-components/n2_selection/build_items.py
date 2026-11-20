# N2 content-selection items (v2, review round 19 corrections).
#
# Fixes over v1 (kept as items-v1.jsonl for traceability):
#  a. IDENTITY CONSISTENCY: the viewpoint entity is the actor of its own
#     facts — same entityId AND same name (v1 could pair viewpoint char_401
#     with actor char_480).
#  b. FACT LOCATIONS: every fact carries `at` (where it happened / what it is
#     about); a global time advance carries at=None. Visibility is therefore
#     computable from data, not from a label.
#  c. VIEWPOINT IS COMPLETE: type + person + entityId + current location +
#     the rule text handed to a model. Models receive all of it.
#  d. LABELS ARE DERIVED, NEVER AUTHORED: must / forbidden / omittable come
#     from the rule below, and `target` is must plus the facts a narrator
#     would surface. Arms may NOT read labels (a separate reference arm does,
#     labelled as such).
#
# Visibility rule (the definition the judge uses):
#   omniscient            -> everything visible
#   kind == "time"        -> visible (global)
#   entityId == viewpoint -> visible (one's own action/state)
#   fact.at == vp.at      -> visible
#   otherwise             -> POV-inaccessible (forbidden)
#
# Isolation: third vocabulary, disjoint from the N4 corpus cast and the frozen
# N4 holdout cast; checked by check_isolation.py against B's archives.
#
# Usage: python experiments/world-components/n2_selection/build_items.py
# Output: experiments/world-components/n2_selection/items.jsonl (v2)

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "items.jsonl"

NAMES = ["裴行舟", "沈拾", "岑半夏", "顾知白", "陆停云", "白蘅"]
LOCS = ["石阶码头", "旧钟铺", "半窗书舍", "竹影茶棚", "西栅桥", "瓦窑"]
TASKS = ["把船灯挂上桅杆", "补好瓦窑的顶棚", "把账簿送回半窗书舍",
         "收好茶棚的坐垫", "修西栅桥的踏板", "清点旧钟铺的存货"]
APPEAR = ["檐角的风铃褪了色", "门前的石阶塌了一角", "窗纸被风戳了个洞",
          "柜台上的铜锁生了锈", "墙根的青苔爬上了半尺", "梁上的吊绳磨细了"]
PERS = ["变得寡言", "变得爽快", "变得谨慎", "变得急躁"]

CHAR_ID = {n: f"char_{400 + i:03d}" for i, n in enumerate(NAMES)}
LOC_ID = {l: f"loc_{400 + i:03d}" for i, l in enumerate(LOCS)}


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def visible(vp: dict, fact: dict) -> bool:
    if vp["type"] == "omniscient":
        return True
    if fact["kind"] == "time":
        return True
    if fact.get("entityId") and fact["entityId"] == vp["entityId"]:
        return True
    return fact.get("at") == vp["at"]


def make_item(iid, viewpoint, facts, must, target, note):
    """Derives forbidden/omittable from the visibility rule, asserts identity
    consistency, and refuses label sets that contradict the rule."""
    ids = [f["factId"] for f in facts]
    assert len(set(ids)) == len(ids), iid
    for f in facts:
        assert "at" in f, f"{iid}/{f['factId']}: fact lacks a location"
        if f["kind"] == "time":
            assert f["at"] is None, iid
        else:
            assert f["at"] in LOC_ID, f"{iid}/{f['factId']}: unknown location"
        if f.get("entityId", "").startswith("char_"):
            assert f.get("name"), f"{iid}/{f['factId']}: character fact without a name"
            assert CHAR_ID.get(f["name"]) == f["entityId"], (
                f"{iid}/{f['factId']}: name/id mismatch "
                f"({f['name']} vs {f['entityId']})")
        if f.get("entityId", "").startswith("loc_"):
            assert LOC_ID.get(f.get("name")) == f["entityId"], (
                f"{iid}/{f['factId']}: location name/id mismatch")
    own = [f for f in facts
           if viewpoint["entityId"] and f.get("entityId") == viewpoint["entityId"]]
    if viewpoint["type"] != "omniscient":
        assert own, f"{iid}: viewpoint person has no fact of their own"
        for f in own:
            assert f.get("name") == viewpoint["name"], f"{iid}: name drift"

    forbidden = [f["factId"] for f in facts if not visible(viewpoint, f)]
    must_set, target_set = set(must), set(target)
    assert must_set <= target_set, iid
    assert not (target_set & set(forbidden)), f"{iid}: target includes POV-forbidden facts"
    omittable = set(ids) - must_set - set(forbidden)
    assert omittable | must_set | set(forbidden) == set(ids), iid

    return {
        "itemId": iid, "task": "n2-select", "split": "dev", "batch": "v2",
        "viewpoint": viewpoint,
        "facts": facts,
        "must": sorted(must_set),
        "target": sorted(target_set),
        "omittable": sorted(omittable),
        "forbidden": sorted(forbidden),
        "note": note,
        "hashes": {"facts": sha(canon(facts)),
                   "labels": sha(canon({"must": sorted(must_set),
                                        "target": sorted(target_set),
                                        "forbidden": sorted(forbidden)}))},
    }


def main() -> None:
    items = []

    def vp_prot(name, at, i):
        return {"type": "protagonist", "entityId": CHAR_ID[name], "name": name,
                "at": at,
                "rule": f"你只知道自己在{at}能看到的，以及自己的行动与状态"}

    def vp_local(name, at):
        return {"type": "location-limited", "entityId": CHAR_ID[name],
                "name": name, "at": at,
                "rule": f"你只知道{at}发生的事，以及自己的行动与状态"}

    def vp_omni():
        return {"type": "omniscient", "entityId": None, "name": None, "at": "全局",
                "rule": "全知视角：全部事实可见，低显著性的可以省略"}

    # A) 1-4: protagonist moved to L2; two facts at another location are
    #    POV-inaccessible for this person.
    for i in range(4):
        me, other = NAMES[i], NAMES[(i + 3) % len(NAMES)]
        frm, to = LOCS[i], LOCS[(i + 2) % len(LOCS)]
        far = LOCS[(i + 4) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "moved", "entityId": CHAR_ID[me], "name": me,
             "from": frm, "to": to, "at": to},
            {"factId": "f2", "kind": "task_achieved", "entityId": CHAR_ID[me],
             "name": me, "goal": TASKS[i], "at": to},
            {"factId": "f3", "kind": "appearance_changed",
             "entityId": LOC_ID[to], "name": to, "text": APPEAR[i], "at": to},
            {"factId": "f4", "kind": "time", "amount": 6 + i, "unit": "minute",
             "at": None},
            {"factId": "f5", "kind": "appearance_changed", "entityId": LOC_ID[far],
             "name": far, "text": APPEAR[(i + 2) % len(APPEAR)], "at": far},
            {"factId": "f6", "kind": "personality_changed",
             "entityId": CHAR_ID[other], "name": other,
             "text": PERS[i % len(PERS)], "at": far},
        ]
        items.append(make_item(
            f"n2-{i + 1:02d}", vp_prot(me, to, i), facts,
            must=["f1", "f2"], target=["f1", "f2", "f3"],
            note="自身移动与任务必述；目的地变化可选；他处变化与他的情绪不可知"))

    # B) 5-8: location-limited viewpoint: own facts plus what happens here.
    for i in range(4):
        me, other = NAMES[(i + 2) % len(NAMES)], NAMES[(i + 4) % len(NAMES)]
        here, far = LOCS[i], LOCS[(i + 3) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "task_achieved", "entityId": CHAR_ID[me],
             "name": me, "goal": TASKS[(i + 2) % len(TASKS)], "at": here},
            {"factId": "f2", "kind": "appearance_changed", "entityId": LOC_ID[here],
             "name": here, "text": APPEAR[(i + 1) % len(APPEAR)], "at": here},
            {"factId": "f3", "kind": "sanity_changed", "entityId": CHAR_ID[me],
             "name": me, "from": 11, "to": 13, "at": here},
            {"factId": "f4", "kind": "moved", "entityId": CHAR_ID[other],
             "name": other, "from": far, "to": LOCS[(i + 5) % len(LOCS)], "at": far},
            {"factId": "f5", "kind": "no_change", "scope": here, "at": here},
        ]
        items.append(make_item(
            f"n2-{i + 5:02d}", vp_local(me, here), facts,
            must=["f1", "f3"], target=["f1", "f2", "f3"],
            note="本地任务与理智必述；本地变化可选；他处移动不可知"))

    # C) 9-12: omniscient, redundant material (no forbidden facts at all).
    for i in range(4):
        a, b = NAMES[i % len(NAMES)], NAMES[(i + 1) % len(NAMES)]
        here = LOCS[(i + 1) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "moved", "entityId": CHAR_ID[a], "name": a,
             "from": LOCS[i % len(LOCS)], "to": here, "at": here},
            {"factId": "f2", "kind": "positioned_at", "entityId": CHAR_ID[b],
             "name": b, "at": here},
            {"factId": "f3", "kind": "personality_changed", "entityId": CHAR_ID[a],
             "name": a, "text": PERS[(i + 2) % len(PERS)], "at": here},
            {"factId": "f4", "kind": "personality_changed", "entityId": CHAR_ID[b],
             "name": b, "text": PERS[(i + 3) % len(PERS)], "at": here},
            {"factId": "f5", "kind": "time", "amount": 9 + i, "unit": "minute",
             "at": None},
            {"factId": "f6", "kind": "no_change", "scope": here, "at": here},
        ]
        items.append(make_item(
            f"n2-{i + 9:02d}", vp_omni(), facts,
            must=["f1", "f2"], target=["f1", "f2", "f3"],
            note="全知无禁止项；冗余时间/空点/他人情绪可省，全选即精度下降"))

    # D) 13-16: protagonist at L1; a same-place task by someone else is
    #    VISIBLE (must not be treated as forbidden), a remote one is not.
    for i in range(4):
        me, near, far_actor = (NAMES[i % len(NAMES)], NAMES[(i + 1) % len(NAMES)],
                               NAMES[(i + 5) % len(NAMES)])
        here, far = LOCS[(i + 4) % len(LOCS)], LOCS[(i + 2) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "task_achieved", "entityId": CHAR_ID[me],
             "name": me, "goal": TASKS[(i + 4) % len(TASKS)], "at": here},
            {"factId": "f2", "kind": "sanity_changed", "entityId": CHAR_ID[me],
             "name": me, "from": 12, "to": 10, "at": here},
            {"factId": "f3", "kind": "task_achieved", "entityId": CHAR_ID[near],
             "name": near, "goal": TASKS[(i + 1) % len(TASKS)], "at": here},
            {"factId": "f4", "kind": "appearance_changed", "entityId": LOC_ID[here],
             "name": here, "text": APPEAR[(i + 3) % len(APPEAR)], "at": here},
            {"factId": "f5", "kind": "task_achieved", "entityId": CHAR_ID[far_actor],
             "name": far_actor, "goal": TASKS[(i + 2) % len(TASKS)], "at": far},
            {"factId": "f6", "kind": "time", "amount": 12 + i, "unit": "minute",
             "at": None},
        ]
        items.append(make_item(
            f"n2-{i + 13:02d}", vp_prot(me, here, i), facts,
            must=["f1", "f2"], target=["f1", "f2", "f3", "f4"],
            note="同地他人任务与本地变化可见；他处任务不可知；时长可省"))

    assert len(items) == 16
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in items) + "\n", encoding="utf-8")

    import collections
    print(f"items: {len(items)} (v2) -> {OUT}")
    print("fact counts:", dict(sorted(collections.Counter(
        len(r["facts"]) for r in items).items())))
    print("must/target/omittable/forbidden mean:",
          round(sum(len(r["must"]) for r in items) / 16, 2),
          round(sum(len(r["target"]) for r in items) / 16, 2),
          round(sum(len(r["omittable"]) for r in items) / 16, 2),
          round(sum(len(r["forbidden"]) for r in items) / 16, 2))
    print("items with a forbidden fact:",
          sum(1 for r in items if r["forbidden"]),
          "| items with same-place other-actor fact:",
          sum(1 for r in items if any(f.get("entityId", "").startswith("char_")
                                      and f["entityId"] != r["viewpoint"]["entityId"]
                                      and f.get("at") == r["viewpoint"]["at"]
                                      and f.get("at") is not None
                                      for f in r["facts"])))


if __name__ == "__main__":
    main()
