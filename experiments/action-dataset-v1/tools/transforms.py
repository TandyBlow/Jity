"""Deterministic state transforms for constructed scenarios.

A constructed row starts from a real base state (the committed static world, or
one extracted evidence snapshot) and applies an ordered, explicit transform
list. Nothing else is allowed to touch the state:

    {"op": "move", "entityId": "chu", "containerId": "top", "slotId": null}
    {"op": "appearance", "entityId": "lin", "text": "脚踝已经用绷带固定"}
    {"op": "personality", "entityId": "lu", "text": "已经答应替诺诺跑一趟"}
    {"op": "sanity", "entityId": "lin", "value": 20}
    {"op": "achieveTask", "ownerId": "su", "taskId": "task_su_report"}
    {"op": "addSubtask", "ownerId": "su", "task": {...}}

Every transform is verified against the state it is applied to: entities must
exist, slots must belong to the named container, sanity stays in [0, 100],
tasks must belong to their owner and still be pending, and a move may not put
an entity inside itself. Any failure raises `TransformError` with the index.

`events_from_transforms` restates each applied transform as a room-scoped
`刚才` event, using the state *after* the whole sequence, so an event's room is
the room the entity is actually in when the row is projected.
"""
from __future__ import annotations

import copy
from typing import Any

from . import state_view


class TransformError(ValueError):
    """Raised when a transform is not legal for the state it is applied to."""


def _require_entity(state: dict[str, Any], entity_id: str) -> str:
    if entity_id in state["characters"]:
        return "character"
    if entity_id in state["items"]:
        return "item"
    raise TransformError(f"unknown entity: {entity_id}")


def _slot_exists(state: dict[str, Any], container_id: str, slot_id: str | None) -> bool:
    if slot_id is None:
        return True
    return any(slot["id"] == slot_id for slot in state_view.container_slots(state, container_id))


def _container_exists(state: dict[str, Any], container_id: str) -> bool:
    return (
        container_id in state["initial"]["locations"]
        or container_id in state["characters"]
        or container_id in state["items"]
    )


def _would_cycle(state: dict[str, Any], entity_id: str, container_id: str) -> bool:
    node: str | None = container_id
    seen: set[str] = set()
    while node and node not in seen:
        if node == entity_id:
            return True
        seen.add(node)
        entity = state["characters"].get(node) or state["items"].get(node)
        if not entity:
            return False
        node = entity["position"]["containerId"]
    return False


def _next_change_id(state: dict[str, Any], entity_id: str, kind: str) -> str:
    entity = state["characters"].get(entity_id) or state["items"].get(entity_id)
    used = {change["id"] for change in entity.get(f"{kind}Changes", [])}
    index = 1
    while f"chg_{entity_id}_{kind[:4]}_{index}" in used:
        index += 1
    return f"chg_{entity_id}_{kind[:4]}_{index}"


def apply_transform(state: dict[str, Any], transform: dict[str, Any], index: int) -> dict[str, Any]:
    op = transform.get("op")
    if op == "move":
        entity_id = transform["entityId"]
        _require_entity(state, entity_id)
        container_id = transform["containerId"]
        if not _container_exists(state, container_id):
            raise TransformError(f"transform {index}: unknown container {container_id}")
        if _would_cycle(state, entity_id, container_id):
            raise TransformError(f"transform {index}: move would create a container cycle")
        slot_id = transform.get("slotId")
        if not _slot_exists(state, container_id, slot_id):
            raise TransformError(f"transform {index}: slot {slot_id} not on {container_id}")
        entity = state["characters"].get(entity_id) or state["items"][entity_id]
        entity["position"] = {"containerId": container_id, "slotId": slot_id, "relativeTo": None}
        return {"index": index, "op": op, "entityId": entity_id, "to": f"{container_id}/{slot_id}"}
    if op in ("appearance", "personality"):
        entity_id = transform["entityId"]
        _require_entity(state, entity_id)
        text = str(transform.get("text", "")).strip()
        if not text:
            raise TransformError(f"transform {index}: empty {op} text")
        if len(text) > 200:
            raise TransformError(f"transform {index}: {op} text longer than 200 chars")
        entity = state["characters"].get(entity_id) or state["items"][entity_id]
        field = f"{op}Changes"
        supersedes = list(transform.get("supersedes") or [])
        active_ids = {change["id"] for change in entity.get(field, []) if change.get("active")}
        missing = [change for change in supersedes if change not in active_ids]
        if missing:
            raise TransformError(f"transform {index}: supersedes unknown active change(s) {missing}")
        for change in entity.setdefault(field, []):
            if change["id"] in supersedes:
                change["active"] = False
        entity[field].append(
            {
                "id": transform.get("id") or _next_change_id(state, entity_id, op),
                "text": text,
                "active": True,
                "supersedes": supersedes,
            }
        )
        return {"index": index, "op": op, "entityId": entity_id, "text": text}
    if op == "sanity":
        entity_id = transform["entityId"]
        _require_entity(state, entity_id)
        if entity_id not in state["characters"]:
            raise TransformError(f"transform {index}: sanity applies to characters only")
        value = transform["value"]
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise TransformError(f"transform {index}: sanity {value!r} outside 0..100")
        state["characters"][entity_id]["sanity"] = value
        return {"index": index, "op": op, "entityId": entity_id, "value": value}
    if op == "achieveTask":
        owner_id = transform["ownerId"]
        task_id = transform["taskId"]
        if owner_id not in state["characters"]:
            raise TransformError(f"transform {index}: unknown task owner {owner_id}")
        tasks = state["characters"][owner_id]["tasks"]
        task = tasks.get(task_id)
        if not task:
            raise TransformError(f"transform {index}: {owner_id} has no task {task_id}")
        if task["status"] != "pending":
            raise TransformError(f"transform {index}: task {task_id} is already {task['status']}")
        task["status"] = "achieved"
        return {"index": index, "op": op, "ownerId": owner_id, "taskId": task_id}
    if op == "addSubtask":
        owner_id = transform["ownerId"]
        if owner_id not in state["characters"]:
            raise TransformError(f"transform {index}: unknown task owner {owner_id}")
        task = copy.deepcopy(transform["task"])
        if task.get("ownerId") != owner_id:
            raise TransformError(f"transform {index}: subtask owner differs")
        tasks = state["characters"][owner_id]["tasks"]
        if task["id"] in tasks:
            raise TransformError(f"transform {index}: task id already exists {task['id']}")
        if task.get("parentTaskId") not in tasks:
            raise TransformError(f"transform {index}: parent task missing {task.get('parentTaskId')}")
        task.setdefault("status", "pending")
        tasks[task["id"]] = task
        return {"index": index, "op": op, "ownerId": owner_id, "taskId": task["id"]}
    raise TransformError(f"transform {index}: unknown op {op!r}")


def apply_transforms(base_state: dict[str, Any], transforms: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply the whole ordered list to a deep copy; return state + records."""
    state = copy.deepcopy(base_state)
    records = []
    for index, transform in enumerate(transforms, start=1):
        records.append(apply_transform(state, transform, index))
    return state, records


def events_from_transforms(state: dict[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Room-scoped `刚才` events for the transforms that were applied.

    The text restates exactly the transform; the room is the entity's room in
    the final state. Events therefore cannot describe an outcome that did not
    happen and cannot tell a character about another room.
    """
    events = []
    for record in records:
        entity_id = record.get("entityId")
        if not entity_id:
            continue
        room_id = state_view.room_of(state, entity_id)
        name = state_view.entity_name(state, entity_id)
        if record["op"] == "move":
            text = f"{name}移动到{state_view.position_label(state, entity_id)}"
            kind = "position"
        elif record["op"] == "appearance":
            text = f"{name}的外观出现变化：{record['text']}"
            kind = "appearance"
        elif record["op"] == "personality":
            text = f"{name}的个性出现变化：{record['text']}"
            kind = "personality"
        elif record["op"] == "sanity":
            text = f"{name}的理智变为{record['value']}"
            kind = "sanity"
        else:
            continue  # task transforms belong to their owner, not the room
        events.append({"seq": record["index"], "kind": kind, "roomId": room_id, "text": text})
    for record in records:
        if record["op"] != "achieveTask":
            continue
        owner_id = record["ownerId"]
        events.append(
            {
                "seq": record["index"],
                "kind": "task",
                "roomId": state_view.room_of(state, owner_id),
                "text": f"{state_view.entity_name(state, owner_id)}的任务{record['taskId']}已完成",
            }
        )
    return events


def verify_constructed_state(state: dict[str, Any]) -> dict[str, Any]:
    """Post-construction invariants, recorded in the row's provenance."""
    problems: list[str] = []
    for character_id, character in state["characters"].items():
        if not _container_exists(state, character["position"]["containerId"]):
            problems.append(f"{character_id}: position container missing")
        if not 0 <= character["sanity"] <= 100:
            problems.append(f"{character_id}: sanity out of range")
        for task_id, task in character["tasks"].items():
            if task.get("ownerId") != character_id:
                problems.append(f"{character_id}: task {task_id} owner mismatch")
            parent = task.get("parentTaskId")
            if parent and parent not in character["tasks"]:
                problems.append(f"{character_id}: task {task_id} parent missing")
    for item_id, item in state["items"].items():
        if not _container_exists(state, item["position"]["containerId"]):
            problems.append(f"{item_id}: position container missing")
    for room_id, room in state["initial"]["locations"].items():
        parent = room.get("parentLocationId")
        if parent and parent not in state["initial"]["locations"]:
            problems.append(f"{room_id}: parent location missing")
    # every entity must sit in a real room, not in a dangling container
    for entity_id in list(state["characters"]) + list(state["items"]):
        room = state_view.room_of(state, entity_id)
        if room not in state["initial"]["locations"]:
            problems.append(f"{entity_id}: room is not a location ({room})")
    return {"ok": not problems, "problems": problems}
