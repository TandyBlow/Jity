# -*- coding: utf-8 -*-
"""Read-only inventory of every local checkpoint that could serve the next round.

Nothing is loaded into memory beyond config.json; no model is instantiated and
no generation is run. For each directory containing model.safetensors the script
records the path, byte size, full sha256, the architecture fields from
config.json, and whether any file in this task's evidence set mentions it.

The point is to answer one question honestly: is there a LOCAL checkpoint that
was ever trained to read a plan block? The old controllability run reported
"weights not committed", so the expected answer is "no".

Usage:
    python -X utf8 inventory_checkpoints.py
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[6]          # D:/others/Jity
TREE = HERE.parents[3]          # c3 worktree root (the design/ and artifacts/ tree used here)
OUT = HERE / "freeze" / "checkpoint-inventory.json"

SEARCH_ROOTS = [
    REPO / ".local" / "models",
    REPO / ".local" / "demo-n1n4",
    REPO / ".local" / "world-components-worktree" / "experiments" / "world-components" / "assets",
    REPO / ".local" / "world-components-worktree" / "experiments" / "world-components" / "n4_corpus_v2",
    REPO / ".local" / "world-components-worktree" / "ckpt-scenevb",
    REPO / ".local" / "world-components-next-worktree" / "artifacts" / "next-runs",
    REPO / ".local" / "mockremote" / "base",
]

# Documents that would have to mention a checkpoint for the claim "this was
# trained on plans" to be checkable.
MENTION_SOURCES = [
    TREE / "design/world-engine-reports/components/plan-controllability-v1.md",
    TREE / "artifacts/world-components/organize-wording/controllability-freeze-v1.json",
    TREE / "design/world-engine-reports/components/README.md",
]

MAX_BYTES = 500 * 1024 * 1024     # skip anything larger (no full hashing)
ARCH_FIELDS = ("model_type", "architectures", "d_model", "num_layers", "num_decoder_layers", "vocab_size")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_checkpoints() -> list[Path]:
    found: list[Path] = []
    for root in SEARCH_ROOTS:
        if root.is_file() and root.name == "model.safetensors":
            found.append(root)
            continue
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", ".git", "__pycache__")]
            if "model.safetensors" in filenames:
                found.append(Path(dirpath) / "model.safetensors")
    return sorted(set(found))


def main() -> int:
    mentions = ""
    for p in MENTION_SOURCES:
        if p.exists():
            mentions += p.read_text(encoding="utf-8", errors="replace")

    rows = []
    for weight in find_checkpoints():
        cfg_path = weight.parent / "config.json"
        cfg = {}
        if cfg_path.exists():
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception as exc:  # recorded, not fatal
                cfg = {"_error": str(exc)}
        size = weight.stat().st_size
        rel = str(weight.parent.relative_to(REPO))
        hashed = sha256_file(weight) if size <= MAX_BYTES else None
        rows.append({
            "dir": rel,
            "sizeBytes": size,
            "modelSha256": hashed,
            "hashed": hashed is not None,
            "arch": {k: cfg.get(k) for k in ARCH_FIELDS if k in cfg},
            "configPresent": cfg_path.exists(),
            "tokenizerFiles": sorted(
                f.name for f in weight.parent.iterdir()
                if f.name in ("spiece.model", "tokenizer_config.json", "special_tokens_map.json")
            ),
            "mentionedInRecords": bool(hashed and hashed in mentions) or (rel in mentions),
            "planTrainingClaim": None,
        })

    # The only claim this round can check: does any record say the weights were
    # trained to consume a plan block, and can that be tied to a file hash?
    doc = {
        "created": datetime.now(timezone.utc).isoformat(),
        "purpose": ("find a local checkpoint usable for the plan-execution arm; "
                    "no model is loaded and no generation is run"),
        "searchRoots": [str(p.relative_to(REPO)) for p in SEARCH_ROOTS],
        "maxHashedBytes": MAX_BYTES,
        "checkpoints": rows,
        "finding": {
            "count": len(rows),
            "withHash": sum(1 for r in rows if r["hashed"]),
            "mentionedInRecords": sum(1 for r in rows if r["mentionedInRecords"]),
            "planTrained": 0,
            "why": ("no record ties any of these weight hashes to training that consumed a plan block; "
                    "the controllability run reported that its checkpoint was not saved, and the frozen "
                    "protocol only pins the base weight hash"),
        },
        "caveat": ("a checkpoint whose hash appears in no record cannot be used to answer 'can a "
                   "plan-trained model follow plans' — its identity is unknown, so any result would be "
                   "unattributable"),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"wrote {OUT}")
    print(f"  checkpoints: {doc['finding']['count']} (hashed {doc['finding']['withHash']})")
    print(f"  plan-trained: {doc['finding']['planTrained']}")
    for r in rows:
        mark = "hash" if r["hashed"] else "skip"
        print(f"  {mark:4s} {r['sizeBytes']//(1<<20):4d}MB {r['dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
