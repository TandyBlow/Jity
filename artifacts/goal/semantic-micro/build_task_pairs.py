#!/usr/bin/env python3
"""Build (task goal, fact) pairs from real turn evidence, labelled by committed state.

Positive pairs come from the tasks-stage answer citing a fact for a task that is
`achieved` in the after-turn snapshot. Negative pairs are pending tasks crossed
with facts that share goal wording (silver negatives). Cited-but-uncommitted
pairs are marked conflict and excluded from training.

Frozen acceptance evidence must be passed with --frozen so its rows are marked
`eval_frozen` and excluded from every training split.

Usage:
  python artifacts/goal/semantic-micro/build_task_pairs.py \
      --glob "D:/others/Jity/artifacts/goal/micro-workflow/evidence-semantic-*.json" \
      --out experiments/semantic-micro/task-pairs.jsonl
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import export_calls as ec  # noqa: E402

WORLD = "data/worlds/dragon-raja-free-day.world.json"


def load_world(path=WORLD):
    data = json.load(open(path, encoding="utf-8"))
    initial = data.get("initial") or data
    names = []
    for group in ("characters", "items", "locations"):
        for entity in (initial.get(group) or {}).values():
            name = entity.get("name") or ""
            if len(name) >= 2:
                names.append(name)
            core = name.split("的")[-1]
            if len(core) >= 2 and core != name:
                names.append(core)
    goals = {}
    for character in (initial.get("characters") or {}).values():
        for task in (character.get("tasks") or {}).values():
            goals[task.get("id")] = task.get("goal") or ""
    return names, goals


def grams(text):
    clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)
    return {clean[i:i + 2] for i in range(max(0, len(clean) - 1))}


def outcome_of(text):
    for marker, label in (("达到目的", "completed"), ("只完成一部分", "partial"),
                          ("没有成功", "failed"), ("被阻止", "blocked"), ("没有变化", "unaffected")):
        if marker in text:
            return label
    return "unknown"


def overlap(goal, fact):
    left, right = grams(fact), grams(goal)
    return len(left & right) / len(right) if right else 0.0


def relevant(goal, fact, names):
    if any(name in fact for name in names if name in goal):
        return True
    return overlap(goal, fact) >= 0.15


def after_tasks(turn):
    snapshot = turn.get("snapshotAfterTurn") or {}
    state = ((snapshot.get("transport") or {}).get("state")) or {}
    out = {}
    for owner_id, character in (state.get("characters") or {}).items():
        for task in (character.get("tasks") or {}).values():
            out[(owner_id, task.get("id"))] = task
    return out


def task_answer(turn):
    """All tasks-stage answer objects plus achieved ids from stage coverage."""
    objects = []
    achieved = {}
    for call in (turn.get("submission") or {}).get("calls") or []:
        if call.get("task") != "updates" or call.get("stage") != "tasks":
            continue
        for value in ec.json_objects(call.get("raw")):
            objects.append(value)
        coverage = call.get("coverage") or {}
        for row in coverage.get("achievedByCharacter") or []:
            achieved.setdefault(row.get("characterId"), []).extend(row.get("taskIds") or [])
    for call in ((turn.get("product") or {}).get("semanticCalls") or []):
        if call.get("task") == "updates" and (call.get("key") or "").endswith("#tasks"):
            for value in ec.json_objects(call.get("raw")):
                objects.append(value)
    answers = [obj for obj in objects if "achieved" in obj or "unchanged" in obj]
    return answers, achieved


def resolve_key(rows_by_owner, owner, raw_task):
    if not raw_task:
        return None
    if not re.fullmatch(r"t\d+", raw_task):
        return raw_task
    for row in rows_by_owner.get(owner, []):
        if row["taskKey"] == raw_task:
            return row["goal"]
    return None


def process_file(path, frozen, names, goals):
    data = json.load(open(path, encoding="utf-8"))
    group = os.path.basename(path).replace(".json", "")
    rows_out = []
    for turn in data.get("turns") or []:
        prompts = [item.get("prompt") or "" for item in (turn.get("product") or {}).get("semanticPrompts") or []]
        task_prompts = [p for p in prompts if ec.classify(p) == "tasks"]
        if not task_prompts:
            continue
        after = after_tasks(turn)
        answers, coverage_achieved = task_answer(turn)
        for prompt in task_prompts:
            facts = ec.parse_facts(prompt)
            rows = ec.parse_task_rows(prompt)
            if not facts or not rows:
                continue
            rows_by_owner = defaultdict(list)
            for row in rows:
                rows_by_owner[row["ownerId"]].append(row)
            fact_by_id = {fact["id"]: fact for fact in facts}
            cited = []
            seen_cited = set()
            for answer in answers:
                for entry in answer.get("achieved") or []:
                    owner = entry.get("characterId")
                    for item in entry.get("tasks") or []:
                        raw_task = item.get("taskId")
                        goal = None
                        task_id = raw_task if not re.fullmatch(r"t\d+", str(raw_task)) else None
                        if task_id is None:
                            goal = resolve_key(rows_by_owner, owner, raw_task)
                            if goal:
                                task_id = next((tid for (oid, tid), task in after.items()
                                                if oid == owner and task.get("goal") == goal), None)
                        else:
                            goal = ((after.get((owner, task_id)) or {}).get("goal")
                                    or goals.get(task_id))
                        basis = item.get("basis")
                        fact = fact_by_id.get(basis)
                        if owner and task_id and goal and fact:
                            key = (owner, task_id, fact["id"])
                            if key not in seen_cited:
                                seen_cited.add(key)
                                cited.append((owner, task_id, goal, fact))
            cited_keys = {(o, t) for o, t, _, _ in cited}
            for owner, task_id, goal, fact in cited:
                committed = after.get((owner, task_id))
                status = committed.get("status") if committed else None
                gold = "committed" if status == "achieved" else "conflict"
                rows_out.append({
                    "group": group, "file": path, "turn": turn.get("turn"),
                    "ownerId": owner, "taskId": task_id, "goal": goal,
                    "factId": fact["id"], "factText": fact["text"],
                    "label": "yes" if gold == "committed" else "no", "evidence": gold,
                    "outcome": outcome_of(fact["text"]),
                    "split": "eval_frozen" if frozen else "train",
                    "input": turn.get("input"),
                })
            # Achievements committed through the micro path have no cited basis in
            # the answer; attach the best completed fact for that goal instead.
            outcome_rank = {"completed": 3, "partial": 2, "failed": 1, "blocked": 1, "unaffected": 0, "unknown": 2}
            for owner, task_ids in coverage_achieved.items():
                for task_id in task_ids:
                    if (owner, task_id) in cited_keys:
                        continue
                    committed = after.get((owner, task_id))
                    if not committed or committed.get("status") != "achieved":
                        continue
                    goal = committed.get("goal") or goals.get(task_id)
                    candidates = [fact for fact in facts if relevant(goal or "", fact["text"], names)]
                    best = max(candidates, key=lambda fact: (outcome_rank[outcome_of(fact["text"])],
                                                            overlap(goal or "", fact["text"])), default=None)
                    if not best or outcome_rank[outcome_of(best["text"])] < 2:
                        continue
                    rows_out.append({
                        "group": group, "file": path, "turn": turn.get("turn"),
                        "ownerId": owner, "taskId": task_id, "goal": goal,
                        "factId": best["id"], "factText": best["text"],
                        "label": "yes", "evidence": "committed_best_fact",
                        "outcome": outcome_of(best["text"]),
                        "split": "eval_frozen" if frozen else "train",
                        "input": turn.get("input"),
                    })
            for row in rows:
                if row["status"] != "待办":
                    continue
                owner = row["ownerId"]
                task_id = next((tid for (oid, tid), task in after.items()
                                if oid == owner and task.get("goal") == row["goal"]), None)
                if not task_id:
                    continue
                if (owner, task_id) in cited_keys:
                    continue
                for fact in facts:
                    if not relevant(row["goal"], fact["text"], names):
                        continue
                    committed = after.get((owner, task_id))
                    status = committed.get("status") if committed else None
                    if status == "achieved":
                        continue  # achieved via another fact; pair is unknown, not negative
                    outcome = outcome_of(fact["text"])
                    # A completed fact that repeats most of the goal while the task
                    # stayed pending is a possible missed achievement, not a negative.
                    if outcome == "completed" and overlap(row["goal"], fact["text"]) >= 0.5:
                        rows_out.append({
                            "group": group, "file": path, "turn": turn.get("turn"),
                            "ownerId": owner, "taskId": task_id, "goal": row["goal"],
                            "factId": fact["id"], "factText": fact["text"],
                            "label": "unknown", "evidence": "conflict_missed", "outcome": outcome,
                            "split": "eval_frozen" if frozen else "train",
                            "input": turn.get("input"),
                        })
                        continue
                    rows_out.append({
                        "group": group, "file": path, "turn": turn.get("turn"),
                        "ownerId": owner, "taskId": task_id, "goal": row["goal"],
                        "factId": fact["id"], "factText": fact["text"],
                        "label": "no", "evidence": "silver_pending", "outcome": outcome,
                        "split": "eval_frozen" if frozen else "train",
                        "input": turn.get("input"),
                    })
    return rows_out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--glob", action="append", default=[])
    parser.add_argument("--frozen", action="append", default=[])
    parser.add_argument("--out", default="experiments/semantic-micro/task-pairs.jsonl")
    args = parser.parse_args()
    names, goals = load_world()
    all_rows = []
    for pattern in args.glob:
        for path in sorted(glob.glob(pattern)):
            if "independent-scenarios" in path:
                continue
            rows = process_file(path, False, names, goals)
            if rows:
                print(f"  {os.path.basename(path)}: {len(rows)}")
            all_rows.extend(rows)
    for path in args.frozen:
        rows = process_file(path, True, names, goals)
        print(f"  [frozen] {os.path.basename(path)}: {len(rows)}")
        all_rows.extend(rows)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = Counter((row["split"], row["label"], row["evidence"]) for row in all_rows)
    print(f"wrote {len(all_rows)} rows to {args.out}")
    for key, value in sorted(counts.items()):
        print(" ", key, value)
    print("groups:", len({row["group"] for row in all_rows if row["split"] == "train"}))


if __name__ == "__main__":
    main()
