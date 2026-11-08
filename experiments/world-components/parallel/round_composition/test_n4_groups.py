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


def render(cid, facts_mutator=None, state_mutator=None):
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
    out = n4_groups.pack_grouped_input(packed, chain["plan"],
                                       scene["worldView"], ids, state=state)
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
    check(any(b["reason"] == "same-name-indistinguishable"
              for b in out["blocked"]),
          "same-name: the reason is recorded")


def test_time_without_value():
    out, _ = render("rb-time-vague")
    check(out["status"] == "ok", "time: render is ok")
    check("时间经过" in out["input"], "time: the fact is rendered")
    check(not any(w in out["input"] for w in ("分钟", "小时", "秒")),
          "time: no duration value is added")


def main() -> int:
    for fn in (test_snapshot, test_determinism, test_same_name_descriptors,
               test_blocked_fact, test_same_name_without_descriptor,
               test_time_without_value):
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
