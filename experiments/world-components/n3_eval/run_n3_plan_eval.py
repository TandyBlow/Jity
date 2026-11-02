# N3 organisation dev diagnostic (review round): pre-registered checks for
# the plan_v3 grouping/time/coreference rules. This is a DEVELOPMENT set,
# not a formal holdout: it is constructed to exercise the known semantic
# assumptions (same-goal merge, time attachment, same-name split, pronoun
# safety) and to catch regressions. It does not claim naturalness or
# end-to-end narrative quality.
#
# Criteria, frozen here before the run:
#   G1 invariants: check_plan_v3(plan) is empty for every non-refusal case.
#   G2 same-goal merge: task facts merge IFF the verbatim goal AND the
#      resolved location agree; a different or missing location never merges;
#      three facts merge pairwise by place (A@L1, B@L2, C@L1 -> {A,C}, {B}).
#   G3 same-name: no group holds two same-name entities; no pronoun grant is
#      emitted for a plan-wide duplicated display name.
#   G4 time: leading time joins the first entity group; otherwise it joins
#      the input-order predecessor's group; consecutive times share the
#      predecessor group; a lone time is refused; a lone no_change is ONE
#      legal group (coverage; refusing it would drop a selected fact).
#   G5 coreference: a grant requires a gender hint, a plan-wide unique name
#      and no same-pronoun collision inside the group; unknown -> TA;
#      no hint / duplicate name -> no grant.
#   G6 order: within-group input order; groups by minimum input index
#      (the frozen entity-bucket R1 convention, recorded not re-litigated).
#   G7 refusals: ill-formed ids, lone time, and no-entity plans refuse.
#
# Usage: python experiments/world-components/n3_eval/run_n3_plan_eval.py
# Output: artifacts/world-components/n3-plan-v3-eval-r1.json

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(WC))

import n3_organize  # noqa: E402


def fact(fid, kind, eid=None, name=None, **kw):
    d = {"factId": fid, "kind": kind}
    if eid is not None:
        d["entityId"] = eid
    if name is not None:
        d["name"] = name
    d.update(kw)
    return d


def moved(fid, eid, name, at, frm="旧地"):
    return fact(fid, "moved", eid, name, **{"from": frm, "to": at, "at": at})


def task(fid, eid, name, goal, at, **kw):
    return fact(fid, "task_achieved", eid, name, goal=goal, at=at, **kw)


def timef(fid, amount=5, unit="minute"):
    return fact(fid, "time", amount=amount, unit=unit)


def noch(fid):
    return fact(fid, "no_change", scope="全局")


def case(name, facts, names, hints=None, groups=None, times=None,
         grants=None, consecutive=None, refusal=None):
    return {"name": name, "facts": facts, "names": names,
            "hints": hints or {}, "groups": groups, "times": times,
            "grants": grants, "consecutive": consecutive,
            "refusal": refusal}


def group_sets(plan):
    return [set(s["factIds"]) for s in plan["sentences"]]


def time_placements(plan):
    out = {}
    for i, s in enumerate(plan["sentences"]):
        for fid in s["factIds"]:
            out[fid] = i
    return out


def grant_set(plan):
    out = set()
    for i, s in enumerate(plan["sentences"]):
        for g in s["coreference"]:
            out.add((i, g["refersTo"], g["pronoun"]))
    return out


def expected_grants(grants):
    return {(i, eid, p) for i, (eid, p) in enumerate(grants) if p}


def eval_case(c):
    plan = n3_organize.plan_v3(c["facts"], c["names"], c["hints"])
    rec = {"name": c["name"], "plan": plan, "checks": {}}
    if c["refusal"]:
        got = json.dumps(plan.get("refusal") or {}, ensure_ascii=False)
        rec["checks"]["refusal"] = c["refusal"] in got
        rec["pass"] = rec["checks"]["refusal"]
        return rec
    if "refusal" in plan:
        rec["checks"]["unexpected_refusal"] = False
        rec["pass"] = False
        return rec
    problems = n3_organize.check_plan_v3(plan, c["facts"], c["names"],
                                         c["hints"])
    rec["checks"]["G1_invariants"] = not problems
    rec["invariantProblems"] = problems
    got_groups = group_sets(plan)
    rec["checks"]["G2_groups"] = got_groups == [set(g) for g in c["groups"]]
    if c["times"] is not None:
        placements = time_placements(plan)
        rec["checks"]["G4_time"] = all(
            placements.get(fid) == gi for fid, gi in c["times"].items())
    if c["grants"] is not None:
        rec["checks"]["G5_grants"] = grant_set(plan) == expected_grants(
            c["grants"])
    if c["consecutive"] is not None:
        rec["checks"]["G4_consecutive"] = \
            plan["edges"]["consecutive-time"] is c["consecutive"]
    rec["pass"] = all(rec["checks"].values())
    return rec


def main() -> int:
    A, B, C, D = "e_a", "e_b", "e_c", "e_d"
    L1, L2 = "loc_1", "loc_2"
    n_ab = {A: "甲", B: "乙", C: "丙", D: "丁"}
    n_same = {A: "乙", B: "乙"}

    cases = [
        # R1/R5 order
        case("single-entity-order",
             [moved("f0", A, "甲", L1), task("f1", A, "甲", "修桥", L1)],
             n_ab, groups=[["f0", "f1"]]),
        case("two-entities-first-appearance",
             [moved("f0", A, "甲", L1), task("f1", B, "乙", "补网", L1)],
             n_ab, groups=[["f0"], ["f1"]]),
        case("entity-bucket-interleaved",
             [moved("f0", A, "甲", L1), moved("f1", B, "乙", L1),
              task("f2", A, "甲", "修桥", L1)],
             n_ab, groups=[["f0", "f2"], ["f1"]],
             times=None, grants=None),
        # R2 same-goal merge: same place merges; different/missing does not
        case("same-goal-same-place",
             [task("f0", A, "甲", "抬钟", L1), task("f1", B, "乙", "抬钟", L1)],
             n_ab, groups=[["f0", "f1"]]),
        case("same-goal-different-place",
             [task("f0", A, "甲", "抬钟", L1), task("f1", B, "乙", "抬钟", L2)],
             n_ab, groups=[["f0"], ["f1"]]),
        case("same-goal-missing-place",
             [task("f0", A, "甲", "抬钟", L1), task("f1", B, "乙", "抬钟", None)],
             n_ab, groups=[["f0"], ["f1"]]),
        case("same-goal-ambiguous-place",
             [task("f0", A, "甲", "抬钟", L1),
              task("f1", B, "乙", "抬钟", L1, atAmbiguous=True)],
             n_ab, groups=[["f0"], ["f1"]]),
        case("same-goal-three-places",
             [task("f0", A, "甲", "抬钟", L1), task("f1", B, "乙", "抬钟", L2),
              task("f2", C, "丙", "抬钟", L1)],
             n_ab, groups=[["f0", "f2"], ["f1"]]),
        # R2b same-name split
        case("same-name-shared-goal",
             [task("f0", A, "乙", "抬钟", L1), task("f1", B, "乙", "抬钟", L1)],
             n_same, groups=[["f0"], ["f1"]],
             grants=[(None, None), (None, None)]),
        case("same-name-other-facts",
             [moved("f0", A, "乙", L1), task("f1", B, "乙", "补网", L1)],
             n_same, groups=[["f0"], ["f1"]],
             grants=[(None, None), (None, None)]),
        # R3 time attribution
        case("time-leading",
             [timef("f0"), moved("f1", A, "甲", L1)],
             n_ab, groups=[["f0", "f1"]], times={"f0": 0}),
        case("time-middle",
             [moved("f0", A, "甲", L1), timef("f1"),
              task("f2", B, "乙", "补网", L1)],
             n_ab, groups=[["f0", "f1"], ["f2"]], times={"f1": 0}),
        case("time-trailing",
             [moved("f0", A, "甲", L1), task("f1", B, "乙", "补网", L1),
              timef("f2")],
             n_ab, groups=[["f0"], ["f1", "f2"]], times={"f2": 1}),
        case("time-after-scene",
             [moved("f0", A, "甲", L1),
              fact("f1", "positioned_at", "loc_1", "钟楼", at="钟楼"),
              timef("f2")],
             n_ab, groups=[["f0"], ["f1", "f2"]], times={"f2": 1}),
        case("time-consecutive",
             [moved("f0", A, "甲", L1), timef("f1"), timef("f2")],
             n_ab, groups=[["f0", "f1", "f2"]],
             times={"f1": 0, "f2": 0}, consecutive=True),
        case("no-change-time",
             [timef("f0"), noch("f1")],
             n_ab, groups=[["f0", "f1"]], times={"f0": 0}),
        case("no-change-lone",
             [noch("f0")], n_ab, groups=[["f0"]], times={}),
        # refusals
        case("time-orphan", [timef("f0")], n_ab, refusal="time-orphan"),
        case("no-entity",
             [fact("f0", "mood", scope="global")], n_ab,
             refusal="no-entity"),
        case("ill-formed-duplicate",
             [moved("f0", A, "甲", L1), moved("f0", B, "乙", L2)],
             n_ab, refusal="ill-formed"),
        # R6 grants
        case("coref-unique",
             [moved("f0", A, "甲", L1), task("f1", B, "乙", "补网", L1)],
             n_ab, hints={A: "male", B: "female"},
             groups=[["f0"], ["f1"]],
             grants=[(A, "他"), (B, "她")]),
        case("coref-duplicate-name",
             [moved("f0", A, "乙", L1), task("f1", B, "乙", "补网", L1)],
             n_same, hints={A: "male", B: "male"},
             groups=[["f0"], ["f1"]],
             grants=[(None, None), (None, None)]),
        case("coref-same-pronoun-group",
             [task("f0", A, "甲", "抬钟", L1),
              task("f1", B, "乙", "抬钟", L1)],
             n_ab, hints={A: "male", B: "male"},
             groups=[["f0", "f1"]], grants=[(A, "他")]),
        case("coref-no-hint",
             [moved("f0", A, "甲", L1), task("f1", B, "乙", "补网", L1)],
             n_ab, groups=[["f0"], ["f1"]],
             grants=[(None, None), (None, None)]),
        case("coref-unknown",
             [moved("f0", A, "甲", L1)], n_ab, hints={A: "unknown"},
             groups=[["f0"]], grants=[(A, "TA")]),
    ]

    results = [eval_case(c) for c in cases]
    failures = [r["name"] for r in results if not r["pass"]]
    archive = {
        "purpose": "N3 plan_v3 development diagnostic (review round): "
                   "same-goal place precondition, lone no_change coverage, "
                   "time attribution, same-name split and pronoun grants",
        "scope": "development diagnostic, not a formal holdout; no "
                 "naturalness or end-to-end quality claim",
        "criteria": {
            "G1": "check_plan_v3 empty",
            "G2": "merge iff same goal AND same non-null, non-ambiguous "
                  "location; pairwise by place; missing/different/ambiguous "
                  "location never merges",
            "G3": "same-name entities never share a group; no grant for a "
                  "duplicated name",
            "G4": "leading time -> first entity group; else predecessor "
                  "group; consecutive times share; lone time refused; lone "
                  "no_change is one legal group",
            "G5": "grant needs hint + unique name + no in-group pronoun "
                  "collision; unknown -> TA; no hint -> no grant",
            "G6": "within-group input order; groups by minimum input index",
            "G7": "ill-formed/lone-time/no-entity refuse",
        },
        "cases": results,
        "summary": {"cases": len(cases), "passed": len(cases) - len(failures),
                    "failed": failures},
        "remainingGaps": [
            "cross-group pronoun ambiguity is not modeled; grants are "
            "group-local, so two adjacent groups may each license 他/她 "
            "without a plan-level chain",
            "time attachment to a preceding scene group is the frozen "
            "predecessor convention, not a semantic scope",
            "entity buckets can reorder interleaved input facts (R1 frozen; "
            "recorded here, not re-litigated)",
            "group size / sentence boundary is not constrained; N4 must "
            "still fit the 128-token gate",
        ],
        "pass": not failures,
    }
    out = REPO / "artifacts" / "world-components" / "n3-plan-v3-eval-r1.json"
    out.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    for r in results:
        print(("PASS" if r["pass"] else "FAIL"), r["name"],
              {k: v for k, v in r["checks"].items() if not v})
    print(f"N3 dev diagnostic: {len(cases) - len(failures)}/{len(cases)} -> {out}")
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
