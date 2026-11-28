#!/usr/bin/env python3
"""Build the human-labeled verifier benchmark (v1) from recorded cases.

The labels below were assigned by reading each (goal, fact) pair and asking
whether the fact completes every clause of the goal. `skip` means the goal text
is missing; `partial` means some but not all of the goal is shown.
"""
import json
import random

CASES = "experiments/semantic-micro/verifier-cases.jsonl"
OUT = "experiments/semantic-micro/bench-v1.jsonl"

SHEET1 = [  # 80 cases sorted: uncommitted yes, committed yes, no; ids 0-79
    "skip", "skip", "partial", "no", "no", "no", "no", "partial", "no", "no",
    "no", "no", "no", "no", "no", "yes", "no", "no", "no", "no",
    "no", "no", "no", "skip", "no", "no", "no", "no", "no", "skip",
    "no", "no", "no", "no", "no", "no", "no", "no", "no", "no",
    "no", "no", "no", "no", "no", "no", "no", "no", "no", "no",
    "no", "no", "no", "no", "no", "no", "no", "no", "no", "no",
    "no", "no", "no", "no", "no", "no", "no", "no", "skip", "no",
    "no", "partial", "no", "no", "skip", "no", "no", "no", "no", "partial",
]
SHEET2 = [  # seed-7 sample of 40 unique committed-yes cases
    "no", "no", "no", "no", "no", "no", "no", "no", "no", "no",
    "no", "no", "no", "partial", "no", "no", "no", "no", "no", "no",
    "no", "yes", "no", "no", "no", "no", "no", "no", "no", "partial",
    "no", "no", "no", "no", "yes", "no", "no", "no", "no", "no",
]


def main():
    rows = [json.loads(line) for line in open(CASES, encoding="utf-8") if line.strip()]
    seen = {}
    for row in rows:
        if not row.get("conditions"):
            continue
        key = ((row.get("goal") or ""), row["factText"])
        if key in seen:
            continue
        seen[key] = {
            "goal": row.get("goal") or "", "taskId": row["taskId"], "fact": row["factText"],
            "conditions": [c.get("label") for c in row["conditions"]],
            "llm": row.get("label"), "committed": row.get("committed"),
            "source": row.get("source"), "verdict": "",
        }
    cases = list(seen.values())
    order = lambda c: (0 if c["llm"] == "yes" and c["committed"] != "achieved" else 1 if c["llm"] == "yes" else 2)
    cases.sort(key=order)
    sheet1 = cases[:80]
    committed = [c for c in cases if c["llm"] == "yes" and c["committed"] == "achieved"]
    random.seed(7)
    random.shuffle(committed)
    sheet2 = [c for c in committed if c["goal"]][:40]
    out = []
    for index, (case, verdict) in enumerate(zip(sheet1, SHEET1)):
        out.append({**case, "id": f"h1-{index}", "sheet": "hard", "verdict": verdict})
    for index, (case, verdict) in enumerate(zip(sheet2, SHEET2)):
        out.append({**case, "id": f"h2-{index}", "sheet": "committed", "verdict": verdict})
    with open(OUT, "w", encoding="utf-8") as handle:
        for row in out:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    from collections import Counter
    print("wrote", len(out), "to", OUT, dict(Counter(row["verdict"] for row in out)))


if __name__ == "__main__":
    main()
