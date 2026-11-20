# -*- coding: utf-8 -*-
"""Inventory GGUF files that already exist on this machine, with sha256.

Purpose: lane 11 must not re-download a model that is already available. The
product tree, the training cache and the earlier model-scout cache are read
only; this script hashes them and records where each file lives and which
metadata the file itself declares.

The hashes let a reviewer match a local file to a Hugging Face LFS sha256
without trusting a file name. Paths are absolute and outside Git on purpose:
weights are never committed.

Usage:
    python -X utf8 src/inventory_local.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "models/local-inventory.json"

ROOTS = [
    "D:/others/Jity/.local/parallel-local-game/worktrees/06-recovery/frontend/public/models",
    "D:/others/Jity/.local/models",
    "D:/others/Jity/.local/models-narration",
    "D:/others/Jity/.local/qwen-train",
    "D:/others/Jity/.local/yuyan",
]

sys.path.insert(0, str(HERE))
from gguf_probe import read_gguf  # noqa: E402


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: pathlib.Path) -> dict:
    try:
        summary = read_gguf(path)["summary"]
        return {
            "architecture": summary["architecture"],
            "name": summary["name"],
            "sizeLabel": summary["sizeLabel"],
            "quantization": summary["quantization"],
            "quantizedBy": summary["quantizedBy"],
            "contextLength": summary["contextLength"],
            "chatTemplateSha256": summary["chatTemplateSha256"],
            "chatTemplateChars": summary["chatTemplateChars"],
            "tensorTypes": summary["tensorTypes"],
            "estimatedParameters": summary["estimatedParameters"],
        }
    except Exception as error:  # a broken file is evidence too
        return {"probeError": f"{type(error).__name__}: {error}"}


def main() -> int:
    files = []
    seen = set()
    for root in ROOTS:
        folder = pathlib.Path(root)
        if not folder.exists():
            files.append({"root": root, "missing": True})
            continue
        for path in sorted(folder.rglob("*.gguf")):
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            entry = {
                "path": resolved,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "probe": probe(path),
            }
            files.append(entry)
            print(f"{entry['sha256'][:12]} {entry['bytes']:>12} {path.name}", flush=True)
    report = {
        "roots": ROOTS,
        "note": "read-only inventory; weights stay outside Git",
        "files": files,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{sum(1 for f in files if 'sha256' in f)} GGUF files -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
