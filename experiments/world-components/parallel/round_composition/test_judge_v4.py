"""Unit checks for N5 v4 (the owner's 2026-11-09 gate rulings).

Plain asserts, no test framework. Each block names the ruling it protects:

  G2   a repeated registered name is a diagnostic; a leaked goal still fails.
  G1   pass / reject / needs-semantic-review: negation, irrealis, conditional,
       rhetorical and quoted speech are rejected; an observer frame or a result
       without a subject goes to semantic review, which is NOT a pass.
  G4   no name counting: two same-name actors need their own identifying
       descriptor in the text, otherwise the verdict is `undetermined`.
  G6   stop/eos normal, length truncated, load not a success, missing/unknown
       reason blocks the judgement.

Parity blocks (D1, D2, grants, D3, D5) protect the machinery imported from the
frozen v3 so the new version cannot silently drift where nothing changed.

Usage: python -X utf8 test_judge_v4.py
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge_v4 as j  # noqa: E402
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
PLAN = {"sentences": [{"index": 0, "factIds": ["f0", "f1"],
                       "coreference": [], "time": None}],
        "edges": {"consecutive-time": False}}

GOOD = "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。"


def run(text, finish="stop", facts=None, must=None, plan=PLAN):
    return j.judge(facts or [PA, OUT], must or ["f0", "f1"], plan, text, finish)


def status(text, finish="stop"):
    r = run(text, finish)
    return r["status"], r["hardPass"], r["problems"], r["diagnostics"]


def test_g2_diagnostics():
    r = run(GOOD + "管线甲在窗边站定。")
    check(r["hardPass"], "G2: a repeated registered name is not a rejection")
    check(any(d["name"] == "管线甲" and d["code"] == "residue-name"
              for d in r["diagnostics"]), "G2: the repetition is recorded")

    leak = "管线甲从管线镇来到了钟楼。任务「把铜铃挂回原位」还没有结束。"
    facts = [PA, dict(OUT, kind="task_achieved", goal="把铜铃挂回原位")]
    r = run(leak, facts=facts, must=["f0", "f1"])
    check(not r["hardPass"], "G2: a leaked goal still fails")
    check(not r["gates"]["G2_goal_residue"], "G2: goal gate is false")
    check(any(p.startswith("residue-goal") for p in r["problems"]),
          "G2: the leaked goal is named")


def test_g1_rejections():
    cases = {
        "negation": "管线甲从管线镇来到了钟楼。管线甲并未把铜铃挂回了钟楼。",
        "irrealis": "管线甲从管线镇来到了钟楼。管线甲差点就把铜铃挂回了钟楼。",
        "conditional": "管线甲从管线镇来到了钟楼。如果管线甲把铜铃挂回了钟楼，钟声就会响。",
        "rhetorical": "管线甲从管线镇来到了钟楼。难道管线甲把铜铃挂回了钟楼？",
        "quoted": "管线甲从管线镇来到了钟楼。他说「管线甲把铜铃挂回了钟楼」。",
        "reported": "管线甲从管线镇来到了钟楼。他听人说管线甲把铜铃挂回了钟楼。",
    }
    for label, text in cases.items():
        st, passed, probs, _ = status(text)
        check(not passed, f"G1: {label} must not pass")
        check(st == "judged", f"G1: {label} is a rejection, not a review")
        check(any(p.startswith("fact-rejected:f1") for p in probs),
              f"G1: {label} names the rejected fact")


def test_g1_review():
    observer = "管线甲从管线镇来到了钟楼。王五看见管线甲把铜铃挂回了钟楼。"
    st, passed, probs, _ = status(observer)
    check(not passed, "G1: an observer frame must not pass")
    check(st == "needs-semantic-review", "G1: observer goes to review")
    check(any("observer" in p for p in probs), "G1: observer is named")

    subjectless = "管线甲从管线镇来到了钟楼。把铜铃挂回了钟楼。"
    st, passed, probs, _ = status(subjectless)
    check(not passed, "G1: a result without a subject must not pass")
    check(st == "needs-semantic-review", "G1: subjectless result goes to review")
    check(any("without-subject" in p for p in probs),
          "G1: subjectless result is named")

    # pro-drop inside a matching clause still passes when the name is present
    st, passed, _, _ = status(GOOD + "管线甲在窗边站定。")
    check(passed, "G1: a clean clause still passes")


def test_g4_undetermined():
    a = {"factId": "g0", "kind": "moved", "entityId": "char_y1",
         "name": "管线乙", "entityGroup": "characters",
         "from": "管线镇", "to": "钟楼"}
    b = {"factId": "g1", "kind": "moved", "entityId": "char_y2",
         "name": "管线乙", "entityGroup": "characters",
         "from": "钟楼", "to": "广场"}
    text = "管线乙从管线镇来到了钟楼。管线乙从钟楼来到了广场。"
    r = run(text, facts=[a, b], must=["g0", "g1"])
    check(r["status"] == "undetermined", "G4: no descriptor -> undetermined")
    check(not r["hardPass"], "G4: undetermined is not a pass")
    check(any(p.startswith("same-name-indistinguishable") for p in r["problems"]),
          "G4: the finding is named")

    a2, b2 = dict(a, text="沉默"), dict(b, text="急躁")
    named = "沉默的管线乙从管线镇来到了钟楼。急躁的管线乙从钟楼来到了广场。"
    r = run(named, facts=[a2, b2], must=["g0", "g1"])
    check(r["status"] == "judged" and r["hardPass"],
          "G4: descriptors in the text separate the actors")

    # the old count-only trick: one person written twice
    r = run("管线乙从管线镇来到了钟楼。管线乙站在钟楼里。",
            facts=[a, b], must=["g0", "g1"])
    check(not r["hardPass"], "G4: two mentions do not satisfy two moves")


def test_g6_finish():
    check(run(GOOD, "stop")["hardPass"], "G6: stop is a normal end")
    check(run(GOOD, "eos")["hardPass"], "G6: eos is a normal end")
    r = run(GOOD, "length")
    check(not r["gates"]["G6_completion"], "G6: length is truncation")
    r = run(GOOD, "load")
    check(not r["gates"]["G6_completion"], "G6: load is not a success")
    for bad in (None, "", "timeout"):
        try:
            run(GOOD, bad)
        except JudgeBlocked as exc:
            check(exc.code in ("finish-reason-missing", "finish-reason-unknown"),
                  f"G6: {bad!r} blocks with the right code")
        else:
            raise AssertionError(f"G6: finish reason {bad!r} was accepted")


def test_parity_d1():
    facts = [PA, dict(OUT, resultText=None)]
    try:
        run(GOOD, facts=facts, must=["f0", "f1"])
    except JudgeBlocked as exc:
        check(exc.code == "outcome-result-missing", "D1: missing resultText blocks")
    else:
        raise AssertionError("D1: a missing resultText was judged")

    blank = dict(OUT, resultText="   ")
    try:
        run(GOOD, facts=[PA, blank], must=["f0", "f1"])
    except JudgeBlocked as exc:
        check(exc.code == "outcome-result-missing",
              "D1: a blank resultText blocks instead of falling back")
    else:
        raise AssertionError("D1: a blank resultText was judged")


def test_parity_d2():
    facts = [PA, dict(OUT, kind="task_achieved", goal="把铜铃挂回钟楼"),
             {"factId": "f2", "kind": "time", "amount": 8, "unit": "minute"}]
    must = ["f0", "f1", "f2"]
    base = "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。"

    check(run(base + "过了一会儿。", facts=facts, must=must)["gates"]["G3_time"],
          "D2: a vague expression covers the time fact")
    check(run(base + "前后大约八分钟过去了。", facts=facts,
              must=must)["gates"]["G3_time"], "D2: the authoritative value passes")
    check(not run(base + "大约十小时过去了。", facts=facts,
                  must=must)["gates"]["G3_time"], "D2: a fabricated value fails")
    check(not run(base, facts=facts, must=must)["gates"]["G3_time"],
          "D2: omitting time fails")
    no_time = [PA, dict(OUT, kind="task_achieved", goal="把铜铃挂回钟楼")]
    r = run(base + "大约八分钟过去了。", facts=no_time, must=["f0", "f1"])
    check(not r["gates"]["G3_time"], "D2: an invented duration fails")


def test_parity_grants():
    plan = {"sentences": [{"index": 0, "factIds": ["f0"],
                           "coreference": [{"mention": "他",
                                            "refersTo": "char_pa",
                                            "pronoun": "他"}],
                           "time": None}]}
    r = run("他从管线镇来到了钟楼。", facts=[PA], must=["f0"], plan=plan)
    check(r["hardPass"], "grant: a legal pronoun still matches")
    r = run("他从管线镇来到了桥头。", facts=[PA], must=["f0"], plan=plan)
    check(not r["hardPass"], "grant: a wrong destination still fails")


def test_d3_quality():
    check(j.quality(None) == "pending", "D3: no N6 -> pending")
    check(j.quality({"status": "not-run"}) == "pending",
          "D3: not-run -> pending")
    check(j.quality({"status": "executed", "result": "pass"}) == "pass",
          "D3: an executed pass is reported")
    check(j.quality({"status": "executed", "result": "maybe"}) == "undetermined",
          "D3: an unknown result is undetermined")


def main() -> int:
    for fn in (test_g2_diagnostics, test_g1_rejections, test_g1_review,
               test_g4_undetermined, test_g6_finish, test_parity_d1,
               test_parity_d2, test_parity_grants, test_d3_quality):
        before = len(FAILURES)
        fn()
        print(("ok   " if len(FAILURES) == before else "FAIL ") + fn.__name__)
    if FAILURES:
        print("failures:")
        for f in FAILURES:
            print("  -", f)
        print(f"FAIL: {len(FAILURES)} check(s)")
        return 1
    print("PASS: judge_v4 unit checks (G1 tri-state, G2 diagnostics, G4 "
          "undetermined, G6 finish, D1/D2/grants/D3 parity)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
