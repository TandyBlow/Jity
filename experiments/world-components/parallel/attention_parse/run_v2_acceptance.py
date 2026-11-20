"""Score the v2 extractor against the frozen A01-A10 labels.

Parse results and the comparison are written to runs/v2-acceptance/:
  parse.json   raw v2 output per sample (no judgement)
  score.json   per-sample comparison, error classes, extra probes X1-X2
  run.log      human table

No fact filtering happens here; that is run_wiring.py.
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

HERE = Path(__file__).resolve().parent
FREEZE = HERE / "freeze"
RUN_DIR = HERE / "runs" / "v2-acceptance"
ROOT = HERE.parents[3]

TARGET_KEYS = ("entityId", "scope", "part", "partAnchored")


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


def canonical(target: dict) -> dict:
    return {key: target.get(key) for key in TARGET_KEYS if key in target}


def compare(expected: dict, actual: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    detail: dict = {}

    if expected["state"] != actual["state"]:
        errors.append("E_STATE")

    exp_targets = [canonical(target) for target in expected.get("targets", [])]
    act_targets = [canonical(target) for target in actual.get("targets", [])]
    if exp_targets != act_targets:
        exp_ids = [target["entityId"] for target in exp_targets]
        act_ids = [target["entityId"] for target in act_targets]
        if set(exp_ids) != set(act_ids):
            errors.append("E_TARGET_SET")
            detail["missing"] = sorted(set(exp_ids) - set(act_ids))
            detail["extra"] = sorted(set(act_ids) - set(exp_ids))
        if exp_ids == act_ids and exp_targets != act_targets:
            errors.append("E_TARGET_FIELDS")
            detail["expected"] = exp_targets
            detail["actual"] = act_targets
        if exp_ids != act_ids and set(exp_ids) == set(act_ids):
            errors.append("E_TARGET_ORDER")

    if "ambiguousCandidates" in expected:
        if sorted(expected["ambiguousCandidates"]) != sorted(actual.get("ambiguousCandidates", [])):
            errors.append("E_AMBIGUOUS_CANDIDATES")
    if "unresolvedMentions" in expected:
        if sorted(expected["unresolvedMentions"]) != sorted(actual.get("unresolvedMentions", [])):
            errors.append("E_UNRESOLVED_MENTIONS")
    if "reason" in expected and expected["reason"] != actual.get("reason"):
        errors.append("E_REASON")
    return errors, detail


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rosters_doc = json.loads((FREEZE / "rosters.json").read_text(encoding="utf-8"))
    anchors_doc = json.loads((FREEZE / "anchors-v1.json").read_text(encoding="utf-8"))
    acceptance = json.loads((FREEZE / "acceptance-v1.json").read_text(encoding="utf-8"))
    probes = json.loads((FREEZE / "v2-extra-probes.json").read_text(encoding="utf-8"))["probes"]

    drift: list[str] = []
    for doc, key in ((rosters_doc, "rosters"), (anchors_doc, "sources")):
        for ref, source in doc[key].items():
            actual_hash = sha256(ROOT / source["sourceFile"])
            if actual_hash != source["sourceSha256"]:
                drift.append(f"{ref} {source['sourceFile']}")
    if drift:
        raise SystemExit("fixture drift, rebuild freeze files first:\n" + "\n".join(drift))

    parse_rows: list[dict] = []
    score_rows: list[dict] = []
    for sample in acceptance["samples"]:
        ref = sample["worldRef"]
        parsed = v2.parse(
            sample["utterance"], rosters_doc["rosters"][ref], sample.get("priorNarration"), anchors_doc, ref
        )
        parse_rows.append(
            {
                "sampleId": sample["sampleId"],
                "worldRef": ref,
                "utterance": sample["utterance"],
                "parsed": parsed,
            }
        )
        errors, detail = compare(sample["expected"], parsed)
        score_rows.append(
            {
                "sampleId": sample["sampleId"],
                "category": sample["category"],
                "expectedState": sample["expected"]["state"],
                "actualState": parsed["state"],
                "expectedTargets": [canonical(t) for t in sample["expected"].get("targets", [])],
                "actualTargets": [canonical(t) for t in parsed.get("targets", [])],
                "errors": errors,
                "detail": detail,
                "match": not errors,
            }
        )

    probe_rows: list[dict] = []
    for probe in probes:
        ref = probe["worldRef"]
        parsed = v2.parse(
            probe["utterance"], rosters_doc["rosters"][ref], probe.get("priorNarration"), anchors_doc, ref
        )
        errors, detail = compare(probe["expected"], parsed)
        probe_rows.append(
            {
                "probeId": probe["probeId"],
                "mechanism": probe["mechanism"],
                "utterance": probe["utterance"],
                "expected": probe["expected"],
                "actual": {
                    "state": parsed["state"],
                    "targets": [canonical(t) for t in parsed.get("targets", [])],
                    "ambiguousCandidates": parsed.get("ambiguousCandidates", []),
                    "unresolvedMentions": parsed.get("unresolvedMentions", []),
                    "reason": parsed.get("reason"),
                },
                "errors": errors,
                "detail": detail,
                "match": not errors,
            }
        )

    passed = sum(1 for row in score_rows if row["match"])
    probe_passed = sum(1 for row in probe_rows if row["match"])
    hashes = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "trackedDirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "files": {
            "attention_parse_v2.py": sha256(HERE / "attention_parse_v2.py"),
            "attention_parse.py": sha256(HERE / "attention_parse.py"),
            "run_v2_acceptance.py": sha256(HERE / "run_v2_acceptance.py"),
            "freeze/acceptance-v1.json": sha256(FREEZE / "acceptance-v1.json"),
            "freeze/anchors-v1.json": sha256(FREEZE / "anchors-v1.json"),
            "freeze/rosters.json": sha256(FREEZE / "rosters.json"),
            "freeze/v2-extra-probes.json": sha256(FREEZE / "v2-extra-probes.json"),
        },
    }
    score = {
        "protocol": "c1-attention-granularity-v1",
        "scope": "parse only; no fact filtering",
        "hashes": hashes,
        "summary": {
            "samples": len(score_rows),
            "passed": passed,
            "failed": len(score_rows) - passed,
            "extraProbes": len(probe_rows),
            "extraProbesPassed": probe_passed,
        },
        "rows": score_rows,
        "extraProbes": probe_rows,
    }
    (RUN_DIR / "parse.json").write_text(
        json.dumps({"protocol": "c1-attention-granularity-v1", "rows": parse_rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (RUN_DIR / "score.json").write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"commit {hashes['commit'][:12]} branch {hashes['branch']} trackedDirty={hashes['trackedDirty']}",
        f"python {hashes['python']} {hashes['platform']}",
        "scope: v2 parse only; no fact filtering",
        "",
    ]
    for row in score_rows:
        exp = ",".join(f"{t['entityId']}/{t['scope']}" + (f"/{t['part']}({t['partAnchored']})" if "part" in t else "") for t in row["expectedTargets"]) or "-"
        act = ",".join(f"{t['entityId']}/{t['scope']}" + (f"/{t['part']}({t['partAnchored']})" if "part" in t else "") for t in row["actualTargets"]) or "-"
        lines.append(
            f"{row['sampleId']} {row['category']:<28} exp={row['expectedState']}/{exp:<34} "
            f"act={row['actualState']}/{act:<34} {','.join(row['errors']) or 'ok'}"
        )
    lines.append("")
    for row in probe_rows:
        lines.append(f"{row['probeId']} {row['mechanism']:<30} {row['actual']['state']:<11} {','.join(row['errors']) or 'ok'}")
    lines.append("")
    lines.append(f"summary: {passed}/{len(score_rows)} parse labels matched; extra probes {probe_passed}/{len(probe_rows)}")
    log = "\n".join(lines) + "\n"
    (RUN_DIR / "run.log").write_text(log, encoding="utf-8")
    print(log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
