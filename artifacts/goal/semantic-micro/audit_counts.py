#!/usr/bin/env python3
"""Per-task semantic call counts from frozen acceptance evidence.

Action-family tasks record one row per engine attempt (`attempt: true`) plus a
result row; stage tasks (results/updates) record one row per call. This script
prints both, so the E53 double-count is visible.

Usage: python artifacts/goal/semantic-micro/audit_counts.py [evidence.json ...]
"""
import json
import statistics
import sys
from collections import Counter, defaultdict

DEFAULTS = [
    "results/product/evidence/09-turns20-pi.json",
    "results/product/evidence/10-scenarios-pi-2026-11-28T1041-fbe4.json",
    "results/product/evidence/10-offline-pi.json",
]
ACTION_FAMILY = {"action", "targets", "reaction"}


def stage_of(key):
    return key.split("#")[-1] if key else "?"


def load_rows(path):
    data = json.load(open(path, encoding="utf-8"))
    rows = []
    for turn in data.get("turns") or []:
        for call in (turn.get("product") or {}).get("semanticCalls") or []:
            row = dict(call)
            row["turn"] = turn.get("turn")
            rows.append(row)
    return data, rows


def task_name(row):
    task = row["task"]
    return f"updates.{stage_of(row.get('key'))}" if task == "updates" else task


def summarize(label, rows):
    by = defaultdict(list)
    for row in rows:
        by[task_name(row)].append(row)
    print(f"== {label}")
    header = (f"{'task':22s} {'rows':>5s} {'res':>5s} {'model_res':>9s} "
              f"{'attempt':>7s} {'engines':>7s} {'sources':34s} {'model_s':>8s} {'p50ms':>6s} {'p50chars':>8s}")
    print(header)
    for task, calls in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        results = [c for c in calls if not c.get("attempt")]
        attempts = [c for c in calls if c.get("attempt")]
        model = [c for c in calls if c.get("source") == "model"]
        base = task.split(".")[0]
        model_results = [c for c in results if c.get("source") == "model"]
        engines = len(attempts) + (len(model_results) if base not in ACTION_FAMILY else 0)
        sources = Counter(c.get("source") for c in results)
        ms = [c["ms"] for c in model if c.get("ms") is not None]
        chars = [c["promptChars"] for c in model if c.get("promptChars")]
        print(f"{task:22s} {len(calls):5d} {len(results):5d} {len(model_results):9d} "
              f"{len(attempts):7d} {engines:7d} {str(dict(sources)):34s} "
              f"{sum(ms) / 1000:8.1f} {statistics.median(ms) if ms else 0:6.0f} "
              f"{statistics.median(chars) if chars else 0:8.0f}")
    semantic = [c for c in rows if c["task"] != "narration"]
    engines = (sum(1 for c in semantic if c.get("attempt"))
               + sum(1 for c in semantic if not c.get("attempt") and c.get("source") == "model"
                     and c["task"] not in ACTION_FAMILY))
    print(f"semantic engine calls (excluding narration): {engines}\n")


def main():
    paths = sys.argv[1:] or DEFAULTS
    for path in paths:
        try:
            data, rows = load_rows(path)
        except FileNotFoundError:
            print(f"== {path}: missing, skipped")
            continue
        summarize(f"{path} ({data.get('status')}, {len(data.get('turns') or [])} turns)", rows)


if __name__ == "__main__":
    main()
