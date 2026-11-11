"""Deterministic own-character projection (X) and its serializer.

X is one row of nine slots, in a fixed order:

    角色 / 目标 / 地点 / 在场 / 物品 / 刚才 / 精神 / 个性 / 候选

The projection answers one question only: what does *this* character know from
where they stand, right now? Therefore:

- 在场 and 物品 are limited to the character's own innermost room; characters
  and items elsewhere never appear (no absent list, no other rooms' text);
- 刚才 carries only structured, room-scoped happenings; narration prose, the
  player's sentence and the product prompt's rule lines are never copied in;
- 目标 holds the character's own pending tasks with their parent links;
- 精神 is the character's sanity; 个性 is the personality text (initial plus
  active changes);
- 候选 is exactly the set of ids a label's `object` may point at.

The serializer is the single text form shared by training and inference: it is
a pure function of the structured X, so the same row always renders the same
bytes. Nothing is truncated silently.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import state_view

X_SLOT_ORDER = (
    "actor",
    "goals",
    "place",
    "present",
    "objects",
    "justNow",
    "mind",
    "personality",
    "candidates",
)
SERIALIZER_VERSION = "action-x-v2"

# Text caps per serializer profile. Entity lists are never cut: every candidate
# in the structured X stays a legal `object` id, and every pending goal stays
# listed. Only long descriptive text is clipped, with an explicit ellipsis, and
# the number of clipped fields is reported so the shortening is never silent.
SERIALIZER_PROFILES: dict[str, dict[str, int | None]] = {
    "full": {
        "actorAppearance": None,
        "goal": None,
        "placeAppearance": None,
        "presentAppearance": None,
        "objectAppearance": None,
        "event": None,
        "personality": None,
        "itemName": None,
    },
    "tight": {
        "actorAppearance": 40,
        "goal": 40,
        "placeAppearance": 40,
        "presentAppearance": 20,
        "objectAppearance": 0,
        "event": 40,
        "personality": 40,
        "itemName": None,
    },
}
EVENT_KINDS = ("position", "appearance", "personality", "task", "sanity", "item")
MAX_EVENT_CHARS = 200

# Lines that belong to the product prompt as instructions, never to a data
# row. A row containing one of these would be leaking rule text into X.
PROMPT_RULE_MARKERS = (
    "只输出 JSON",
    "待办任务只是方向",
    "不要复述",
    "输出只能是",
    "你是中文跑团游戏",
)


class ProjectionError(ValueError):
    """Raised when a snapshot or event list cannot produce a faithful X."""


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
                "position": state_view.position_label(state, character_id),
                "appearance": [str(initial.get("initialAppearance") or "")]
                + state_view.active_text(current.get("appearanceChanges")),
            }
        )
    return entries


def _objects(state: dict[str, Any], room_id: str, actor_id: str) -> list[dict[str, Any]]:
    return state_view.room_items(state, room_id, exclude_held_by=actor_id)


def _events(events: Iterable[dict[str, Any]], room_id: str) -> list[dict[str, Any]]:
    kept = []
    for event in events:
        if not isinstance(event, dict):
            raise ProjectionError(f"event is not an object: {event!r}")
        missing = {"seq", "kind", "roomId", "text"} - set(event)
        if missing:
            raise ProjectionError(f"event missing keys {sorted(missing)}: {event!r}")
        if event["kind"] not in EVENT_KINDS:
            raise ProjectionError(f"event kind not registered: {event['kind']!r}")
        text = str(event["text"]).strip()
        if not text:
            raise ProjectionError(f"event text is empty: {event!r}")
        if len(text) > MAX_EVENT_CHARS:
            raise ProjectionError(f"event text exceeds {MAX_EVENT_CHARS} chars: {event['seq']!r}")
        if "\n" in text:
            raise ProjectionError(f"event text contains a newline: {event['seq']!r}")
        if event["roomId"] != room_id:
            # A happening in another room is not this character's knowledge.
            continue
        kept.append({"seq": int(event["seq"]), "kind": str(event["kind"]), "text": text})
    kept.sort(key=lambda item: (item["seq"], item["kind"], item["text"]))
    return kept


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
    objects = _objects(state, room_id, actor_id)
    holds = state_view.held_items(state, actor_id)
    candidates = [{"id": entry["id"], "kind": "character", "name": entry["name"]} for entry in present]
    candidates += [
        {"id": entry["id"], "kind": "item", "name": entry["name"]}
        for entry in sorted(holds + [{"id": item["id"], "name": item["name"]} for item in objects], key=lambda item: item["id"])
    ]

    return {
        "actor": {
            "id": actor_id,
            "name": str(initial_actor["name"]),
            "position": state_view.position_label(state, actor_id),
            "appearance": [str(initial_actor.get("initialAppearance") or "")]
            + state_view.active_text(actor.get("appearanceChanges")),
            "holds": holds,
        },
        "goals": _goal_entries(state, actor_id),
        "place": {
            "roomId": room_id,
            "name": state_view.location_name(state, room_id),
            "chain": state_view.room_chain(state, room_id),
            "appearance": [str(room.get("initialAppearance") or "")]
            + state_view.active_text(state["locations"].get(room_id, {}).get("appearanceChanges")),
            "slots": [
                {"id": str(slot["id"]), "label": str(slot.get("label") or slot["id"])}
                for slot in state_view.container_slots(state, room_id)
            ],
            "time": str(state["time"]["dateTime"]),
        },
        "present": present,
        "objects": objects,
        "justNow": _events(events, room_id),
        "mind": {"sanity": int(actor["sanity"])},
        "personality": [str(initial_actor.get("initialPersonality") or "")]
        + state_view.active_text(actor.get("personalityChanges")),
        "candidates": candidates,
    }


def candidate_ids(x: dict[str, Any]) -> list[str]:
    return [entry["id"] for entry in x["candidates"]]


def validate_x_shape(x: dict[str, Any]) -> list[str]:
    """Structural checks that do not need the world snapshot."""
    problems: list[str] = []
    if set(x) != set(X_SLOT_ORDER):
        problems.append(f"x slots are {sorted(x)}, expected {sorted(X_SLOT_ORDER)}")
        return problems
    actor_id = x["actor"].get("id")
    if not actor_id:
        problems.append("actor.id missing")
    if actor_id and any(entry["id"] == actor_id for entry in x["present"]):
        problems.append("actor appears in present")
    candidate_list = [entry["id"] for entry in x["candidates"]]
    if len(candidate_list) != len(set(candidate_list)):
        problems.append("duplicate candidate ids")
    if x["present"] and any(entry["id"] not in candidate_list for entry in x["present"]):
        problems.append("present entry missing from candidates")
    if x["objects"] and any(entry["id"] not in candidate_list for entry in x["objects"]):
        problems.append("object entry missing from candidates")
    for entry in x["candidates"]:
        if not entry.get("name"):
            problems.append(f"candidate {entry['id']} has no name")
    for entry in x["actor"].get("holds", []):
        if entry["id"] not in candidate_list:
            problems.append(f"held item {entry['id']} missing from candidates")
    if x["objects"] and any(entry["id"] in {held["id"] for held in x["actor"].get("holds", [])} for entry in x["objects"]):
        problems.append("a held item is also listed under room objects")
    # An empty goal list is legal (every task achieved): it is one of the
    # situations where a genuine skip row can come from.
    for goal in x["goals"]:
        if not goal.get("goal"):
            problems.append(f"goal {goal.get('id')} has no text")
    return problems


def contains_prompt_rule(text: str) -> str | None:
    for marker in PROMPT_RULE_MARKERS:
        if marker in text:
            return marker
    return None


def _cap(text: str, limit: int | None, clipped: dict[str, int], field: str) -> str:
    if limit is None or limit <= 0 or len(text) <= limit:
        return text
    clipped[field] = clipped.get(field, 0) + 1
    return text[: limit - 1] + "…"


def serialize_x(x: dict[str, Any], *, profile: str = "full") -> str:
    return serialize_report(x, profile=profile)["text"]


def serialize_report(x: dict[str, Any], *, profile: str = "full") -> dict[str, Any]:
    """Stable text form of X plus the measured clipping that produced it.

    `profile` selects a registered cap set (see SERIALIZER_PROFILES). Caps only
    shorten descriptive text; entity lists and candidate ids are never cut, so
    a label can always point at a candidate that is still visible in the text.
    """
    if profile not in SERIALIZER_PROFILES:
        raise ProjectionError(f"unknown serializer profile: {profile}")
    caps = SERIALIZER_PROFILES[profile]
    clipped: dict[str, int] = {}
    lines: list[str] = []

    actor = x["actor"]
    lines.append(f"【角色】{actor['name']}（id={actor['id']}）位置={actor['position']}")
    appearance = [_cap(part, caps["actorAppearance"], clipped, "actorAppearance") for part in actor.get("appearance", []) if part]
    if appearance:
        lines.append(f"  外貌：{'；'.join(appearance)}")
    if actor.get("holds"):
        lines.append("  随身：" + "；".join(f"{item['name']}（id={item['id']}）" for item in actor["holds"]))
    else:
        lines.append("  随身：无")

    lines.append("【目标】")
    if not x["goals"]:
        lines.append("- 无待办目标")
    for goal in x["goals"]:
        parent = f"；上级={goal['parentId']}" if goal.get("parentId") else "；顶层"
        lines.append(f"- {goal['id']}{parent}：{_cap(goal['goal'], caps['goal'], clipped, 'goal')}")

    place = x["place"]
    lines.append(f"【地点】{place['name']}（id={place['roomId']}）；层级={' < '.join(place['chain'])}；时间={place['time']}")
    place_appearance = [_cap(part, caps["placeAppearance"], clipped, "placeAppearance") for part in place.get("appearance", []) if part]
    if place_appearance:
        lines.append(f"  环境：{'；'.join(place_appearance)}")
    if place.get("slots"):
        lines.append("  位置：" + "；".join(f"{slot['label']}（id={slot['id']}）" for slot in place["slots"]))

    lines.append("【在场】")
    if not x["present"]:
        lines.append("- 无其他人在此地点")
    for entry in x["present"]:
        appearance = "；".join(
            _cap(part, caps["presentAppearance"], clipped, "presentAppearance") for part in entry.get("appearance", []) if part
        )
        lines.append(f"- {entry['name']}（id={entry['id']}）位置={entry['position']}；外貌={appearance}")

    lines.append("【物品】")
    if not x["objects"]:
        lines.append("- 本地点没有登记物品")
    for entry in x["objects"]:
        appearance = "；".join(
            _cap(part, caps["objectAppearance"], clipped, "objectAppearance") for part in entry.get("appearance", []) if part
        )
        suffix = f"；外观={appearance}" if appearance else ""
        lines.append(f"- {entry['name']}（id={entry['id']}）位置={entry['position']}{suffix}")

    lines.append("【刚才】")
    if not x["justNow"]:
        lines.append("- 无")
    for event in x["justNow"]:
        lines.append(f"- [{event['kind']}] {_cap(event['text'], caps['event'], clipped, 'event')}")

    lines.append(f"【精神】理智={x['mind']['sanity']}/100")
    personality = [_cap(part, caps["personality"], clipped, "personality") for part in x["personality"] if part]
    lines.append("【个性】" + ("；".join(personality) or "无"))
    lines.append(
        "【候选】"
        + ("；".join(f"{entry['name']}（id={entry['id']}，{entry['kind']}）" for entry in x["candidates"]) or "无")
    )
    text = "\n".join(lines)
    marker = contains_prompt_rule(text)
    if marker:
        raise ProjectionError(f"X serializer output contains prompt rule text: {marker}")
    return {
        "text": text,
        "chars": len(text),
        "profile": profile,
        "caps": {key: value for key, value in caps.items()},
        "clipped": dict(sorted(clipped.items())),
        "lines": len(lines),
    }


def x_char_length(x: dict[str, Any], profile: str = "full") -> int:
    return len(serialize_x(x, profile=profile))
