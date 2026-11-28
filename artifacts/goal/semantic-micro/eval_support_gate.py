#!/usr/bin/env python3
"""Program condition gate vs the LLM verifier on recorded supports.

For each recorded support (goal, fact, conditions), decide whether the fact
satisfies every condition: action verb, confirmation word, item, target,
location, time, decision. The fact must also carry a completed outcome.

Reports acceptance on supports the LLM accepted, and rejection on supports the
LLM accepted but the task did not commit (hard negatives).
"""
import json
import re
from collections import Counter

CASES = "experiments/semantic-micro/verifier-cases.jsonl"
CONFIRM = ["确认", "报告", "说明", "告知", "问清", "核实", "看见", "检查", "证明", "登记", "回答", "听清", "核对"]


def outcome(text):
    for marker, label in (("达到目的", "completed"), ("只完成一部分", "partial"),
                          ("没有成功", "failed"), ("被阻止", "blocked"), ("没有变化", "unaffected")):
        if marker in text:
            return label
    return "unknown"


def condition_ok(label, fact):
    kind, _, value = label.partition("：")
    if kind == "action":
        return value in fact or value[:1] in fact
    if kind == "confirmation":
        if not any(word in fact for word in CONFIRM):
            return False
        at = min((fact.find(word) for word in CONFIRM if word in fact), default=-1)
        return at < 0 or not re.search(r"没有|没|未|不|拒绝|无法", fact[max(0, at - 4):at])
    if kind == "item":
        core = value.split("的")[-1]
        return core in fact or value in fact
    if kind in ("target", "location", "time"):
        return value in fact or (len(value) > 4 and value[-4:] in fact)
    if kind == "decision":
        return bool(re.search(r"决定|选择|选定|选了|就走|走这", fact))
    return True


def gate(row):
    text = row.get("factText") or ""
    conditions = row.get("conditions") or []
    if not conditions:
        return None
    if outcome(text) not in ("completed", "unknown"):
        return False
    return all(condition_ok(item.get("label") or "", text) for item in conditions)


def main():
    rows = [json.loads(line) for line in open(CASES, encoding="utf-8") if line.strip()]
    groups = {
        "accepted_committed": [r for r in rows if r.get("label") == "yes" and r.get("committed") == "achieved"],
        "accepted_uncommitted": [r for r in rows if r.get("label") == "yes" and r.get("committed") != "achieved"],
        "llm_no_pending": [r for r in rows if r.get("label") == "no" and r.get("committed") != "achieved"],
    }
    for name, items in groups.items():
        verdicts = Counter()
        for row in items:
            result = gate(row)
            verdicts["no_conditions" if result is None else ("accept" if result else "reject")] += 1
        print(f"{name:24s} n={len(items):4d} {dict(verdicts)}")
    print("\naccepted_uncommitted gate rejects (sample):")
    for row in groups["accepted_uncommitted"]:
        if gate(row) is False:
            print(" -", row["taskId"], "|", (row.get("goal") or "")[:36], "|", row["factText"][:60],
                  "|", [c.get("label") for c in row.get("conditions") or []])
            break
    print("\naccepted_uncommitted gate accepts (sample):")
    for row in groups["accepted_uncommitted"]:
        if gate(row) is True:
            print(" -", row["taskId"], "|", (row.get("goal") or "")[:36], "|", row["factText"][:60],
                  "|", [c.get("label") for c in row.get("conditions") or []])
            break


if __name__ == "__main__":
    main()
