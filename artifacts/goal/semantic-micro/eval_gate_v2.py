#!/usr/bin/env python3
"""Compare recorded (old) support conditions with conditions recomputed by the
fixed decomposition (ranked items + precondition stripping + earliest verb).

Usage: python artifacts/goal/semantic-micro/eval_gate_v2.py
"""
import json
import re
from collections import Counter

CASES = "experiments/semantic-micro/verifier-cases.jsonl"
WORLD = "data/worlds/dragon-raja-free-day.world.json"
CONFIRM = ["确认", "报告", "说明", "告知", "问清", "核实", "看见", "检查", "证明", "登记", "回答", "听清", "核对"]
TIME = re.compile(r"\d{1,2}:\d{2}|停赛前|结束前|午夜|天亮|天黑|明天|次日|黄昏|清晨|小时后|分钟后|入夜")
ACTION = ['前往', '走向', '走进', '进入', '赶到', '回到', '退到', '离开', '登上', '走到',
          '守住', '护住', '挡住', '拦住', '守', '递给', '交给', '戴上', '戴好', '拿起', '拿到', '取得',
          '获取', '开笼', '放出', '发布', '扣好', '恢复', '更换', '换上', '打开', '使用', '到达',
          '安排', '询问', '查明', '保留', '让出', '拖到', '推到', '拍', '搬', '移', '摆', '叠', '挂']

WORLD_DATA = json.load(open(WORLD, encoding="utf-8"))
INITIAL = WORLD_DATA.get("initial") or WORLD_DATA


def names(group):
    return [entity.get("name") or "" for entity in (INITIAL.get(group) or {}).values() if entity.get("name")]


CHARACTERS = names("characters")
ITEMS = names("items")
LOCATIONS = names("locations")


def longest_overlap(left, right):
    best = 0
    for i in range(len(left)):
        for j in range(i + 2, len(left) + 1):
            if left[i:j] in right:
                best = max(best, j - i)
    return best


def rank_items(text):
    strip = lambda value: value.replace("的", "")
    target = strip(text)
    scored = []
    for name in ITEMS:
        core = re.sub(r"^.+?的", "", name) or name
        plain = strip(name)
        overlap = max(longest_overlap(strip(core), target), longest_overlap(plain, target))
        tail = plain[-2:]
        bonus = 3 if len(tail) == 2 and tail in target else 0
        if overlap + bonus >= 2:
            scored.append((name, overlap + bonus))
    return sorted(scored, key=lambda row: -row[1])


def decompose(goal):
    action_text = re.sub(r"在[^，。；]*?[前后]", "", goal)
    item = None
    for name, _ in rank_items(goal):
        core = re.sub(r"^.+?的", "", name)
        if core in goal and (len(core) >= 3 or name in goal):
            item = name
            break
    target = next((name for name in CHARACTERS if name in goal), None)
    decision = None
    if re.search(r"选择|决定|选定|选一条", goal):
        match = re.search(r"选择[^，。；]*|决定[^，。；]*|选定[^，。；]*|选一条[^，。；]*", goal)
        decision = match.group(0) if match else "选择"
    location = None if decision else next((name for name in sorted(LOCATIONS, key=len, reverse=True) if name in goal), None)
    time = TIME.search(goal)
    confirmation = next((word for word in CONFIRM if word in goal), None)
    action, at = None, 10 ** 9
    for word in ACTION:
        index = action_text.find(word)
        if index < 0:
            continue
        if index < at or (index == at and action and len(word) > len(action)):
            action, at = word, index
    rows = []
    if time:
        rows.append(("time", time.group(0)))
    if location:
        rows.append(("location", location))
    if item:
        rows.append(("item", item))
    if target:
        rows.append(("target", target))
    if decision:
        rows.append(("decision", decision))
    if confirmation:
        rows.append(("confirmation", confirmation))
    if action:
        rows.append(("action", action))
    return [{"kind": kind, "value": value, "label": f"{kind}：{value}"} for kind, value in rows]


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
        return value.split("的")[-1] in fact or value in fact
    if kind in ("target", "location", "time"):
        return value in fact or (len(value) > 4 and value[-4:] in fact)
    if kind == "decision":
        return bool(re.search(r"决定|选择|选定|选了|就走|走这", fact))
    return True


def gate(conditions, fact):
    if not conditions:
        return None
    if outcome(fact) not in ("completed", "unknown"):
        return False
    return all(condition_ok(row["label"], fact) for row in conditions)


def main():
    rows = [json.loads(line) for line in open(CASES, encoding="utf-8") if line.strip()]
    seen = set()
    groups = {"accepted_committed": [], "accepted_uncommitted": [], "llm_no_pending": []}
    for row in rows:
        key = (row.get("taskId"), row.get("factText"))
        if key in seen:
            continue
        seen.add(key)
        if row.get("label") == "yes" and row.get("committed") == "achieved":
            groups["accepted_committed"].append(row)
        elif row.get("label") == "yes":
            groups["accepted_uncommitted"].append(row)
        elif row.get("label") == "no":
            groups["llm_no_pending"].append(row)
    for name, items in groups.items():
        old, new = Counter(), Counter()
        for row in items:
            goal = row.get("goal") or ""
            old_result = gate(row.get("conditions") or [], row["factText"]) if row.get("conditions") else None
            old_verdict = "no_conditions" if old_result is None else ("accept" if old_result else "reject")
            conditions = decompose(goal) if goal else []
            new_result = gate(conditions, row["factText"]) if conditions else None
            new_verdict = "no_conditions" if new_result is None else ("accept" if new_result else "reject")
            old[old_verdict] += 1
            new[new_verdict] += 1
        print(f"{name:24s} n={len(items):4d}\n  old {dict(old)}\n  new {dict(new)}")
    print("\nnew decomposition examples:")
    for goal in ["在进入交火区前拿到可用的护目镜与演习装备",
                 "在红方进入顶层前安排旗台的持守与撤退信号",
                 "让红方的旗台行动有可执行的掩护，而不把路明非当诱饵",
                 "若路明非求助，给出可验证的器材或路线帮助，而不是空口保证安全"]:
        print(" ", goal, "->", [row["label"] for row in decompose(goal)])


if __name__ == "__main__":
    main()
