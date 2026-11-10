# -*- coding: utf-8 -*-
"""Assemble the combined training file (long scenes + lane 01 short + lane 05 scenes).

Output row shape:
    {"id", "split", "mode", "user", "target", "weight", "source", "sourceSha256"}

`mode` conditions the user prompt on the wanted length; `weight` repeats a row
inside one epoch so the 21 short fact-bound scenes are not drowned by the 199
long literary ones. Everything is deterministic; source files are only read.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))

ROWS_V2 = os.path.join(V2, "data", "rows-v2.jsonl")
SHORT_ROWS = os.path.join(V2, "data", "rows-short-v1.jsonl")
SCENE_ROWS = os.path.abspath(os.path.join(
    REPO, "..", "05-kernel", "experiments", "narration-quality", "corpus-scenes",
    "generated", "rows.jsonl"))
OUT = os.path.join(V2, "data", "train-v2.jsonl")

SHORT_DIRECTIVE = "三句以内，只写这一回合的改动。"
SCENE_DIRECTIVE = "一个完整场景。"

sys.path.insert(0, HERE)
import projection_v2  # noqa: E402
import v2_render  # noqa: E402


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def user_text(mode: str, body: str, prior: str = "") -> str:
    directive = SHORT_DIRECTIVE if mode == "short" else SCENE_DIRECTIVE
    head = f"【篇幅】{directive}\n"
    if prior:
        head += f"【上文】{prior}\n"
    return head + body


def main() -> int:
    out: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    cleaned = 0

    splits_file = os.path.abspath(os.path.join(
        REPO, "experiments", "world-components", "narration-dataset-v1",
        "splits", "v1.json"))
    frozen = json.load(io.open(splits_file, encoding="utf-8"))
    split_of = {}
    for name in ("train", "dev", "test"):
        for row_id in frozen[name]:
            split_of[row_id] = name
    hashes["splits-v1"] = sha256(splits_file)

    rows_v2 = read_jsonl(ROWS_V2)
    hashes["rows-v2"] = sha256(ROWS_V2)
    for row in rows_v2:
        out.append({"id": row["id"], "split": split_of[row["id"]], "mode": "scene",
                    "user": user_text("scene", row["xProse"]),
                    "target": row["y"], "weight": 1, "source": "rows-v2",
                    "sourceSha256": hashes["rows-v2"]})

    short = read_jsonl(SHORT_ROWS)
    hashes["rows-short-v1"] = sha256(SHORT_ROWS)
    for row in short:
        out.append({"id": row["id"], "split": row["split"], "mode": "short",
                    "user": user_text("short", row["xProse"]),
                    "target": row["target"], "weight": 6, "source": "short-01",
                    "sourceSha256": hashes["rows-short-v1"]})

    scene_source = ""
    # lane 05 hand-authored its delta as scalars (解除个性: "…"), which is not the
    # frozen kernel shape this serializer was validated against; including it
    # would train on text the product page never produces. Re-enable only after
    # 05's rows round-trip through the kernel serializer.
    if os.environ.get("INCLUDE_05") == "1" and os.path.exists(SCENE_ROWS):
        scene_source = sha256(SCENE_ROWS)
        hashes["scenes-05"] = scene_source
        for row in read_jsonl(SCENE_ROWS):
            normalized, ledger = projection_v2.normalize_projection(row["input"])
            body = v2_render.serialize(normalized).text
            unexpected = [entry for entry in ledger
                          if entry.get("path") != "本回合变化/时间推进"]
            if unexpected:
                raise SystemExit(f"{row['id']}: whitespace removal outside 时间推进: {unexpected[:2]}")
            if ledger:
                cleaned += 1
            prior = (row.get("priorText") or "").strip()
            out.append({"id": row["id"], "split": row.get("split") or "train",
                        "mode": "scene", "user": user_text("scene", body, prior),
                        "target": row["targetText"], "weight": 3,
                        "source": "scenes-05", "sourceSha256": scene_source})

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as handle:
        for row in out:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    splits: Dict[str, int] = {}
    weighted: Dict[str, int] = {}
    modes: Dict[str, int] = {}
    for row in out:
        splits[row["split"]] = splits.get(row["split"], 0) + 1
        weighted[row["split"]] = weighted.get(row["split"], 0) + row["weight"]
        modes[row["mode"]] = modes.get(row["mode"], 0) + 1
    summary = {"rows": len(out), "sha256": sha256(OUT), "splits": splits,
               "weighted": weighted, "modes": modes, "sources": hashes,
               "sourceFiles": {"rows-v2": ROWS_V2, "short": SHORT_ROWS,
                               "scenes": SCENE_ROWS if scene_source else None}}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
