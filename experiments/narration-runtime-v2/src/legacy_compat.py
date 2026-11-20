# -*- coding: utf-8 -*-
"""Load the frozen v1 conversion code and prove the legacy arm is unchanged.

The source directory is read-only for this lane.  We import it by path instead
of copying its functions, so the legacy byte comparison really runs the code
that produced `rows-yuyan.jsonl`.  Each source file is checked against the
LF-normalized SHA-256 registered in the input adapter spec; the checkout may
have CRLF on Windows, so both raw and LF hashes are recorded.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
from typing import Any, Dict, List, Tuple


SOURCE_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "world-components", "narration-dataset-v1"))

REGISTERED_LF_SHA256 = {
    "rows_common.py": "cf87c6a7cf7f9441ad2fe8e77cc21bd6323faa9034e073c5bb3ef34938ff7d64",
    "split_xy.py": "c1160ce76904540b26588463634efa46c4ba314e6bcc458b4365c6113d398022",
    "yuyan/convert_yuyan.py": "dd21a2c4f30b16ffc4d3fc1fbea3ad19c72cacbfda36b91606d504534478d044",
    "rows-xy.jsonl": "b7cc1c1b33f7b3f179c58c2244fe3d532184840be0ef2827ea72d3f71ca62ef2",
    "yuyan/rows-yuyan.jsonl": "645df1b1438c4a388fbb09fb7d71ed99796b33393005dbda528f3d3d8c5db824",
    "README.md": "14f33377005c376a0ebc33c9367b500252886f50b48c4ba9a13760405cad99e1",
    "splits/v1.json": None,  # registered separately by the manifest after first read
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def lf_sha256_file(path: str) -> str:
    with open(path, "rb") as handle:
        return sha256_bytes(handle.read().replace(b"\r\n", b"\n"))


def verify_sources(source_dir: str = SOURCE_DIR) -> Dict[str, Any]:
    report: Dict[str, Any] = {"sourceDir": source_dir, "files": {}, "ok": True,
                              "problems": []}
    for rel, expected in REGISTERED_LF_SHA256.items():
        path = os.path.join(source_dir, rel)
        if not os.path.exists(path):
            report["ok"] = False
            report["problems"].append(f"missing {rel}")
            report["files"][rel] = {"exists": False}
            continue
        raw = sha256_file(path)
        lf = lf_sha256_file(path)
        record = {"exists": True, "sha256": raw, "sha256Lf": lf,
                  "bytes": os.path.getsize(path)}
        if expected is not None and lf != expected:
            report["ok"] = False
            report["problems"].append(
                f"{rel}: LF sha256 {lf} != registered {expected}")
        report["files"][rel] = record
    return report


def _load_module(rel: str, name: str):
    path = os.path.join(SOURCE_DIR, rel)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_convert_module():
    return _load_module(os.path.join("yuyan", "convert_yuyan.py"), "legacy_convert_yuyan")


def load_rows_common():
    return _load_module("rows_common.py", "legacy_rows_common")


def load_split_xy():
    return _load_module("split_xy.py", "legacy_split_xy")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def legacy_rows(source_dir: str = SOURCE_DIR) -> List[Dict[str, Any]]:
    return read_jsonl(os.path.join(source_dir, "rows-xy.jsonl"))


def legacy_yuyan_rows(source_dir: str = SOURCE_DIR) -> List[Dict[str, Any]]:
    return read_jsonl(os.path.join(source_dir, "yuyan", "rows-yuyan.jsonl"))


def legacy_render_row(row: Dict[str, Any]) -> str:
    return load_convert_module().render_row(row)


def legacy_render_state(state: Dict[str, Any]) -> str:
    return load_convert_module().render_state(state)


def legacy_split(source_dir: str = SOURCE_DIR) -> Dict[str, Any]:
    with io.open(os.path.join(source_dir, "splits", "v1.json"), encoding="utf-8") as handle:
        return json.load(handle)


def byte_identity(left: str, right: str) -> bool:
    return left.encode("utf-8") == right.encode("utf-8")


def compare_legacy_bytes(source_dir: str = SOURCE_DIR) -> Dict[str, Any]:
    """Re-render every row with the frozen v1 converter and compare stored bytes."""
    convert = load_convert_module()
    rows = legacy_rows(source_dir)
    stored = {row["id"]: row for row in legacy_yuyan_rows(source_dir)}
    problems: List[str] = []
    comparisons: List[Dict[str, Any]] = []
    for row in rows:
        rendered = convert.render_row(row)
        expected = stored.get(row["id"])
        if expected is None:
            problems.append(f"{row['id']}: missing from rows-yuyan.jsonl")
            continue
        same = rendered.encode("utf-8") == expected["xProse"].encode("utf-8")
        comparisons.append({"id": row["id"], "same": same,
                            "renderedChars": len(rendered),
                            "storedChars": len(expected["xProse"])})
        if not same:
            problems.append(f"{row['id']}: legacy render differs")
    return {"ok": not problems, "rows": len(rows),
            "same": sum(1 for item in comparisons if item["same"]),
            "problems": problems, "comparisons": comparisons}


def split_identity(source_dir: str = SOURCE_DIR) -> Dict[str, Any]:
    split = legacy_split(source_dir)
    rows = legacy_rows(source_dir)
    ids = [row["id"] for row in rows]
    id_set = set(ids)
    covered = set(split["train"]) | set(split["dev"]) | set(split["test"])
    overlap = (set(split["train"]) & set(split["dev"])) | \
              (set(split["train"]) & set(split["test"])) | \
              (set(split["dev"]) & set(split["test"]))
    return {
        "ok": id_set == covered and not overlap,
        "rows": len(rows),
        "train": len(split["train"]),
        "dev": len(split["dev"]),
        "test": len(split["test"]),
        "missingFromSplit": sorted(id_set - covered),
        "extraInSplit": sorted(covered - id_set),
        "overlap": sorted(overlap),
        "sha256Lf": lf_sha256_file(os.path.join(source_dir, "splits", "v1.json")),
    }
