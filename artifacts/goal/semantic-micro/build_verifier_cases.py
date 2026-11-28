#!/usr/bin/env python3
"""Build verifier (task goal, fact) cases with LLM verdict labels from evidence.

The tasks stage records the verifier's answer as `{"judgments":[...]}` and the
verifier prompt carries the exact (owner, task, goal, fact) rows. This script
pairs prompts with answers by their key sets, so each case gets its verdict.

Usage:
  python artifacts/goal/semantic-micro/build_verifier_cases.py \
      --evidence "D:/others/Jity/artifacts/goal/micro-workflow/evidence-*.json" \
      --out experiments/semantic-micro/verifier-cases.jsonl
"""
import argparse
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_calls as ec  # noqa: E402

WORLD = "data/worlds/dragon-raja-free-day.world.json"


def load_goals():
    data = json.load(open(WORLD, encoding="utf-8"))
    return {task.get("id"): task.get("goal") or ""
            for character in (data.get("characters") or {}).values()
            for task in (character.get("tasks") or {}).values()}


def after_status(turn, owner, task_id):
    snapshot = turn.get("snapshotAfterTurn") or {}
    state = ((snapshot.get("transport") or {}).get("state")) or {}
    task = (((state.get("characters") or {}).get(owner) or {}).get("tasks") or {}).get(task_id)
    return task.get("status") if task else None


def process(path, frozen):
    data = json.load(open(path, encoding="utf-8"))
    group = os.path.basename(path).replace(".json", "")
    rows = []
    for turn in data.get("turns") or []:
        supports_by_task = {}
        for call in (turn.get("submission") or {}).get("calls") or []:
            if call.get("task") != "updates" or call.get("stage") != "tasks":
                continue
            for support in (call.get("coverage") or {}).get("supports") or []:
                supports_by_task[(support.get("characterId"), support.get("taskId"))] = support
        prompts = [item.get("prompt") or "" for item in (turn.get("product") or {}).get("semanticPrompts") or []]
        verifier_prompts = [ec.parse_verifier(prompt) for prompt in prompts if ec.classify(prompt) == "verifier"]
        verifier_prompts = [cases for cases in verifier_prompts if cases]
        answers = []
        for call in (turn.get("submission") or {}).get("calls") or []:
            if call.get("task") != "updates" or call.get("stage") != "tasks":
                continue
            for value in ec.json_objects(call.get("raw")):
                if "judgments" in value:
                    answers.append(value["judgments"])
        for call in ((turn.get("product") or {}).get("semanticCalls") or []):
            if call.get("task") == "updates" and (call.get("key") or "").endswith("#tasks"):
                for value in ec.json_objects(call.get("raw")):
                    if "judgments" in value:
                        answers.append(value["judgments"])
        used_answers = set()
        for cases in verifier_prompts:
            key_set = {(row["characterId"], row["taskId"]) for row in cases}
            match = None
            for index, judgments in enumerate(answers):
                if index in used_answers:
                    continue
                answered = {(row.get("characterId"), row.get("taskId")) for row in judgments}
                if answered == key_set:
                    match = (index, judgments)
                    break
            if not match:
                for index, judgments in enumerate(answers):
                    if index in used_answers:
                        continue
                    answered = {(row.get("characterId"), row.get("taskId")) for row in judgments}
                    if key_set.issubset(answered):
                        match = (index, judgments)
                        break
            verdicts = {}
            if match:
                used_answers.add(match[0])
                verdicts = {(row.get("characterId"), row.get("taskId")): row for row in match[1]}
            for case in cases:
                key = (case["characterId"], case["taskId"])
                verdict = verdicts.get(key)
                if not verdict:
                    continue
                rows.append({
                    "group": group, "file": path, "turn": turn.get("turn"),
                    "ownerId": case["characterId"], "taskId": case["taskId"],
                    "goal": case["goal"], "factText": case["factText"],
                    "label": verdict.get("satisfied"), "reason": verdict.get("reason"),
                    "committed": after_status(turn, case["characterId"], case["taskId"]),
                    "source": "llm_verifier",
                    "conditions": (supports_by_task.get(key) or {}).get("conditions"),
                    "split": "eval_frozen" if frozen else "train",
                })
        # Accepted supports without a captured verdict are still verifier-yes.
        for call in (turn.get("submission") or {}).get("calls") or []:
            if call.get("task") != "updates" or call.get("stage") != "tasks":
                continue
            for support in (call.get("coverage") or {}).get("supports") or []:
                text = support.get("basisText")
                if not text:
                    continue
                rows.append({
                    "group": group, "file": path, "turn": turn.get("turn"),
                    "ownerId": support.get("characterId"), "taskId": support.get("taskId"),
                    "goal": GOALS.get(support.get("taskId")), "factText": text, "label": "yes", "reason": None,
                    "committed": after_status(turn, support.get("characterId"), support.get("taskId")),
                    "source": "accepted_support", "conditions": support.get("conditions"),
                    "split": "eval_frozen" if frozen else "train",
                })
    return rows


def main():
    global GOALS
    GOALS = load_goals()
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--frozen", action="append", default=[])
    parser.add_argument("--out", default="experiments/semantic-micro/verifier-cases.jsonl")
    args = parser.parse_args()
    rows = []
    for pattern in args.evidence:
        for path in sorted(glob.glob(pattern)):
            if "scenario" in os.path.basename(path):
                continue
            found = process(path, False)
            if found:
                print(f"  {os.path.basename(path)}: {len(found)}")
            rows.extend(found)
    for path in args.frozen:
        found = process(path, True)
        print(f"  [frozen] {os.path.basename(path)}: {len(found)}")
        rows.extend(found)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = Counter((row["split"], row["source"], row["label"]) for row in rows)
    print(f"wrote {len(rows)} rows to {args.out}")
    for key, value in sorted(counts.items()):
        print(" ", key, value)


if __name__ == "__main__":
    main()
