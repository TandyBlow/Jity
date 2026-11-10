# -*- coding: utf-8 -*-
"""Copy one lane-10 HPC result directory into this experiment.

No network and no HPC access: lane 10 fetches the files, this only verifies the
recorded hashes and moves the evidence next to the analysis. It refuses to
overwrite a non-empty destination unless --force is given.

    python -X utf8 src/ingest_result.py \
      --source ../../results/product/hpc-results/12-best-of-n-b01-v2 \
      --batch b01-template-v2
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.abspath(os.path.join(HERE, ".."))


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--dest", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = os.path.abspath(args.source)
    dest = os.path.abspath(args.dest or os.path.join(EXP, "results", args.batch))
    record_path = os.path.join(source, "record.json")
    if not os.path.isfile(record_path):
        raise SystemExit(f"record.json missing in {source}")
    with io.open(record_path, encoding="utf-8") as handle:
        record = json.load(handle)
    files = record.get("outputs", {}).get("files") or {}
    if "raw.jsonl" not in files or "env.json" not in files:
        raise SystemExit("record.outputs.files lacks raw.jsonl/env.json; refusing a partial copy")

    if os.path.isdir(dest) and os.listdir(dest) and not args.force:
        raise SystemExit(f"destination is not empty: {dest} (use --force to replace)")

    os.makedirs(dest, exist_ok=True)
    copied = []
    for name, expected in files.items():
        src = os.path.join(source, name)
        if not os.path.isfile(src):
            raise SystemExit(f"record names a missing file: {src}")
        actual = sha256(src)
        if actual != expected:
            raise SystemExit(f"hash mismatch {name}: {actual} != {expected}")
        dst_name = "hpc-record.json" if name == "record.json" else name
        shutil.copy2(src, os.path.join(dest, dst_name))
        copied.append((name, actual))

    # Keep the full record as evidence even when 10 named it separately.
    record_copy = os.path.join(dest, "hpc-record.json")
    if not os.path.isfile(record_copy):
        shutil.copy2(record_path, record_copy)

    batch = json.load(io.open(os.path.join(EXP, "configs", f"{args.batch}.json"), encoding="utf-8"))
    expected_calls = len(batch["caseIds"]) * len(batch["seeds"])
    raw_lines = sum(1 for _ in io.open(os.path.join(dest, "raw.jsonl"), encoding="utf-8"))
    if raw_lines != expected_calls:
        raise SystemExit(f"raw rows {raw_lines} != expected {expected_calls}")

    print(json.dumps({
        "batch": args.batch,
        "dest": dest,
        "jobId": record.get("jobId"),
        "calls": raw_lines,
        "files": {name: digest for name, digest in copied},
        "slurm": record.get("slurm"),
        "record": record_copy,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
