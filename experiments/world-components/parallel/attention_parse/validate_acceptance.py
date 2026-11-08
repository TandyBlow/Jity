"""Validate the frozen granularity acceptance labels against committed data.

This does NOT run an extractor. It answers one question: are the 10 frozen
labels internally consistent and traceable to the two committed fixtures?

Checks per sample:
  - referenced world/roster exists; every entityId is in that roster
  - scope is one of the five; part/partAnchored only on scope=part
  - surface / scopeCue / part appear literally in the utterance
  - partAnchored equals what freeze/anchors-v1.json says for that entity
  - state rules: resolved -> targets; ambiguous -> >=2 shared-form candidates;
    unresolved -> mentions; none -> nothing
  - category prefix agrees with the expected state

Writes runs/contract-v1/validation.json and run.log.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FREEZE = HERE / "freeze"
RUN_DIR = HERE / "runs" / "contract-v1"
ROOT = HERE.parents[3]

SCOPES = {"object", "position", "appearance", "task", "part"}
STATES = {"resolved", "ambiguous", "unresolved", "none"}


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


def shared_form(entities: list[dict]) -> bool:
    names = [entity["name"] for entity in entities]
    if len(set(names)) < len(names):
        return True
    for length in range(2, min(len(name) for name in names)):
        prefixes = {name[:length] for name in names}
        if len(prefixes) < len(names):
            return True
    return False


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    rosters_doc = json.loads((FREEZE / "rosters.json").read_text(encoding="utf-8"))
    anchors_doc = json.loads((FREEZE / "anchors-v1.json").read_text(encoding="utf-8"))
    acceptance = json.loads((FREEZE / "acceptance-v1.json").read_text(encoding="utf-8"))

    drift: list[str] = []
    for doc, label in ((rosters_doc, "rosters"), (anchors_doc, "anchors")):
        for ref, source in doc.get("rosters", doc.get("sources", {})).items():
            actual = sha256(ROOT / source["sourceFile"])
            if actual != source["sourceSha256"]:
                drift.append(f"{label}:{ref} {source['sourceFile']} {source['sourceSha256'][:12]} -> {actual[:12]}")
    if drift:
        raise SystemExit("fixture drift, rebuild freeze files first:\n" + "\n".join(drift))

    anchors_by_entity: dict[str, list[dict]] = {}
    for source in anchors_doc["sources"].values():
        for anchor in source["anchors"]:
            anchors_by_entity.setdefault(anchor["entityId"], []).append(anchor)

    rows: list[dict] = []
    for sample in acceptance["samples"]:
        checks: list[dict] = []
        errors: list[str] = []

        def check(name: str, ok: bool, detail: str = "") -> None:
            checks.append({"check": name, "ok": ok, "detail": detail})
            if not ok:
                errors.append(name)

        roster = rosters_doc["rosters"].get(sample["worldRef"])
        check("roster_exists", roster is not None, sample["worldRef"])
        if roster is None:
            rows.append({"sampleId": sample["sampleId"], "errors": errors, "checks": checks})
            continue

        entities = {entity["entityId"]: entity for entity in roster["entities"]}
        utterance = sample["utterance"]
        expected = sample["expected"]
        state = expected["state"]
        check("state_known", state in STATES, state)
        category_prefix = sample["category"].split("_")[0]
        check(
            "category_matches_state",
            (category_prefix == "state" and state != "resolved") or (category_prefix == "scope" and state == "resolved"),
            f"category={sample['category']} state={state}",
        )

        targets = expected.get("targets", [])
        if state == "resolved":
            check("resolved_has_targets", bool(targets), f"{len(targets)} targets")
            for index, target in enumerate(targets):
                entity = entities.get(target.get("entityId"))
                check(f"target{index}_entity_exists", entity is not None, str(target.get("entityId")))
                scope = target.get("scope")
                check(f"target{index}_scope_known", scope in SCOPES, str(scope))
                check(
                    f"target{index}_surface_in_utterance",
                    bool(target.get("surface")) and target["surface"] in utterance,
                    str(target.get("surface")),
                )
                cue = target.get("scopeCue")
                if scope == "object":
                    check(f"target{index}_object_has_no_part", "part" not in target, str(target.get("part")))
                else:
                    check(
                        f"target{index}_scope_cue_in_utterance",
                        bool(cue) and cue in utterance,
                        str(cue),
                    )
                if scope == "part":
                    part = target.get("part")
                    check(f"target{index}_part_in_utterance", bool(part) and part in utterance, str(part))
                    anchor_texts = [anchor["text"] for anchor in anchors_by_entity.get(target["entityId"], [])]
                    anchored = any(part and part in text for text in anchor_texts)
                    check(
                        f"target{index}_part_anchored_matches_fixture",
                        target.get("partAnchored") == anchored,
                        f"label={target.get('partAnchored')} fixture={anchored} anchors={len(anchor_texts)}",
                    )
                else:
                    check(
                        f"target{index}_no_part_outside_part_scope",
                        "part" not in target and "partAnchored" not in target,
                        str({k: target.get(k) for k in ("part", "partAnchored")}),
                    )

        if state == "ambiguous":
            candidates = expected.get("ambiguousCandidates", [])
            check("ambiguous_no_targets", not targets)
            check("ambiguous_has_two_plus", len(candidates) >= 2, str(candidates))
            known = [entities[c] for c in candidates if c in entities]
            check("ambiguous_candidates_exist", len(known) == len(candidates), str(candidates))
            if len(known) >= 2:
                check("ambiguous_share_form", shared_form(known), ",".join(e["name"] for e in known))
            check("ambiguous_has_reason", bool(expected.get("reason")), str(expected.get("reason")))

        if state == "unresolved":
            mentions = expected.get("unresolvedMentions", [])
            check("unresolved_no_targets", not targets)
            check("unresolved_has_mentions", bool(mentions), str(mentions))
            check(
                "unresolved_mentions_in_utterance",
                all(mention in utterance for mention in mentions),
                str(mentions),
            )
            check("unresolved_has_reason", bool(expected.get("reason")), str(expected.get("reason")))

        if state == "none":
            check("none_no_targets", not targets)
            check("none_no_candidates", not expected.get("ambiguousCandidates") and not expected.get("unresolvedMentions"))
            check("none_has_reason", bool(expected.get("reason")), str(expected.get("reason")))

        rows.append(
            {
                "sampleId": sample["sampleId"],
                "category": sample["category"],
                "worldRef": sample["worldRef"],
                "utterance": utterance,
                "state": state,
                "scopes": [target.get("scope") for target in targets],
                "checks": checks,
                "errors": errors,
                "match": not errors,
            }
        )

    passed = sum(1 for row in rows if row.get("match"))
    scope_counts: dict[str, int] = {}
    for row in rows:
        for scope in row["scopes"]:
            scope_counts[scope] = scope_counts.get(scope, 0) + 1
    state_counts: dict[str, int] = {}
    for row in rows:
        state_counts[row["state"]] = state_counts.get(row["state"], 0) + 1

    hashes = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "trackedDirty": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "files": {
            "build_anchors.py": sha256(HERE / "build_anchors.py"),
            "validate_acceptance.py": sha256(HERE / "validate_acceptance.py"),
            "freeze/contract-v1.md": sha256(FREEZE / "contract-v1.md"),
            "freeze/acceptance-v1.json": sha256(FREEZE / "acceptance-v1.json"),
            "freeze/anchors-v1.json": sha256(FREEZE / "anchors-v1.json"),
            "freeze/rosters.json": sha256(FREEZE / "rosters.json"),
        },
    }

    report = {
        "protocol": "c1-attention-granularity-v1",
        "scope": "label validation only; no extractor was run",
        "hashes": hashes,
        "summary": {
            "samples": len(rows),
            "passed": passed,
            "failed": len(rows) - passed,
            "scopes": scope_counts,
            "states": state_counts,
        },
        "rows": rows,
    }
    (RUN_DIR / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"commit {hashes['commit'][:12]} branch {hashes['branch']} trackedDirty={hashes['trackedDirty']}",
        f"python {hashes['python']} {hashes['platform']}",
        "scope: frozen label validation only; no extractor run",
        "",
    ]
    for row in rows:
        failed = [check["check"] for check in row["checks"] if not check["ok"]]
        lines.append(
            f"{row['sampleId']} {row['category']:<28} {row['state']:<11} scopes={','.join(row['scopes']) or '-':<24} "
            f"{'ok' if row['match'] else 'FAIL: ' + ','.join(failed)}"
        )
    lines.append("")
    lines.append(
        f"summary: {passed}/{len(rows)} labels valid; scopes={scope_counts}; states={state_counts}"
    )
    log = "\n".join(lines) + "\n"
    (RUN_DIR / "run.log").write_text(log, encoding="utf-8")
    print(log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
