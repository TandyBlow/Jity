"""Unit checks for N5 v4.1: v4 plus the review's three counter-examples.

Added here (each one is a case the owner wrote against v4):
  A  "管线甲站在旁边，看着王五把铜铃挂回了钟楼" must NOT credit 管线甲, with or
     without the comma, and an observer verb plus another actor is a rejection.
  B  Same-name descriptors must modify the right person: swapped descriptors are
     `undetermined`, not a pass.
  C  "先没挂上，后来挂回去了" must not be rejected: negation is scoped to the
     segment that carries the result.

The v4 rulings are re-checked so the new version cannot silently lose them.

Usage: python -X utf8 test_judge_v4_1.py
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge_v4_1 as j  # noqa: E402
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
GOOD = "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。"


def run(text, finish="stop", facts=None, must=None):
    return j.judge(facts or [PA, OUT], must or ["f0", "f1"], None, text, finish)


def test_observer_subject_first():
    cases = [
        "管线甲站在旁边，看着王五把铜铃挂回了钟楼。",
        "管线甲看着王五把铜铃挂回了钟楼。",
        "管线甲站在旁边，听见王五把铜铃挂回了钟楼。",
    ]
    for text in cases:
        r = run(text)
        check(not r["hardPass"], f"observer: must not pass: {text}")
        check(r["status"] == "judged",
              f"observer: a named other actor is a rejection: {text}")
        check(any(p.startswith("fact-rejected:f1:attribution-other-actor")
                  for p in r["problems"]),
              f"observer: rejection is named: {text}")

    # no observer verb and an unnamed actor: cannot bind, goes to review
    r = run("管线甲站在旁边，王五把铜铃挂回了钟楼。")
    check(r["status"] == "needs-semantic-review",
          "observer: an unbound result goes to review")
    check(not r["hardPass"], "observer: review is not a pass")


def test_same_name_descriptors_bind():
    a = {"factId": "g0", "kind": "moved", "entityId": "char_y1",
         "name": "管线乙", "entityGroup": "characters",
         "from": "管线镇", "to": "钟楼", "text": "沉默"}
    b = {"factId": "g1", "kind": "moved", "entityId": "char_y2",
         "name": "管线乙", "entityGroup": "characters",
         "from": "钟楼", "to": "广场", "text": "急躁"}
    good = "沉默的管线乙从管线镇来到了钟楼。急躁的管线乙从钟楼来到了广场。"
    swapped = "急躁的管线乙从管线镇来到了钟楼。沉默的管线乙从钟楼来到了广场。"
    mixed = "沉默的管线乙和急躁的管线乙从管线镇来到了钟楼。沉默的管线乙从钟楼来到了广场。"
    bare = "管线乙从管线镇来到了钟楼。管线乙从钟楼来到了广场。"

    r = run(good, facts=[a, b], must=["g0", "g1"])
    check(r["hardPass"], "G4: correct descriptor binding passes")
    for text, label in ((swapped, "swapped"), (mixed, "mixed"), (bare, "bare")):
        r = run(text, facts=[a, b], must=["g0", "g1"])
        check(r["status"] == "undetermined",
              f"G4: {label} descriptors must be undetermined")
        check(not r["hardPass"], f"G4: {label} is not a pass")


def test_negation_scope():
    text = "管线甲从管线镇来到了钟楼。管线甲先没挂上，后来把铜铃挂回了钟楼。"
    r = run(text)
    check(r["hardPass"], "scope: failure then success is covered")
    check(not any("negation" in p for p in r["problems"]),
          "scope: the earlier failure is not a negation of the result")

    for text, cue in (
            ("管线甲从管线镇来到了钟楼。管线甲并未把铜铃挂回了钟楼。", "negation"),
            ("管线甲从管线镇来到了钟楼。如果管线甲把铜铃挂回了钟楼，钟声就会响。",
             "irrealis"),
            ("管线甲从管线镇来到了钟楼。难道管线甲把铜铃挂回了钟楼？", "rhetorical")):
        r = run(text)
        check(not r["hardPass"], f"scope: {cue} still rejected")
        check(any(cue in p for p in r["problems"]), f"scope: {cue} is named")


def test_v4_rulings_kept():
    r = run(GOOD + "管线甲在窗边站定。")
    check(r["hardPass"], "v4: repeated registered name is a diagnostic")
    check(any(d["code"] == "residue-name" for d in r["diagnostics"]),
          "v4: the repetition is recorded")

    leak = "管线甲从管线镇来到了钟楼。任务「把铜铃挂回原位」还没有结束。"
    facts = [PA, dict(OUT, kind="task_achieved", goal="把铜铃挂回原位")]
    r = run(leak, facts=facts, must=["f0", "f1"])
    check(not r["gates"]["G2_goal_residue"], "v4: goal leak still hard")

    r = run("管线甲从管线镇来到了钟楼。把铜铃挂回了钟楼。")
    check(r["status"] == "needs-semantic-review",
          "v4: a subjectless result still goes to review")

    for finish, ok in (("stop", True), ("eos", True), ("length", False),
                       ("load", False)):
        r = run(GOOD, finish)
        check(r["gates"]["G6_completion"] is ok, f"v4: finish {finish}")
    for bad in (None, "", "timeout"):
        try:
            run(GOOD, bad)
        except JudgeBlocked as exc:
            check(exc.code in ("finish-reason-missing", "finish-reason-unknown"),
                  f"v4: {bad!r} blocks")
        else:
            raise AssertionError(f"v4: finish {bad!r} accepted")


def test_parity():
    facts = [PA, dict(OUT, resultText=None)]
    try:
        run(GOOD, facts=facts)
    except JudgeBlocked as exc:
        check(exc.code == "outcome-result-missing", "D1: missing result blocks")

    tfacts = [PA, dict(OUT, kind="task_achieved", goal="把铜铃挂回钟楼"),
              {"factId": "f2", "kind": "time", "amount": 8, "unit": "minute"}]
    base = "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。"
    check(run(base + "过了一会儿。", facts=tfacts,
              must=["f0", "f1", "f2"])["gates"]["G3_time"],
          "D2: vague time covers")
    check(not run(base + "大约十小时过去了。", facts=tfacts,
                  must=["f0", "f1", "f2"])["gates"]["G3_time"],
          "D2: fabricated duration fails")

    plan = {"sentences": [{"index": 0, "factIds": ["f0"],
                           "coreference": [{"mention": "他",
                                            "refersTo": "char_pa",
                                            "pronoun": "他"}],
                           "time": None}]}
    r = run("他从管线镇来到了钟楼。", facts=[PA], must=["f0"])
    check(not r["hardPass"], "grant: no plan means no pronoun")
    r = j.judge([PA], ["f0"], plan, "他从管线镇来到了钟楼。", "stop")
    check(r["hardPass"], "grant: a legal pronoun matches")


def main() -> int:
    for fn in (test_observer_subject_first, test_same_name_descriptors_bind,
               test_negation_scope, test_v4_rulings_kept, test_parity):
        before = len(FAILURES)
        fn()
        print(("ok   " if len(FAILURES) == before else "FAIL ") + fn.__name__)
    if FAILURES:
        for f in FAILURES:
            print("  -", f)
        print(f"FAIL: {len(FAILURES)} check(s)")
        return 1
    print("PASS: judge_v4_1 checks (observer attribution, descriptor binding, "
          "negation scope, v4 rulings, parity)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
