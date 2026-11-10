"""Re-judge the archived first calls with N5 v4 and compare against v3.

The owner's ruling: the new version re-judges historical text, but the old
archives are never overwritten. This script only READS out/real-batch-v{1,2,3}.json
and writes a separate report.

What it reports per batch:
  - v3 vs v4 status counts and hard passes
  - per-fact tri-state under v4 (covered / rejected / needs review / uncovered)
  - residue-name diagnostics (now informational) and goal residues (still hard)
  - same-name verdicts (undetermined)
  - completion classes (stop / length / load / blocked)

Usage: python -X utf8 rejudge_archives_v4.py
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge_v3 as v3  # noqa: E402
import judge_v4 as v4  # noqa: E402
import judge_v4_1 as v4_1  # noqa: E402
import judge_v4_2 as v4_2  # noqa: E402
import judge_v4_3 as v4_3  # noqa: E402
import character_identity  # noqa: E402
from judge_v3 import JudgeBlocked  # noqa: E402
import real_batch_v3 as rb  # noqa: E402

OUT = HERE / "out" / "archive-rejudge-v4.json"


def rejudge(run_doc, cases_by_id, judge_mod):
    rows = []
    for case in run_doc["cases"]:
        cid = case["caseId"]
        chain = rb.build_chain(cases_by_id[cid])
        facts = chain["n1Facts"]
        must = [f["factId"] for f in chain["selected"]]
        attempt = case["attempts"][0]
        text = attempt["output"]
        finish = attempt["finishReason"]

        old = v3.judge(facts, must, chain["plan"], text, finish or "eos")
        row = {"caseId": cid, "finishReason": finish,
               "v3": {"status": old["status"], "hardPass": old["hardPass"],
                      "problems": old["problems"]}}
        try:
            if judge_mod in (v4_2, v4_3):
                ids = character_identity.build_identities(
                    cases_by_id[cid]["point"]["state"])
                new = judge_mod.judge(facts, must, chain["plan"], text, finish,
                                      identities=ids)
            else:
                new = judge_mod.judge(facts, must, chain["plan"], text, finish)
        except JudgeBlocked as exc:
            row["v4"] = {"blocked": exc.code, "detail": exc.detail}
            rows.append(row)
            continue
        kinds = {}
        for fid, st in new["facts"].items():
            kind = next(f["kind"] for f in facts if f["factId"] == fid)
            kinds.setdefault(kind, {}).setdefault(st["status"], 0)
            kinds[kind][st["status"]] += 1
        row["v4"] = {"status": new["status"], "hardPass": new["hardPass"],
                     "gates": new["gates"], "problems": new["problems"],
                     "diagnostics": new["diagnostics"],
                     "factsByKind": kinds}
        rows.append(row)

    def count(key, value):
        return sum(1 for r in rows if r.get("v4", {}).get(key) == value)

    return {
        "samples": rows,
        "v3HardPass": sum(1 for r in rows if r["v3"]["hardPass"]),
        "v4HardPass": sum(1 for r in rows if r.get("v4", {}).get("hardPass")),
        "v4Status": {
            s: count("status", s)
            for s in ("judged", "needs-semantic-review", "undetermined")
        },
        "v4Blocked": sum(1 for r in rows if "blocked" in r.get("v4", {})),
        "goalResidueSamples": sum(
            1 for r in rows
            if any(p.startswith("residue-goal")
                   for p in r.get("v4", {}).get("problems", []))),
        "residueNameDiagnostics": sum(
            d.get("count", 0) for r in rows
            for d in r.get("v4", {}).get("diagnostics", [])),
        "sameNameUndetermined": sum(
            1 for r in rows
            if any(p.startswith("same-name-")
                   for p in r.get("v4", {}).get("problems", []))),
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=("v4", "v4.1", "v4.2", "v4.3"),
                    default="v4")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    judge_mod = {"v4": v4, "v4.1": v4_1, "v4.2": v4_2, "v4.3": v4_3}[args.judge]
    out_path = pathlib.Path(args.out) if args.out else OUT
    cases_doc = json.loads(
        (HERE / "fixtures" / "batch-v1-cases.json").read_text(encoding="utf-8"))
    by_id = {c["caseId"]: c for c in cases_doc["cases"]}
    report = {"version": f"archive-rejudge-{args.judge}", "judge": judge_mod.VERSION,
              "note": "old archives are read-only here; v3 verdicts are kept "
                      "for comparison and were not recomputed into the archives",
              "batches": {}}
    for name in ("real-batch-v1", "real-batch-v2", "real-batch-v3"):
        doc = json.loads((HERE / "out" / f"{name}.json")
                         .read_text(encoding="utf-8"))
        report["batches"][name] = rejudge(doc, by_id, judge_mod)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")

    for name, b in report["batches"].items():
        print(f"{name}: v3 hardPass {b['v3HardPass']}/10 -> v4 "
              f"{b['v4HardPass']}/10 | status {b['v4Status']} | "
              f"blocked {b['v4Blocked']} | goal-residue "
              f"{b['goalResidueSamples']} | residue-name diagnostics "
              f"{b['residueNameDiagnostics']} | same-name undetermined "
              f"{b['sameNameUndetermined']}")
    print(f"-> {out_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
