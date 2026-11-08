"""Checks for N5 v4.2: v4.1 plus the shared identity record.

The interface point under test: N4 (rendering) and N5 (judging) must read the
same descriptors. The judge no longer trusts descriptors embedded in fact
objects when an identity record is supplied, and identical descriptors are
refused as evidence.

Usage: python -X utf8 test_judge_v4_2.py
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import character_identity as ci  # noqa: E402
import judge_v4_2 as j  # noqa: E402
from judge_v3 import JudgeBlocked  # noqa: E402

FAILURES = []


def check(cond, label):
    if not cond:
        FAILURES.append(label)


PA = {"factId": "f0", "kind": "moved", "entityId": "char_pa",
      "name": "管线甲", "from": "管线镇", "to": "钟楼",
      "entityGroup": "characters"}
OUT = {"factId": "f1", "kind": "outcome", "entityId": "char_pa",
       "name": "管线甲", "entityGroup": "characters",
       "resultText": "把铜铃挂回了钟楼"}
A = {"factId": "g0", "kind": "moved", "entityId": "char_y1",
     "name": "管线乙", "entityGroup": "characters",
     "from": "管线镇", "to": "钟楼"}
B = {"factId": "g1", "kind": "moved", "entityId": "char_y2",
     "name": "管线乙", "entityGroup": "characters",
     "from": "钟楼", "to": "广场"}


def ids_for(desc1="急躁", desc2="沉默"):
    return {"version": "test",
            "entries": {
                "char_y1": {"entityId": "char_y1", "name": "管线乙",
                            "descriptor": desc1, "field": "性格",
                            "source": "initial.characters.char_y1."
                                      "initialPersonality"},
                "char_y2": {"entityId": "char_y2", "name": "管线乙",
                            "descriptor": desc2, "field": "性格",
                            "source": "initial.characters.char_y2."
                                      "initialPersonality"}},
            "sameName": {}, "indistinguishable": {}}


def run(text, finish="stop", facts=None, must=None, identities=None):
    return j.judge(facts or [PA, OUT], must or ["f0", "f1"], None, text,
                   finish, identities=identities)


def test_identity_record_is_used():
    good = "急躁的管线乙从管线镇来到了钟楼。沉默的管线乙从钟楼来到了广场。"
    r = run(good, facts=[A, B], must=["g0", "g1"], identities=ids_for())
    check(r["hardPass"], "identity: distinct descriptors pass")

    # facts carry NO descriptor fields; without the record this is undetermined
    r = run(good, facts=[A, B], must=["g0", "g1"])
    check(r["status"] == "undetermined",
          "identity: without a record the facts cannot separate them")

    swapped = "沉默的管线乙从管线镇来到了钟楼。急躁的管线乙从钟楼来到了广场。"
    r = run(swapped, facts=[A, B], must=["g0", "g1"], identities=ids_for())
    check(r["status"] == "undetermined",
          "identity: swapped descriptors are undetermined")


def test_identical_descriptors_refused():
    same = ids_for("急躁", "急躁")
    text = "急躁的管线乙从管线镇来到了钟楼。急躁的管线乙从钟楼来到了广场。"
    r = run(text, facts=[A, B], must=["g0", "g1"], identities=same)
    check(r["status"] == "undetermined",
          "identity: identical descriptors cannot separate two actors")
    check(any("descriptors-identical" in p for p in r["problems"]),
          "identity: the reason is named")


def test_builder_flags_indistinguishable():
    state = {"initial": {"characters": {
        "char_y1": {"name": "管线乙", "initialPersonality": "急躁"},
        "char_y2": {"name": "管线乙", "initialPersonality": "急躁"}}},
        "characters": {"char_y1": {}, "char_y2": {}}}
    ids = ci.build_identities(state)
    check("管线乙" in ids["indistinguishable"],
          "builder: identical traits are flagged")
    check("管线乙" not in ids["sameName"],
          "builder: identical traits are not offered as separation")
    got, reason = ci.same_name_descriptors(ids, "管线乙",
                                           ["char_y1", "char_y2"])
    check(got is None and reason == "descriptors-identical",
          "builder: refusal names the reason")


def test_v41_behaviour_kept():
    watch = "管线甲站在旁边，看着王五把铜铃挂回了钟楼。"
    r = run(watch)
    check(not r["hardPass"] and r["status"] == "judged",
          "v4.1: observer attribution still rejected")
    scope = "管线甲从管线镇来到了钟楼。管线甲先没挂上，后来把铜铃挂回了钟楼。"
    check(run(scope)["hardPass"], "v4.1: failure then success still covered")
    neg = "管线甲从管线镇来到了钟楼。管线甲并未把铜铃挂回了钟楼。"
    check(not run(neg)["hardPass"], "v4.1: negation still rejected")

    r = run("管线甲站在旁边，王五把铜铃挂回了钟楼。")
    check(r["status"] == "needs-semantic-review",
          "v4.1: unbound result still goes to review")

    leak = "管线甲从管线镇来到了钟楼。任务「把铜铃挂回原位」还没有结束。"
    facts = [PA, dict(OUT, kind="task_achieved", goal="把铜铃挂回原位")]
    r = run(leak, facts=facts, must=["f0", "f1"])
    check(not r["gates"]["G2_goal_residue"], "v4: goal leak still hard")

    for finish, ok in (("stop", True), ("length", False), ("load", False)):
        check(run("管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。",
                  finish)["gates"]["G6_completion"] is ok,
              f"v4: finish {finish}")
    try:
        run("管线甲把铜铃挂回了钟楼。", None)
    except JudgeBlocked as exc:
        check(exc.code == "finish-reason-missing", "v4: missing finish blocks")


def main() -> int:
    for fn in (test_identity_record_is_used, test_identical_descriptors_refused,
               test_builder_flags_indistinguishable, test_v41_behaviour_kept):
        before = len(FAILURES)
        fn()
        print(("ok   " if len(FAILURES) == before else "FAIL ") + fn.__name__)
    if FAILURES:
        for f in FAILURES:
            print("  -", f)
        print(f"FAIL: {len(FAILURES)} check(s)")
        return 1
    print("PASS: judge_v4_2 checks (shared identity, identical descriptors, "
          "v4.1 behaviour)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
