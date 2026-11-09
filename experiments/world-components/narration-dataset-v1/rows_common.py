"""Shared row helpers: the trimmed "result" view of the after state.

The row keeps three blocks:

  上回合状态   the whole scoped scene before the round
  本回合变化   what happened, in the protocol's change vocabulary
  本回合状态   only the entities that changed, and only the fields that
               changed, carrying their settled values

Nothing unchanged is repeated in 本回合状态.
"""


def result_view(after_entity, ops, is_person):
    view = {}
    if "位置" in ops:
        view["位置"] = after_entity["位置"]
    if "精神值" in ops:
        view["精神值"] = after_entity["精神值"]
    if "新增外貌" in ops or "解除外貌" in ops:
        view["外貌"] = list(after_entity["外貌"])
    if "新增个性" in ops or "解除个性" in ops:
        view["个性"] = list(after_entity["个性"])
    if "完成任务" in ops or "新增小任务" in ops:
        tasks = {}
        for goal in ops.get("完成任务", []):
            if after_entity["任务"]["大任务"]["目标"] == goal:
                tasks["大任务"] = dict(after_entity["任务"]["大任务"])
            for task in after_entity["任务"]["小任务"]:
                if task["目标"] == goal:
                    tasks.setdefault("小任务", []).append(dict(task))
        for added in ops.get("新增小任务", []):
            goal = added["目标"]
            for task in after_entity["任务"]["小任务"]:
                if task["目标"] == goal:
                    tasks.setdefault("小任务", []).append(dict(task))
        view["任务"] = tasks
    return view


def build_result(after, changes):
    """Result block for a whole row: changed entities only, changed fields only."""
    result = {}
    for entity, ops in changes.items():
        if entity in after["人物"]:
            result[entity] = result_view(after["人物"][entity], ops, True)
        elif entity in after["物品"] or entity in after["地点"]:
            target = after["物品"].get(entity) or after["地点"][entity]
            view = {}
            if "新增外貌" in ops or "解除外貌" in ops:
                view["外貌"] = list(target["外貌"])
            result[entity] = view
        else:
            raise SystemExit(f"result view: unknown entity {entity!r}")
    return {name: view for name, view in result.items() if view}
