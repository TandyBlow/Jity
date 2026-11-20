# Deterministic one-slot serializer for the next-action classifier.
#
# X is ONE text sequence with one labelled slot per line, in this fixed order:
#     角色 目标 地点 在场 物品 刚才 精神 个性 候选
# Nothing else goes in: no rules text, no free-form action examples, no
# previous-turn prose, no remote room the character cannot know about. Each
# slot is projected from what this character knows (the product's knowledge
# sources), not from the whole world snapshot.
#
# The SAME function runs for training and inference. Its sha256 is registered
# in freeze.json; train.py refuses a different serializer.

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any, Dict, List, Sequence

HERE = pathlib.Path(__file__).resolve().parent
SERIALIZER_VERSION = "action-next-step-x1"
EMPTY = "（无）"
SLOTS = ("角色", "目标", "地点", "在场", "物品", "刚才", "精神", "个性", "候选")


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    raise TypeError(f"slot value must be text or number, got {type(value).__name__}")


def _entity(entry: Any, *, with_place: bool = False, with_holds: bool = False) -> str:
    """One entity as `id=name` (plus `（位置）` for items).

    The id is printed next to the name on purpose: the candidate pointer has to
    resolve to an id, and a model (or a person reading the row) cannot map a
    bare id to a name otherwise. That is the open protocol ambiguity recorded
    for 01/13; the serializer does not silently pick a different convention.
    """
    if isinstance(entry, str):
        return entry.strip()
    if not isinstance(entry, dict):
        raise TypeError("entity must be a string or an object")
    key = _text(entry.get("id")) or _text(entry.get("name"))
    name = _text(entry.get("name"))
    if not key:
        raise ValueError("entity without id or name")
    label = f"{key}={name}" if name and name != key else key
    kind = _text(entry.get("type"))
    if kind:
        label += f"（{kind}）"
    if with_place:
        place = _text(entry.get("place")) or _text(entry.get("position"))
        if place:
            label += f"@ {place}"
    if with_holds:
        # What the character is carrying is part of what he knows and can act on
        # right now. 13's X carries it as `character.holds`; without printing it
        # a held item is indistinguishable from one lying in a box.
        holds = entry.get("holds") or []
        if holds:
            label += "（持有：" + "；".join(_entity(hold) for hold in holds) + "）"
    return label


def _list_slot(entries: Sequence[Any] | None, *, with_place: bool = False, limit: int = 16) -> str:
    if not entries:
        return EMPTY
    out = [_entity(entry, with_place=with_place) for entry in entries]
    # A cap is a documented projection, not a silent truncation: the caller can
    # see it by comparing the row's candidate count with the printed count, and
    # measure_tokens.py reports how often the cap applies.
    if len(out) > limit:
        out = out[:limit] + [f"（另有 {len(out) - limit} 项未列出）"]
    return "；".join(out)


def row_x(row: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalise the X object of one row."""
    x = row.get("x")
    if not isinstance(x, dict):
        raise ValueError(f"{row.get('rowId', '?')}: x must be an object")
    character = x.get("character")
    if not isinstance(character, dict):
        raise ValueError(f"{row.get('rowId', '?')}: x.character must be an object")
    candidates = x.get("candidates") or []
    if not isinstance(candidates, list):
        raise ValueError(f"{row.get('rowId', '?')}: x.candidates must be a list")
    goals = x.get("goals")
    if goals is None:
        goal = x.get("goal")
        goals = [] if goal in (None, "") else [goal]
    if isinstance(goals, str):
        goals = [goals]
    if not isinstance(goals, list):
        raise ValueError(f"{row.get('rowId', '?')}: x.goals must be a list")
    return {
        "character": character,
        "goals": [_text(goal) for goal in goals if _text(goal)],
        "place": _text(x.get("place")),
        "present": x.get("present") or [],
        "items": x.get("items") or [],
        "recent": x.get("recent") or [],
        "sanity": x.get("sanity"),
        "personality": _text(x.get("personality")),
        "candidates": candidates,
    }


def render_x(row: Dict[str, Any]) -> str:
    x = row_x(row)
    recent = x["recent"]
    if isinstance(recent, str):
        recent = [recent]
    goals = x["goals"]
    lines = [
        f"角色：{_entity(x['character'], with_holds=True)}",
        f"目标：{'；'.join(goals) if goals else EMPTY}",
        f"地点：{x['place'] or EMPTY}",
        f"在场：{_list_slot(x['present'])}",
        f"物品：{_list_slot(x['items'], with_place=True)}",
        f"刚才：{'；'.join(_text(item) for item in recent) if recent else EMPTY}",
        f"精神：{_text(x['sanity']) or EMPTY}",
        f"个性：{x['personality'] or EMPTY}",
        f"候选：{_list_slot(x['candidates'], with_place=True)}",
    ]
    return "\n".join(lines)


def render_candidate(candidate: Any) -> str:
    """A candidate keeps its container/slot when the row has one: the pointer
    answer says which object, and where that object is decides whether the step
    is possible at all."""
    return _entity(candidate, with_place=True)


def candidate_ids(row: Dict[str, Any]) -> List[str]:
    ids: List[str] = []
    for candidate in row_x(row)["candidates"]:
        if isinstance(candidate, str):
            ids.append(candidate.strip())
            continue
        if not isinstance(candidate, dict):
            raise TypeError("candidate must be a string or an object")
        key = _text(candidate.get("id")) or _text(candidate.get("name"))
        if not key:
            raise ValueError("candidate without id or name")
        ids.append(key)
    if len(set(ids)) != len(ids):
        raise ValueError(f"{row.get('rowId', '?')}: duplicate candidate id")
    return ids


def object_index(row: Dict[str, Any], step: Dict[str, Any]) -> int:
    """0 = null (no object); 1..n = the candidate at that position."""
    target = step.get("object")
    if target in (None, "", "null"):
        return 0
    ids = candidate_ids(row)
    if target not in ids:
        raise ValueError(
            f"{row.get('rowId', '?')}: y step names object {target!r} which is not among the row's candidates {ids}"
        )
    return ids.index(target) + 1


def serializer_digest() -> str:
    body = pathlib.Path(__file__).read_bytes()
    return hashlib.sha256(body).hexdigest()


if __name__ == "__main__":
    sample = {
        "rowId": "demo",
        "x": {
            "character": {"id": "lu", "name": "路明非"},
            "goals": ["在自由一日结束前作出自己的参赛选择"],
            "place": "西回廊（走廊）",
            "present": [{"id": "nono", "name": "诺诺"}],
            "items": [{"id": "goggles_lu", "name": "护目镜", "place": "lu/slot_body"}],
            "recent": ["诺诺说红蓝两方在西回廊交火"],
            "sanity": 55,
            "personality": "犹豫，怕被卷进麻烦",
            "candidates": [{"id": "nono", "name": "诺诺"}, {"id": "west_arcade", "name": "西回廊"}],
        },
    }
    print(render_x(sample))
    print("digest", serializer_digest()[:16])
