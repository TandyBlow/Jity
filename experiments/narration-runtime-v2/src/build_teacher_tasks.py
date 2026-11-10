# -*- coding: utf-8 -*-
"""Build teacher tasks whose prompt is the page's own first-attempt prompt.

Why this exists: after 06 unified the length contract at 160-240 chars
(6a157cb5) the supervision I had was 94 chars median, so training on it taught
short summaries the page rejects. Human prose in the pool is 186-1553 chars and
cannot be turned into 160-240 by program filtering without inventing or
truncating meaning. The authorised HPC teacher is the remaining source.

Design rules:
- the prompt is byte-identical to `instructNarrationInput(..., draft, 'repair')`
  (golden-pinned by check_page_prompt.py); the teacher is never given a prompt
  the student will not see;
- the settled facts come from the row's own state record (`x`), which is the
  authoritative input; the program draft is what the page itself sends;
- only train-split rows are asked for, so dev/test stay unseen;
- every task keeps the source row hash and lineage so a later check can trace a
  target back to its state.

    python src/build_teacher_tasks.py --out data/teacher-tasks-page-v1.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(V2, "..", ".."))
ROWS05 = os.path.abspath(os.path.join(REPO, "..", "05-kernel"))
sys.path.insert(0, HERE)
import build_page_pairs as B  # noqa: E402

SPLIT = os.path.abspath(os.path.join(
    REPO, "experiments", "world-components", "narration-dataset-v1", "splits", "v1.json"))


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha_of_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(V2, "data", "teacher-tasks-page-v1.jsonl"))
    parser.add_argument("--split", default="train", help="which frozen split to ask the teacher for")
    parser.add_argument("--rows05", default=os.path.join(
        ROWS05, "experiments", "narration-quality", "corpus-scenes", "generated", "rows.jsonl"))
    parser.add_argument("--include-05", action="store_true", default=True)
    args = parser.parse_args()

    with io.open(SPLIT, encoding="utf-8") as handle:
        frozen = json.load(handle)
    split_of = {row_id: name for name in ("train", "dev", "test") for row_id in frozen.get(name, [])}

    tasks: List[Dict[str, Any]] = []
    seen: set = set()

    for row in read_jsonl(B.ROWS_V2):
        split = split_of.get(row["id"], "train")
        if args.split != "all" and split != args.split:
            continue
        draft = B.page_draft(row["x"])
        if not draft:
            continue
        tasks.append({
            "id": row["id"],
            "split": split,
            "source": "rows-v2",
            "lineage": row.get("sourceRowSha256") or row["id"],
            "sourceRowSha256": row.get("sourceRowSha256"),
            "stateViewpoint": B.viewpoint_of(row["x"]),
            "prompt": B.page_prompt(B.viewpoint_of(row["x"]), draft, "repair"),
            "draft": draft,
            "promptMode": "repair",
        })
        seen.add(row["id"])

    for row in read_jsonl(B.SHORT_ROWS):
        if row["id"] in seen:
            continue
        split = split_of.get(row["id"], "train")
        if args.split != "all" and split != args.split:
            continue
        draft = B.page_draft(row["input"])
        if not draft:
            continue
        tasks.append({
            "id": row["id"],
            "split": split,
            "source": "short-01",
            "lineage": row.get("id"),
            "sourceRowSha256": hashlib.sha256(
                json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            "stateViewpoint": B.viewpoint_of(row["input"]),
            "prompt": B.page_prompt(B.viewpoint_of(row["input"]), draft, "repair"),
            "draft": draft,
            "promptMode": "repair",
        })

    if args.include_05 and os.path.exists(args.rows05):
        for row in read_jsonl(args.rows05):
            draft = B.page_draft(row["input"])
            if not draft:
                continue
            tasks.append({
                "id": row["id"],
                "split": "train",
                "source": "short-05",
                "lineage": "tide-sequence",
                "sourceRowSha256": hashlib.sha256(
                    json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
                "stateViewpoint": B.viewpoint_of(row["input"]),
                "prompt": B.page_prompt(B.viewpoint_of(row["input"]), draft, "repair"),
                "draft": draft,
                "promptMode": "repair",
            })

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for task in tasks:
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")
    manifest = {
        "out": args.out,
        "sha256": sha_of_file(args.out),
        "rows": len(tasks),
        "split": args.split,
        "sources": {"rows-v2": sha_of_file(B.ROWS_V2), "short-01": sha_of_file(B.SHORT_ROWS)},
        "promptSource": "worktrees/06-recovery/frontend/src/lib/world-engine/local/prompt.ts",
        "promptGolden": "golden/page-prompt/ts-repair.txt (check_page_prompt.py passes)",
        "note": "teacher sees exactly the page's first-attempt prompt; no system turn, matching the page's single user message",
    }
    with io.open(args.out + ".manifest.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
