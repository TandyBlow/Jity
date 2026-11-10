#!/usr/bin/env python
"""Build the legacy byte goldens from the real narration dataset.

The expected bytes come from the source Python converter
(`yuyan/convert_yuyan.py::render_row`), not from the TypeScript port. The
script also checks every recomputed row against the already stored `xProse`,
so a stale or edited dataset fails loudly.

Usage:
  python -X utf8 frontend/scripts/parallel-input/build_legacy_goldens.py
  python -X utf8 ... --dataset-dir <narration-dataset-v1> --out-dir <goldens>

The output contains the structured X and the expected xProse for a
representative subset, plus a SHA-256 manifest for all rows. Narratives (`y`)
are never written to the projection or the golden input; the expected output
is only a test oracle.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

DEFAULT_DATASET = "D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1"
DEFAULT_OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "lib", "world-engine", "local", "narration-input", "goldens"))
REPRESENTATIVE = ["row-0002", "row-0006", "row-0008", "row-0095"]


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with io.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_converter(dataset_dir: str):
    path = os.path.join(dataset_dir, "yuyan", "convert_yuyan.py")
    spec = importlib.util.spec_from_file_location("parallel_input_convert_yuyan", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_rows(rows: list[dict]) -> list[str]:
    selected = [row["id"] for row in rows if row["id"] in REPRESENTATIVE]
    seen = set(selected)
    op_order = ["位置", "精神值", "解除外貌", "新增外貌", "解除个性", "新增个性", "完成任务", "新增小任务"]
    for op in op_order:
        for row in rows:
            ops = row["x"].get("本回合变化", {}).get("变化", {})
            if any(op in value for value in ops.values()) and row["id"] not in seen:
                selected.append(row["id"])
                seen.add(row["id"])
                break
    first_item = next((row["id"] for row in rows if any(
        name in row["x"].get("上回合状态", {}).get("物品", {})
        for name in row["x"].get("本回合变化", {}).get("变化", {})
    )), None)
    if first_item and first_item not in seen:
        selected.append(first_item)
        seen.add(first_item)
    first_location = next((row["id"] for row in rows if any(
        name in row["x"].get("上回合状态", {}).get("地点", {})
        for name in row["x"].get("本回合变化", {}).get("变化", {})
    )), None)
    if first_location and first_location not in seen:
        selected.append(first_location)
        seen.add(first_location)
    # Fill deterministically to 30 rows, evenly spaced, without dropping the
    # explicit cases above.
    index = 0
    while len(selected) < 30 and index < len(rows):
        row_id = rows[index]["id"]
        if row_id not in seen:
            selected.append(row_id)
            seen.add(row_id)
        index += max(1, len(rows) // 30)
    return [row["id"] for row in rows if row["id"] in seen]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", default=DEFAULT_DATASET)
    parser.add_argument("--out-dir", default=DEFAULT_OUT)
    args = parser.parse_args()
    dataset = os.path.abspath(args.dataset_dir)
    out_dir = os.path.abspath(args.out_dir)
    converter = load_converter(dataset)

    xy_path = os.path.join(dataset, "rows-xy.jsonl")
    prose_path = os.path.join(dataset, "yuyan", "rows-yuyan.jsonl")
    with io.open(xy_path, encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    with io.open(prose_path, encoding="utf-8") as handle:
        prose = {record["id"]: record for record in (json.loads(line) for line in handle if line.strip())}
    if len(rows) != len(prose):
        raise SystemExit(f"row count mismatch: {len(rows)} rows, {len(prose)} prose records")

    selected_ids = set(select_rows(rows))
    golden_rows = []
    manifest_rows = []
    for row in rows:
        expected = converter.render_row({"xText": row["xText"], "y": ""})
        stored = prose[row["id"]]["xProse"]
        if expected != stored:
            raise SystemExit(f"{row['id']}: Python render differs from stored xProse")
        encoded = expected.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        manifest_rows.append({
            "id": row["id"],
            "xProseSha256": digest,
            "xProseChars": len(expected),
            "xProseUtf8Bytes": len(encoded),
        })
        if row["id"] in selected_ids:
            golden_rows.append({
                "id": row["id"],
                "x": row["x"],
                "xProse": expected,
                "xProseSha256": digest,
                "xProseChars": len(expected),
                "xProseUtf8Bytes": len(encoded),
            })
    if len(golden_rows) < 30:
        # select_rows is a deterministic filter; if a pathological dataset
        # cannot reach 30, fail instead of silently shipping a thin sample.
        raise SystemExit(f"expected at least 30 representative rows, got {len(golden_rows)}")

    try:
        commit = subprocess.check_output(
            ["git", "-C", dataset, "rev-parse", "HEAD"], text=True,
        ).strip()
    except Exception:
        commit = "unknown"

    meta = {
        "datasetVersion": "narration-dataset-v1",
        "sourceCommit": commit,
        "sourceFiles": {
            "rows-xy.jsonl": sha256_file(xy_path),
            "yuyan/rows-yuyan.jsonl": sha256_file(prose_path),
            "yuyan/convert_yuyan.py": sha256_file(os.path.join(dataset, "yuyan", "convert_yuyan.py")),
            "rows_common.py": sha256_file(os.path.join(dataset, "rows_common.py")),
            "split_xy.py": sha256_file(os.path.join(dataset, "split_xy.py")),
        },
        "rowCount": len(rows),
        "goldenRowCount": len(golden_rows),
        "selection": "explicit known failures + first row per operation + first item/location change + evenly spaced fill",
        "expectedSource": "Python convert_yuyan.render_row on each row's xText",
    }
    os.makedirs(out_dir, exist_ok=True)
    golden = {"meta": meta, "rows": golden_rows}
    manifest = {"meta": meta, "rows": manifest_rows}
    for name, value in (("legacy-rows-v1.json", golden), ("legacy-rows-v1-manifest.json", manifest)):
        target = os.path.join(out_dir, name)
        fd, temp = tempfile.mkstemp(prefix=name + ".", suffix=".tmp", dir=out_dir)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(temp, target)
        print(f"{target}: {os.path.getsize(target)} bytes")
    print(f"rows={len(rows)} golden={len(golden_rows)} commit={commit}")


if __name__ == "__main__":
    main()
