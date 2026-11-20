"""Short pair serializer for the 13-way action-group experiment (v2).

One row becomes 13 short texts: the same context plus one candidate action group
(12 groups + 不动), and a single-logit head scores each text. This file is the
only official renderer: lane 13 imports it, it does not copy it.

Format (user-given, 2026-11-11):

    任务：<every unfinished goal, task id stripped, first 18 chars, | separated>
    所见：<own innermost place and slot>；在场：<up to 3 names>；物品：<up to 3 names>
    刚见：<the most recent perceivable event, first 30 chars>
    动作：<candidate group name or 不动>

Second step, same short context with one prefix line:

    已做：<first group>（<first object or 无>）

Deliberately absent: appearance paragraphs, judgement rules, worked example
sentences, previous-turn prose, other characters' rooms, sanity/personality.
The candidate entity table survives as per-pair metadata (id / name / type /
place) so an object experiment can reuse it without re-projecting the row; it is
not printed into the text by default (printing it changes the length, report it
separately).

Anything the format drops is recorded per pair under "omitted", so review and
lane 13 can see exactly what information was lost; nothing is silently cut.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

VERSION = "action-pairwise-x2"
SERIALIZER_PATH = Path(__file__).resolve()

GROUP_ORDER: List[str] = [
    "感知", "移动", "战斗", "援助", "请求", "胁迫",
    "言语", "算计", "情绪", "物品", "身体", "立场",
]
SKIP_GROUP = "不动"
ALL_GROUPS: List[str] = GROUP_ORDER + [SKIP_GROUP]
SKIP_INDEX = len(GROUP_ORDER)

GOAL_CHARS = 18
RECENT_CHARS = 30
PRESENT_LIMIT = 3
ITEM_LIMIT = 3
EMPTY = "（无）"

# Fields of a row that carry the answer must never reach the text.
LABEL_KEYS = ("y", "yGroup", "yRationale", "skipReason", "labelSource")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clip(text: str, limit: int) -> str:
    return text[:limit]


def strip_task_id(goal: str) -> str:
    """Goals arrive as "task_lu_goggles：把胸前的护目镜戴好…". The id is not part
    of the goal text and must not reach the model."""
    for sep in ("：", ":"):
        head, found, tail = goal.partition(sep)
        if found and tail.strip() and " " not in head.strip():
            return tail.strip()
    return goal.strip()


def _goals(x: Dict[str, Any]) -> List[str]:
    goals = x.get("goals")
    if goals is None:
        goal = x.get("goal")
        goals = [] if goal in (None, "") else [goal]
    if isinstance(goals, str):
        goals = [goals]
    if not isinstance(goals, list):
        raise ValueError("x.goals must be a list")
    out: List[str] = []
    for entry in goals:
        text = _text(entry)
        if text:
            out.append(strip_task_id(text))
    return out


def _place(value: Any, fallback: Any = None) -> str:
    """Innermost place plus slot (no ancestor chain) and the clock.

    The clock stays: lane 01's per-pair audit found the only 5 failing rows are
    time-gated skip decisions ("wait until 15:45"), which cannot be judged from a
    text that hides the time. Format: "服务巷/检修口 时间=15:20"."""
    text = _text(value)
    if not text:
        return f"{EMPTY} 时间=?"
    clock = ""
    if "时间=" in text:
        clock = text.split("时间=", 1)[1].strip()
    elif fallback is not None and "时间=" in _text(fallback):
        # The row-level place carries the clock when the character's own place
        # does not (the five time-gated skip rows lane 01 flagged).
        clock = _text(fallback).split("时间=", 1)[1].strip()
    body = text.split("时间=")[0].strip()
    innermost = body.split(" < ")[0].strip()
    short_clock = _short_clock(clock)
    return f"{innermost or EMPTY} 时间={short_clock or '?'}"


def _short_clock(value: str) -> str:
    """2009-10-17T15:20:00 -> 15:20."""
    text = value.strip()
    if "T" in text:
        text = text.split("T", 1)[1]
    return text[:5] if len(text) >= 5 else text


def _names(entries: Any, limit: int) -> tuple[List[str], List[str]]:
    """Names in order, plus the ones the limit dropped (for the omission log)."""
    if entries is None:
        return [], []
    if not isinstance(entries, list):
        entries = [entries]
    names: List[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = _text(entry.get("name")) or _text(entry.get("id"))
        else:
            name = _text(entry)
        if name:
            names.append(name)
    return names[:limit], names[limit:]


def _recent(x: Dict[str, Any]) -> tuple[str, int, int]:
    recent = x.get("recent")
    if recent is None:
        return EMPTY, 0, 0
    if isinstance(recent, str):
        recent = [recent]
    if not isinstance(recent, list):
        raise ValueError("x.recent must be a list or a string")
    texts = [_text(item) for item in recent if _text(item)]
    if not texts:
        return EMPTY, 0, 0
    chosen = texts[-1]
    return _clip(chosen, RECENT_CHARS), len(texts), len(chosen)


def candidate_table(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The entity table as metadata: id, name, type, place. Never printed into the
    short text unless a caller explicitly asks for the candidate variant."""
    x = row.get("x") or {}
    table: List[Dict[str, Any]] = []
    for entry in x.get("candidates") or []:
        if isinstance(entry, str):
            table.append({"id": entry.strip(), "name": entry.strip(), "type": None, "place": None})
            continue
        if not isinstance(entry, dict):
            raise TypeError("candidate must be a string or an object")
        table.append({
            "id": _text(entry.get("id")) or _text(entry.get("name")),
            "name": _text(entry.get("name")) or _text(entry.get("id")),
            "type": _text(entry.get("type")) or None,
            "place": _text(entry.get("place")) or None,
        })
    return table


def object_index(row: Dict[str, Any], step_index: int) -> Optional[int]:
    """1-based position in the candidate table, None when the step has no object.

    This is answer-side information: it is returned as metadata for the dataset
    and never rendered into the text."""
    import serialize as _v1  # the frozen v1 object mapping, reused not copied

    _object_index = getattr(_v1, "object_index")
    steps = ((row.get("y") or {}).get("steps") or [])
    if step_index >= len(steps):
        return None
    index = _object_index(row, steps[step_index])
    return index or None


def step_count(row: Dict[str, Any]) -> int:
    return len((row.get("y") or {}).get("steps") or [])


def row_group(
    row: Dict[str, Any],
    step_index: int = 0,
    predicate_to_group: Optional[Dict[str, str]] = None,
) -> str:
    """The coarse group of one step.

    `yGroup` is the coarse label of step 0 ("skip" for a skip row). A second
    step has no coarse label of its own: its `action` is a fine predicate, mapped
    through the frozen labels file (`predicate_to_group`), never guessed.
    """
    steps = ((row.get("y") or {}).get("steps") or [])
    group = _text(row.get("yGroup"))
    if group == "skip" or not steps:
        return SKIP_GROUP
    if step_index == 0:
        if group not in ALL_GROUPS:
            raise ValueError(f"{row.get('rowId', '?')}: unknown action group {group!r}")
        return group
    if step_index >= len(steps):
        raise ValueError(f"{row.get('rowId', '?')}: step {step_index} does not exist")
    fine = _text(steps[step_index].get("action"))
    if not fine:
        raise ValueError(f"{row.get('rowId', '?')}: step {step_index} has no fine predicate")
    if not predicate_to_group:
        raise ValueError(f"{row.get('rowId', '?')}: step {step_index} needs predicate_to_group")
    coarse = predicate_to_group.get(fine)
    if coarse not in ALL_GROUPS:
        raise ValueError(f"{row.get('rowId', '?')}: predicate {fine!r} is not in the frozen label list")
    return coarse


def short_context(row: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """The one short context and the omission record that belongs to it."""
    x = row.get("x")
    if not isinstance(x, dict):
        raise ValueError(f"{row.get('rowId', '?')}: x must be an object")
    character = x.get("character") or {}
    place = _place(character.get("place"), x.get("place"))
    goals = _goals(x)
    goals_clipped = [goal for goal in goals if len(goal) > GOAL_CHARS]
    present, present_omitted = _names(x.get("present"), PRESENT_LIMIT)
    items, items_omitted = _names(x.get("items"), ITEM_LIMIT)
    recent, recent_total, recent_length = _recent(x)
    task_line = "|".join(_clip(goal, GOAL_CHARS) for goal in goals)
    context = {
        "tasks": task_line,
        "place": place,
        "present": present,
        "items": items,
        "recent": recent,
    }
    omitted = {
        "goalsTotal": len(goals),
        "goalsClipped": len(goals_clipped),
        "goalsClippedIds": [goal[:12] for goal in goals_clipped],
        "presentShown": present,
        "presentOmitted": present_omitted,
        "itemsShown": items,
        "itemsOmitted": items_omitted,
        "recentTotal": recent_total,
        "recentChosenChars": recent_length,
        "recentClipped": recent_length > RECENT_CHARS,
        "timeIncluded": True,
        "droppedSections": [
            "appearance", "sanity", "personality", "rules", "previousProse",
            "otherRooms", "candidateTable(text)",
        ],
    }
    return context, omitted


def render_context(context: Dict[str, Any]) -> str:
    present = "，".join(context["present"]) if context["present"] else EMPTY
    items = "，".join(context["items"]) if context["items"] else EMPTY
    return "\n".join([
        f"任务：{context['tasks'] or EMPTY}",
        f"所见：{context['place']}；在场：{present}；物品：{items}",
        f"刚见：{context['recent']}",
    ])


def done_line(prior: Optional[Dict[str, Any]]) -> Optional[str]:
    """`已做：<coarse group>（<object name or id>）`. Lane 01's provisional audit
    used the object name ("已做：言语（路明非）") and judged it sufficient, so the
    name is preferred and the id is the fallback."""
    if not prior:
        return None
    group = _text(prior.get("group"))
    if group not in GROUP_ORDER:
        return None
    obj = _text(prior.get("objectName")) or _text(prior.get("object"))
    return f"已做：{group}（{obj or '无'}）"


def render_pair(
    context: Dict[str, Any],
    group: str,
    *,
    prior: Optional[Dict[str, Any]] = None,
) -> str:
    if group not in ALL_GROUPS:
        raise ValueError(f"unknown action group {group!r}")
    lines = [render_context(context)]
    prefix = done_line(prior)
    if prefix:
        lines.append(prefix)
    lines.append(f"动作：{group}")
    return "\n".join(lines)


def load_predicate_groups(path: str | Path) -> Dict[str, str]:
    """Fine predicate -> coarse group, from the frozen labels file."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    mapping: Dict[str, str] = {}
    for entry in data.get("groups") or []:
        group = _text(entry.get("group"))
        for predicate in entry.get("predicates") or []:
            name = _text(predicate)
            if not name:
                continue
            if name in mapping and mapping[name] != group:
                raise ValueError(f"predicate {name!r} appears in two groups")
            mapping[name] = group
    if not mapping:
        raise ValueError(f"{path}: no predicates found")
    return mapping


def pairs_for_step(
    row: Dict[str, Any],
    step_index: int = 0,
    *,
    context: Optional[Dict[str, Any]] = None,
    omitted: Optional[Dict[str, Any]] = None,
    predicate_to_group: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """13 pairs (12 groups + 不动) for one step. Exactly one is positive; a skip
    row's positive is 不动."""
    if context is None:
        context, omitted = short_context(row)
    label = row_group(row, step_index, predicate_to_group)
    steps = (row.get("y") or {}).get("steps") or []
    prior = None
    if step_index > 0:
        first = steps[0]
        # The prior step is named by its coarse group (a fine predicate such as
        # 提问 is not a candidate group); the object is the frozen first-step id.
        object_id = _text(first.get("object"))
        names = {entry["id"]: entry["name"] for entry in candidate_table(row)}
        prior = {
            "group": row_group(row, 0, predicate_to_group) if predicate_to_group else _text(row.get("yGroup")),
            "object": object_id,
            "objectName": names.get(object_id, "") if object_id else "",
        }
    index = object_index(row, step_index) if steps else None
    table = candidate_table(row)
    out: List[Dict[str, Any]] = []
    for group in ALL_GROUPS:
        text = render_pair(context, group, prior=prior)
        out.append({
            "rowId": row.get("rowId"),
            "characterId": row.get("characterId"),
            "stepIndex": step_index,
            "steps": step_count(row),
            "group": group,
            "label": 1 if group == label else 0,
            "text": text,
            "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "objectIndex": index,
            "candidates": table,
            "omitted": omitted,
            "prior": prior,
        })
    return out


def pairs_for_row(
    row: Dict[str, Any],
    predicate_to_group: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    context, omitted = short_context(row)
    out: List[Dict[str, Any]] = []
    for step_index in range(max(1, step_count(row))):
        out.extend(pairs_for_step(
            row, step_index, context=context, omitted=omitted,
            predicate_to_group=predicate_to_group,
        ))
    return out


def pairs_for_rows(
    rows: Iterable[Dict[str, Any]],
    predicate_to_group: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        out.extend(pairs_for_row(row, predicate_to_group))
    return out


def load_rows(path: str | Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def serializer_digest() -> str:
    """Source digest plus the frozen format constants, so a change to either is a
    frozen-input change."""
    hasher = hashlib.sha256()
    hasher.update(SERIALIZER_PATH.read_bytes())
    hasher.update(json.dumps({
        "version": VERSION,
        "groups": ALL_GROUPS,
        "goalChars": GOAL_CHARS,
        "recentChars": RECENT_CHARS,
        "presentLimit": PRESENT_LIMIT,
        "itemLimit": ITEM_LIMIT,
    }, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    return hasher.hexdigest()


def leak_check(row: Dict[str, Any], texts: Sequence[str]) -> List[str]:
    """Texts must not contain the labels or the rationale. Used by the tests and
    the dataset builder; an empty list means clean."""
    problems: List[str] = []
    rationale = _text(row.get("yRationale"))
    if rationale and any(rationale[:20] in text for text in texts):
        problems.append("rationale_in_text")
    for text in texts:
        for key in LABEL_KEYS:
            value = row.get(key)
            if isinstance(value, str) and len(value) > 4 and value in text:
                problems.append(f"{key}_in_text")
    return problems
