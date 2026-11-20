# -*- coding: utf-8 -*-
"""Combine long scenes, lane-01 short scenes and graded teacher beats.

Row shape stays `{"id","split","mode","user","target","weight","source"}` so
`train/train_beats.py` can consume it unchanged. Weighting is explicit: the
teacher beats are the only rows that train the short "one settled fact" shape
with broad coverage, so they are repeated; the 199 long scenes keep the prose
density and are not allowed to dominate.

    python src/build_train_v3.py \
        --beats data/beats-v1.jsonl \
        --kept data/beats-teacher-kept-v1.jsonl \
        --out data/train-v3.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))
ROWS_V2 = os.path.join(V2, "data", "rows-v2.jsonl")
SHORT_ROWS = os.path.join(V2, "data", "rows-short-v1.jsonl")
SPLIT = os.path.abspath(os.path.join(
    REPO, "experiments", "world-components", "narration-dataset-v1", "splits", "v1.json"))

SHORT_DIRECTIVE = "三句以内，只写这一回合的改动。"
SCENE_DIRECTIVE = "一个完整场景。"


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def user_text(mode: str, body: str) -> str:
    directive = SHORT_DIRECTIVE if mode == "short" else SCENE_DIRECTIVE
    return f"【篇幅】{directive}\n" + body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beats", default=os.path.join(V2, "data", "beats-v1.jsonl"))
    parser.add_argument("--kept", default=os.path.join(V2, "data", "beats-teacher-kept-v1.jsonl"))
    parser.add_argument("--out", default=os.path.join(V2, "data", "train-v3.jsonl"))
    parser.add_argument("--beat-weight", type=int, default=2)
    parser.add_argument("--short-weight", type=int, default=6)
    parser.add_argument("--scene-weight", type=int, default=1)
    parser.add_argument("--world-targets", default="")
    parser.add_argument("--world-weight", type=int, default=6)
    args = parser.parse_args()

    with io.open(SPLIT, encoding="utf-8") as handle:
        frozen = json.load(handle)
    split_of = {row_id: name for name in ("train", "dev", "test")
                for row_id in frozen.get(name, [])}

    out: List[Dict[str, Any]] = []
    sources: Dict[str, str] = {}

    sources["rows-v2"] = sha256(ROWS_V2)
    for row in read_jsonl(ROWS_V2):
        out.append({"id": row["id"], "split": split_of[row["id"]], "mode": "scene",
                    "user": user_text("scene", row["xProse"]), "target": row["y"],
                    "weight": args.scene_weight, "source": "rows-v2"})

    sources["rows-short-v1"] = sha256(SHORT_ROWS)
    for row in read_jsonl(SHORT_ROWS):
        out.append({"id": row["id"], "split": row["split"], "mode": "short",
                    "user": user_text("short", row["xProse"]), "target": row["target"],
                    "weight": args.short_weight, "source": "short-01"})

    beats = {beat["id"]: beat for beat in read_jsonl(args.beats)}
    kept = read_jsonl(args.kept)
    sources["beats-teacher-kept"] = sha256(args.kept)
    seen = set()
    for row in kept:
        source_id = row.get("sourceId") or ""
        beat = (beats.get(source_id) or beats.get(row["id"])
                or beats.get(re.sub(r"-\d+$", "", row["id"])))
        if beat is None:
            raise SystemExit(f"{row['id']}: no beat for the kept sentence")
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        out.append({"id": row["id"], "split": row["split"], "mode": "beat",
                    "user": beat["prompt"], "target": row["target"],
                    "weight": args.beat_weight,
                    "source": "teacher-beat:" + row["kind"]})

    if args.world_targets:
        sources["world-targets"] = sha256(args.world_targets)
        authored = {row["id"]: row for row in read_jsonl(args.world_targets)}
        for beat_id, row in authored.items():
            beat = beats.get(beat_id)
            if beat is None:
                raise SystemExit(f"{beat_id}: no beat for the authored target")
            out.append({"id": beat_id, "split": beat["split"], "mode": "beat",
                        "user": beat["prompt"], "target": row["target"],
                        "weight": args.world_weight,
                        "source": "authored-world"})

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for row in out:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    splits: Dict[str, int] = {}
    weighted: Dict[str, int] = {}
    modes: Dict[str, int] = {}
    for row in out:
        splits[row["split"]] = splits.get(row["split"], 0) + 1
        weighted[row["split"]] = weighted.get(row["split"], 0) + row["weight"]
        modes[row["mode"]] = modes.get(row["mode"], 0) + 1
    kept_by_kind: Dict[str, int] = {}
    for row in kept:
        kept_by_kind[row["kind"]] = kept_by_kind.get(row["kind"], 0) + 1
    summary = {"rows": len(out), "sha256": sha256(args.out), "splits": splits,
               "weighted": weighted, "modes": modes, "teacherKept": kept_by_kind,
               "sources": sources}
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
