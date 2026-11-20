#!/usr/bin/env python3
"""Attach handwritten short targets to more frozen train rows.

The frozen x is copied unchanged and hashed. Rows built here use ids starting
with ``short2-``; every other line in rows.jsonl is preserved byte for byte.
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
CORPUS = HERE.parent
ROWS_PATH = CORPUS / "rows.jsonl"
SPEC_PATH = HERE / "scenes.json"
SOURCE_ROOT = pathlib.Path(
    "D:/others/Jity/.local/world-components-worktree/experiments/world-components/narration-dataset-v1"
)
SOURCE_COMMIT = "1ab6ca791f97529a7bffed1f4837bf81a28badcb"
ID_PREFIX = "short2-"


def canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    spec = json.load(io.open(SPEC_PATH, encoding="utf-8"))
    frozen = {
        row["id"]: row
        for row in (json.loads(line) for line in io.open(SOURCE_ROOT / "rows-xy.jsonl", encoding="utf-8") if line.strip())
    }
    splits = json.load(io.open(SOURCE_ROOT / "splits" / "v1.json", encoding="utf-8"))
    split_of = {rid: name for name, ids in splits.items() for rid in ids}

    built = []
    for entry in spec["rows"]:
        source_id = entry["sourceRowId"]
        if split_of.get(source_id) != "train":
            raise SystemExit(f"{entry['id']}: source row is not train")
        if not entry["id"].startswith(ID_PREFIX):
            raise SystemExit(f"{entry['id']}: id must start with {ID_PREFIX}")
        source_input = frozen[source_id]["x"]
        text = entry["targetText"]
        built.append({
            "id": entry["id"],
            "sourceRowId": source_id,
            "sourceEvidence": {
                "dataset": "narration-dataset-v1",
                "sourceCommit": SOURCE_COMMIT,
                "sourceRoot": "D:/others/Jity/.local/world-components-worktree",
                "sourceFile": "experiments/world-components/narration-dataset-v1/rows-xy.jsonl",
                "rowId": source_id,
                "split": "train",
            },
            "sourceSplit": "train",
            "sourceInputSha256": hashlib.sha256(canonical(source_input).encode("utf-8")).hexdigest(),
            "worldFamily": entry["worldFamily"],
            "categories": entry["categories"],
            "sequenceId": None,
            "turnIndex": None,
            "input": source_input,
            "targetText": text,
            "targetChars": len(text),
            "requiredFacts": entry["requiredFacts"],
            "licensedDetails": entry["licensedDetails"],
            "knowledgeBoundary": entry["knowledgeBoundary"],
            "forbiddenInventions": entry["forbiddenInventions"],
            "styleReferenceIds": entry["styleReferenceIds"],
            "notes": entry["notes"],
            "reviewState": entry["reviewState"],
        })

    existing = ROWS_PATH.read_text(encoding="utf-8").splitlines()
    kept = [line for line in existing if line.strip() and not json.loads(line)["id"].startswith(ID_PREFIX)]
    authored_start = next(
        (index for index, line in enumerate(kept) if json.loads(line)["id"].startswith("dr-")),
        len(kept),
    )
    merged = kept[:authored_start] + [json.dumps(row, ensure_ascii=False) for row in built] + kept[authored_start:]
    with io.open(ROWS_PATH, "w", encoding="utf-8", newline="\n") as handle:
        for line in merged:
            handle.write(line + "\n")

    for row in built:
        print(f"{row['id']}: {row['targetChars']} chars")
    print(f"rows.jsonl: {len(merged)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
