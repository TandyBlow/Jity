"""Check every dataset row.

The row keeps three blocks: the whole scoped scene before the round, the change
list, and a trimmed result block (changed entities, changed fields only). The
strong check -- that applying the declared changes to the before state gives
the after state, and that the before/after diff equals the declaration -- runs
inside the generators, where both full states still exist.

This file checks what a reader can still check from the written row:

  1. every entity in 本回合状态 also appears in 本回合变化, and every changed
     entity appears in 本回合状态;
  2. each field in 本回合状态 equals the before value with the declared change
     applied, and no unchanged field is repeated;
  3. no entity outside 本回合变化 shows up in 本回合状态.

usage: python verify_rows.py [row files...]
"""

import glob
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

PERSON_FIELDS = ("位置", "精神值", "外貌", "个性", "任务")


def task_entries(before_entity, ops):
    """The task entries a change should leave in the result block."""
    big = before_entity["任务"]["大任务"]
    small = {task["目标"]: dict(task) for task in before_entity["任务"]["小任务"]}
    out_big = None
    out_small = []
    for goal in ops.get("完成任务", []):
        if big["目标"] == goal:
            out_big = {"目标": goal, "状态": "已完成"}
        elif goal in small:
            out_small.append({"目标": goal, "状态": "已完成"})
        else:
            raise SystemExit(f"完成任务 {goal!r} is not in the before task tree")
    for added in ops.get("新增小任务", []):
        out_small.append({"目标": added["目标"], "状态": added.get("状态", "未完成")})
    tasks = {}
    if out_big:
        tasks["大任务"] = out_big
    if out_small:
        tasks["小任务"] = out_small
    return tasks


def expected_view(before_entity, ops, is_person):
    view = {}
    if "位置" in ops:
        view["位置"] = ops["位置"]
    if "精神值" in ops:
        view["精神值"] = ops["精神值"]
    if "新增外貌" in ops or "解除外貌" in ops:
        entries = list(before_entity["外貌"])
        for gone in ops.get("解除外貌", []):
            entries.remove(gone)
        entries.extend(ops.get("新增外貌", []))
        view["外貌"] = entries
    if "新增个性" in ops or "解除个性" in ops:
        entries = list(before_entity["个性"])
        for gone in ops.get("解除个性", []):
            entries.remove(gone)
        entries.extend(ops.get("新增个性", []))
        view["个性"] = entries
    if "完成任务" in ops or "新增小任务" in ops:
        view["任务"] = task_entries(before_entity, ops)
    return view


def normalise_tasks(view):
    view = dict(view)
    for field in ("外貌", "个性"):
        if field in view:
            view[field] = sorted(view[field])
    if "任务" not in view:
        return view
    tasks = dict(view["任务"])
    if "小任务" in tasks:
        tasks["小任务"] = sorted(tasks["小任务"], key=lambda task: task["目标"])
    view["任务"] = tasks
    return view


def check(path):
    row = json.loads(io.open(path, encoding="utf-8").read())
    before, delta, result = row["上回合状态"], row["本回合变化"], row["本回合状态"]
    changes = delta["变化"]
    people = before["人物"]
    places = before["地点"]
    things = before["物品"]

    problems = []
    if set(result) != set(changes):
        problems.append(f"result entities {sorted(result)} != changed {sorted(changes)}")

    for entity, ops in changes.items():
        if entity not in result:
            continue
        if entity in people:
            expected = normalise_tasks(expected_view(people[entity], ops, True))
        elif entity in things or entity in places:
            base = (things.get(entity) or places[entity])
            expected = expected_view(base, ops, False)
        else:
            problems.append(f"{entity}: not present in the before state")
            continue
        expected = normalise_tasks(expected)
        actual = normalise_tasks(result[entity])
        for field in sorted(set(expected) | set(actual)):
            if field not in expected:
                problems.append(f"{entity}.{field}: repeated although unchanged")
            elif field not in actual:
                problems.append(f"{entity}.{field}: missing from the result block")
            elif expected[field] != actual[field]:
                problems.append(f"{entity}.{field}: expected {expected[field]!r} "
                                f"got {actual[field]!r}")

    size = len(io.open(path, encoding="utf-8").read())
    line = f"{os.path.basename(path)}: {size} chars, {len(changes)} changed entities"
    if problems:
        print(line + "  MISMATCH")
        for problem in problems:
            print("    " + problem)
        return False
    print(line + "  ok")
    return True


def main():
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(HERE, "row-*-scene.jsonl")) +
                                   glob.glob(os.path.join(HERE, "row-scene-only.jsonl")))
    ok = True
    for path in paths:
        ok = check(path) and ok
    print("ALL OK" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
