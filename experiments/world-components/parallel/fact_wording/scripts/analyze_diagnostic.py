"""Aggregate a completed cf24 diagnostic run (protocol v3 §4).

Reads:
  <run dir>/raw.jsonl            generation rows (arm, text, tokens, seconds, limits)
  <run dir>/blind/judged-*.json  assistant blind verdicts (one file per batch)
  <run dir>/blind/map.json       code -> unitId/arm (only used AFTER judging)

Writes:
  <run dir>/analysis.json        counts, categories, source level, paired comparison, timings

Rules implemented here (and nowhere else):
  * a row with limitHit is U regardless of its text;
  * categories may overlap and are never summed into a failure count;
  * U never counts as pass;
  * source clean = every unit in that source passes and no addition flag anywhere.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
CATEGORIES = ["subject", "direction", "sanity_value", "position",
              "extra_action_state", "repetition", "language"]


def main() -> int:
    runs = sorted((EXPERIMENT / "artifacts/fact-wording/diagnostic-r1").glob("*/raw.jsonl"))
    if not runs:
        raise SystemExit("no diagnostic run")
    run_dir = runs[-1].parent
    rows = [json.loads(line) for line in runs[-1].read_text(encoding="utf-8").splitlines() if line.strip()]
    mapping = json.loads((run_dir / "blind/map.json").read_text(encoding="utf-8"))["mapping"]

    judged = {}
    for path in sorted((run_dir / "blind").glob("judged-*.json")):
        for item in json.loads(path.read_text(encoding="utf-8"))["items"]:
            judged[item["code"]] = item

    missing = [code for code in mapping if code not in judged]
    if missing:
        raise SystemExit(f"missing verdicts for {len(missing)} codes, e.g. {missing[:5]}")

    by_arm = {"greedy": {}, "beam2": {}}
    for code, meta in mapping.items():
        verdict = judged[code]
        row = next(r for r in rows if r["unitId"] == meta["unitId"] and r["arm"] == meta["arm"])
        by_arm[meta["arm"]][meta["unitId"]] = dict(
            code=code, verdict=verdict["verdict"], categories=verdict.get("categories", []),
            flags=verdict.get("flags", []), reason=verdict.get("reason", ""),
            limitHit=row["limitHit"], stopReason=row["stopReason"],
            seconds=row["seconds"], newTokens=row["newTokens"], text=row["text"],
            score=row["score"],
        )

    summary = {}
    for arm, units in by_arm.items():
        passes = [u for u, v in units.items() if v["verdict"] == "pass" and not v["limitHit"]]
        fails = [u for u, v in units.items() if v["verdict"] == "fail" and not v["limitHit"]]
        undetermined = [u for u, v in units.items() if v["verdict"] == "undetermined" or v["limitHit"]]
        cats = {c: sorted(u for u, v in units.items() if c in v["categories"]) for c in CATEGORIES}
        times = [v["seconds"] for v in units.values()]
        summary[arm] = dict(
            units=len(units), passCount=len(passes), failCount=len(fails),
            undeterminedCount=len(undetermined),
            passUnits=sorted(passes), failUnits=sorted(fails), undeterminedUnits=sorted(undetermined),
            categories={c: dict(count=len(u), units=u) for c, u in cats.items()},
            timing=dict(
                medianSeconds=round(statistics.median(times), 3),
                p95Seconds=round(sorted(times)[max(0, int(round(0.95 * len(times))) - 1)], 3),
                maxSeconds=round(max(times), 3),
                budgetHits=sum(1 for v in units.values() if v["stopReason"] == "budget"),
                capHits=sum(1 for v in units.values() if v["stopReason"] == "cap"),
            ),
        )

    # paired comparison
    paired = {}
    for unit in sorted(by_arm["greedy"]):
        g, b = by_arm["greedy"][unit], by_arm["beam2"][unit]
        def level(v):
            return 0 if (v["limitHit"] or v["verdict"] == "undetermined") else (1 if v["verdict"] == "pass" else 2)
        gl, bl = level(g), level(b)
        if gl == 0 or bl == 0:
            verdict = "undetermined"
        elif bl < gl:
            verdict = "improved"
        elif bl > gl:
            verdict = "regressed"
        else:
            verdict = "unchanged"
        paired[unit] = dict(level=verdict, greedy=g["verdict"], beam2=b["verdict"],
                            greedyCats=g["categories"], beamCats=b["categories"])
    counts = {k: sum(1 for v in paired.values() if v["level"] == k)
              for k in ("improved", "regressed", "unchanged", "undetermined")}

    sources = {}
    for unit, row in paired.items():
        src = unit.split(":")[0]
        sources.setdefault(src, []).append(unit)
    source_level = {}
    for arm, units in by_arm.items():
        clean = []
        for src, members in sorted(sources.items()):
            ok = all(units[u]["verdict"] == "pass" and not units[u]["limitHit"]
                     and "extra_action_state" not in units[u]["categories"] for u in members)
            clean.append(dict(source=src, clean=ok, units=members))
        source_level[arm] = dict(cleanSources=sum(1 for s in clean if s["clean"]),
                                 totalSources=len(clean), detail=clean)

    out = dict(
        run=str(run_dir.relative_to(EXPERIMENT)).replace(chr(92), "/"),
        rows=len(rows), judgedRows=len(judged),
        summary=summary, paired=counts, pairedDetail=paired,
        sourceLevel=source_level,
        caveats=[
            "cf24 is an old, repeatedly-inspected set; results describe these 85 units only",
            "verdicts are assistant blind judging, not human review",
            "five units (t01:f0 t07:f0 t11:f1 t22:f0 t24:f1) were seen during preflight, so their judging may be partially unblinded",
            "categories overlap and must not be summed",
            "width-2 beam is an approximation; limitHit rows count as U",
        ],
    )
    (run_dir / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                            encoding="utf-8")

    for arm in ("greedy", "beam2"):
        s = summary[arm]
        print(f"{arm:<7} pass {s['passCount']:2d} fail {s['failCount']:2d} U {s['undeterminedCount']:2d} "
              f"| median {s['timing']['medianSeconds']:.2f}s p95 {s['timing']['p95Seconds']:.2f}s "
              f"| budget {s['timing']['budgetHits']} cap {s['timing']['capHits']}")
        print("        " + ", ".join(f"{c}={s['categories'][c]['count']}" for c in CATEGORIES))
        print(f"        clean sources {source_level[arm]['cleanSources']}/{source_level[arm]['totalSources']}")
    print("paired:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
