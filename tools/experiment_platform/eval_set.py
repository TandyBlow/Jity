#!/usr/bin/env python3
"""Validate and freeze independent evaluation sets.

Record contract (JSONL, one object per line):
  id          unique within the file
  modality    "semantic" | "narration"
  world       world id, e.g. dragon-raja-free-day
  split       "dev" | "test"
  input       object; modality-specific payload the model receives
  expected    object with non-empty "facts" (list); optional "outcomes"
  forbidden   object; required for test sets, e.g. {"newNames": [], "unsettled": []}
  provenance  object with non-empty "labelSource"; optional humanVerified bool
  source      optional object (evidence file, point id, commit)

`freeze` writes a manifest with a canonical-JSON hash; `check` re-verifies it.
A test set is only independent if its provenance says so and its ids never
appear in a training set (enforced by split_sets.py).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MODALITIES = {"semantic", "narration"}
SPLITS = {"dev", "test"}
HASH_MODE = "canonical-json"


def load_rows(path: Path) -> list[dict]:
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: {exc.msg}") from exc
    return rows


def canonical_hash(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()


def validate_rows(rows: list[dict]) -> list[str]:
    failures = []
    seen = set()
    for idx, row in enumerate(rows, 1):
        where = f"row {idx} ({row.get('id', '?')})"
        for key in ("id", "modality", "world", "split", "input", "expected", "provenance"):
            if key not in row:
                failures.append(f"{where}: missing {key}")
        identity = row.get("id")
        if identity in seen:
            failures.append(f"{where}: duplicate id")
        seen.add(identity)
        if row.get("modality") not in MODALITIES:
            failures.append(f"{where}: modality must be one of {sorted(MODALITIES)}")
        if row.get("split") not in SPLITS:
            failures.append(f"{where}: split must be one of {sorted(SPLITS)}")
        expected = row.get("expected") or {}
        if not isinstance(expected.get("facts"), list) or not expected.get("facts"):
            failures.append(f"{where}: expected.facts must be a non-empty list")
        if "outcomes" in expected and not isinstance(expected["outcomes"], list):
            failures.append(f"{where}: expected.outcomes must be a list")
        provenance = row.get("provenance") or {}
        if not str(provenance.get("labelSource") or "").strip():
            failures.append(f"{where}: provenance.labelSource is required")
        if row.get("split") == "test":
            forbidden = row.get("forbidden")
            if not isinstance(forbidden, dict) or not forbidden:
                failures.append(f"{where}: test row needs a non-empty forbidden object")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "freeze", "check"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--path", required=True)
        cmd.add_argument("--out")
        cmd.add_argument("--manifest")
    args = parser.parse_args(argv)

    path = Path(args.path)
    rows = load_rows(path)
    failures = validate_rows(rows)
    if args.cmd == "validate":
        print(json.dumps({"path": str(path), "rows": len(rows), "failures": failures},
                         ensure_ascii=False, indent=1))
        return 1 if failures else 0
    if args.cmd == "freeze":
        if failures:
            print(json.dumps({"refuse": "invalid rows", "failures": failures}, ensure_ascii=False, indent=1))
            return 1
        manifest = {
            "schema": "jity-eval-set/1",
            "path": str(path).replace("\\", "/"),
            "rows": len(rows),
            "sha256": canonical_hash(rows),
            "hashMode": HASH_MODE,
            "frozenAt": datetime.now(tz=timezone.utc).isoformat(),
        }
        out = Path(args.out) if args.out else path.with_suffix(path.suffix + ".manifest.json")
        out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(manifest, ensure_ascii=False, indent=1))
        return 0
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    actual = canonical_hash(rows)
    ok = manifest.get("sha256") == actual and manifest.get("rows") == len(rows)
    print(json.dumps({"path": str(path), "ok": ok, "declared": str(manifest.get("sha256"))[:12],
                      "actual": actual[:12], "rows": len(rows)}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
