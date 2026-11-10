#!/usr/bin/env python
"""Freeze the lane-10 v2 contract into this lane's goldens.

The source of truth is the actual trained arm:
`experiments/narration-runtime-v2` at the recorded commit. This script copies
the public golden vectors and the 199 trained projections, verifies their
hashes against lane 10's manifests, and records the expected output hashes.
The TypeScript serializer is then tested byte-for-byte against this freeze.

Usage:
  python -X utf8 frontend/scripts/parallel-input/sync_v2_contract.py
  python -X utf8 ... --source <narration-runtime-v2> --out <goldens/runtime-v2>
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile

DEFAULT_SOURCE = (
    "D:/others/Jity/.local/parallel-local-game/worktrees/10-training/"
    "experiments/narration-runtime-v2"
)
DEFAULT_OUT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "src", "lib", "world-engine", "local",
    "narration-input", "goldens", "runtime-v2",
))


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with io.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: str, payload: bytes) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(path: str, value) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def write_jsonl(path: str, rows) -> None:
    atomic_write(path, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode("utf-8"))


def percentile(sorted_values, fraction: float) -> int:
    return sorted_values[max(0, -(-int(fraction * len(sorted_values)) // 1) - 1)]


def source_commit(source: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", source, "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()
    source = os.path.abspath(args.source)
    out = os.path.abspath(args.out)

    data_manifest_path = os.path.join(source, "data", "manifest.json")
    golden_manifest_path = os.path.join(source, "golden", "manifest.json")
    vectors_path = os.path.join(source, "golden", "vectors.jsonl")
    rows_path = os.path.join(source, "data", "rows-v2.jsonl")
    yuyan_rows_path = os.path.join(source, "data", "rows-yuyan-v2.jsonl")
    for path in (data_manifest_path, golden_manifest_path, vectors_path, rows_path, yuyan_rows_path):
        if not os.path.exists(path):
            raise SystemExit(f"missing source file: {path}")

    data_manifest = json.load(io.open(data_manifest_path, encoding="utf-8"))
    golden_manifest = json.load(io.open(golden_manifest_path, encoding="utf-8"))

    checks = {}
    for name, path, expected in [
        ("vectors.jsonl", vectors_path, golden_manifest["files"]["vectors.jsonl"]["sha256"]),
        ("rows-v2.jsonl", rows_path, data_manifest["files"]["rows-v2.jsonl"]["sha256"]),
        ("rows-yuyan-v2.jsonl", yuyan_rows_path, data_manifest["files"]["rows-yuyan-v2.jsonl"]["sha256"]),
        ("data/manifest.json", data_manifest_path, golden_manifest["dataManifestSha256"]),
    ]:
        actual = sha256_file(path)
        checks[name] = {"expected": expected, "actual": actual, "ok": actual == expected}
        if not checks[name]["ok"]:
            raise SystemExit(f"{name}: hash {actual} != registered {expected}")

    rows = [json.loads(line) for line in io.open(rows_path, encoding="utf-8") if line.strip()]
    yuyan = [json.loads(line) for line in io.open(yuyan_rows_path, encoding="utf-8") if line.strip()]
    if len(rows) != 199 or len(yuyan) != 199:
        raise SystemExit(f"expected 199 rows, got {len(rows)} / {len(yuyan)}")
    by_id = {row["id"]: row for row in yuyan}

    projections = []
    index = []
    v2_chars, v2_bytes, legacy_chars = [], [], []
    for row in rows:
        row_id = row["id"]
        if row_id not in by_id:
            raise SystemExit(f"{row_id} missing from rows-yuyan-v2.jsonl")
        xprose = by_id[row_id]["xProse"]
        encoded = xprose.encode("utf-8")
        canonical = json.dumps(row["x"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        projections.append({"id": row_id, "x": row["x"]})
        index.append({
            "id": row_id,
            "xProseSha256": hashlib.sha256(encoded).hexdigest(),
            "xProseChars": len(xprose),
            "xProseUtf8Bytes": len(encoded),
            "xSha256": hashlib.sha256(canonical).hexdigest(),
            "legacySha256": hashlib.sha256(row["xProseLegacy"].encode("utf-8")).hexdigest(),
            "legacyChars": len(row["xProseLegacy"]),
        })
        v2_chars.append(len(xprose))
        v2_bytes.append(len(encoded))
        legacy_chars.append(len(row["xProseLegacy"]))
        if row.get("xProseLegacySha256") and row.get("xProseSha256"):
            if hashlib.sha256(encoded).hexdigest() != row["xProseSha256"]:
                raise SystemExit(f"{row_id}: xProse hash disagrees with row record")

    v2_chars.sort()
    v2_bytes.sort()
    legacy_chars.sort()
    stats = {
        "version": "narration-input-length-stats-v1",
        "population": "lane-10 rows-v2.jsonl xProse (yuyan-prose-result-v2)",
        "rowCount": len(v2_chars),
        "v2": {
            "chars": {"min": v2_chars[0], "p50": percentile(v2_chars, 0.5), "p75": percentile(v2_chars, 0.75), "max": v2_chars[-1]},
            "utf8Bytes": {"min": v2_bytes[0], "p50": percentile(v2_bytes, 0.5), "p75": percentile(v2_bytes, 0.75), "max": v2_bytes[-1]},
        },
        "legacy": {
            "chars": {"min": legacy_chars[0], "p50": percentile(legacy_chars, 0.5), "p75": percentile(legacy_chars, 0.75), "max": legacy_chars[-1]},
        },
        "note": "Character counts are Unicode code points (Python len), not tokenizer tokens.",
    }

    commit = source_commit(source)
    atomic_write(os.path.join(out, "vectors.jsonl"), io.open(vectors_path, "rb").read())
    write_json(os.path.join(out, "golden-manifest.json"), golden_manifest)
    write_jsonl(os.path.join(out, "train-projections.jsonl"), projections)
    write_json(os.path.join(out, "train-rows-index.json"), {
        "source": {
            "root": source,
            "commit": commit,
            "files": checks,
            "dataVersion": data_manifest["dataVersion"],
            "versions": data_manifest["versions"],
        },
        "rows": index,
    })
    write_json(os.path.join(out, "length-stats.json"), stats)
    write_json(os.path.join(out, "source.json"), {
        "root": source,
        "commit": commit,
        "dataVersion": data_manifest["dataVersion"],
        "versions": data_manifest["versions"],
        "tokenizer": data_manifest["tokenizer"],
        "files": checks,
    })
    print(f"{out}: vectors + {len(projections)} projections + index + length stats")
    print(f"source commit {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
