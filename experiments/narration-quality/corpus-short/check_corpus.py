#!/usr/bin/env python3
"""Structural checks for the short-scene corpus.

This script does not judge prose quality or semantic fact coverage. It checks
that every base row keeps the frozen input intact, that derived rows differ
only in a documented time advance, that all material comes from the train split,
and that every row carries the metadata a consumer needs. Fact coverage is
checked by hand in review.md.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import pathlib
import sys
from collections import Counter

DEFAULT_SOURCE_ROOT = pathlib.Path(
    "D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1"
)
SOURCE_COMMIT = "1ab6ca791f97529a7bffed1f4837bf81a28badcb"
MIN_CHARS = 60
MAX_CHARS = 160
KNOWN_CATEGORIES = {
    "no_change",
    "movement",
    "separation",
    "item_change",
    "location_change",
    "appearance_change",
    "personality_change",
    "secret_reveal",
    "task_complete",
    "task_added",
    "sanity_change",
}


def canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", default=str(pathlib.Path(__file__).with_name("rows.jsonl")))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    args = parser.parse_args()

    rows_path = pathlib.Path(args.rows)
    source_root = pathlib.Path(args.source_root)
    source_rows_path = source_root / "rows-xy.jsonl"
    splits_path = source_root / "splits" / "v1.json"

    for path in (rows_path, source_rows_path, splits_path):
        if not path.exists():
            print(f"missing required file: {path}", file=sys.stderr)
            return 2

    raw = rows_path.read_text(encoding="utf-8")
    if "\r" in raw:
        print("rows.jsonl contains CR; expected LF", file=sys.stderr)
        return 2

    source_rows = {
        item["id"]: item
        for item in (json.loads(line) for line in io.open(source_rows_path, encoding="utf-8") if line.strip())
    }
    splits = json.load(io.open(splits_path, encoding="utf-8"))
    split_of = {rid: name for name, ids in splits.items() for rid in ids}

    records = [json.loads(line) for line in raw.splitlines() if line.strip()]
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_sources: set[str] = set()
    derived_sources: set[str] = set()
    family_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    lengths: list[int] = []

    required_fields = {
        "id",
        "sourceRowId",
        "sourceEvidence",
        "sourceSplit",
        "sourceInputSha256",
        "worldFamily",
        "categories",
        "input",
        "targetText",
        "targetChars",
        "requiredFacts",
        "licensedDetails",
        "knowledgeBoundary",
        "forbiddenInventions",
        "styleReferenceIds",
    }

    for index, record in enumerate(records, start=1):
        label = f"row {index} ({record.get('id', '?')})"
        missing = required_fields - set(record)
        if missing:
            fail(errors, f"{label}: missing fields {sorted(missing)}")
            continue

        rid = record["id"]
        source_id = record["sourceRowId"]
        if rid in seen_ids:
            fail(errors, f"{label}: duplicate id {rid}")
        seen_ids.add(rid)
        is_derived = record.get("sourceEvidence", {}).get("derived") is True
        if source_id in seen_sources:
            if not is_derived:
                fail(errors, f"{label}: duplicate sourceRowId {source_id}")
            elif source_id in derived_sources:
                fail(errors, f"{label}: duplicate derived row for sourceRowId {source_id}")
        seen_sources.add(source_id)
        if is_derived:
            derived_sources.add(source_id)

        if source_id not in source_rows:
            fail(errors, f"{label}: sourceRowId {source_id} not in frozen rows")
            continue
        if split_of.get(source_id) != "train" or record["sourceSplit"] != "train":
            fail(errors, f"{label}: split must be train, got {split_of.get(source_id)!r}/{record['sourceSplit']!r}")

        evidence = record["sourceEvidence"]
        if evidence.get("rowId") != source_id:
            fail(errors, f"{label}: sourceEvidence.rowId != sourceRowId")
        if evidence.get("split") != "train":
            fail(errors, f"{label}: sourceEvidence.split must be train")
        if evidence.get("sourceCommit") != SOURCE_COMMIT:
            fail(errors, f"{label}: sourceEvidence.sourceCommit mismatch")

        source_input = source_rows[source_id]["x"]
        derived = evidence.get("derived") is True
        if derived:
            if evidence.get("baseRowId") != source_id:
                fail(errors, f"{label}: derived row baseRowId must equal sourceRowId")
            if not evidence.get("derivation"):
                fail(errors, f"{label}: derived row needs a derivation note")
            expected_input = copy.deepcopy(source_input)
            expected_input["本回合变化"]["时间推进"] = record["input"]["本回合变化"]["时间推进"]
            if record["input"] != expected_input:
                fail(errors, f"{label}: derived input must differ from the base only in time advance")
            expected_hash = hashlib.sha256(canonical(record["input"]).encode("utf-8")).hexdigest()
        else:
            if record["input"] != source_input:
                fail(errors, f"{label}: input differs from frozen x")
            expected_hash = hashlib.sha256(canonical(source_input).encode("utf-8")).hexdigest()
        if record["sourceInputSha256"] != expected_hash:
            fail(errors, f"{label}: sourceInputSha256 mismatch")

        text = record["targetText"]
        length = len(text)
        lengths.append(length)
        if record["targetChars"] != length:
            fail(errors, f"{label}: targetChars says {record['targetChars']}, actual {length}")
        if not (MIN_CHARS <= length <= MAX_CHARS):
            fail(errors, f"{label}: targetText length {length} outside {MIN_CHARS}-{MAX_CHARS}")
        if "\n" in text or "\r" in text:
            fail(errors, f"{label}: targetText must be one paragraph")
        if text != text.strip():
            fail(errors, f"{label}: targetText has leading/trailing whitespace")
        if any(marker in text for marker in ("TODO", "待补", "……")):
            fail(errors, f"{label}: targetText contains a placeholder marker")

        if not record["requiredFacts"]:
            fail(errors, f"{label}: requiredFacts is empty")
        if not record["licensedDetails"]:
            fail(errors, f"{label}: licensedDetails is empty")
        boundary = record["knowledgeBoundary"]
        for key in ("viewpoint", "canKnow", "mustNotReveal"):
            if key not in boundary:
                fail(errors, f"{label}: knowledgeBoundary missing {key}")
        if not record["forbiddenInventions"]:
            fail(errors, f"{label}: forbiddenInventions is empty")

        cats = set(record["categories"])
        unknown = cats - KNOWN_CATEGORIES
        if unknown:
            fail(errors, f"{label}: unknown categories {sorted(unknown)}")
        family = record["worldFamily"]
        if not family:
            fail(errors, f"{label}: worldFamily is empty")
        family_counts[family] += 1
        for cat in cats:
            category_counts[cat] += 1

        for ref in record["styleReferenceIds"]:
            if ref not in source_rows:
                fail(errors, f"{label}: styleReferenceId {ref} not in frozen rows")

    print(f"rows: {len(records)}")
    derived_count = sum(1 for r in records if r.get("sourceEvidence", {}).get("derived") is True)
    print(f"derived rows: {derived_count}")
    print(f"length: min={min(lengths) if lengths else 0} max={max(lengths) if lengths else 0}")
    print("world families:", dict(sorted(family_counts.items())))
    print("categories:", dict(sorted(category_counts.items())))
    if errors:
        print("\nFAILED:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("OK: structure, frozen input, train-only split and length bounds pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
