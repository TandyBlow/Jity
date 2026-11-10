"""Checks for N5 v4.3: confirmed failures must not hide behind `undetermined`.

Cases:
- a truncated passage with everything else fine is a FAILURE (judged), with
  failureKinds ["finish-length"];
- two same-name actors with identical descriptors, everything else covered, is
  genuinely undetermined (no confirmed failure);
- the same row truncated reports BOTH the truncation and the identity doubt, and
  the status stays a failure;
- an uncovered fact plus identity doubt keeps the uncovered fact named.

Usage: python -X utf8 test_judge_v4_3.py
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge_v4_3 as j  # noqa: E402

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
GOOD = "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。"
SAME_COVERED = "急躁的管线乙从管线镇来到了钟楼。急躁的管线乙从钟楼来到了广场。"


def ids(desc1="急躁", desc2="急躁"):
    return {"version": "t", "entries": {
        "char_y1": {"entityId": "char_y1", "name": "管线乙",
                    "descriptor": desc1, "field": "性格", "source": "s1"},
        "char_y2": {"entityId": "char_y2", "name": "管线乙",
                    "descriptor": desc2, "field": "性格", "source": "s2"}},
        "sameName": {}, "sameNameField": {}, "indistinguishable": {}}


def test_truncation_is_a_failure():
    r = j.judge([PA, OUT], ["f0", "f1"], None, GOOD, "length")
    check(r["status"] == "judged", "truncation: status is a failure")
    check(r["hardPass"] is False, "truncation: not a pass")
    check("finish-length" in r["failureKinds"],
          "truncation: the kind is recorded")
    check(not r["gates"]["G6_completion"], "truncation: G6 false")


def test_identity_doubt_alone():
    r = j.judge([A, B], ["g0", "g1"], None, SAME_COVERED, "stop",
                identities=ids())
    check(r["status"] == "undetermined",
          "identity only: undetermined when nothing else failed")
    check(r["failureKinds"] == ["same-name-undetermined"],
          "identity only: the reason is recorded")
    check(r["gates"]["G4_conflict_names"] == "undetermined",
          "identity only: G4 is undetermined")
    check(all(v["status"] == "ok" for v in r["facts"].values()),
          "identity only: per-fact results are kept")


def test_truncation_beats_undetermined():
    r = j.judge([A, B], ["g0", "g1"], None, SAME_COVERED, "length",
                identities=ids())
    check(r["status"] == "judged",
          "both: a confirmed truncation keeps the row a failure")
    check(r["hardPass"] is False, "both: not a pass")
    check("finish-length" in r["failureKinds"],
          "both: the truncation is named")
    check("same-name-undetermined" in r["failureKinds"],
          "both: the identity doubt is named separately")
    check(r["gates"]["G4_conflict_names"] == "undetermined",
          "both: G4 stays undetermined")


def test_uncovered_kept_with_identity():
    text = "急躁的管线乙从管线镇来到了钟楼。"
    r = j.judge([A, B], ["g0", "g1"], None, text, "stop", identities=ids())
    check(r["status"] == "judged", "uncovered: a missing fact is a failure")
    check(any(k.startswith("uncovered:") for k in r["failureKinds"]),
          "uncovered: the fact id is recorded")
    check("same-name-undetermined" in r["failureKinds"],
          "uncovered: identity doubt stays visible")


def test_pass_unchanged():
    r = j.judge([PA, OUT], ["f0", "f1"], None, GOOD, "stop")
    check(r["hardPass"], "pass: a clean row still passes")
    check(r["failureKinds"] == [], "pass: no failure kinds")


def main() -> int:
    for fn in (test_truncation_is_a_failure, test_identity_doubt_alone,
               test_truncation_beats_undetermined, test_uncovered_kept_with_identity,
               test_pass_unchanged):
        before = len(FAILURES)
        fn()
        print(("ok   " if len(FAILURES) == before else "FAIL ") + fn.__name__)
    if FAILURES:
        for f in FAILURES:
            print("  -", f)
        print(f"FAIL: {len(FAILURES)} check(s)")
        return 1
    print("PASS: judge_v4_3 checks (failure kinds, identity doubt, truncation)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
