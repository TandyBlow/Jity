# -*- coding: utf-8 -*-
"""Turn one screening run into the input lane 01's reviewer already accepts.

01's batch harness reads a JSONL of `{"id","input","text"}` from
`NARRATION_QUALITY_ROWS` and writes a report. This script builds that JSONL from
the raw per-case files `screen.py` wrote plus the cases from 01's frozen
package. It refuses a run that is missing a case, has an extra case, or whose
recorded `inputSha256` does not match the package case.

No judging happens here: the output is a review request, not a verdict.

Usage:
    python -X utf8 src/make_review_input.py \
      --cases D:/others/Jity/.local/parallel-local-game/results/quality/dev-package-v1/cases.jsonl \
      --run evidence/runs/batch-1/internlm2_5-1.8b-chat \
      --prompt-manifest evidence/prompts-dev-v1/prompts.manifest.json \
      --out evidence/review-requests/internlm2_5-1.8b-chat
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import pathlib
import sys


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=pathlib.Path, required=True)
    parser.add_argument("--run", type=pathlib.Path, required=True)
    parser.add_argument("--prompt-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--allow-partial", action="store_true",
                        help="write the cases that exist and list the missing ones; never for a gate claim")
    args = parser.parse_args()

    prompt_manifest = json.loads(args.prompt_manifest.read_text(encoding="utf-8"))
    if not prompt_manifest.get("frozen") and not args.allow_partial:
        print("prompt manifest is not frozen; refusing", file=sys.stderr)
        return 2
    cases = {}
    for line in args.cases.read_text(encoding="utf-8").splitlines():
        if line.strip():
            case = json.loads(line)
            cases[case["caseId"]] = case

    results = {}
    for path in sorted(args.run.glob("*.json")):
        if path.name == "run-manifest.json":
            continue
        record = json.loads(path.read_text(encoding="utf-8"))
        if "caseId" not in record:
            continue
        results[record["caseId"]] = record

    declared_excluded = {
        entry["caseId"]
        for entry in ((prompt_manifest.get("subset") or {}).get("excludedCases") or [])
    }
    missing = sorted(set(cases) - set(results))
    undeclared_missing = [case_id for case_id in missing if case_id not in declared_excluded]
    extra = sorted(set(results) - set(cases))
    if (undeclared_missing or missing) and not args.allow_partial:
        if undeclared_missing:
            print(f"run is missing undeclared case(s): {undeclared_missing}", file=sys.stderr)
            return 2
    if extra:
        print(f"run has cases not in the package: {extra}", file=sys.stderr)
        return 2

    rows = []
    problems = []
    for case_id, case in cases.items():
        record = results.get(case_id)
        if not record:
            continue
        expected = case.get("inputSha256")
        actual = record.get("inputSha256")
        if expected and actual and expected != actual:
            problems.append({"caseId": case_id, "problem": "inputSha256 mismatch",
                             "case": expected, "record": actual})
            continue
        text = record.get("text") or ""
        if not text.strip():
            problems.append({"caseId": case_id, "problem": "empty text"})
        rows.append({
            "id": case_id,
            "input": case["input"],
            "text": text,
            "textSource": "model" if text.strip() and not record.get("error") else "unknown",
        })

    args.out.mkdir(parents=True, exist_ok=True)
    rows_path = args.out / "review-rows.jsonl"
    tmp = rows_path.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(rows_path)
    run_manifest = {}
    run_manifest_path = args.run / "run-manifest.json"
    if run_manifest_path.exists():
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    manifest = {
        "createdAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "kind": "01-review-request",
        "modelId": run_manifest.get("modelId") or args.run.name,
        "modelSha256": run_manifest.get("modelSha256"),
        "modelPath": run_manifest.get("modelPath"),
        "promptManifestPath": str(args.prompt_manifest),
        "promptManifestSha256": sha(args.prompt_manifest),
        "promptFrozen": bool(prompt_manifest.get("frozen")),
        "devPackage": prompt_manifest.get("devPackage"),
        "runDir": str(args.run),
        "runManifestSha256": sha(run_manifest_path) if run_manifest_path.exists() else None,
        "rows": len(rows),
        "rowsPath": str(rows_path),
        "rowsSha256": sha(rows_path),
        "missingCases": missing,
        "declaredExcluded": sorted(declared_excluded),
        "problems": problems,
        "usage": "NARRATION_QUALITY_ROWS=<rowsPath> NARRATION_QUALITY_REPORT=<report.json> "
                 "npx vitest run src/lib/world-engine/local/narration-quality/batch.test.ts --maxWorkers=1",
        "notAcceptance": "01's independent review is required; this file is only the request input.",
    }
    manifest_path = args.out / "review.manifest.json"
    tmp = manifest_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(manifest_path)
    print(json.dumps({"rows": len(rows), "missing": missing, "problems": problems,
                      "rowsSha256": manifest["rowsSha256"]}, ensure_ascii=False, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
