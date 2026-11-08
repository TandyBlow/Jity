# Record the input manifest for the round-composition experiment: which
# N1-N5 contract implementations, which fixtures and which N5 rule the run
# used, with per-file SHA-256 and the git HEAD of this worktree.
#
# The hashes are of the bytes actually imported/read by compose.py (same
# paths, same working tree), so a cited number can be reproduced from this
# file plus the commit. A missing mandatory source is a FAILURE, not a pass.
#
# Usage: python -X utf8 record_manifest.py

import hashlib
import json
import pathlib
import platform
import subprocess
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent          # experiments/world-components
REPO = WC.parent.parent          # worktree root
OUT = HERE / "fixtures" / "manifest.json"

# role -> repo-relative paths that the composer imports or reads
SOURCES = {
    "N1_fact_extraction": [
        "experiments/world-components/narration_pipeline.py"],
    "N2_selection_rule": [
        "experiments/world-components/n2_perspective.py"],
    "N3_organization_check": [
        "experiments/world-components/n3_organize.py"],
    "N4_0_scene_and_packing": [
        "experiments/world-components/n4_input_renderer/__init__.py",
        "experiments/world-components/n4_input_renderer/packer.py",
        "experiments/world-components/n4_input_renderer/renderer.py",
        "experiments/world-components/n4_input_renderer/scene_context.py"],
    "N5_rule_v2_aligner": [
        "experiments/world-components/n4_corpus_v2/eval_n4_v2.py"],
    "N5_rule_v7_recognizer_crosscheck": [
        "experiments/world-components/n4_corpus/corpus_check.py"],
    "N3_plan_baselines_and_interface": [
        "experiments/world-components/n2_selection/n3_plan.py",
        "experiments/world-components/n2_selection/n3_n4_fixture.py"],
    "legacy_renderer_units": [
        "experiments/world-components/n4_corpus/n4_render.py"],
    "contracts_and_rules": [
        "design/world-engine-reports/components/component-contracts.md",
        "design/world-engine-reports/components/n4-input-packing.md",
        "design/world-engine-reports/components/n4-narrative-dev.md",
        "design/world-engine-reports/components/n2-annotation-rubric.md"],
    "previous_composition_archives": [
        "artifacts/world-components/n1-n5-composition-r1.json",
        "artifacts/world-components/n1-n5-composition-v2-r1.json",
        "artifacts/world-components/n4-input-packing-r1.json"],
    "this_experiment": [
        "experiments/world-components/parallel/round_composition/.gitattributes",
        "experiments/world-components/parallel/round_composition/README.md",
        "experiments/world-components/parallel/round_composition/conclusion.md",
        "experiments/world-components/parallel/round_composition/"
        "contract-decisions.md",
        "experiments/world-components/parallel/round_composition/"
        "contract_probes.py",
        # v3 (adjudicated) implementation
        "experiments/world-components/parallel/round_composition/judge_v3.py",
        "experiments/world-components/parallel/round_composition/"
        "compose_v3.py",
        "experiments/world-components/parallel/round_composition/"
        "make_v3_fixtures.py",
        "experiments/world-components/parallel/round_composition/"
        "test_judge_v3.py",
        "experiments/world-components/parallel/round_composition/"
        "human-review-v1.md",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/cases-v3-extra.json",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/annotations-v1.json",
        "experiments/world-components/parallel/round_composition/"
        "out/console-v3.log",
        # first real-model batch (pre-registration, runner, review)
        "experiments/world-components/parallel/round_composition/"
        "make_real_batch.py",
        "experiments/world-components/parallel/round_composition/"
        "real_batch.py",
        "experiments/world-components/parallel/round_composition/"
        "write_review_v1.py",
        "experiments/world-components/parallel/round_composition/"
        "apply_review.py",
        "experiments/world-components/parallel/round_composition/"
        "real-batch-v1.md",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/batch-v1.json",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/batch-v1-cases.json",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/review-v1.json",
        "experiments/world-components/parallel/round_composition/"
        "out/real-batch-v1-raw.jsonl",
        "experiments/world-components/parallel/round_composition/"
        "out/real-batch-v1-summary.txt",
        # budget-control batch v2 (384) + v1 errata
        "experiments/world-components/parallel/round_composition/"
        "fixtures/errata-v1.json",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/batch-v2.json",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/review-v2.json",
        "experiments/world-components/parallel/round_composition/"
        "make_real_batch_v2.py",
        "experiments/world-components/parallel/round_composition/"
        "real_batch_v2.py",
        "experiments/world-components/parallel/round_composition/"
        "write_review_v2.py",
        "experiments/world-components/parallel/round_composition/"
        "test_tripwire_v2.py",
        "experiments/world-components/parallel/round_composition/"
        "real-batch-v2.md",
        "experiments/world-components/parallel/round_composition/"
        "out/real-batch-v2-raw.jsonl",
        "experiments/world-components/parallel/round_composition/"
        "out/real-batch-v2-summary.txt",
        "experiments/world-components/parallel/round_composition/compose.py",
        "experiments/world-components/parallel/round_composition/"
        "make_fixtures.py",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/cases.json",
        "experiments/world-components/parallel/round_composition/"
        "fixtures/mocks.json"],
}


def sha_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          text=True, check=False).stdout.strip()


def gate_coverage(archive_path) -> dict:
    """Measure which N5 gates the archived run actually evaluated.

    Derived from the archive, never hand-maintained: for each gate name,
    the cases and attempts that carry it and the values seen. G4/G5 are
    triggered by a rowId substring in judge_row, so a gate can appear on a
    case that is not designed for it — the record says which cases, and
    flags the trigger mechanism, instead of asserting a boolean.
    """
    if not archive_path.exists():
        return {"status": "archive-missing",
                "path": str(archive_path)}
    doc = json.loads(archive_path.read_text(encoding="utf-8"))
    seen, values = {}, {}
    for case in doc.get("cases") or []:
        stages = case.get("stages") or {}
        for att in (stages.get("n4n5") or {}).get("attempts") or []:
            for gate, ok in ((att.get("n5") or {}).get("gates") or {}).items():
                seen.setdefault(gate, []).append(
                    {"caseId": case.get("caseId"), "attempt": att.get("attempt")})
                values.setdefault(gate, set()).add(ok)
    return {
        "status": "measured",
        "archive": str(archive_path.name),
        "archiveSha256": sha_file(archive_path),
        "trigger": "eval_n4_v2.judge_row gates: G1/G2/G3/G6 always run; "
                   "G4 runs only when rowId[case] contains 'conflict' and "
                   "G5 only when it contains 'same-name'",
        "executed": {g: {"evaluations": len(v), "cases": sorted(
            {x["caseId"] for x in v}), "values": sorted(values[g])}
            for g, v in sorted(seen.items())},
        "notExecuted": sorted({"G1_alignment", "G2_no_fabrication",
                               "G3_time", "G4_conflict_names",
                               "G5_same_name_bare", "G6_no_truncation"}
                              - set(seen)),
        "notes": {
            "G4": "evaluated only on the case whose caseId contains "
                  "'conflict' (contract-time-conflict). That case has ONE "
                  "actor (two facts, both 管线甲), so G4 took its "
                  "'same-name multiple mention' branch text.count(name)>=2; "
                  "this is an ACCIDENTAL trigger, not a validated conflict "
                  "case. No designed two-actor conflict case exists in this "
                  "composition.",
            "G5": "not executed: no caseId contains 'same-name'.",
            "G3": "evaluated on one case carrying a time fact; it fails on "
                  "the N4.0-compliant vague time and passes only on an exact "
                  "value (see out/contract-probes.json).",
        },
    }


def main() -> int:
    missing, files = [], {}
    for role, paths in SOURCES.items():
        entries = []
        for rel in paths:
            p = REPO / rel
            if not p.exists():
                missing.append({"role": role, "path": rel})
                continue
            entries.append({"path": rel, "sha256": sha_file(p),
                            "bytes": p.stat().st_size})
        files[role] = entries

    # the archived run(s) are outputs, hashed separately so an input/output
    # split is visible
    outputs = []
    for p in sorted((HERE / "out").glob("*.json")):
        outputs.append({"path": str(p.relative_to(REPO)), "sha256": sha_file(p),
                        "bytes": p.stat().st_size})

    doc = {
        "version": "round-composition-manifest-v0.1",
        "experiment": "C7 / R11 offline round composition",
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "worktree": str(REPO),
        "git": {"branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                # This file is written BEFORE the commit that ships it, so
                # this is that commit's PARENT. History rewrites (amend,
                # squash) can leave it dangling; the per-file SHA-256 above
                # is what binds the evidence, not this field.
                "headAtRecording": git("rev-parse", "HEAD"),
                "headSubject": git("log", "-1", "--pretty=%s"),
                # The manifest is written just before it is committed, so
                # HEAD is the PARENT of the commit that carries this
                # directory and the porcelain list names this experiment's
                # own files plus the coordinator's untracked TASK.md brief.
                # The list is recorded verbatim so nothing is hidden behind
                # a single boolean.
                "porcelain": [line for line in
                              git("status", "--porcelain").splitlines()
                              if line.strip()]},
        "environment": {"python": sys.version.split()[0],
                        "platform": platform.platform()},
        "sources": files,
        "outputs": outputs,
        "missing": missing,
        "n5Rules": {
            "v3_adjudicated": {
                "file": "judge_v3.py",
                "version": "n5-v3",
                "applies": "out/composition-v3-run.json only",
                "D1": "outcome + resultText; missing resultText blocks "
                      "(JudgeBlocked outcome-result-missing); the goal is never "
                      "accepted as a substitute",
                "D2": "vague expression accepted; any stated duration is parsed "
                      "and compared with the authoritative time fact",
                "D3": "hard gates only; quality() returns pending/undetermined "
                      "unless an executed N6 result is supplied",
                "D5": "G4/G5 data-triggered; the judge takes no rowId",
                "D4": "unregistered names come from human labels: unchecked -> "
                      "count null, checked-and-clean -> 0",
            },
            "v2_frozen": {
                "file": "eval_n4_v2.py",
                "applies": "out/composition-run.json (kept unchanged)",
                "note": "still rowId-substring triggered; still requires the "
                        "exact time value and the quoted task goal",
            },
        },
        "n5Rule": {
            "gating": "eval_n4_v2.judge_row (frozen v2 holdout gate): "
                      "G1 alignment/must coverage, G2 residue name+goal scan, "
                      "G3 exact time value, G4 conflict names (rowId-gated), "
                      "G5 same-name bare (rowId-gated), G6 no truncation. "
                      "P1/P2 pronoun gates are aggregate-level and not used "
                      "per case.",
            "recordedOnly": "corpus_check.check_narration via "
                            "narration_pipeline.verify_text (v7 recognizer): "
                            "must-coverage and unrecognized content are "
                            "review-class, no truncation rule. Archived as "
                            "n5CrossCheck; never gates, never auto-passes.",
            "semanticReview": "not run in this experiment",
        },
        "n5GateCoverage": gate_coverage(REPO / "experiments" /
                                        "world-components" / "parallel" /
                                        "round_composition" / "out" /
                                        "composition-run.json"),
        "tokenGate": {"applied": False,
                      "reason": "mock ports take text, so no N4 token limit "
                                "applies here; N4.0 packs measure 287-390 "
                                "tokens with the T5 tokenizer in the archived "
                                "n4-input-packing-r1 record, and no checkpoint "
                                "is present in this worktree to recount"},
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"manifest -> {OUT}")
    print(f"missing sources: {len(missing)}")
    for m in missing:
        print("  MISSING", m["role"], m["path"])
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
