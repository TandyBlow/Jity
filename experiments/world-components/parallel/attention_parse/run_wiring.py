"""Independent N2 wiring experiment: parse -> scope filter, scored separately.

Writes three separate result files under runs/wiring-v1/:
  parse.json      what v2 read from each utterance (no judgement)
  selection.json  what the filter kept/dropped per fact, with reasons
  score.json      comparison with the frozen expected selections + summaries

The three questions this run answers:
  1. are optional facts outside the attention scope excluded?
  2. do empty targets leave every optional fact unselected?
  3. are must facts kept in every case?
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import attention_parse_v2 as v2
import n2_attention_filter as n2

HERE = Path(__file__).resolve().parent
FREEZE = HERE / "freeze"
RUN_DIR = HERE / "runs" / "wiring-v1"
ROOT = HERE.parents[3]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except Exception as exc:  # pragma: no cover
        return f"<git error: {exc}>"


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rosters_doc = json.loads((FREEZE / "rosters.json").read_text(encoding="utf-8"))
    anchors_doc = json.loads((FREEZE / "anchors-v1.json").read_text(encoding="utf-8"))
    facts_doc = json.loads((FREEZE / "facts-v1.json").read_text(encoding="utf-8"))
    wiring = json.loads((FREEZE / "wiring-v1.json").read_text(encoding="utf-8"))

    source = ROOT / facts_doc["sourceFile"]
    if sha256(source) != facts_doc["sourceSha256"]:
        raise SystemExit("fact source drift: rebuild freeze/facts-v1.json")

    facts = facts_doc["facts"]
    must_ids = [fact["factId"] for fact in facts if fact["authorization"] == "must"]

    parse_rows: list[dict] = []
    selection_rows: list[dict] = []
    score_rows: list[dict] = []
    for case in wiring["cases"]:
        ref = case["worldRef"]
        parsed = v2.parse(case["utterance"], rosters_doc["rosters"][ref], None, anchors_doc, ref)
        filtered = n2.select(facts, parsed["targets"])

        parse_rows.append(
            {
                "caseId": case["caseId"],
                "worldRef": ref,
                "utterance": case["utterance"],
                "state": parsed["state"],
                "targets": parsed["targets"],
                "reason": parsed.get("reason"),
            }
        )
        selection_rows.append(
            {
                "caseId": case["caseId"],
                "targetsEmpty": not parsed["targets"],
                "selectedFactIds": filtered["selectedFactIds"],
                "decisions": filtered["decisions"],
            }
        )

        expected = case["expectedSelectedFactIds"]
        actual = filtered["selectedFactIds"]
        errors: list[str] = []
        if actual != expected:
            if set(actual) != set(expected):
                errors.append("E_SELECTION_SET")
            else:
                errors.append("E_SELECTION_ORDER")
        missing_must = [fact_id for fact_id in must_ids if fact_id not in actual]
        if missing_must:
            errors.append("E_MUST_DROPPED")
        if not parsed["targets"]:
            optional_selected = [
                fact_id
                for fact_id in actual
                if fact_id not in must_ids
            ]
            if optional_selected:
                errors.append("E_EMPTY_TARGETS_SELECTED_OPTIONAL")
        forbidden_selected = [
            fact["factId"]
            for fact in facts
            if fact["authorization"] == "forbidden" and fact["factId"] in actual
        ]
        if forbidden_selected:
            errors.append("E_FORBIDDEN_SELECTED")
        out_of_scope = [
            decision["factId"]
            for decision in filtered["decisions"]
            if decision["reason"] == "out_of_scope"
        ]
        score_rows.append(
            {
                "caseId": case["caseId"],
                "targets": case["targets"],
                "state": parsed["state"],
                "expectedSelectedFactIds": expected,
                "actualSelectedFactIds": actual,
                "outOfScopeExcluded": out_of_scope,
                "mustKept": not missing_must,
                "errors": errors,
                "match": not errors,
            }
        )

    passed = sum(1 for row in score_rows if row["match"])
    out_of_scope_total = sum(len(row["outOfScopeExcluded"]) for row in score_rows)
    hashes = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "trackedDirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "files": {
            "attention_parse_v2.py": sha256(HERE / "attention_parse_v2.py"),
            "n2_attention_filter.py": sha256(HERE / "n2_attention_filter.py"),
            "run_wiring.py": sha256(HERE / "run_wiring.py"),
            "freeze/facts-v1.json": sha256(FREEZE / "facts-v1.json"),
            "freeze/wiring-v1.json": sha256(FREEZE / "wiring-v1.json"),
        },
    }
    score = {
        "protocol": "c1-n2-wiring-v1",
        "scope": "scope filtering on the committed fact bundle; no model, no service, no page",
        "hashes": hashes,
        "summary": {
            "cases": len(score_rows),
            "passed": passed,
            "failed": len(score_rows) - passed,
            "emptyTargetCases": len([row for row in score_rows if row["state"] != "resolved"]),
            "emptyTargetCasesWithNoOptional": len(
                [
                    row
                    for row in score_rows
                    if row["state"] != "resolved"
                    and not [fact_id for fact_id in row["actualSelectedFactIds"] if fact_id not in must_ids]
                ]
            ),
            "outOfScopeExclusions": out_of_scope_total,
            "mustKeptInAllCases": all(row["mustKept"] for row in score_rows),
            "forbiddenSelected": sum(1 for row in score_rows if "E_FORBIDDEN_SELECTED" in row["errors"]),
        },
        "rows": score_rows,
    }
    (RUN_DIR / "parse.json").write_text(
        json.dumps({"protocol": "c1-n2-wiring-v1", "rows": parse_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (RUN_DIR / "selection.json").write_text(
        json.dumps({"protocol": "c1-n2-wiring-v1", "rows": selection_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (RUN_DIR / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"commit {hashes['commit'][:12]} branch {hashes['branch']} trackedDirty={hashes['trackedDirty']}",
        f"python {hashes['python']} {hashes['platform']}",
        "scope: parse -> scope filter; no model, no service",
        "",
    ]
    for row in score_rows:
        kept = [fact_id for fact_id in row["actualSelectedFactIds"]]
        excluded = row["outOfScopeExcluded"]
        lines.append(
            f"{row['caseId']} {row['targets']:<24} state={row['state']:<10} "
            f"kept={','.join(f.split('#')[-1] for f in kept):<52} "
            f"excluded={','.join(f.split('#')[-1] for f in excluded) or '-':<28} {','.join(row['errors']) or 'ok'}"
        )
    lines.append("")
    lines.append(
        f"summary: {passed}/{len(score_rows)} cases matched; must kept in all cases="
        f"{all(row['mustKept'] for row in score_rows)}; out-of-scope exclusions={out_of_scope_total}; "
        f"forbidden selected={sum(1 for row in score_rows if 'E_FORBIDDEN_SELECTED' in row['errors'])}"
    )
    log = "\n".join(lines) + "\n"
    (RUN_DIR / "run.log").write_text(log, encoding="utf-8")
    print(log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
