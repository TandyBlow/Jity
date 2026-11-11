"""Deterministic read-only views over one world-state snapshot.

Every helper here is a pure function of the snapshot (a `WorldState` dict as
produced by the product runtime and stored under `results/product/evidence`).
They mirror the product's own semantics so a dataset row describes the same
world the game shows:

- a character's room is the innermost location reached by following container
  chains (character -> item -> ... -> location), exactly like
  `frontend/src/lib/world-engine/local/prompt.ts:roomOf`;
- visible names come from `initial`, current values from the live tables;
- slot labels come from the container's own slot definitions, never from a
  hardcoded dictionary in this experiment.

No function here reads narration text or any other prose field.
"""
from __future__ import annotations

import json
from typing import Any, Iterable

State = dict[str, Any]


def active_text(changes: Iterable[dict[str, Any]] | None) -> list[str]:
    """Active stored description changes, in stored order."""
    return [str(change["text"]) for change in (changes or []) if change.get("active") and change.get("text")]


def entity_name(state: State, entity_id: str) -> str:
    initial = state["initial"]
    for table in ("characters", "items", "locations"):
        entry = initial[table].get(entity_id)
        if entry and entry.get("name"):
            return str(entry["name"])
    return entity_id


def location_name(state: State, location_id: str) -> str:
    entry = state["initial"]["locations"].get(location_id)
    return str(entry["name"]) if entry and entry.get("name") else location_id


def room_of(state: State, entity_id: str) -> str:
    """Innermost location containing the entity (characters included)."""
    node = entity_id
    seen: set[str] = set()
    while node not in state["initial"]["locations"]:
        if node in seen:
            return node
        seen.add(node)
        entity = state["characters"].get(node) or state["items"].get(node)
        if not entity:
            return node
        node = entity["position"]["containerId"]
    return node


def room_chain(state: State, room_id: str) -> list[str]:
    chain: list[str] = []
    node: str | None = room_id
    seen: set[str] = set()
    while node and node not in seen:
        seen.add(node)
        chain.append(location_name(state, node))
        entry = state["initial"]["locations"].get(node)
        node = entry.get("parentLocationId") if entry else None
    return chain


def container_slots(state: State, container_id: str) -> list[dict[str, Any]]:
    initial = state["initial"]
    for table in ("locations", "characters", "items"):
        entry = initial[table].get(container_id)
        if entry and entry.get("slots"):
            return [dict(slot) for slot in entry["slots"]]
    return []


def slot_label(state: State, container_id: str, slot_id: str | None) -> str | None:
    if not slot_id:
        return None
    for slot in container_slots(state, container_id):
        if slot.get("id") == slot_id:
            return str(slot.get("label") or slot_id)
    return slot_id


_RELATION_LABELS = {
    "under": "下面",
    "above": "上方",
    "beside": "旁边",
    "in_front_of": "前面",
    "behind": "后面",
}


def position_label(state: State, entity_id: str) -> str:
    """Human-readable position: container name plus slot label and relation."""
    entity = state["characters"].get(entity_id) or state["items"].get(entity_id)
    if not entity:
        raise KeyError(f"unknown entity position: {entity_id}")
    container_id = entity["position"]["containerId"]
    slot_id = entity["position"].get("slotId")
    location = state["initial"]["locations"].get(container_id)
    if location:
        container = str(location["name"])
    elif container_id in state["initial"]["items"]:
        container = f"{entity_name(state, container_id)}（在{location_name(state, room_of(state, container_id))}）"
    elif container_id in state["initial"]["characters"]:
        container = f"{entity_name(state, container_id)}身上"
    else:
        container = container_id
    slot = slot_label(state, container_id, slot_id)
    relative = ""
    relation = entity["position"].get("relativeTo")
    if relation:
        target = entity_name(state, relation["entityId"])
        word = _RELATION_LABELS.get(str(relation.get("relation")), str(relation.get("relation")))
        relative = f"，在{target}{word}"
    return f"{container}/{slot}{relative}" if slot else f"{container}{relative}"


def held_items(state: State, character_id: str) -> list[dict[str, str]]:
    """Items whose container is this character, sorted by id."""
    held = []
    for item_id in sorted(state["items"]):
        if state["items"][item_id]["position"]["containerId"] == character_id:
            held.append({"id": item_id, "name": entity_name(state, item_id)})
    return held


def item_entry(state: State, item_id: str) -> dict[str, Any]:
    initial = state["initial"]["items"][item_id]
    current = state["items"][item_id]
    return {
        "id": item_id,
        "name": str(initial["name"]),
        "position": position_label(state, item_id),
        "appearance": [str(initial.get("initialAppearance") or "")] + active_text(current.get("appearanceChanges")),
    }


def room_items(state: State, room_id: str, *, exclude_held_by: str | None = None) -> list[dict[str, Any]]:
    """Items reachable in the room, including items held by people in it."""
    found = []
    for item_id in sorted(state["items"]):
        if room_of(state, item_id) != room_id:
            continue
        if exclude_held_by and state["items"][item_id]["position"]["containerId"] == exclude_held_by:
            continue
        found.append(item_entry(state, item_id))
    return found


def room_characters(state: State, room_id: str, *, exclude: str | None = None) -> list[str]:
    return [
        character_id
        for character_id in sorted(state["characters"])
        if character_id != exclude and room_of(state, character_id) == room_id
    ]


def character_task_list(state: State, character_id: str) -> list[dict[str, Any]]:
    """Current tasks, pending first, then by id (stable)."""
    tasks = list(state["characters"][character_id]["tasks"].values())
    tasks.sort(key=lambda task: (0 if task.get("status") == "pending" else 1, str(task["id"])))
    return [dict(task) for task in tasks]


def canonical_bytes(value: Any) -> bytes:
    """Stable byte form used for every hash this experiment records."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
