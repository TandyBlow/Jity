# -*- coding: utf-8 -*-
"""Turn checked teacher targets into the training file the trainer reads.

Input is the output of check_teacher_targets.py (tasks + accepted target). The
prompt is kept verbatim; only the target and the weighting are added. Rows that
failed a check never reach this file, so the trainer cannot learn from them.

Weights: teacher text is secondary to human text, so the default weight is 4
against 6 for lane-01 rows and 2 for the 05 scenes. That number is a policy, not
a measurement — it is written here so a later experiment can change it with a
reason.

    python src/build_grounded_dataset.py --targets data/teacher-targets-page-v1.jsonl \
        --out data/train-page-grounded-v1.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.abspath(os.path.join(HERE, ".."))


def read_jsonl(path: str) -> list:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", default=os.path.join(V2, "data", "teacher-targets-page-v1.jsonl"))
    parser.add_argument("--out", default=os.path.join(V2, "data", "train-page-grounded-v1.jsonl"))
    parser.add_argument("--weight", type=int, default=4)
    parser.add_argument("--max-chars", type=int, default=240)
    args = parser.parse_args()

    rows: list = []
    for row in read_jsonl(args.targets):
        target = (row.get("target") or "").strip()
        if not target or len(target) > args.max_chars:
            continue
        rows.append({
            "id": row["id"],
            "split": row.get("split", "train"),
            "mode": "scene",
            "draft": row.get("draft") or "",
            "user": row["prompt"],
            "target": target,
            "weight": args.weight,
            "source": "teacher-page-v1",
            "targetSource": row.get("targetSource") or "teacher:qwen7b@hpc",
            "lineage": row.get("lineage"),
            "stateRowSha256": row.get("sourceRowSha256"),
        })
    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["split"]] = counts.get(row["split"], 0) + 1
    digest = hashlib.sha256(io.open(args.out, "rb").read()).hexdigest()
    summary = {"out": args.out, "sha256": digest, "rows": len(rows), "splits": counts,
               "weight": args.weight,
               "targetSource": "qwen7b teacher on the page's own first-attempt prompt; "
                               "accepted only through check_teacher_targets.py",
               "notHumanReviewed": True,
               "note": "teacher text is a supervision aid, not a quality claim; 01 reviews any model output"}
    with io.open(args.out + ".manifest.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
