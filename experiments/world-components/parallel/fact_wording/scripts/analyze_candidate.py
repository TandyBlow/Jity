"""Analyse the T1 diagnostic against r1 greedy with the pre-registered criteria.

Inputs
  r1 run: artifacts/fact-wording/diagnostic-r1/*/raw.jsonl + blind/judged-*.json + blind/map.json
  T1 run: artifacts/fact-wording/diagnostic-r2-cand-t1/*/raw.jsonl + blind/judged-*.json + blind/map.json
  overlap labels: cf24-overlap.json (seen-fact / independent)

Output: <T1 run>/candidate-analysis.json and a printed summary.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
NEXT = Path(os.environ.get("JITY_REPO", "<repo>") + "/.local/world-components-next-worktree")
CATEGORIES = ["subject", "direction", "sanity_value", "position",
              "extra_action_state", "repetition", "language"]
ADDITION_UNITS = ["t07:f0", "t07:f1", "t11:f0", "t12:f0", "t15:f0", "t17:f0"]
CONFLICT_UNITS = ["t12:f2", "t24:f3"]
R1_PASS_UNITS = None  # filled from r1 verdicts

OVERLAP = NEXT / "artifacts/next-acceptance/cf24-u240-baseline/cf24-u240-baseline/cf24-overlap.json"


def load_verdicts(run_dir: Path) -> dict:
    blind = run_dir / "blind"
    mapping = json.loads((blind / "map.json").read_text(encoding="utf-8"))["mapping"]
    judged = {}
    for path in sorted(blind.glob("judged-*.json")):
        for item in json.loads(path.read_text(encoding="utf-8"))["items"]:
            judged[item["code"]] = item
    out = {}
    for code, meta in mapping.items():
        item = judged[code]
        scheme = meta.get("scheme") or meta.get("arm") or "r1-greedy"
        out[(scheme, meta["unitId"])] = dict(
            verdict=item["verdict"], categories=item.get("categories", []),
            flags=item.get("flags", []), reason=item.get("reason", ""),
        )
    return out


def main() -> int:
    r1_dir = sorted((EXPERIMENT / "artifacts/fact-wording/diagnostic-r1").glob("*/raw.jsonl"))[-1].parent
    t1_dirs = sorted((EXPERIMENT / "artifacts/fact-wording/diagnostic-r2-cand-t1").glob("*/raw.jsonl"))
    t1_dir = t1_dirs[-1].parent
    r1_rows = {r["unitId"]: r for r in (json.loads(l) for l in (r1_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()) if r["arm"] == "greedy"}
    t1_rows = {r["unitId"]: r for r in (json.loads(l) for l in (t1_dir / "raw.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
    cand = json.loads((EXPERIMENT / "freeze/candidate-t1-v2.json").read_text(encoding="utf-8"))

    r1_v = load_verdicts(r1_dir)          # original r1 verdicts
    mixed = load_verdicts(t1_dir)         # mixed pack: re-judged r1 rows + T1 rows
    r1 = {u: mixed[("r1-greedy", u)] for u in r1_rows}       # same-session re-judging
    r1_original = {u: r1_v[("greedy", u)] for u in r1_rows}
    t1 = {u: mixed[("T1-greedy", u)] for u in t1_rows}

    labels = {r["unitId"]: r["label"] for r in json.loads(OVERLAP.read_text(encoding="utf-8"))["records"]}

    def level(v):
        if "limitHit" in v and v["limitHit"]:
            return "U"
        return {"pass": "P", "fail": "F"}.get(v["verdict"], "U")

    units = sorted(r1_rows)

    def blocks(unit_ids):
        out = {}
        for scheme, verdicts, rows in (("r1", r1, r1_rows), ("T1", t1, t1_rows)):
            v = [verdicts[u] for u in unit_ids]
            out[scheme] = dict(
                units=len(unit_ids),
                passCount=sum(1 for x in v if x["verdict"] == "pass"),
                failCount=sum(1 for x in v if x["verdict"] == "fail"),
                undeterminedCount=sum(1 for x in v if x["verdict"] == "undetermined"),
                categories={c: sorted(u for u in unit_ids if c in verdicts[u]["categories"]) for c in CATEGORIES},
            )
            times = [rows[u]["seconds"] for u in unit_ids]
            out[scheme]["timing"] = dict(
                medianSeconds=round(statistics.median(times), 3),
                p95Seconds=round(sorted(times)[max(0, int(round(0.95 * len(times))) - 1)], 3),
                maxSeconds=round(max(times), 3),
                budgetHits=sum(1 for u in unit_ids if rows[u]["stopReason"] == "budget"),
                capHits=sum(1 for u in unit_ids if rows[u]["stopReason"] == "cap"),
            )
        # paired
        paired = Counter()
        detail = {}
        for u in unit_ids:
            a, b = level(r1[u]), level(t1[u])
            if a == "P" and b == "P":
                k = "unchanged-pass"
            elif a == "F" and b == "F":
                k = "unchanged-fail"
            elif a == "U" and b == "U":
                k = "unchanged-U"
            elif a == "F" and b == "P":
                k = "improved"
            elif a == "P" and b == "F":
                k = "regressed"
            elif a == "P" and b == "U":
                k = "pass-to-U"
            elif a == "U" and b == "P":
                k = "U-to-pass"
            elif a == "U" and b == "F":
                k = "U-to-fail"
            else:  # F -> U
                k = "fail-to-U"
            paired[k] += 1
            detail[u] = dict(level=k, r1=r1[u]["verdict"], T1=t1[u]["verdict"],
                             r1Cats=r1[u]["categories"], T1Cats=t1[u]["categories"])
        out["paired"] = dict(paired)
        out["pairedDetail"] = detail
        return out

    all_units = units
    sensitivity = [u for u in units if u not in CONFLICT_UNITS]

    # --- six addition defects, unit by unit ---------------------------------
    addition_detail = {}
    for u in ADDITION_UNITS:
        a, b = r1[u], t1[u]
        fixed = ("extra_action_state" not in b["categories"]
                 and b["verdict"] == "pass"
                 and not any(c in b["categories"] for c in CATEGORIES if c != "extra_action_state"))
        addition_detail[u] = dict(
            r1=dict(text=r1_rows[u]["text"], verdict=a["verdict"], categories=a["categories"]),
            T1=dict(text=t1_rows[u]["text"], verdict=b["verdict"], categories=b["categories"]),
            validFix=fixed,
        )

    # --- admission criteria -------------------------------------------------
    r1_pass_units = [u for u in units if r1_original[u]["verdict"] == "pass"]
    r1_u_units = [u for u in units if r1_original[u]["verdict"] == "undetermined"]
    c2_violations = [u for u in r1_pass_units if t1[u]["verdict"] != "pass"]
    c3_violations = [u for u in r1_u_units if t1[u]["verdict"] == "fail"]
    fact_omitted = [u for u in units if "fact_not_expressed" in t1[u]["flags"]]
    valid_fixes = [u for u, d in addition_detail.items() if d["validFix"]]

    criteria = dict(
        C1=dict(required=3, validFixes=len(valid_fixes), units=valid_fixes,
                passed=len(valid_fixes) >= 3),
        C2=dict(violations=c2_violations, passed=not c2_violations),
        C3=dict(violations=c3_violations, passed=not c3_violations),
        C4=dict(factNotExpressed=fact_omitted, passed=not fact_omitted),
    )
    criteria["allPassed"] = all(v["passed"] for k, v in criteria.items() if k.startswith("C"))

    # --- strata -------------------------------------------------------------
    strata = {}
    for label in ("seen-fact", "independent"):
        subset = [u for u in units if labels.get(u) == label]
        strata[label] = dict(
            units=len(subset),
            improvements=[u for u in subset if level(r1[u]) == "F" and level(t1[u]) == "P"],
            regressions=[u for u in subset if level(r1[u]) == "P" and level(t1[u]) != "P"],
        )

    # --- r1 re-judging consistency -----------------------------------------
    disagreements = []
    for u in units:
        if r1_original[u]["verdict"] != r1[u]["verdict"]:
            disagreements.append(dict(
                unitId=u, original=r1_original[u]["verdict"], rejudged=r1[u]["verdict"],
                originalReason=r1_original[u]["reason"][:80], rejudgedReason=r1[u]["reason"][:80],
            ))

    result = dict(
        protocol="c4-candidate-t1-analysis",
        candidateSha256=hashlib.sha256((EXPERIMENT / "freeze/candidate-t1-v2.json").read_bytes()).hexdigest(),
        r1Run=str(r1_dir.relative_to(EXPERIMENT)).replace(chr(92), "/"),
        t1Run=str(t1_dir.relative_to(EXPERIMENT)).replace(chr(92), "/"),
        main=blocks(all_units),
        sensitivity=blocks(sensitivity),
        additionDetail=addition_detail,
        criteria=criteria,
        strata=strata,
        r1RejudgeDisagreements=disagreements,
        notes=[
            "verdicts are assistant blind judging of 170 recoded items; not human review",
            "timing is descriptive for this session only; cross-session differences are not attributed to T1",
            "categories overlap and are not summed",
            "two units (t12:f2, t24:f3) carry a known input/fact conflict; the sensitivity table excludes them",
        ],
    )
    (t1_dir / "candidate-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    for name, block in (("MAIN 85", result["main"]), ("SENSITIVITY 83", result["sensitivity"])):
        print(f"== {name}")
        for scheme in ("r1", "T1"):
            s = block[scheme]
            print(f"  {scheme:<3} pass {s['passCount']:2d} fail {s['failCount']:2d} U {s['undeterminedCount']:2d} "
                  f"| median {s['timing']['medianSeconds']:.2f}s p95 {s['timing']['p95Seconds']:.2f}s")
            print("      " + ", ".join(f"{c}={len(s['categories'][c])}" for c in CATEGORIES))
        print("  paired:", dict(block["paired"]))
    print("== admission")
    for key in ("C1", "C2", "C3", "C4"):
        print(f"  {key}: {json.dumps({k: v for k, v in criteria[key].items() if k != 'units' or len(str(v)) < 200}, ensure_ascii=False)}")
    print("  allPassed:", criteria["allPassed"])
    print("== strata")
    for label, s in strata.items():
        print(f"  {label}: units={s['units']} improvements={s['improvements']} regressions={s['regressions']}")
    print("== r1 re-judge disagreements:", disagreements)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
