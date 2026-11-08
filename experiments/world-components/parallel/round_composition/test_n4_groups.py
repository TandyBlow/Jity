"""Checks for the grouped N4.1 renderer (program-only; no model calls).

Protected behaviour:
- the rb-move-outcome input matches the reviewed snapshot byte for byte;
- repeated renders are identical (determinism);
- same-name actors carry their OWN authoritative descriptor inside their own
  fact block, with the entity id recorded;
- a fact that cannot be expressed safely blocks the row (`productQualified`
  False) while the rest is still rendered for diagnosis;
- a same-name actor without an authoritative descriptor is blocked, not
  invented;
- a time fact renders without any duration value.

Usage: python -X utf8 test_n4_groups.py
"""

import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import n4_groups  # noqa: E402
import real_batch_v3 as rb  # noqa: E402

CASES = json.loads((HERE / "fixtures" / "batch-v1-cases.json")
                   .read_text(encoding="utf-8"))["cases"]
FAILURES = []


def check(cond, label):
    if not cond:
        FAILURES.append(label)


def render(cid, facts_mutator=None, state_mutator=None, plan_mutator=None):
    case = next(c for c in CASES if c["caseId"] == cid)
    chain = rb.build_chain(case)
    selected = copy.deepcopy(chain["selected"])
    if facts_mutator:
        facts_mutator(selected)
    scene_state = copy.deepcopy(case["point"]["state"])
    state = copy.deepcopy(scene_state)
    if state_mutator:
        state_mutator(state)
    scene = rb.build_scene_context(scene_state, chain["perspective"], selected,
                                   environment=case.get("environment"))
    ids = [f["factId"] for f in selected]
    packed = {"facts": selected, "perspective": chain["perspective"],
              "sceneState": scene["sceneContext"]["sceneState"],
              "characterContext": scene["sceneContext"]["characterContext"]}
    plan = copy.deepcopy(chain["plan"])
    if plan_mutator:
        plan_mutator(plan)
    out = n4_groups.pack_grouped_input(packed, plan, scene["worldView"], ids,
                                       state=state)
    v3 = rb.pack_narrative_input(packed, plan, scene["worldView"],
                                 selected_fact_ids=ids)
    out["_v3"] = v3.get("input")
    return out, selected


def test_snapshot():
    out, _ = render("rb-move-outcome")
    snap = (HERE / "fixtures" / "n4-groups-rb-move-outcome.txt").read_text(
        encoding="utf-8")
    check(out["status"] == "ok", "snapshot: render is ok")
    check(out["input"] == snap, "snapshot: bytes match the reviewed sample")
    check("起点：管线镇" in out["input"] and "终点：钟楼" in out["input"],
          "snapshot: movement has explicit origin and destination lines")
    check("句组 G1" in out["input"], "snapshot: the group header is present")


def test_determinism():
    a, _ = render("rb-move-outcome")
    b, _ = render("rb-move-outcome")
    check(a["input"] == b["input"], "determinism: identical bytes")


def test_same_name_descriptors():
    out, _ = render("rb-same-name")
    check(out["status"] == "ok", "same-name: render is ok")
    check(out["sameName"] == {"管线乙": ["char_pb", "char_pc"]},
          "same-name: both entity ids are recorded")
    check("人物：管线乙（性格=急躁）" in out["input"],
          "same-name: char_pb carries 急躁")
    check("人物：管线乙（性格=沉默）" in out["input"],
          "same-name: char_pc carries 沉默")
    check(out["input"].find("急躁") < out["input"].find("沉默"),
          "same-name: descriptors stay in plan order")


def test_blocked_fact():
    def drop_result(facts):
        for f in facts:
            if f["kind"] == "outcome":
                f.pop("resultText", None)

    out, _ = render("rb-move-outcome", facts_mutator=drop_result)
    check(out["status"] == "blocked", "blocked: status is blocked")
    check(out["productQualified"] is False,
          "blocked: a partial passage is not a qualified product")
    check(out["blocked"] and out["blocked"][0]["reason"] == "missing-field",
          "blocked: the reason is recorded")
    check("f0｜移动" in out["input"] and "起点：管线镇" in out["input"],
          "blocked: the other fact is still rendered for diagnosis")


def test_same_name_without_descriptor():
    def strip_traits(state):
        for eid in ("char_pb", "char_pc"):
            state["initial"]["characters"][eid].pop("initialPersonality", None)
            state["characters"][eid]["personalityChanges"] = []

    out, _ = render("rb-same-name", state_mutator=strip_traits)
    check(out["status"] == "blocked",
          "same-name: no descriptor blocks instead of inventing")
    check(any(b["reason"] in ("descriptor-missing",
                              "same-name-indistinguishable")
              for b in out["blocked"]),
          "same-name: the reason is recorded")


def test_ab_invariants():
    out, _ = render("rb-move-outcome")
    v3 = out["_v3"].split(chr(10))
    b = out["input"].split(chr(10))
    v3_header = v3[:v3.index("事实：")]
    while v3_header and not v3_header[-1].strip():
        v3_header.pop()
    b_persp = next(i for i, l in enumerate(b) if l.startswith("视角："))
    b_header = b[:b_persp]
    while b_header and not b_header[-1].strip():
        b_header.pop()
    check(v3_header == b_header,
          "A/B: scene, characters and visible blocks are byte identical")
    v3_persp = next(l for l in v3 if l.startswith("视角："))
    v3_req = next(l for l in v3 if l.startswith("要求："))
    check(b[b_persp] == v3_persp,
          "A/B: the perspective line is byte identical")
    check(b[b_persp + 1] == v3_req,
          "A/B: the registered requirement line is byte identical")
    check(out["input"].count(v3_req) == 1,
          "A/B: the requirement line appears exactly once")


def test_time_handling():
    out, _ = render("rb-time-vague")
    check("组后时间=过去了一会儿" in out["input"],
          "time: the group time suffix is kept")

    def drop_time_from_groups(plan):
        for s in plan["sentences"]:
            s["factIds"] = [f for f in s["factIds"] if f != "f2"]
            s["time"] = None

    out, _ = render("rb-time-vague", plan_mutator=drop_time_from_groups)
    check("全局时间=过去了一会儿" in out["input"],
          "time: an ungrouped time fact is not dropped")
    check("f2｜时间" not in out["input"],
          "time: the ungrouped fact is not turned into a group block")


def test_identical_descriptors_blocked():
    def same_traits(state):
        state["initial"]["characters"]["char_pc"]["initialPersonality"] = "急躁"

    out, _ = render("rb-same-name", state_mutator=same_traits)
    check(out["status"] == "blocked",
          "identical descriptors: the row is blocked")
    check(any(b["reason"] == "descriptors-identical"
              for b in out["blocked"]),
          "identical descriptors: the reason is named")


def test_time_without_value():
    out, _ = render("rb-time-vague")
    check(out["status"] == "ok", "time: render is ok")
    check("时间经过" in out["input"], "time: the fact is rendered")
    check(not any(w in out["input"] for w in ("分钟", "小时", "秒")),
          "time: no duration value is added")


def main() -> int:
    for fn in (test_snapshot, test_determinism, test_same_name_descriptors,
               test_blocked_fact, test_same_name_without_descriptor,
               test_time_without_value, test_ab_invariants,
               test_time_handling, test_identical_descriptors_blocked):
        before = len(FAILURES)
        fn()
        print(("ok   " if len(FAILURES) == before else "FAIL ") + fn.__name__)
    if FAILURES:
        for f in FAILURES:
            print("  -", f)
        print(f"FAIL: {len(FAILURES)} check(s)")
        return 1
    print("PASS: n4_groups checks (snapshot, determinism, descriptors, "
          "blocked facts, time)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
