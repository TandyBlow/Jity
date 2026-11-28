#!/usr/bin/env python3
"""Merge task-pair and verifier-case exports into train/val/test/eval splits.

Rules:
- A verifier `yes` whose task is not `achieved` after the turn is a conflict,
  not a positive; a verifier `no` whose task is `achieved` is also a conflict.
- task-pairs `silver_pending` stays a negative; `conflict_missed` is review-only.
- Dedupe by (taskId, goal, factText, label).
- Split by evidence file group, never by row. Frozen acceptance evidence is
  exported separately and never enters train/val/test.

Usage:
  python artifacts/goal/semantic-micro/build_task_dataset.py \
      --pairs experiments/semantic-micro/task-pairs.jsonl \
      --verifier experiments/semantic-micro/verifier-cases.jsonl \
      --out experiments/semantic-micro/dataset
"""
import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict


def norm_fact(text):
    return " ".join((text or "").split())


def load_rows(path):
    if not path:
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def clean(rows):
    out = []
    review = []
    for row in rows:
        label = row.get("label")
        committed = row.get("committed")
        evidence = row.get("evidence") or row.get("source")
        if row.get("split") == "eval_frozen":
            out.append(row)
            continue
        if label == "unknown" or label is None:
            review.append({**row, "review_reason": "unlabeled"})
            continue
        if row.get("source") == "llm_verifier" or row.get("source") == "accepted_support":
            if label == "yes" and committed != "achieved":
                review.append({**row, "review_reason": "verifier_yes_not_committed"})
                continue
            if label == "no" and committed == "achieved":
                review.append({**row, "review_reason": "verifier_no_but_committed"})
                continue
        if evidence == "conflict_missed":
            review.append({**row, "review_reason": "completed_fact_task_pending"})
            continue
        goal = row.get("goal") or ""
        fact = norm_fact(row.get("factText"))
        if not goal or not fact:
            review.append({**row, "review_reason": "missing_field"})
            continue
        out.append({**row, "goal": goal, "factText": fact,
                    "label": "yes" if label == "yes" else "no"})
    return out, review


def split_of(group, test_ratio=0.15, val_ratio=0.15):
    bucket = int(hashlib.sha1(group.encode("utf-8")).hexdigest(), 16) % 1000
    if bucket < test_ratio * 1000:
        return "test"
    if bucket < (test_ratio + val_ratio) * 1000:
        return "val"
    return "train"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", default="experiments/semantic-micro/task-pairs.jsonl")
    parser.add_argument("--verifier", default="experiments/semantic-micro/verifier-cases.jsonl")
    parser.add_argument("--out", default="experiments/semantic-micro/dataset")
    args = parser.parse_args()
    rows = load_rows(args.pairs) + load_rows(args.verifier)
    cleaned, review = clean(rows)
    seen = set()
    unique = []
    for row in cleaned:
        key = (row.get("taskId"), row.get("goal"), row.get("factText"), row.get("label"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    buckets = defaultdict(list)
    frozen = []
    for row in unique:
        if row.get("split") == "eval_frozen":
            frozen.append(row)
            continue
        row["split"] = split_of(row.get("group") or "unknown")
        buckets[row["split"]].append(row)
    os.makedirs(args.out, exist_ok=True)
    for name, items in list(buckets.items()) + [("eval_frozen", frozen), ("review", review)]:
        path = os.path.join(args.out, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as handle:
            for row in items:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    for name in ("train", "val", "test", "eval_frozen", "review"):
        items = buckets.get(name, []) + (frozen if name == "eval_frozen" else []) + (review if name == "review" else [])
        labels = Counter(row.get("label") for row in items)
        groups = {row.get("group") for row in items if row.get("split") not in (None, "eval_frozen")}
        print(f"{name:10s} rows={len(items):5d} labels={dict(labels)} groups={len(groups)}")
    print("review reasons:", dict(Counter(row.get("review_reason") for row in review)))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
