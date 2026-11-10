"""Run the frozen attention-selection v2 cases and write the raw result.

No model, no network, no backend: the script reads cases-v2.json, applies the
four rule arms, evaluates them against the manual selection, and writes a
single JSON file with every selected id and every check. Every number in the
report is taken from this file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import sys
from pathlib import Path

import selector

HERE = Path(__file__).resolve().parent
CASE_FILE = HERE / "cases-v2.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(cases: dict) -> None:
    assert cases["protocol"] == "attention-selection-v2"
    seen_cases = set()
    for case in cases["cases"]:
        cid = case["caseId"]
        if cid in seen_cases:
            raise ValueError(f"duplicate case id: {cid}")
        seen_cases.add(cid)
        fids = [fact["factId"] for fact in case["facts"]]
        if len(fids) != len(set(fids)):
            raise ValueError(f"duplicate fact id in {cid}")
        known = set(fids)
        for key in ("manualSelectedFactIds", "targetOptionalFactIds", "relatedOptionalFactIds",
                    "alreadyNarratedFactIds"):
            unknown = set(case[key]) - known
            if unknown:
                raise ValueError(f"{cid}: {key} has unknown ids {sorted(unknown)}")
        must = selector.must_ids(case)
        if set(case["targetOptionalFactIds"]) & must:
            raise ValueError(f"{cid}: target optional overlaps must")
        for fid in case["targetOptionalFactIds"] + case["relatedOptionalFactIds"]:
            fact = selector.facts_by_id(case)[fid]
            if fact["authorization"] != "optional":
                raise ValueError(f"{cid}: target/related {fid} is not optional")
        if not case.get("attentionTargets"):
            raise ValueError(f"{cid}: no attentionTargets")
        if not case.get("focus"):
            raise ValueError(f"{cid}: no focus")
        for fact in case["facts"]:
            if "source" not in fact:
                raise ValueError(f"{cid}: fact {fact['factId']} has no source")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=CASE_FILE)
    parser.add_argument("--out", type=Path,
                        default=HERE.parents[3] / "artifacts/world-components/parallel/fact-selection-v2/selection-v2.json")
    args = parser.parse_args()

    cases = selector.load_cases(args.cases)
    validate(cases)
    result = selector.run_all(cases)
    result["generatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
    result["python"] = platform.python_version()
    result["inputs"] = {
        "cases": str(args.cases),
        "casesSha256": sha256(args.cases),
        "sourceFixture": cases["sourceFixture"],
        "selectorSha256": sha256(HERE / "selector.py"),
        "runnerSha256": sha256(Path(__file__)),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8", newline="\n")

    print(f"wrote {args.out}")
    print(f"cases {len(cases['cases'])}; cases sha256 {result['inputs']['casesSha256']}")
    for arm in ("manual", "no_attention", "lexical", "lexical_content", "semantic"):
        summary = result["summary"][arm]
        print(f"{arm:16s} all {summary['all']['lenientPass']}/{summary['all']['n']} lenient, "
              f"{summary['all']['strictPass']}/{summary['all']['n']} strict, "
              f"{summary['all']['hardPass']}/{summary['all']['n']} hard, "
              f"controlled {summary['controlled']['lenientPass']}/{summary['controlled']['n']}, "
              f"manualEqual {summary['all']['manualEqual']}/{summary['all']['n']}, "
              f"mustP {summary['all']['mustPrecisionMean']:.3f}")
    print("\nfailing controlled cases by arm:")
    for row in result["cases"]:
        if row["groupId"] == "R":
            continue
        for arm in ("no_attention", "lexical", "lexical_content", "semantic"):
            cell = row["arms"][arm]
            if not cell["lenientPass"]:
                print(f"  {row['caseId']} {arm}: unrelated={cell['unrelatedSelected']} "
                      f"target={cell['targetSelected']} missing={cell['missingMust']} "
                      f"selected={cell['selected']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
