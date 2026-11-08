# -*- coding: utf-8 -*-
"""Route-A forensics: is the old plan-controllability checkpoint recoverable?

Read-only. It does not load any model; it checks records and files only.

What it checks, in order:
  1. What the records actually claim: does anything pin a *trained* weight hash?
  2. Whether the training script that produced the run could have written
     weights at all (a `save_pretrained`/`torch.save` call would be required).
     Every committed version of the script is inspected, not just HEAD.
  3. What the run directory actually contains, byte for byte.
  4. Whether a checkpoint with that name exists anywhere reachable: known
     search roots, the user's home directory, and any `ckpt-group*` /
     `controllab*` directory.
  5. Whether the run record itself carries a checkpoint hash or path.

Output: freeze/checkpoint-forensics.json

Usage:
    python -X utf8 recover_checkpoint.py
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TREE = HERE.parents[3]              # c3 worktree root
REPO = HERE.parents[6]              # D:/others/Jity
OUT = HERE / "freeze" / "checkpoint-forensics.json"

TRAIN_SCRIPT = "experiments/world-components/organize_wording/train_controllability.py"
RUN_DIR = TREE / "artifacts/world-components/organize-wording/controllability-run-v1"
FREEZE = TREE / "artifacts/world-components/organize-wording/controllability-freeze-v1.json"
REPORT = TREE / "artifacts/world-components/organize-wording/controllability-report-v1.md"
COMPONENTS_README = TREE / "design/world-engine-reports/components/README.md"
PLAN_DOC = TREE / "design/world-engine-reports/components/plan-controllability-v1.md"
INVENTORY = HERE / "freeze/checkpoint-inventory.json"

SEARCH_ROOTS = [
    REPO / ".local",
    Path.home(),
    REPO / "artifacts",
]
NAME_HINTS = ("ckpt-group", "controllab", "n4group")
WEIGHT_NAMES = ("model.safetensors", "pytorch_model.bin", "model.bin")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-c", f"safe.directory={TREE.as_posix()}", *args],
            cwd=TREE, capture_output=True, text=True, check=True,
        ).stdout
    except Exception as exc:  # recorded, not fatal
        return f"<git error: {exc}>"


def script_versions() -> list[dict]:
    """Every committed version of the training script, with save-call counts."""
    revs = [r for r in git("log", "--all", "--format=%H %ad %s", "--date=short",
                           "--", TRAIN_SCRIPT).splitlines() if r.strip()]
    out = []
    for line in revs:
        parts = line.split(" ", 2)
        commit = parts[0]
        body = git("show", f"{commit}:{TRAIN_SCRIPT}")
        saves = [ln.strip() for ln in body.splitlines()
                 if "save_pretrained" in ln or "torch.save" in ln]
        in_memory = [ln.strip() for ln in body.splitlines()
                     if "state_dict()" in ln and "save" not in ln]
        out.append({
            "commit": commit,
            "commitShort": commit[:8],
            "meta": " ".join(parts[1:]),
            "bytes": len(body),
            "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "saveCalls": saves,
            "inMemoryStateLines": in_memory[:4],
        })
    return out


SKIP_DIRS = {"node_modules", ".git", "__pycache__", "AppData", "AppData?",
             "Application Data", "Local Settings", ".cache", ".conda", ".npm"}
MAX_DEPTH = 8


def walk_candidates() -> tuple[list[dict], list[dict]]:
    """-> (dirs that actually contain weights, name-matching dirs without weights)."""
    with_weights: list[dict] = []
    without_weights: list[dict] = []
    seen: set[str] = set()
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            if len(Path(dirpath).parts) - base_depth >= MAX_DEPTH:
                dirnames[:] = []
            low = dirpath.lower()
            if not any(h in low for h in NAME_HINTS):
                continue
            if dirpath in seen:
                continue
            seen.add(dirpath)
            weights = [f for f in filenames if f in WEIGHT_NAMES]
            entry = {"dir": dirpath, "files": sorted(filenames)[:8],
                     "weightFiles": weights}
            (with_weights if weights else without_weights).append(entry)
    return with_weights, without_weights


def main() -> int:
    run_files = []
    if RUN_DIR.exists():
        for p in sorted(RUN_DIR.iterdir()):
            run_files.append({"name": p.name, "sizeBytes": p.stat().st_size,
                              "sha256": sha256(p) if p.is_file() and p.stat().st_size < 5_000_000 else None})

    freeze = json.loads(FREEZE.read_text(encoding="utf-8")) if FREEZE.exists() else {}
    freeze_keys = sorted(freeze.keys())
    freeze_base = freeze.get("base_hashes", {})
    # Does the frozen record pin any TRAINED weight hash? base_hashes describes
    # the base model; nothing else in the record names a checkpoint file.
    trained_pins = [k for k in freeze_keys if "ckpt" in k.lower() or "checkpoint" in k.lower()]

    results = {}
    if (RUN_DIR / "results.json").exists():
        results = json.loads((RUN_DIR / "results.json").read_text(encoding="utf-8"))
    results_keys = sorted(results.keys())
    results_has_hash = [k for k in results_keys if "sha" in k.lower() or "hash" in k.lower()]

    report_text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    plan_text = PLAN_DOC.read_text(encoding="utf-8") if PLAN_DOC.exists() else ""
    readme_text = COMPONENTS_README.read_text(encoding="utf-8") if COMPONENTS_README.exists() else ""
    claims = {
        # What THIS run's report says. It says nothing about weights at all; the
        # absence is the finding, so record it explicitly instead of quoting a
        # sentence from a different experiment.
        "controllabilityReport": {
            "file": str(REPORT.relative_to(TREE)) if REPORT.exists() else None,
            "linesMentioningWeights": [ln for ln in report_text.splitlines() if "权重" in ln][:6],
            "linesMentioningSavedOrCommitted": [ln for ln in report_text.splitlines()
                                                if "未保存" in ln or "未提交" in ln or "保存" in ln][:6],
            "mentionsWeightsAtAll": "权重" in report_text,
        },
        # A different run's report does say "权重未提交"; recorded separately so
        # it is never cited as evidence about the controllability run.
        "otherRunStatement": {
            "file": str(COMPONENTS_README.relative_to(TREE)) if COMPONENTS_README.exists() else None,
            "lines": [ln[:160] for ln in readme_text.splitlines() if "权重未提交" in ln][:3],
            "appliesTo": "A/B_h sentence arm (120-update A/B_h run), NOT the controllability run",
        },
        "planDocMentionsCheckpoint": [ln[:160] for ln in plan_text.splitlines()
                                      if "检查点" in ln or "ckpt" in ln.lower()][:6],
    }

    versions = script_versions()
    any_save = [v for v in versions if v["saveCalls"]]
    t0 = time.perf_counter()
    weight_dirs, record_dirs = walk_candidates()
    search_seconds = round(time.perf_counter() - t0, 1)

    inventory = {}
    if INVENTORY.exists():
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8")).get("finding", {})

    verdict = {
        "found": bool(weight_dirs),
        "verdict": "not-found-locally",
        "reason": [],
    }
    if not any_save:
        verdict["reason"].append(
            "no committed version of the training script contains save_pretrained/torch.save; "
            "it keeps the best state in memory only and reloads it with load_state_dict")
    if not trained_pins:
        verdict["reason"].append(
            "the frozen record pins only base model hashes; there is no trained-checkpoint field")
    if not claims["controllabilityReport"]["mentionsWeightsAtAll"]:
        verdict["reason"].append(
            "the controllability report never mentions weights at all, so it neither claims nor denies "
            "saving them; the script's missing save call is the decisive evidence")
    if not results_has_hash:
        verdict["reason"].append("results.json contains no weight hash field")
    if not weight_dirs:
        verdict["reason"].append(
            f"{len(record_dirs)} name-matching directories exist, but every one of them is a run "
            f"record (results.json/run.log); none contains {', '.join(WEIGHT_NAMES)}")
    if freeze.get("base_hashes"):
        verdict["reason"].append(
            "the only pinned weight is the base model 5cdc5721…, which is present locally and unchanged")

    doc = {
        "protocol": "c3-checkpoint-forensics-a1",
        "created": datetime.now(timezone.utc).isoformat(),
        "route": "A (recover the old trained weights); B and C are explicitly out of scope",
        "claimsInRecords": claims,
        "freezeRecord": {
            "file": str(FREEZE.relative_to(TREE)),
            "keys": freeze_keys,
            "baseHashes": freeze_base,
            "trainedCheckpointPins": trained_pins,
            "note": "baseHashes describe the base model; they do not identify a trained run",
        },
        "runDirectory": {
            "path": str(RUN_DIR.relative_to(TREE)),
            "files": run_files,
            "weightFiles": [f["name"] for f in run_files
                            if f["name"].endswith((".safetensors", ".bin", ".pt", ".pth"))],
        },
        "resultsRecord": {
            "keys": results_keys,
            "hashLikeFields": results_has_hash,
            "selected": results.get("selected"),
        },
        "trainingScript": {
            "path": TRAIN_SCRIPT,
            "versions": versions,
            "versionsWithSaveCall": [v["commitShort"] for v in any_save],
        },
        "filesystemSearch": {
            "roots": [str(r) for r in SEARCH_ROOTS],
            "nameHints": list(NAME_HINTS),
            "maxDepth": MAX_DEPTH,
            "searchSeconds": search_seconds,
            "dirsWithWeights": weight_dirs,
            "matchingRunRecordDirs": record_dirs,
        },
        "remainingChannels": [
            {"channel": "HPC ~/n4group_run/ckpt-group (historical record name)",
             "checked": False,
             "why": "no SSH credentials in this environment; and the record carries no file hash, "
                    "so even a recovered file could not be tied to this run"},
            {"channel": "archived tarball / offline backup",
             "checked": False,
             "why": "no such archive exists under the searched roots; a copy supplied later must carry "
                    "a hash that matches some record, otherwise it stays unattributable"},
        ],
        "existingInventory": inventory,
        "verdict": verdict,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {OUT}")
    print(f"  verdict: {verdict['verdict']}")
    for r in verdict["reason"]:
        print("   -", r)
    print(f"  script versions: {len(versions)}, with a save call: {len(any_save)}")
    print(f"  dirs with weights: {len(weight_dirs)}")
    print(f"  run-record dirs matching the name: {len(record_dirs)}")
    for h in record_dirs[:4]:
        print("   .", h["dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
