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
                "head": git("rev-parse", "HEAD"),
                "headSubject": git("log", "-1", "--pretty=%s"),
                "dirty": bool(git("status", "--porcelain"))},
        "environment": {"python": sys.version.split()[0],
                        "platform": platform.platform()},
        "sources": files,
        "outputs": outputs,
        "missing": missing,
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
        "gateScope": {"G4_executed": False, "G5_executed": False,
                      "G4_G5_reason": "only fire on rowId containing "
                                      "'conflict'/'same-name'; no such case is "
                                      "part of this composition",
                      "G3_executed": True,
                      "G3_reason": "contract-time-conflict carries a time fact"},
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
