"""Run the c1 attention-parse rule baseline and score it against frozen labels.

Reads:  freeze/rosters.json, freeze/samples.json, freeze/rule-cases.json
Writes: runs/r1/input-hashes.json, runs/r1/raw-output.json,
        runs/r1/score.json, runs/r1/run.log

No model, no network, no service call. Deterministic: same inputs -> same
bytes except for the recorded environment block.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import attention_parse

HERE = Path(__file__).resolve().parent
FREEZE = HERE / "freeze"
RUN_DIR = HERE / "runs" / "r1"
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
    except Exception as exc:  # pragma: no cover - recorded, not fatal
        return f"<git error: {exc}>"


def diff(expected: list[str], actual: list[str]) -> tuple[list[str], list[str]]:
    return sorted(set(expected) - set(actual)), sorted(set(actual) - set(expected))


def score_row(sample: dict, parsed: dict, roster: dict) -> dict:
    expected = sample["expected"]
    known_ids = {entity["entityId"] for entity in roster["entities"]}
    errors: list[str] = []

    if parsed["status"] != expected["status"]:
        errors.append("E_STATUS")

    missing, extra = diff(expected["attentionTargets"], parsed["attentionTargets"])
    if missing:
        errors.append("E_MISSING_TARGET")
    if extra:
        errors.append("E_EXTRA_TARGET")

    _, amb_missing = diff(expected["ambiguousCandidates"], parsed["ambiguousCandidates"])
    if amb_missing or sorted(set(expected["ambiguousCandidates"]) - set(parsed["ambiguousCandidates"])):
        errors.append("E_AMBIG_MISMATCH")

    res_missing, res_extra = diff(expected.get("resolvedCandidates", []), parsed["resolvedCandidates"])
    if res_missing or res_extra:
        errors.append("E_RESOLVED_MISMATCH")

    unr_missing, unr_extra = diff(expected.get("unresolvedMentions", []), parsed["unresolvedMentions"])
    if unr_missing or unr_extra:
        errors.append("E_UNRESOLVED_MISMATCH")

    if parsed["attentionTargets"] and set(parsed["attentionTargets"]) == known_ids:
        errors.append("E_SELECT_ALL")

    unknown_ids = sorted(set(parsed["attentionTargets"]) - known_ids)
    if unknown_ids:
        errors.append("E_UNKNOWN_ID")

    return {
        "sampleId": sample["sampleId"],
        "category": sample["category"],
        "worldRef": sample["worldRef"],
        "utterance": sample["utterance"],
        "priorNarration": sample.get("priorNarration"),
        "expected": expected,
        "actual": {
            "status": parsed["status"],
            "attentionTargets": parsed["attentionTargets"],
            "resolvedCandidates": parsed["resolvedCandidates"],
            "ambiguousCandidates": parsed["ambiguousCandidates"],
            "unresolvedMentions": parsed["unresolvedMentions"],
        },
        "match": not errors,
        "errors": errors,
        "unknownIds": unknown_ids,
    }


def score_unit(case: dict, parsed: dict) -> dict:
    expected = case["expected"]
    errors: list[str] = []
    if parsed["status"] != expected["status"]:
        errors.append("E_STATUS")
    if sorted(expected["attentionTargets"]) != sorted(parsed["attentionTargets"]):
        errors.append("E_TARGET_MISMATCH")
    if "ambiguousCandidates" in expected and sorted(expected["ambiguousCandidates"]) != sorted(parsed["ambiguousCandidates"]):
        errors.append("E_AMBIG_MISMATCH")
    if expected.get("assertTargetsStrictlySmallerThanRoster"):
        if len(parsed["attentionTargets"]) >= len(case["roster"]["entities"]):
            errors.append("E_SELECT_ALL_FALLBACK")
    return {
        "caseId": case["caseId"],
        "targets": case["targets"],
        "utterance": case["utterance"],
        "expected": expected,
        "actual": {
            "status": parsed["status"],
            "attentionTargets": parsed["attentionTargets"],
            "ambiguousCandidates": parsed["ambiguousCandidates"],
            "unresolvedMentions": parsed["unresolvedMentions"],
        },
        "match": not errors,
        "errors": errors,
    }


def _behaviour(parsed: dict) -> dict:
    return {"status": parsed["status"], "attentionTargets": sorted(parsed["attentionTargets"])}


def _same(a: dict, b: dict) -> bool:
    return a["status"] == b["status"] and sorted(a["attentionTargets"]) == sorted(b["attentionTargets"])


def score_probe(probe: dict, parsed: dict) -> dict:
    actual = _behaviour(parsed)
    if _same(actual, probe["desiredBehavior"]):
        outcome = "unexpected_pass"
    elif _same(actual, probe["expectedRuleBehavior"]):
        outcome = "known_limit"
    else:
        outcome = "unclassified"
    return {
        "probeId": probe["probeId"],
        "mechanism": probe["mechanism"],
        "utterance": probe["utterance"],
        "priorNarration": probe.get("priorNarration"),
        "expectedRuleBehavior": probe["expectedRuleBehavior"],
        "desiredBehavior": probe["desiredBehavior"],
        "actual": actual,
        "outcome": outcome,
        "note": probe["note"],
    }


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rosters_doc = json.loads((FREEZE / "rosters.json").read_text(encoding="utf-8"))
    samples_doc = json.loads((FREEZE / "samples.json").read_text(encoding="utf-8"))
    cases_doc = json.loads((FREEZE / "rule-cases.json").read_text(encoding="utf-8"))
    probes_doc = json.loads((FREEZE / "stress-probes.json").read_text(encoding="utf-8"))

    drift: list[str] = []
    for ref, roster in rosters_doc["rosters"].items():
        source = ROOT / roster["sourceFile"]
        actual = sha256(source)
        if actual != roster["sourceSha256"]:
            drift.append(f"{ref}: {roster['sourceFile']} sha256 {roster['sourceSha256'][:12]} -> {actual[:12]}")
    if drift:
        raise SystemExit("roster source drift, rebuild rosters first:\n" + "\n".join(drift))

    hashes = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "trackedDirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "files": {
            "attention_parse.py": sha256(HERE / "attention_parse.py"),
            "build_rosters.py": sha256(HERE / "build_rosters.py"),
            "run_experiment.py": sha256(HERE / "run_experiment.py"),
            "freeze/rosters.json": sha256(FREEZE / "rosters.json"),
            "freeze/samples.json": sha256(FREEZE / "samples.json"),
            "freeze/rule-cases.json": sha256(FREEZE / "rule-cases.json"),
            "freeze/stress-probes.json": sha256(FREEZE / "stress-probes.json"),
            "rosterSourceW1": rosters_doc["rosters"]["W1"]["sourceSha256"],
            "rosterSourceW2": rosters_doc["rosters"]["W2"]["sourceSha256"],
        },
    }

    rows: list[dict] = []
    raw_rows: list[dict] = []
    for sample in samples_doc["samples"]:
        roster = rosters_doc["rosters"][sample["worldRef"]]
        parsed = attention_parse.as_dict(
            attention_parse.parse(sample["utterance"], roster, sample.get("priorNarration")), roster
        )
        raw_rows.append(
            {
                "sampleId": sample["sampleId"],
                "worldRef": sample["worldRef"],
                "utterance": sample["utterance"],
                "priorNarration": sample.get("priorNarration"),
                "parsed": parsed,
            }
        )
        rows.append(score_row(sample, parsed, roster))

    unit_rows: list[dict] = []
    for case in cases_doc["cases"]:
        parsed = attention_parse.as_dict(
            attention_parse.parse(case["utterance"], case["roster"], case.get("priorNarration")), case["roster"]
        )
        unit_rows.append(score_unit(case, parsed))

    probe_rows: list[dict] = []
    for probe in probes_doc["probes"]:
        roster = probe.get("roster") or rosters_doc["rosters"][probe["worldRef"]]
        parsed = attention_parse.as_dict(
            attention_parse.parse(probe["utterance"], roster, probe.get("priorNarration")), roster
        )
        probe_rows.append(score_probe(probe, parsed))

    passed = sum(1 for row in rows if row["match"])
    unit_passed = sum(1 for row in unit_rows if row["match"])
    select_all = sum(1 for row in rows if "E_SELECT_ALL" in row["errors"])
    none_or_unresolved = [row for row in rows if row["actual"]["status"] in {"none", "unresolved"}]
    empty_targets = sum(1 for row in none_or_unresolved if not row["actual"]["attentionTargets"])

    score = {
        "protocol": "c1-attention-parse-v1",
        "hashes": hashes,
        "headline": {
            "samples": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "unitCases": len(unit_rows),
            "unitPassed": unit_passed,
            "selectAllHits": select_all,
            "noneOrUnresolvedSamples": len(none_or_unresolved),
            "noneOrUnresolvedWithEmptyTargets": empty_targets,
            "probes": len(probe_rows),
            "probeKnownLimits": sum(1 for row in probe_rows if row["outcome"] == "known_limit"),
            "probeUnexpectedPasses": sum(1 for row in probe_rows if row["outcome"] == "unexpected_pass"),
            "probeUnclassified": sum(1 for row in probe_rows if row["outcome"] == "unclassified"),
        },
        "byCategory": {},
        "rows": rows,
        "unitCases": unit_rows,
        "probes": probe_rows,
    }
    for row in rows:
        bucket = score["byCategory"].setdefault(row["category"], {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += 1 if row["match"] else 0

    (RUN_DIR / "input-hashes.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RUN_DIR / "raw-output.json").write_text(
        json.dumps({"protocol": "c1-attention-parse-v1", "rows": raw_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (RUN_DIR / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"commit {hashes['commit'][:12]} branch {hashes['branch']} dirty={hashes['dirty']}",
        f"python {hashes['python']} {hashes['platform']}",
        "",
        "sample  category            status(expected/actual)  targets(expected -> actual)          errors",
    ]
    for row in rows:
        exp = row["expected"]
        act = row["actual"]
        lines.append(
            f"{row['sampleId']}     {row['category']:<20} {exp['status']}/{act['status']:<12} "
            f"{','.join(exp['attentionTargets']) or '-':<20} -> {','.join(act['attentionTargets']) or '-':<20} "
            f"{','.join(row['errors']) or 'ok'}"
        )
    lines.append("")
    for row in unit_rows:
        lines.append(
            f"{row['caseId']} unit {row['targets']:<24} {row['expected']['status']}/{row['actual']['status']:<12} "
            f"{','.join(row['errors']) or 'ok'}"
        )
    lines.append("")
    for row in probe_rows:
        lines.append(
            f"{row['probeId']} probe {row['mechanism']:<28} desired={row['desiredBehavior']['status']}/{','.join(row['desiredBehavior']['attentionTargets']) or '-'}"
            f" actual={row['actual']['status']}/{','.join(row['actual']['attentionTargets']) or '-'} -> {row['outcome']}"
        )
    lines.append("")
    lines.append(
        f"headline: {passed}/{len(rows)} samples passed; unit {unit_passed}/{len(unit_rows)}; "
        f"selectAllHits={select_all}; probes known_limit={sum(1 for r in probe_rows if r['outcome'] == 'known_limit')}"
        f" unexpected_pass={sum(1 for r in probe_rows if r['outcome'] == 'unexpected_pass')}"
        f" unclassified={sum(1 for r in probe_rows if r['outcome'] == 'unclassified')}"
    )
    log = "\n".join(lines) + "\n"
    (RUN_DIR / "run.log").write_text(log, encoding="utf-8")
    print(log)
    return 0 if passed == len(rows) and unit_passed == len(unit_rows) else 0


if __name__ == "__main__":
    sys.exit(main())
