# -*- coding: utf-8 -*-
"""Decide which teacher samples may become training targets.

The teacher writes 160-240 chars from the page's own prompt. A sample is kept
only when the objective checks pass; anything unproven is dropped, not repaired
by hand, because a target teaches whatever it contains.

Checks (all objective, all from the row's own record):
  length     160-240 chars after stripping whitespace
  coverage   every time/move/task/sanity/personality clause in the draft is
             present (scenery clauses are optional; the page allows one or two
             touches)
  numbers    no number in the prose that the draft does not contain
  names      no roster name in the prose that the draft does not contain
  labels     no state-label words (精神值/任务/未完成/视角/结算)
  paraphrase not a verbatim re-listing of the draft (<=60% of draft sentences)
  leak       no 12-char span that also appears in a different row's target and
             carries a roster name (generic phrasing reuse is allowed)

    python src/check_teacher_targets.py --samples hpc/runs/teacher-page-v1/samples.jsonl \
        --tasks data/teacher-tasks-page-v1.jsonl --out data/teacher-targets-page-v1.jsonl
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
sys.path.insert(0, HERE)
import eval_draft as E  # noqa: E402

LABELS = ("精神值", "未完成", "任务", "视角", "结算", "状态")
SPLIT_SENT = re.compile(r"(?<=[。！？])")


def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with io.open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def roster() -> set:
    names: set = set()
    for row in read_jsonl(os.path.join(V2, "data", "rows-v2.jsonl")):
        state = row.get("x") or {}
        for key in ("上回合状态", "本回合状态"):
            block = state.get(key) or {}
            for section in ("人物", "在场", "人们"):
                text = block.get(section)
                if isinstance(text, str):
                    names.update(n.strip() for n in re.split(r"[、，,]", text) if 2 <= len(n.strip()) <= 4)
                elif isinstance(text, dict):
                    names.update(str(k) for k in text if 2 <= len(str(k)) <= 4)
    return names


def clean(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def check(sample: str, draft: str, names: set) -> Dict[str, Any]:
    prose = clean(sample)
    issues: List[str] = []
    if not (160 <= len(prose) <= 240):
        issues.append(f"length:{len(prose)}")
    clauses = [c for c in SPLIT_SENT.split(draft) if c.strip()]
    missing = [c for c in clauses if not E.covers(prose, c)]
    if missing:
        issues.append(f"missing_draft:{len(missing)}")
    allowed_numbers = set(re.findall(r"[0-9]+", draft))
    invented = [n for n in re.findall(r"[0-9]+", prose) if n not in allowed_numbers]
    if invented:
        issues.append("invented_number:" + ",".join(invented[:3]))
    unknown_names = [n for n in names if n in prose and n not in draft]
    if unknown_names:
        issues.append("unknown_name:" + ",".join(unknown_names[:3]))
    labels = [word for word in LABELS if word in prose]
    if labels:
        issues.append("state_label:" + ",".join(labels))
    quoted = E.has_added_dialogue(prose, draft)
    # Dialogue is allowed polish when the draft licenses it; a pair of quotes
    # around the task goal is not new speech, so has_added_dialogue already
    # removes the goal span before looking.
    copied = sum(1 for c in clauses if c and c in prose) / max(1, len(clauses))
    if copied > 0.6:
        issues.append(f"copied_draft:{copied:.2f}")
    return {"prose": prose, "chars": len(prose), "missing": missing, "issues": issues,
            "dialogueAdded": quoted}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True)
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--out", default=os.path.join(V2, "data", "teacher-targets-page-v1.jsonl"))
    parser.add_argument("--leak-span", type=int, default=12)
    args = parser.parse_args()

    tasks = {row["id"]: row for row in read_jsonl(args.tasks)}
    names = roster()
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for row in read_jsonl(args.samples):
        task = tasks.get(row["id"])
        if not task:
            continue
        best = None
        for index, sample in enumerate(row.get("samples") or []):
            verdict = check(sample, task["draft"], names)
            verdict.update({"id": row["id"], "sampleIndex": index})
            if not verdict["issues"]:
                if best is None or abs(verdict["chars"] - 200) < abs(best["chars"] - 200):
                    best = verdict
            else:
                rejected.append(verdict)
        if best:
            kept.append({**task, "target": best["prose"], "targetChars": best["chars"],
                         "targetSource": "teacher:qwen7b@hpc", "sampleIndex": best["sampleIndex"],
                         "checks": {"length": True, "coverage": True, "numbers": True,
                                    "names": True, "labels": True}})

    # Leak pass across kept targets: only spans that carry a roster name count,
    # so ordinary Chinese phrasing reuse is not treated as memorisation.
    for row in kept:
        for other in kept:
            if other["id"] == row["id"]:
                continue
            text = other["target"]
            for start in range(0, max(0, len(text) - args.leak_span)):
                span = text[start:start + args.leak_span]
                if any(name in span for name in names) and span not in row["draft"] and span in row["target"]:
                    row.setdefault("leaks", []).append({"otherId": other["id"], "span": span})
                    break

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        for row in kept:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    digest = hashlib.sha256(io.open(args.out, "rb").read()).hexdigest()
    summary = {
        "tasks": len(tasks),
        "kept": len(kept),
        "rejectedSamples": len(rejected),
        "rowsWithoutTarget": sorted(set(tasks) - {row["id"] for row in kept}),
        "withLeak": [row["id"] for row in kept if row.get("leaks")],
        "out": args.out,
        "sha256": digest,
        "rejectionReasons": _tally(rejected),
    }
    with io.open(args.out + ".summary.json", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


def _tally(rejected: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rejected:
        for issue in row["issues"]:
            key = issue.split(":")[0]
            counts[key] = counts.get(key, 0) + 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
