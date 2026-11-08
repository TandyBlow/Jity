# Unit checks for the adjudicated N5 v3 (`judge_v3.py`).
#
# Plain asserts, no test framework (the repository's pytest boundary covers
# backend code; these experiments use runnable scripts). Every check below
# names the ruling it protects:
#
#   D1  outcome + resultText is judgeable; a missing resultText BLOCKS and the
#       task goal is never accepted as a substitute.
#   D2  a vague expression covers the time fact; a stated duration is compared
#       numerically with the authoritative time fact (a fabricated value fails,
#       and so does a duration when the row has no time fact).
#   D4  unregistered-name counts come from labels: unchecked -> null,
#       checked-and-clean -> 0, checked-with-names -> list.
#   D5  G4/G5 fire from DATA (same display name, two entity ids), not from a
#       case name; one occurrence cannot satisfy two identical facts.
#   D3  quality() never returns "pass" without an executed N6 result.
#
# Usage: python -X utf8 test_judge_v3.py

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge_v3 as j  # noqa: E402

FAILURES = []


def check(cond, label):
    if not cond:
        FAILURES.append(label)


def facts_pair(kind="task_achieved", **over):
    f0 = {"factId": "f0", "kind": "moved", "entityId": "char_pa",
          "name": "管线甲", "from": "管线镇", "to": "钟楼",
          "entityGroup": "characters"}
    f1 = {"factId": "f1", "kind": kind, "entityId": "char_pa",
          "name": "管线甲", "goal": "把铜铃挂回钟楼",
          "entityGroup": "characters", **over}
    return [f0, f1]


PLAN = {"sentences": [{"index": 0, "factIds": ["f0", "f1"],
                       "coreference": [], "time": None}]}


def outcome_facts(result_text="把铜铃挂回了钟楼"):
    return facts_pair(kind="outcome", resultText=result_text)


def test_d1():
    facts = outcome_facts()
    r = j.judge(facts, ["f0", "f1"], PLAN,
                "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。")
    check(r["hardPass"], "D1: outcome with resultText passes")
    check("G1_alignment" in r["gates"], "D1: G1 reported")

    # goal quoted instead of the result text: not a substitute
    r = j.judge(facts, ["f0", "f1"], PLAN,
                "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。")
    check(not r["hardPass"], "D1: quoting the goal does not cover an outcome")
    check(any(p.startswith("uncovered:f1:outcome") for p in r["problems"]),
          "D1: goal text leaves the outcome uncovered")

    # missing resultText blocks, never falls back to the goal
    blocked = None
    try:
        j.judge(outcome_facts(result_text=None), ["f0", "f1"], PLAN,
                "管线甲把铜铃挂回了钟楼。")
    except j.JudgeBlocked as exc:
        blocked = exc.code
    check(blocked == "outcome-result-missing", "D1: missing resultText blocks")


def time_facts(amount=8, unit="minute"):
    return facts_pair(kind="task_achieved") + [
        {"factId": "f2", "kind": "time", "amount": amount, "unit": unit}]


def test_d2():
    facts = time_facts()
    must = ["f0", "f1", "f2"]
    base = "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。"

    r = j.judge(facts, must, PLAN, base + "过了一会儿。")
    check(r["gates"]["G3_time"], "D2: vague expression covers the time fact")
    check(r["time"]["vague"] == "过了一会儿", "D2: vague token recorded")

    r = j.judge(facts, must, PLAN, base + "前后大约八分钟过去了。")
    check(r["gates"]["G3_time"], "D2: the authoritative value passes")

    r = j.judge(facts, must, PLAN, base + "大约十小时过去了。")
    check(not r["gates"]["G3_time"], "D2: a fabricated value fails")
    check(any("time-value-mismatch" in p for p in r["problems"]),
          "D2: mismatch is named")

    r = j.judge(facts, must, PLAN, base)
    check(not r["gates"]["G3_time"], "D2: omitting time entirely fails")

    # a duration in a row with no time fact is an invented claim
    no_time = facts_pair(kind="task_achieved")
    r = j.judge(no_time, ["f0", "f1"], PLAN, base + "大约八分钟过去了。")
    check(not r["gates"]["G3_time"], "D2: duration without a time fact fails")
    check(any("time-value-without-fact" in p for p in r["problems"]),
          "D2: invented duration is named")


def test_d2_regressions():
    """Reviewer counter-examples (2026-11-08): the first duration scanner only
    matched a trailing numeral and let wrong values through. Each case below
    must fail; the compliant ones must still pass."""
    facts = time_facts()
    must = ["f0", "f1", "f2"]
    base = "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。"

    def g3(text):
        r = j.judge(facts, must, PLAN, base + text)
        return r["gates"]["G3_time"], r["problems"]

    ok, _ = g3("8.8分钟过去了。")
    check(not ok, "D2 regression: 8.8分钟 must not be read as 8分钟")
    ok, probs = g3("8.8分钟过去了。")
    check(any("time-value-mismatch" in p for p in probs),
          "D2 regression: decimal mismatch is named")

    ok, _ = g3("负八分钟过去了。")
    check(not ok, "D2 regression: a negative duration must fail")

    ok, probs = g3("过了一会儿，八分半钟过去了。")
    check(not ok, "D2 regression: 八分半钟 must not pass via the vague clause")
    check(any("time-value-mismatch" in p for p in probs),
          "D2 regression: half-minute value is parsed (8.5) and compared")

    ok, probs = g3("几分钟过去了。")
    check(not ok, "D2 regression: an unparseable duration fails")
    check(any("time-value-unparseable" in p for p in probs),
          "D2 regression: unparseable duration is named")

    ok, _ = g3("约八分钟过去了。")
    check(ok, "D2 regression: the authoritative value still passes")
    ok, _ = g3("过了一会儿。")
    check(ok, "D2 regression: a pure vague clause still passes")


def test_pronoun_grant():
    """Reviewer finding (2026-11-08): v3 ignored plan grants and rejected a
    legal 他 grant that v2 accepts."""
    facts = [{"factId": "f0", "kind": "moved", "entityId": "char_pa",
              "name": "管线甲", "from": "管线镇", "to": "钟楼",
              "entityGroup": "characters"}]
    plan = {"sentences": [{"index": 0, "factIds": ["f0"],
                           "coreference": [{"mention": "他",
                                            "refersTo": "char_pa",
                                            "pronoun": "他"}],
                           "time": None}]}
    r = j.judge(facts, ["f0"], plan, "他从管线镇来到了钟楼。")
    check(r["hardPass"], "grant: a legal 他 grant is matched")
    r = j.judge(facts, ["f0"], plan, "管线甲从管线镇来到了钟楼。")
    check(r["hardPass"], "grant: the plain name is still accepted")
    r = j.judge(facts, ["f0"], plan, "他从管线镇来到了桥头。")
    check(not r["hardPass"], "grant: a wrong destination still fails")

    # same-name restriction survives: a grant on a same-name entity fails G5
    facts2 = same_name_facts()
    plan2 = {"sentences": [{"index": 0, "factIds": ["f0", "f1"],
                            "coreference": [{"mention": "他",
                                             "refersTo": "char_pb",
                                             "pronoun": "他"}],
                            "time": None}]}
    r = j.judge(facts2, ["f0", "f1"], plan2,
                "管线乙完成了任务「合力抬钟」。管线乙完成了任务「合力抬钟」。")
    check(r["gates"].get("G5_same_name_discipline") is False,
          "grant: same-name grant still fails G5")
    check(not r["hardPass"], "grant: same-name grant still rejected")


def same_name_facts():
    return [
        {"factId": "f0", "kind": "task_achieved", "entityId": "char_pb",
         "name": "管线乙", "goal": "合力抬钟", "entityGroup": "characters"},
        {"factId": "f1", "kind": "task_achieved", "entityId": "char_pc",
         "name": "管线乙", "goal": "合力抬钟", "entityGroup": "characters"},
    ]


def test_d5():
    facts = same_name_facts()
    must = ["f0", "f1"]
    two = "管线乙完成了任务「合力抬钟」。管线乙完成了任务「合力抬钟」。"
    one = "管线乙完成了任务「合力抬钟」。"

    r = j.judge(facts, must, PLAN, two)
    check(r["triggers"]["G4"], "D5: G4 triggers on two same-name entities")
    check(r["gates"].get("G4_conflict_names") is True,
          "D5: two mentions satisfy G4")
    check(r["hardPass"], "D5: two same-name actors can pass")

    r = j.judge(facts, must, PLAN, one)
    check(r["gates"].get("G4_conflict_names") is False,
          "D5: one mention fails G4")
    check(not r["hardPass"], "D5: one occurrence cannot satisfy both facts")

    # different names never trigger G4
    other = [
        {"factId": "f0", "kind": "task_achieved", "entityId": "char_pa",
         "name": "管线甲", "goal": "合力抬钟", "entityGroup": "characters"},
        {"factId": "f1", "kind": "task_achieved", "entityId": "char_pb",
         "name": "管线乙", "goal": "合力抬钟", "entityGroup": "characters"},
    ]
    r = j.judge(other, ["f0", "f1"], PLAN,
                "管线甲完成了任务「合力抬钟」。管线乙完成了任务「合力抬钟」。")
    check(not r["triggers"]["G4"], "D5: different names do not trigger G4")
    check("G4_conflict_names" not in r["gates"],
          "D5: untriggered G4 has no gate value")

    # G5: a grant for a same-name entity must fail
    plan_grant = {"sentences": [{"index": 0, "factIds": ["f0", "f1"],
                                 "coreference": [{"mention": "他",
                                                  "refersTo": "char_pb",
                                                  "pronoun": "他"}],
                                 "time": None}]}
    r = j.judge(facts, must, plan_grant, two)
    check(r["triggers"]["G5"], "D5: G5 triggers on a same-name grant")
    check(r["gates"].get("G5_same_name_discipline") is False,
          "D5: same-name grant fails G5")
    check(not r["hardPass"], "D5: same-name grant is rejected")

    # no grant -> G5 not triggered, no gate value
    r = j.judge(facts, must, PLAN, two)
    check(not r["triggers"]["G5"], "D5: no grant, G5 not triggered")
    check("G5_same_name_discipline" not in r["gates"],
          "D5: untriggered G5 has no gate value")


def test_case_id_invariance():
    facts = same_name_facts()
    plan = dict(PLAN)
    a = j.judge(facts, ["f0", "f1"], plan,
                "管线乙完成了任务「合力抬钟」。", "eos")
    b = j.judge(facts, ["f0", "f1"], plan,
                "管线乙完成了任务「合力抬钟」。", "eos")
    check(a["gates"] == b["gates"], "D5: repeated judgement is stable")
    check("rowId" not in j.judge.__code__.co_varnames,
          "D5: judge takes no rowId at all")


def test_d4():
    check(j.unregistered_names(None) == {"checked": False, "count": None,
                                         "items": []},
          "D4: no labels -> count null")
    clean = j.unregistered_names([])
    check(clean["checked"] and clean["count"] == 0,
          "D4: checked and clean -> count 0")
    found = j.unregistered_names([{"snippet": "这时管线丙从巷口走来",
                                   "position": "第3句"}])
    check(found["count"] == 1, "D4: labelled name is counted")
    check(found["items"][0]["source"] == "human",
          "D4: default annotation source is human")
    check(found["items"][0]["reviewStatus"] == "pending-independent-review",
          "D4: default review status is pending")
    err = None
    try:
        j.unregistered_names([{"position": "第1句"}])
    except j.JudgeBlocked as exc:
        err = exc.code
    check(err == "annotation-shape-invalid",
          "D4: an annotation without a snippet is rejected")


def test_d3_quality():
    check(j.quality(None) == "pending", "D3: no N6 -> pending")
    check(j.quality({"status": "not-run"}) == "pending",
          "D3: N6 not-run -> pending")
    check(j.quality({"status": "executed", "result": "pass"}) == "pass",
          "D3: executed pass -> pass")
    check(j.quality({"status": "executed", "result": None}) == "undetermined",
          "D3: executed without judgement -> undetermined")
    check(j.quality({"status": "weird"}) == "undetermined",
          "D3: unknown status -> undetermined")


def main() -> int:
    for fn in (test_d1, test_d2, test_d2_regressions, test_pronoun_grant,
               test_d5, test_case_id_invariance, test_d4, test_d3_quality):
        fn()
    if FAILURES:
        print(f"FAIL ({len(FAILURES)})")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("PASS: judge_v3 unit checks (D1, D2, D2 regressions, grants, "
          "D3, D4, D5)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
