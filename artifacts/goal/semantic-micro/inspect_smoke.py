#!/usr/bin/env python3
"""Summarize a product acceptance evidence file for the semantic task stage."""
import json
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "results/product/evidence/smoke-goal-taskstage-20261128.json"
data = json.load(open(path, encoding="utf-8"))
print("status", data.get("status"), "turns", len(data.get("turns") or []), "failures", len(data.get("failures") or []))
for turn in data.get("turns") or []:
    product = turn.get("product") or {}
    calls = Counter((call.get("task"), (call.get("key") or "").split("#")[-1] if call.get("task") == "updates" else call.get("source"))
                    for call in product.get("semanticCalls") or [])
    micro = Counter(row.get("port") for row in product.get("microStats") or [])
    print(f"\nturn {turn.get('turn')} input={turn.get('input')!r}")
    print("  semanticCalls", dict(calls))
    print("  microStats", dict(micro))
    print("  acceptedMs", product.get("acceptedMs"), "firstReadable", product.get("firstReadableAtMs"), "problems", turn.get("problems"))
    snapshot = turn.get("snapshotAfterTurn") or {}
    state = ((snapshot.get("transport") or {}).get("state")) or {}
    protagonist = state.get("protagonistId")
    tasks = (((state.get("characters") or {}).get(protagonist) or {}).get("tasks")) or {}
    print("  protagonist", protagonist, "tasks", {tid: task.get("status") for tid, task in tasks.items()})
    print("  text", (turn.get("text") or "")[:200].replace("\n", " "))
