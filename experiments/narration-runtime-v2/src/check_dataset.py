# -*- coding: utf-8 -*-
"""CPU checks for the v2 narration dataset.

This is the small, fast verification the lane runs after conversion.  It does
not need a model, GPU or the cluster.  Every check either passes on the current
files or prints the exact row/path that failed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import legacy_compat as legacy
import projection_v2 as projection
import v2_render as v2
from tokenizer_profile import load_tokenizer_profile, validate_tokenizer_text


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
DEFAULT_DATA = os.path.join(ROOT, "data")
DEFAULT_SOURCE = legacy.SOURCE_DIR
DEFAULT_TOKENIZER = os.path.join(ROOT, "tokenizers", "yuyan-v1", "dict.txt")


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=DEFAULT_DATA)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--tokenizer", default=DEFAULT_TOKENIZER)
    args = parser.parse_args()

    problems: List[str] = []
    checks: Dict[str, Any] = {}

    manifest_path = os.path.join(args.data, "manifest.json")
    with io.open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    rows = read_jsonl(os.path.join(args.data, "rows-v2.jsonl"))
    yuyan_rows = read_jsonl(os.path.join(args.data, "rows-yuyan-v2.jsonl"))
    source_rows = legacy.legacy_rows(args.source)
    stored_yuyan = {row["id"]: row for row in legacy.legacy_yuyan_rows(args.source)}
    split = legacy.legacy_split(args.source)
    tokenizer = load_tokenizer_profile(args.tokenizer)

    def check(name: str, condition: bool, detail: Any = None) -> None:
        checks[name] = {"ok": bool(condition), "detail": detail}
        if not condition:
            problems.append(f"{name}: {detail}")

    source_report = legacy.verify_sources(args.source)
    check("sourceHashes", source_report["ok"], source_report["problems"])
    legacy_bytes = legacy.compare_legacy_bytes(args.source)
    check("legacyBytes", legacy_bytes["ok"], legacy_bytes["problems"])
    split_identity = legacy.split_identity(args.source)
    check("splitIdentity", split_identity["ok"], split_identity)
    check("splitHash", split_identity["sha256Lf"] == manifest["source"]["splitSha256Lf"],
          {"actual": split_identity["sha256Lf"],
           "manifest": manifest["source"]["splitSha256Lf"]})

    check("rowCount", len(rows) == 199 and len(yuyan_rows) == 199,
          {"rows": len(rows), "yuyanRows": len(yuyan_rows)})
    check("rowSet", [row["id"] for row in rows] == [row["id"] for row in source_rows],
          "row order/id changed")
    check("yuyanRowSet", [row["id"] for row in yuyan_rows] == [row["id"] for row in rows],
          "rows-yuyan-v2 ids/order changed")

    split_ids = set(split["train"]) | set(split["dev"]) | set(split["test"])
    check("splitCoversRows", split_ids == {row["id"] for row in rows},
          {"missing": sorted({row["id"] for row in rows} - split_ids),
           "extra": sorted(split_ids - {row["id"] for row in rows})})
    check("splitCounts", manifest["counts"] == {
        "rows": 199, "train": len(split["train"]), "dev": len(split["dev"]),
        "test": len(split["test"])}, manifest["counts"])

    target_mismatches: List[str] = []
    legacy_mismatches: List[str] = []
    v2_mismatches: List[str] = []
    whitespace: List[str] = []
    leaks: List[str] = []
    result_missing: List[str] = []
    result_extra: List[str] = []
    item_position_missing: List[str] = []
    tokenizer_failures: List[Dict[str, Any]] = []
    normalization_missing: List[str] = []
    result_fills: List[Dict[str, Any]] = []
    result_mismatches: List[str] = []

    for row, yuyan_row, source in zip(rows, yuyan_rows, source_rows):
        row_id = row["id"]
        if row["y"].encode("utf-8") != source["y"].encode("utf-8"):
            target_mismatches.append(row_id)
        if row["yMarked"].encode("utf-8") != stored_yuyan[row_id]["yMarked"].encode("utf-8"):
            target_mismatches.append(f"{row_id}:yMarked")
        if yuyan_row["y"].encode("utf-8") != row["y"].encode("utf-8"):
            target_mismatches.append(f"{row_id}:yuyan-y")
        expected_legacy = legacy.legacy_render_row(source)
        if row["xProseLegacy"].encode("utf-8") != expected_legacy.encode("utf-8"):
            legacy_mismatches.append(row_id)
        if expected_legacy.encode("utf-8") != stored_yuyan[row_id]["xProse"].encode("utf-8"):
            legacy_mismatches.append(f"{row_id}:stored")
        serialized = v2.serialize(row["x"])
        if serialized.text.encode("utf-8") != row["xProse"].encode("utf-8"):
            v2_mismatches.append(row_id)
        if serialized.text.encode("utf-8") != yuyan_row["xProse"].encode("utf-8"):
            v2_mismatches.append(f"{row_id}:yuyan")
        if any(char in "\r\n" or char.isspace() for char in row["xProse"]):
            whitespace.append(row_id)
        target = row["y"]
        if target.strip() and target.strip() in row["xProse"]:
            leaks.append(row_id)
        for start in range(0, max(len(target) - 40, 0), 40):
            chunk = target[start:start + 40]
            if chunk and chunk in row["xProse"]:
                leaks.append(f"{row_id}:40@{start}")
                break
        has_result = bool(row["x"]["本回合状态"])
        if has_result != ("【本回合状态】" in row["xProse"]):
            result_missing.append(row_id)
        if not has_result and "【本回合状态】" in row["xProse"]:
            result_extra.append(row_id)
        if has_result != ("【本回合状态】" in row["xProseLegacy"]):
            # The legacy arm must not contain the result block.
            if "【本回合状态】" in row["xProseLegacy"]:
                result_extra.append(f"{row_id}:legacy")
        for name in row["x"]["上回合状态"].get("物品", {}):
            marker = f"{name}（位于"
            if marker not in row["xProse"]:
                item_position_missing.append(f"{row_id}:{name}")
        try:
            validate_tokenizer_text(row["xProse"], tokenizer)
        except Exception as error:  # noqa: BLE001
            tokenizer_failures.append({"id": row_id, "error": str(error),
                                       "code": getattr(error, "code", None)})
        if not row.get("normalizations") and row["x"]["本回合变化"]["时间推进"] != \
                source["x"]["本回合变化"]["时间推进"]:
            normalization_missing.append(row_id)
        rebuilt, fills = v2.build_result(row["x"]["上回合状态"],
                                         row["x"]["本回合变化"],
                                         row["x"]["本回合状态"])
        if rebuilt != row["x"]["本回合状态"]:
            result_mismatches.append(row_id)
        if fills:
            result_fills.append({"id": row_id, "fills": fills})

    check("targetsUnchanged", not target_mismatches, target_mismatches)
    check("legacyBytesUnchanged", not legacy_mismatches, legacy_mismatches)
    check("v2RenderDeterministic", not v2_mismatches, v2_mismatches)
    check("noWhitespace", not whitespace, whitespace)
    check("noAnswerLeak", not leaks, leaks)
    check("resultBlockPresence", not result_missing and not result_extra,
          {"missing": result_missing, "extra": result_extra})
    check("itemPositionsRendered", not item_position_missing, item_position_missing)
    check("tokenizerEncodable", not tokenizer_failures, tokenizer_failures)
    check("normalizationLedger", not normalization_missing, normalization_missing)
    check("resultIdempotent", not result_mismatches, result_mismatches)
    check("realRowsNeedNoFill", not result_fills, result_fills)

    # Manifest file hashes must match the bytes on disk.
    for name, record in manifest["files"].items():
        path = os.path.join(args.data, name)
        actual = sha256_file(path)
        check(f"fileHash:{name}", actual == record["sha256"],
              {"actual": actual, "manifest": record["sha256"]})
    check("manifestIdentity", manifest["identity"]["sameRowIds"]
          and manifest["identity"]["sameTargets"]
          and manifest["identity"]["sameSplit"]
          and manifest["identity"]["legacyBytesEqual"],
          manifest["identity"])
    check("manifestVersions", manifest["versions"]["projectionVersion"] == v2.PROJECTION_VERSION
          and manifest["versions"]["serializerVersion"] == v2.SERIALIZER_VERSION,
          manifest["versions"])

    summary = {
        "ok": not problems,
        "problems": problems,
        "checks": checks,
        "counts": {"rows": len(rows), "train": len(split["train"]),
                   "dev": len(split["dev"]), "test": len(split["test"])},
        "resultRows": sum(1 for row in rows if row["x"]["本回合状态"]),
        "emptyResultRows": sum(1 for row in rows if not row["x"]["本回合状态"]),
        "normalizationEntries": sum(len(row.get("normalizations", [])) for row in rows),
        "itemLinesChecked": sum(len(row["x"]["上回合状态"].get("物品", {})) for row in rows),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
