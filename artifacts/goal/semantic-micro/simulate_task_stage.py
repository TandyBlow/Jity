#!/usr/bin/env python3
"""Offline simulation of a goal-verifier tasks stage on frozen evidence.

For each turn: pending task rows from the tasks prompt crossed with its facts;
score every pair with the int8 goal verifier; a task is predicted achieved when
its best pair >= threshold. Compare with the tasks the stage actually committed.

Usage: python artifacts/goal/semantic-micro/simulate_task_stage.py [threshold]
"""
import json
import os
import sys

import numpy as np
import onnxruntime as ort
from transformers import BertTokenizer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_calls as ec  # noqa: E402

MODEL = "artifacts/goal/semantic-micro/models/goal-verifier-v1-int8.onnx"
SNAP = "D:/others/Jity/artifacts/benchmark/minirbt-h256-snapshot"
EVIDENCE = [
    "results/product/evidence/09-turns20-pi.json",
    "results/product/evidence/10-scenarios-pi-2026-11-28T1041-fbe4.json",
]


def committed(turn):
    snapshot = turn.get("snapshotAfterTurn") or {}
    state = ((snapshot.get("transport") or {}).get("state")) or {}
    out = set()
    for owner_id, character in (state.get("characters") or {}).items():
        for task in (character.get("tasks") or {}).values():
            if task.get("status") == "achieved":
                out.add((owner_id, task.get("id")))
    return out


def main():
    threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    tokenizer = BertTokenizer(vocab_file=os.path.join(SNAP, "vocab.txt"))
    session = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])

    def score(goal, fact):
        enc = tokenizer(goal + " \u241f " + fact, truncation=True, max_length=192)
        ids = np.array([enc["input_ids"]], dtype=np.int64)
        mask = np.array([enc["attention_mask"]], dtype=np.int64)
        logits = session.run(None, {"input_ids": ids, "attention_mask": mask})[0][0]
        probs = np.exp(logits - logits.max()) / np.exp(logits - logits.max()).sum()
        return float(probs[1])

    totals = {"turns": 0, "pairs": 0, "pred": 0, "hit": 0, "false": 0, "missed": 0}
    for path in EVIDENCE:
        data = json.load(open(path, encoding="utf-8"))
        print("==", path, data.get("status"))
        prev_committed = set()
        for turn in data.get("turns") or []:
            prompts = [item.get("prompt") or "" for item in (turn.get("product") or {}).get("semanticPrompts") or []]
            task_prompts = [p for p in prompts if ec.classify(p) == "tasks"]
            committed_now = committed(turn)
            newly = committed_now - prev_committed
            prev_committed = committed_now
            all_tasks = _tasks(turn)
            predicted = set()
            pairs = 0
            for prompt in task_prompts:
                facts = ec.parse_facts(prompt)
                rows = ec.parse_task_rows(prompt)
                for row in rows:
                    if row["status"] != "待办":
                        continue
                    task_id = next((tid for (owner, tid), task in all_tasks.items()
                                    if owner == row["ownerId"] and task.get("goal") == row["goal"]), None)
                    if not task_id:
                        continue
                    for fact in facts:
                        pairs += 1
                        s = score(row["goal"], fact["text"])
                        if s >= threshold:
                            predicted.add((row["ownerId"], task_id))
            totals["turns"] += 1
            totals["pairs"] += pairs
            totals["pred"] += len(predicted)
            totals["hit"] += len(predicted & newly)
            totals["false"] += len(predicted - newly)
            totals["missed"] += len(newly - predicted)
            if predicted or newly:
                print(f" turn {turn.get('turn')}: pairs={pairs} pred={sorted(predicted)} newly={sorted(newly)}")
    print("totals", totals)


def _tasks(turn):
    snapshot = turn.get("snapshotAfterTurn") or {}
    state = ((snapshot.get("transport") or {}).get("state")) or {}
    out = {}
    for owner_id, character in (state.get("characters") or {}).items():
        for task in (character.get("tasks") or {}).values():
            out[(owner_id, task.get("id"))] = task
    return out


if __name__ == "__main__":
    main()
