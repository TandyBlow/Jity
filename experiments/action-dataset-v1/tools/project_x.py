"""Own-character projection (X) in the loader's frozen shape.

The row's `x` is consumed by 04's trainer through
`worktrees/04-settlement/experiments/action-next-step/serialize.py`
(`action-next-step-x1`), so this module does **not** define a second serializer.
It projects the nine slots into exactly the keys that serializer reads:

    角色 character / 目标 goals / 地点 place / 在场 present / 物品 items /
    刚才 recent / 精神 sanity / 个性 personality / 候选 candidates

`character` additionally carries `appearance` and `holds`; the frozen renderer
ignores unknown keys today (requested rendering change to 04 is recorded in
`results/action-dataset-20261111/13-to-04-x-shape.md`), and the two keys are
how the row keeps gear/wounds visible to a human reviewer in the meantime.

What X must contain is decided by the character's own knowledge:

- `present` / `items` only cover the character's innermost room (container
  chains resolved like the product's `prompt.ts:roomOf`); there is no absent
  list and no other room's text;
- `recent` carries only perceivable in-room happenings, never engine logs
  ("任务x已完成", "移动到") and never narration prose;
- `goals` is the character's own pending tasks, `sanity` their sanity,
  `personality` their personality text;
- `candidates` is exactly the id set a step's `object` may point at:
  same-room characters, same-room items, and the actor's carried items.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import state_view

X_SLOT_ORDER = (
    "character",
    "goals",
    "place",
    "present",
    "items",
    "recent",
    "sanity",
    "personality",
    "candidates",
)
LOADER_SERIALIZER = "action-next-step-x1"
EVENT_KINDS = ("position", "appearance", "item")
MAX_EVENT_CHARS = 60

# Phrasings that are engine logs rather than something a character perceives.
ENGINE_EVENT_MARKERS = (
    "移动到",
    "位置变为",
    "外观出现变化",
    "个性出现变化",
    "理智变为",
    "任务",
    "已完成",
    "entityDeltas",
    "slot",
)

PROMPT_RULE_MARKERS = (
    "只输出 JSON",
    "待办任务只是方向",
    "不要复述",
    "输出只能是",
    "你是中文跑团游戏",
)


class ProjectionError(ValueError):
    """Raised when a snapshot or event list cannot produce a faithful X."""


def _clean(text: str) -> str:
    text = " ".join(str(text).split())
    return text[:-1] + "…" if len(text) > MAX_EVENT_CHARS else text


def _goal_entries(state: dict[str, Any], actor_id: str) -> list[dict[str, Any]]:
    tasks = state_view.character_task_list(state, actor_id)
    by_id = {task["id"]: task for task in tasks}
    goals = []
    for task in tasks:
        if task.get("status") != "pending":
            continue
        parent = task.get("parentTaskId")
        depth = 0
        walker = parent
        seen: set[str] = set()
        while walker and walker not in seen:
            seen.add(walker)
            depth += 1
            walker = by_id.get(walker, {}).get("parentTaskId")
        goals.append(
            {
                "id": str(task["id"]),
                "goal": str(task["goal"]),
                "parentId": str(parent) if parent else None,
                "depth": depth,
            }
        )
    return goals


def _present(state: dict[str, Any], room_id: str, actor_id: str) -> list[dict[str, Any]]:
    entries = []
    for character_id in state_view.room_characters(state, room_id, exclude=actor_id):
        initial = state["initial"]["characters"][character_id]
        current = state["characters"][character_id]
        entries.append(
            {
                "id": character_id,
                "name": str(initial["name"]),
                "place": state_view.position_label(state, character_id),
                "appearance": [str(initial.get("initialAppearance") or "")]
                + state_view.active_text(current.get("appearanceChanges")),
            }
        )
    return entries


def _items(state: dict[str, Any], room_id: str, actor_id: str) -> list[dict[str, Any]]:
    entries = []
    for item in state_view.room_items(state, room_id, exclude_held_by=actor_id):
        entries.append(
            {
                "id": item["id"],
                "name": item["name"],
                "place": item["position"],
                "appearance": item["appearance"],
            }
        )
    return entries


def _event_check(event: dict[str, Any], room_id: str, state: dict[str, Any]) -> str:
    """Validate one `刚才` sentence; return its cleaned text."""
    if not isinstance(event, dict):
        raise ProjectionError(f"event is not an object: {event!r}")
    missing = {"seq", "kind", "roomId", "text"} - set(event)
    if missing:
        raise ProjectionError(f"event missing keys {sorted(missing)}: {event!r}")
    if event["kind"] not in EVENT_KINDS:
        raise ProjectionError(f"event kind not registered: {event['kind']!r}")
    if event["roomId"] != room_id:
        raise ProjectionError(f"event from another room passed the filter: {event!r}")
    if any(character in str(event["text"]) for character in ("\n", "\r", "\t")):
        raise ProjectionError(f"event text contains a control character: {event['text']!r}")
    text = _clean(event["text"])
    if not text:
        raise ProjectionError(f"event text is empty: {event!r}")
    for marker in ENGINE_EVENT_MARKERS:
        if marker in text:
            raise ProjectionError(f"event reads like an engine log ({marker}): {text!r}")
    for marker in PROMPT_RULE_MARKERS:
        if marker in text:
            raise ProjectionError(f"event carries prompt rule text: {text!r}")
    return text


def _recent(events: Iterable[dict[str, Any]], room_id: str, state: dict[str, Any]) -> list[str]:
    kept = []
    for event in events:
        if event.get("roomId") != room_id:
            continue
        kept.append((int(event["seq"]), _event_check(event, room_id, state)))
    kept.sort(key=lambda item: item[0])
    return [text for _, text in kept]


def project_x(
    state: dict[str, Any],
    actor_id: str,
    *,
    events: Iterable[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Build the nine-slot X for one character in one snapshot."""
    actor = state["characters"].get(actor_id)
    if actor is None:
        raise ProjectionError(f"actor_unknown:{actor_id}")
    initial_actor = state["initial"]["characters"][actor_id]
    room_id = state_view.room_of(state, actor_id)
    room = state["initial"]["locations"].get(room_id)
    if room is None:
        raise ProjectionError(f"room_not_a_location:{actor_id}->{room_id}")

    present = _present(state, room_id, actor_id)
    items = _items(state, room_id, actor_id)
    holds = state_view.held_items(state, actor_id)
    candidates = [{"id": entry["id"], "name": entry["name"], "type": "人物"} for entry in present]
    candidates += [
        {"id": entry["id"], "name": entry["name"], "type": "物品", "place": entry.get("place")}
        for entry in sorted(
            holds + [{"id": item["id"], "name": item["name"], "place": item["place"]} for item in items],
            key=lambda entry: entry["id"],
        )
    ]
    goals = _goal_entries(state, actor_id)
    return {
        "character": {
            "id": actor_id,
            "name": str(initial_actor["name"]),
            "place": state_view.position_label(state, actor_id),
            "appearance": [str(initial_actor.get("initialAppearance") or "")]
            + state_view.active_text(actor.get("appearanceChanges")),
            "holds": holds,
        },
        "goals": [f"{goal['id']}：{goal['goal']}" for goal in goals],
        "place": "{name}（{chain}）；时间={time}".format(
            name=state_view.location_name(state, room_id),
            chain=" < ".join(state_view.room_chain(state, room_id)),
            time=state["time"]["dateTime"],
        ),
        "present": present,
        "items": items,
        "recent": _recent(events, room_id, state),
        "sanity": int(actor["sanity"]),
        "personality": "；".join(
            [str(initial_actor.get("initialPersonality") or "")]
            + state_view.active_text(actor.get("personalityChanges"))
        ),
        "candidates": candidates,
    }


def goal_ids(x: dict[str, Any]) -> list[str]:
    """Task ids carried by the goal strings (`task_x：goal`)."""
    ids = []
    for goal in x["goals"]:
        ids.append(str(goal).split("：", 1)[0].strip())
    return ids


def candidate_ids(x: dict[str, Any]) -> list[str]:
    return [entry["id"] for entry in x["candidates"]]


def validate_x_shape(x: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if set(x) != set(X_SLOT_ORDER):
        problems.append(f"x slots are {sorted(x)}, expected {sorted(X_SLOT_ORDER)}")
        return problems
    character = x["character"]
    actor_id = character.get("id")
    if not actor_id:
        problems.append("character.id missing")
    if not isinstance(x["goals"], list) or not all(isinstance(goal, str) and "：" in goal for goal in x["goals"]):
        problems.append("goals must be a list of 'id：goal' strings")
    if not isinstance(x["place"], str) or not x["place"]:
        problems.append("place must be a non-empty string")
    if not isinstance(x["sanity"], int):
        problems.append("sanity must be an integer")
    if not isinstance(x["personality"], str) or not x["personality"]:
        problems.append("personality must be a non-empty string")
    if not isinstance(x["recent"], list) or not all(isinstance(item, str) for item in x["recent"]):
        problems.append("recent must be a list of strings")
    ids = [entry["id"] for entry in x["candidates"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate candidate ids")
    if actor_id and any(entry["id"] == actor_id for entry in x["present"]):
        problems.append("actor appears in present")
    if any(entry["id"] not in ids for entry in x["present"]):
        problems.append("present entry missing from candidates")
    if any(entry["id"] not in ids for entry in x["items"]):
        problems.append("item entry missing from candidates")
    for held in character.get("holds", []):
        if held["id"] not in ids:
            problems.append(f"held item {held['id']} missing from candidates")
    if x["items"] and any(entry["id"] in {held["id"] for held in character.get("holds", [])} for entry in x["items"]):
        problems.append("a held item is also listed under room items")
    for entry in x["candidates"]:
        if not entry.get("name"):
            problems.append(f"candidate {entry['id']} has no name")
    for text in x["recent"]:
        for marker in ENGINE_EVENT_MARKERS:
            if marker in text:
                problems.append(f"recent line reads like an engine log ({marker}): {text}")
    return problems


def contains_prompt_rule(text: str) -> str | None:
    for marker in PROMPT_RULE_MARKERS:
        if marker in text:
            return marker
    return None
