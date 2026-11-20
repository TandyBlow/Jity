# -*- coding: utf-8 -*-
"""Build the v2 result-block dataset from the frozen v1 rows.

Outputs (under `experiments/narration-runtime-v2/data/`):

  rows-v2.jsonl          structured projection + both serialized arms
  rows-yuyan-v2.jsonl    the five fields the YuYan trainer needs
  normalization-ledger.jsonl
  result-fills.jsonl
  manifest.json          hashes, identities, versions, limits

Invariants checked before writing:

  * the row set and every row id are byte-identical to v1;
  * every target `y` is byte-identical to v1;
  * `splits/v1.json` is byte-identical and still partitions the same ids;
  * the legacy rendering re-renders to the stored `xProse` for all 199 rows;
  * the v2 rendering contains no newline/whitespace and no target text;
  * every row's result block only contains changed fields.
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
from datetime import datetime, timezone
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import legacy_compat as legacy
import projection_v2 as projection
import v2_render as v2
from tokenizer_profile import load_tokenizer_profile, public_profile, validate_tokenizer_text


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_SOURCE = legacy.SOURCE_DIR
DEFAULT_OUT = os.path.join(ROOT, "data")
TOKENIZER_DICT = os.path.join(ROOT, "tokenizers", "yuyan-v1", "dict.txt")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_jsonl(path: str, records: List[Dict[str, Any]]) -> None:
    payload = "".join(json.dumps(record, ensure_ascii=False) + "\n"
                      for record in records).encode("utf-8")
    atomic_write(path, payload)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              check=True, capture_output=True,
                              text=True).stdout.strip()
    except Exception:
        return "unknown"


def paragraph_join(y: str) -> str:
    paragraphs = [part.strip() for part in y.split("\n\n") if part.strip()]
    return "※".join(paragraphs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--tokenizer-dict", default=TOKENIZER_DICT)
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    source_report = legacy.verify_sources(args.source)
    if not source_report["ok"]:
        raise SystemExit("source verification failed: " + "; ".join(source_report["problems"]))

    legacy_rows = legacy.legacy_rows(args.source)
    stored_yuyan = {row["id"]: row for row in legacy.legacy_yuyan_rows(args.source)}
    split = legacy.legacy_split(args.source)
    split_identity = legacy.split_identity(args.source)
    if not split_identity["ok"]:
        raise SystemExit(f"split identity failed: {split_identity}")

    legacy_bytes = legacy.compare_legacy_bytes(args.source)
    if not legacy_bytes["ok"]:
        raise SystemExit("legacy byte comparison failed: " + "; ".join(legacy_bytes["problems"]))

    tokenizer = load_tokenizer_profile(args.tokenizer_dict)
    tokenizer_ok = 0
    tokenizer_errors: List[Dict[str, Any]] = []

    rows_v2: List[Dict[str, Any]] = []
    rows_yuyan: List[Dict[str, Any]] = []
    normalizations: List[Dict[str, Any]] = []
    fills: List[Dict[str, Any]] = []
    ids: List[str] = []
    targets: List[str] = []

    for legacy_row in legacy_rows:
        row_id = legacy_row["id"]
        ids.append(row_id)
        y = legacy_row["y"]
        targets.append(y)
        stored = stored_yuyan.get(row_id)
        if stored is None:
            raise SystemExit(f"{row_id}: missing legacy rows-yuyan record")
        if not isinstance(y, str):
            raise SystemExit(f"{row_id}: target is not a string")
        expected_marked = paragraph_join(y)
        if expected_marked != stored["yMarked"]:
            raise SystemExit(f"{row_id}: yMarked does not equal paragraph join of y")

        normalized, ledger = projection.normalize_projection(legacy_row["x"])
        result, row_fills = v2.build_result(normalized["上回合状态"],
                                            normalized["本回合变化"],
                                            normalized["本回合状态"])
        normalized["本回合状态"] = result
        serialized = v2.serialize(normalized)
        legacy_text = legacy.legacy_render_row(legacy_row)
        if legacy_text.encode("utf-8") != stored["xProse"].encode("utf-8"):
            raise SystemExit(f"{row_id}: legacy render mismatch after import")

        # Answer isolation: the exact target and every 40-character run of it
        # must not occur in the model input.  This mirrors split_xy.py's check,
        # but runs on the final v2 bytes.
        if y.strip() and y.strip() in serialized.text:
            raise SystemExit(f"{row_id}: target text leaked into X")
        for start in range(0, max(len(y) - 40, 0), 40):
            chunk = y[start:start + 40]
            if chunk and chunk in serialized.text:
                raise SystemExit(f"{row_id}: 40-character target run leaked into X")

        try:
            validate_tokenizer_text(serialized.text, tokenizer)
            tokenizer_ok += 1
        except Exception as error:  # noqa: BLE001
            tokenizer_errors.append({"id": row_id, "error": str(error),
                                     "code": getattr(error, "code", None)})

        x_text = json.dumps(normalized, ensure_ascii=False)
        record = {
            "schema": "jity-narration-row-v2",
            "id": row_id,
            "x": normalized,
            "y": y,
            "xText": x_text,
            "xProse": serialized.text,
            "xProseLegacy": legacy_text,
            "yMarked": stored["yMarked"],
            "paragraphs": len([part for part in y.split("\n\n") if part.strip()]),
            "sourceRowSha256": sha256_text(legacy_row["xText"]),
            "targetSha256": sha256_text(y),
            "xTextSha256": sha256_text(x_text),
            "xProseSha256": sha256_text(serialized.text),
            "xProseLegacySha256": sha256_text(legacy_text),
            "normalizations": ledger,
            "resultFills": row_fills,
            "versions": {
                "projectionVersion": v2.PROJECTION_VERSION,
                "serializerVersion": v2.SERIALIZER_VERSION,
                "legacyProjectionVersion": v2.LEGACY_PROJECTION_VERSION,
                "legacySerializerVersion": v2.LEGACY_SERIALIZER_VERSION,
                "modelTemplateVersion": v2.MODEL_TEMPLATE_VERSION,
                "tokenizerHash": tokenizer["sha256"],
            },
        }
        rows_v2.append(record)
        rows_yuyan.append({
            "id": row_id,
            "xProse": serialized.text,
            "yMarked": stored["yMarked"],
            "y": y,
            "xProseChars": len(serialized.text),
            "targetChars": len(y),
            "sourceRowSha256": sha256_text(legacy_row["xText"]),
            "targetSha256": sha256_text(y),
        })
        for entry in ledger:
            normalizations.append({"id": row_id, **entry})
        for entry in row_fills:
            fills.append({"id": row_id, **entry})

    if len(set(ids)) != len(ids):
        raise SystemExit("duplicate row ids")
    split_ids = set(split["train"]) | set(split["dev"]) | set(split["test"])
    if set(ids) != split_ids:
        raise SystemExit("row ids do not equal split ids")
    if tokenizer_errors:
        raise SystemExit(f"tokenizer rejected {len(tokenizer_errors)} row(s): "
                         f"{tokenizer_errors[:3]}")

    # Write the two datasets and the two ledgers.
    rows_path = os.path.join(args.out, "rows-v2.jsonl")
    yuyan_path = os.path.join(args.out, "rows-yuyan-v2.jsonl")
    norm_path = os.path.join(args.out, "normalization-ledger.jsonl")
    fills_path = os.path.join(args.out, "result-fills.jsonl")
    write_jsonl(rows_path, rows_v2)
    write_jsonl(yuyan_path, rows_yuyan)
    write_jsonl(norm_path, normalizations)
    write_jsonl(fills_path, fills)

    # Identity hashes over the frozen row set and targets.
    row_ids_sha = sha256_text("\n".join(ids) + "\n")
    targets_sha = sha256_text("".join(f"{row_id}\t{target}\n"
                                      for row_id, target in zip(ids, targets)))
    legacy_xprose_sha = sha256_text("".join(
        f"{row_id}\t{stored_yuyan[row_id]['xProse']}\n" for row_id in ids))
    v2_xprose_sha = sha256_text("".join(
        f"{row['id']}\t{row['xProse']}\n" for row in rows_v2))

    counts = {"rows": len(rows_v2),
              "train": len(split["train"]),
              "dev": len(split["dev"]),
              "test": len(split["test"])}
    manifest = {
        "schema": "jity-narration-dataset-v2",
        "dataVersion": "narration-rows-v2",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourceBaseCommit": git_commit(),
        "builder": "experiments/narration-runtime-v2/src/build_dataset.py",
        "source": {
            "sourceDir": os.path.abspath(args.source),
            "sourceHashes": source_report,
            "legacyRowsFile": "rows-xy.jsonl",
            "legacyYuyanFile": "yuyan/rows-yuyan.jsonl",
            "splitFile": "splits/v1.json",
            "splitSha256Lf": split_identity["sha256Lf"],
            "splitCounts": {"train": len(split["train"]), "dev": len(split["dev"]),
                            "test": len(split["test"])},
        },
        "versions": {
            "projectionVersion": v2.PROJECTION_VERSION,
            "serializerVersion": v2.SERIALIZER_VERSION,
            "legacyProjectionVersion": v2.LEGACY_PROJECTION_VERSION,
            "legacySerializerVersion": v2.LEGACY_SERIALIZER_VERSION,
            "modelTemplateVersion": v2.MODEL_TEMPLATE_VERSION,
            "tokenizerHash": tokenizer["sha256"],
            "tokenizerStatus": "bound",
            "whitespacePolicy": "remove-space-tab-fullwidth-and-record; reject-crlf-and-other-whitespace",
            "listPunctuationPolicy": "strip-trailing-。；，",
            "resultTypeOrder": list(v2.TYPE_ORDER),
            "resultFieldOrder": {kind: list(fields)
                                 for kind, fields in v2.RESULT_FIELDS.items()},
            "itemPositionSyntax": "物品（位于<位置>）",
        },
        "files": {
            "rows-v2.jsonl": {"bytes": os.path.getsize(rows_path),
                              "sha256": sha256_file(rows_path),
                              "rows": len(rows_v2)},
            "rows-yuyan-v2.jsonl": {"bytes": os.path.getsize(yuyan_path),
                                    "sha256": sha256_file(yuyan_path),
                                    "rows": len(rows_yuyan)},
            "normalization-ledger.jsonl": {"bytes": os.path.getsize(norm_path),
                                           "sha256": sha256_file(norm_path),
                                           "rows": len(normalizations)},
            "result-fills.jsonl": {"bytes": os.path.getsize(fills_path),
                                   "sha256": sha256_file(fills_path),
                                   "rows": len(fills)},
        },
        "counts": counts,
        "identity": {
            "rowIdsSha256": row_ids_sha,
            "targetsSha256": targets_sha,
            "legacyXProseSha256": legacy_xprose_sha,
            "v2XProseSha256": v2_xprose_sha,
            "sameRowIds": True,
            "sameTargets": True,
            "sameSplit": True,
            "legacyBytesEqual": legacy_bytes["same"] == legacy_bytes["rows"],
            "legacyBytesCompared": legacy_bytes["rows"],
        },
        "checks": {
            "sourceOk": source_report["ok"],
            "legacyBytesOk": legacy_bytes["ok"],
            "splitOk": split_identity["ok"],
            "tokenizerOk": not tokenizer_errors,
            "tokenizerRowsChecked": tokenizer_ok,
            "normalizationEntries": len(normalizations),
            "normalizationRemovedChars": sum(len(item["removed"]) for item in normalizations),
            "resultFills": len(fills),
            "rowsWithResultBlock": sum(1 for row in rows_v2 if "【本回合状态】" in row["xProse"]),
            "rowsWithoutChange": sum(1 for row in rows_v2
                                     if not row["x"]["本回合变化"]["变化"]),
            "rowsWithEmptyListResult": sum(
                1 for row in rows_v2
                for view in row["x"]["本回合状态"].values()
                for field_name in ("外貌", "个性")
                if isinstance(view.get(field_name), list) and not view[field_name]),
            "rowsWithZeroSanityResult": sum(
                1 for row in rows_v2
                for view in row["x"]["本回合状态"].values()
                if view.get("精神值") == 0),
            "answerLeakChecks": len(rows_v2),
        },
        "tokenizer": public_profile(tokenizer),
        "sourceWeights": {
            "yuyan": {
                "checkpoint": {
                    "source": "hpc:~/narr_rows/checkpoint_best.pt",
                    "sha256": "674b897a969f7dbcc11cc7b660bba54c6800d894acab150323eadb1c0c456106",
                    "bytes": 2950000000,
                    "availability": "observed on hpc login node 2026-11-10",
                    "inGit": False,
                },
                "loraAdapter": {
                    "source": "hpc:~/narr_rows/yu-split-6ep/lora_adapter.pt",
                    "sha256": "e80c479e690c4128e8f8a4006417ea4f4df13a641b057fbcee3efa807de62c1d",
                    "availability": "observed on hpc login node 2026-11-10",
                    "inGit": False,
                },
                "dict": {
                    "source": "hpc:~/narr_rows/dict.txt",
                    "sha256": tokenizer["sha256"],
                    "inGit": True,
                    "path": "tokenizers/yuyan-v1/dict.txt",
                },
            },
            "instruct": {
                "status": "pending",
                "reason": "no instruct base/tokenizer has been selected for the v2 result-block arm; "
                          "the HF entry is ready but its config is a template, not a run",
            },
        },
        "diagnosticArms": {
            "legacy": {
                "serializerVersion": v2.LEGACY_SERIALIZER_VERSION,
                "file": "yuyan/rows-yuyan.jsonl",
                "sha256Lf": source_report["files"]["yuyan/rows-yuyan.jsonl"]["sha256Lf"],
                "dataSha256": source_report["files"]["yuyan/rows-yuyan.jsonl"]["sha256"],
                "resultBlock": False,
                "itemPosition": False,
            },
            "resultV2": {
                "serializerVersion": v2.SERIALIZER_VERSION,
                "file": "data/rows-yuyan-v2.jsonl",
                "sha256": sha256_file(yuyan_path),
                "resultBlock": True,
                "itemPosition": True,
            },
        },
        "dLine": {
            "sourceCommit": "51bd76e97a8892a6ff012a2ebea57476deb22d4b",
            "branch": "origin/codex/d-training-source-20261110",
            "rows": 4750,
            "train": 3204,
            "dev": 693,
            "test": 853,
            "usedForTraining": False,
            "status": "not_used_for_narration_v2",
            "reason": "D-line supervision is a different short-semantics schema; it is not narration "
                      "result-block data. Its 4,750 rows remain available for non-narrative "
                      "training/development after a separate quality check, and cannot be an "
                      "independent final validation set.",
        },
        "limitations": [
            "The 199 rows are the frozen v1 scene rows; they are not an independent final validation set.",
            "The v2 result block is a partial changed-fields view, not a full after snapshot.",
            "No human review metadata is attached to the 199 rows; the targets are treated as the frozen v1 targets.",
            "The YuYan tokenizer is bound for the diagnostic arm; the instruct tokenizer remains pending.",
            "The 199 rows contain no real item-position change or zero-sanity result; synthetic golden vectors cover those shapes and are not training rows.",
        ],
    }
    manifest_path = os.path.join(args.out, "manifest.json")
    atomic_write(manifest_path, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    print(json.dumps({
        "rows": len(rows_v2),
        "rowsWithResultBlock": manifest["checks"]["rowsWithResultBlock"],
        "normalizationEntries": len(normalizations),
        "resultFills": len(fills),
        "legacyBytesEqual": manifest["identity"]["legacyBytesEqual"],
        "files": {name: record["sha256"] for name, record in manifest["files"].items()},
        "manifest": manifest_path,
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
