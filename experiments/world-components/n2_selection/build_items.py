# N2 content-selection items (round 18): fact table + viewpoint -> which facts
# the narration states.
#
# Isolation: third independent vocabulary (not the N4 training corpus cast,
# not the frozen N4 holdout cast). No model output is used as a label: the
# gold selection is PROGRAM-DEFINED from the viewpoint rule below, so
# "select all" is not a legitimate answer and no arm can prove itself.
#
# Labels per fact:
#   must      - the narration has to state it (the protagonist's own action,
#               the committed task result the player is acting on)
#   omittable - legitimate to state or skip (background visible at the scene,
#               redundant time detail, someone else's mood shift)
#   forbidden - the viewpoint cannot know it (another location's change or a
#               private action elsewhere); stating it is a fact violation
#   target    - program-defined competent selection = must + the facts a
#               narrator would surface (salient); used for precision/recall
#
# Usage: python experiments/world-components/n2_selection/build_items.py
# Output: experiments/world-components/n2_selection/items.jsonl

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "items.jsonl"

# third cast: disjoint from n4 corpus (陈舟/苏晚/周砚/林望/沈青/顾一帆/...) and
# from the frozen holdout (陆知微/江砚白/顾青梧/秦照野/温屿/...)
NAMES = ["裴行舟", "沈拾", "岑半夏", "顾知白", "陆停云", "白蘅"]
LOCS = ["石阶码头", "旧钟铺", "半窗书舍", "竹影茶棚", "西栅桥", "瓦窑"]
TASKS = ["把船灯挂上桅杆", "补好瓦窑的顶棚", "把账簿送回半窗书舍",
         "收好茶棚的坐垫", "修西栅桥的踏板", "清点旧钟铺的存货"]
APPEAR = ["檐角的风铃褪了色", "门前的石阶塌了一角", "窗纸被风戳了个洞",
          "柜台上的铜锁生了锈", "墙根的青苔爬上了半尺", "梁上的吊绳磨细了"]
PERS = ["变得寡言", "变得爽快", "变得谨慎", "变得急躁"]


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def item(iid, viewpoint, facts, must, target, forbidden, note):
    """omittable is DERIVED: every fact is must, forbidden, or legally
    skippable. Callers never hand-label omissions, so no fact can silently
    drop out of the label space."""
    ids = [f["factId"] for f in facts]
    must, target, forbidden = set(must), set(target), set(forbidden)
    omittable = set(ids) - must - forbidden
    assert not (must & forbidden), iid
    assert must <= target, iid
    assert not (target & forbidden), iid
    assert target <= set(ids), iid
    return {
        "itemId": iid,
        "task": "n2-select",
        "split": "dev",
        "viewpoint": viewpoint,
        "facts": facts,
        "must": sorted(must),
        "target": sorted(target),
        "omittable": sorted(omittable),
        "forbidden": sorted(forbidden),
        "note": note,
        "hashes": {"facts": sha(canon(facts)),
                   "labels": sha(canon({"must": sorted(must),
                                        "target": sorted(target),
                                        "omittable": sorted(omittable),
                                        "forbidden": sorted(forbidden)}))},
    }


def main() -> None:
    items = []

    def prot(idx):
        return {"type": "protagonist", "entityId": f"char_{400 + idx:03d}",
                "name": NAMES[idx % len(NAMES)],
                "rule": "主角只知道自己在场的地点与自己的行动"}

    def local(name, loc):
        return {"type": "location-limited", "entityId": name, "at": loc,
                "rule": "叙述者只知道该人物所在地点发生的事情"}

    def omni():
        return {"type": "omniscient", "entityId": None,
                "rule": "全知视角，但低显著性事实可以省略"}

    # 1-4: protagonist moves + own task + scene detail + another location's
    # change (forbidden) + another character's mood (omittable)
    for i in range(4):
        n = NAMES[i]
        other = NAMES[(i + 3) % len(NAMES)]
        here, there = LOCS[i], LOCS[(i + 2) % len(LOCS)]
        far = LOCS[(i + 4) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "moved", "entityId": f"char_{400 + i:03d}",
             "name": n, "from": here, "to": there},
            {"factId": "f2", "kind": "task_achieved",
             "entityId": f"char_{400 + i:03d}", "name": n,
             "goal": TASKS[i % len(TASKS)]},
            {"factId": "f3", "kind": "time", "amount": 6 + i, "unit": "minute"},
            {"factId": "f4", "kind": "appearance_changed",
             "entityId": f"loc_{400 + i:03d}", "name": there,
             "text": APPEAR[i % len(APPEAR)]},
            {"factId": "f5", "kind": "appearance_changed",
             "entityId": f"loc_{410 + i:03d}", "name": far,
             "text": APPEAR[(i + 2) % len(APPEAR)]},
            {"factId": "f6", "kind": "personality_changed",
             "entityId": f"char_{420 + i:03d}", "name": other,
             "text": PERS[i % len(PERS)]},
        ]
        items.append(item(
            f"n2-{i + 1:02d}", prot(i), facts,
            must=["f1", "f2"], target=["f1", "f2", "f4"], forbidden=["f5"],
            note="自述行动与任务结果必述；所在地点变化可选；远处地点变化视角不可知"))

    # 5-8: location-limited viewpoint: only what happens at that location
    for i in range(4):
        n = NAMES[(i + 2) % len(NAMES)]
        here = LOCS[i % len(LOCS)]
        other = NAMES[(i + 4) % len(NAMES)]
        far = LOCS[(i + 3) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "task_achieved",
             "entityId": f"char_{430 + i:03d}", "name": n,
             "goal": TASKS[(i + 2) % len(TASKS)]},
            {"factId": "f2", "kind": "appearance_changed",
             "entityId": f"loc_{440 + i:03d}", "name": here,
             "text": APPEAR[(i + 1) % len(APPEAR)]},
            {"factId": "f3", "kind": "sanity_changed",
             "entityId": f"char_{430 + i:03d}", "name": n,
             "from": 11, "to": 13},
            {"factId": "f4", "kind": "moved",
             "entityId": f"char_{450 + i:03d}", "name": other,
             "from": far, "to": LOCS[(i + 5) % len(LOCS)]},
            {"factId": "f5", "kind": "no_change", "scope": here},
        ]
        items.append(item(
            f"n2-{i + 5:02d}", local(n, here), facts,
            must=["f1", "f2"], target=["f1", "f2", "f3"], forbidden=["f4"],
            note="本地任务与本地变化必述；他处移动不可知；空点可省"))

    # 9-12: omniscient but redundant material: select-all must lose precision
    for i in range(4):
        a = NAMES[i % len(NAMES)]
        b = NAMES[(i + 1) % len(NAMES)]
        here = LOCS[(i + 1) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "moved", "entityId": f"char_{460 + i:03d}",
             "name": a, "from": LOCS[i % len(LOCS)], "to": here},
            {"factId": "f2", "kind": "positioned_at",
             "entityId": f"char_{470 + i:03d}", "name": b, "at": here},
            {"factId": "f3", "kind": "personality_changed",
             "entityId": f"char_{460 + i:03d}", "name": a,
             "text": PERS[(i + 2) % len(PERS)]},
            {"factId": "f4", "kind": "personality_changed",
             "entityId": f"char_{470 + i:03d}", "name": b,
             "text": PERS[(i + 3) % len(PERS)]},
            {"factId": "f5", "kind": "time", "amount": 9 + i, "unit": "minute"},
            {"factId": "f6", "kind": "no_change", "scope": here},
        ]
        items.append(item(
            f"n2-{i + 9:02d}", omni(), facts,
            must=["f1", "f2"], target=["f1", "f2", "f3"], forbidden=[],
            note="全知视角无禁止项；冗余时间、空点与他人情绪可省，全选即精度下降"))

    # 13-16: protagonist POV with a second actor's private task elsewhere
    for i in range(4):
        n = NAMES[(i + 1) % len(NAMES)]
        other = NAMES[(i + 5) % len(NAMES)]
        here = LOCS[(i + 2) % len(LOCS)]
        far = LOCS[(i + 4) % len(LOCS)]
        facts = [
            {"factId": "f1", "kind": "task_achieved",
             "entityId": f"char_{480 + i:03d}", "name": n,
             "goal": TASKS[(i + 4) % len(TASKS)]},
            {"factId": "f2", "kind": "time", "amount": 12 + i, "unit": "minute"},
            {"factId": "f3", "kind": "task_achieved",
             "entityId": f"char_{490 + i:03d}", "name": other,
             "goal": TASKS[(i + 1) % len(TASKS)]},
            {"factId": "f4", "kind": "appearance_changed",
             "entityId": f"loc_{495 + i:03d}", "name": here,
             "text": APPEAR[(i + 3) % len(APPEAR)]},
            {"factId": "f5", "kind": "sanity_changed",
             "entityId": f"char_{480 + i:03d}", "name": n, "from": 12, "to": 10},
        ]
        items.append(item(
            f"n2-{i + 13:02d}", prot((i + 1) % len(NAMES)), facts,
            must=["f1", "f5"], target=["f1", "f4", "f5"], forbidden=["f3"],
            note="自身理智变化必述；他人他处任务不可知；时长可省"))

    assert len(items) == 16
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in items) + "\n", encoding="utf-8")
    print(f"items: {len(items)} -> {OUT}")
    import collections
    print("fact counts:",
          dict(collections.Counter(len(r["facts"]) for r in items)))
    print("mean must/target/omittable/forbidden:",
          round(sum(len(r["must"]) for r in items) / len(items), 2),
          round(sum(len(r["target"]) for r in items) / len(items), 2),
          round(sum(len(r["omittable"]) for r in items) / len(items), 2),
          round(sum(len(r["forbidden"]) for r in items) / len(items), 2))


if __name__ == "__main__":
    main()
