"""Row schema and validators for the action dataset.

A row is exactly the user's ten fields:

    rowId / source / worldId / characterId / x / y / yGroup / yRationale /
    labelSource / skipReason

`y` has one field, `steps`, with 0..2 `{action, object}` entries. `action` is
one of the 115 frozen fine predicates; `object` is an id from `x.candidates` or
null. An empty `steps` list is the skip class. Coarse groups never appear in
`action`; they are derived into `yGroup` (and evaluation).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .project_x import candidate_ids, contains_prompt_rule, validate_x_shape

ROW_KEYS = (
    "rowId",
    "source",
    "worldId",
    "characterId",
    "x",
    "y",
    "yGroup",
    "yRationale",
    "labelSource",
    "skipReason",
)
ROW_SOURCES = ("evidence-snapshot", "constructed")
LABEL_SOURCES = ("builder-judgment",)
SKIP_GROUP = "skip"
MAX_STEPS = 2
MAX_RATIONALE_CHARS = 400
BANNED_SKIP_PHRASES = ("不知道", "不明", "随便", "无理由", "无关")


class SchemaError(ValueError):
    """Raised when a frozen file (labels, criterion) is not the expected bytes."""


def load_labels(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    groups: list[dict[str, Any]] = payload["groups"]
    predicates: list[str] = []
    group_of: dict[str, str] = {}
    for group in groups:
        name = str(group["group"])
        for predicate in group["predicates"]:
            if predicate in group_of:
                raise SchemaError(f"predicate in two groups: {predicate}")
            group_of[predicate] = name
            predicates.append(predicate)
    if len(predicates) != int(payload.get("fineActionCount", len(predicates))):
        raise SchemaError(f"fine predicate count {len(predicates)} != declared {payload.get('fineActionCount')}")
    if len(groups) != int(payload.get("coarseActionCount", len(groups))):
        raise SchemaError(f"group count {len(groups)} != declared {payload.get('coarseActionCount')}")
    return {
        "version": payload.get("version"),
        "groups": [str(group["group"]) for group in groups],
        "predicates": predicates,
        "predicateSet": set(predicates),
        "groupOf": group_of,
        "playerFallbackLabel": payload.get("playerFallbackLabel"),
    }


def group_of_action(labels: dict[str, Any], action: str) -> str:
    return labels["groupOf"][action]


def expected_group(row: dict[str, Any], labels: dict[str, Any]) -> str:
    steps = row["y"]["steps"]
    return SKIP_GROUP if not steps else group_of_action(labels, steps[0]["action"])


def _task_ids(x: dict[str, Any]) -> set[str]:
    return {goal["id"] for goal in x["goals"]}


def _validate_goals_and_events(x: dict[str, Any]) -> list[str]:
    problems = validate_x_shape(x)
    for event in x.get("justNow", []):
        if contains_prompt_rule(event["text"]):
            problems.append(f"justNow[{event['seq']}] contains prompt rule text")
    return problems


def validate_row(row: dict[str, Any], labels: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    if set(row) != set(ROW_KEYS):
        problems.append(f"row keys are {sorted(row)}, expected {sorted(ROW_KEYS)}")
        return problems
    if not isinstance(row["rowId"], str) or not row["rowId"]:
        problems.append("rowId must be a non-empty string")
    if row["source"] not in ROW_SOURCES:
        problems.append(f"source not registered: {row['source']!r}")
    if row["labelSource"] not in LABEL_SOURCES:
        problems.append(f"labelSource not registered: {row['labelSource']!r}")
    if not isinstance(row["worldId"], str) or not row["worldId"]:
        problems.append("worldId must be a non-empty string")
    x = row["x"]
    if not isinstance(x, dict):
        problems.append("x must be an object")
        return problems
    problems.extend(_validate_goals_and_events(x))
    if x["actor"]["id"] != row["characterId"]:
        problems.append("characterId differs from x.actor.id")
    if not isinstance(row["y"], dict) or set(row["y"]) != {"steps"}:
        problems.append("y must have exactly one field: steps")
        return problems
    steps = row["y"]["steps"]
    if not isinstance(steps, list):
        problems.append("steps must be a list")
        return problems
    if len(steps) > MAX_STEPS:
        problems.append(f"steps has {len(steps)} entries, more than {MAX_STEPS}")
    ids = set(candidate_ids(x))
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or sorted(step) != ["action", "object"]:
            problems.append(f"step {index} must have exactly action and object")
            continue
        action = step["action"]
        obj = step["object"]
        if action not in labels["predicateSet"]:
            problems.append(f"step {index} action not one of the 115 fine predicates: {action!r}")
        if obj is not None:
            if not isinstance(obj, str):
                problems.append(f"step {index} object must be an id or null")
            elif obj not in ids:
                problems.append(f"step {index} object {obj!r} is not in x.candidates")
            elif obj == row["characterId"]:
                problems.append(f"step {index} object is the actor itself")
    derived = expected_group(row, labels) if not problems else None
    if derived is not None and row["yGroup"] != derived:
        problems.append(f"yGroup {row['yGroup']!r} != derived {derived!r}")
    rationale = row["yRationale"]
    if not isinstance(rationale, str) or len(rationale.strip()) < 8:
        problems.append("yRationale is missing or too short")
    elif len(rationale) > MAX_RATIONALE_CHARS:
        problems.append(f"yRationale longer than {MAX_RATIONALE_CHARS} chars")
    if contains_prompt_rule(rationale or ""):
        problems.append("yRationale contains prompt rule text")
    reason = row["skipReason"]
    if steps:
        if reason is not None:
            problems.append("skipReason must be null for a non-skip row")
    else:
        if not isinstance(reason, str) or len(reason.strip()) < 8:
            problems.append("skip row needs a written skipReason")
        if isinstance(reason, str):
            for banned in BANNED_SKIP_PHRASES:
                if banned in reason:
                    problems.append(f"skipReason uses uninformative wording: {banned}")
    if not problems and isinstance(rationale, str) and steps:
        # The rationale must point at something this row actually shows, so a
        # copied template cannot pass as a per-row judgement.
        mentioned = any(task_id in rationale for task_id in _task_ids(x))
        mentioned = mentioned or any(entry["id"] in rationale or entry["name"] in rationale for entry in x["candidates"])
        mentioned = mentioned or ("刚才" in rationale and bool(x["justNow"]))
        if not mentioned:
            problems.append("yRationale cites no task id, candidate, or event from this row")
    if not problems and isinstance(rationale, str) and not steps:
        # A skip needs a scene- or goal-based reason, not silence.
        cited_goal = any(task_id in (rationale + (reason or "")) for task_id in _task_ids(x))
        cited_scene = bool(x["present"]) or bool(x["objects"])
        if not cited_goal and not cited_scene and "待办" not in (rationale + (reason or "")):
            problems.append("skip rationale cites neither a goal nor a scene fact")
    return problems


def validate_dataset(rows: Iterable[dict[str, Any]], labels: dict[str, Any]) -> dict[str, Any]:
    problems: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_x: dict[str, str] = {}
    counts = {"rows": 0, "skip": 0, "oneStep": 0, "twoStep": 0}
    predicates: dict[str, int] = {}
    groups: dict[str, int] = {}
    sources: dict[str, int] = {}
    actors: dict[str, int] = {}
    for row in rows:
        counts["rows"] += 1
        row_problems = validate_row(row, labels)
        if row_problems:
            problems.append({"rowId": row.get("rowId"), "problems": row_problems})
        if not isinstance(row, dict) or "rowId" not in row:
            continue
        if row["rowId"] in seen_ids:
            problems.append({"rowId": row["rowId"], "problems": ["duplicate rowId"]})
        seen_ids.add(row["rowId"])
        try:
            from .project_x import serialize_x

            text = serialize_x(row["x"])
        except Exception as error:  # noqa: BLE001 - report, do not hide
            problems.append({"rowId": row["rowId"], "problems": [f"x cannot be serialized: {error}"]})
            continue
        if text in seen_x:
            problems.append({"rowId": row["rowId"], "problems": [f"identical X to {seen_x[text]}"]})
        seen_x[text] = row["rowId"]
        steps = row["y"]["steps"]
        if not steps:
            counts["skip"] += 1
            groups[SKIP_GROUP] = groups.get(SKIP_GROUP, 0) + 1
        else:
            counts["oneStep" if len(steps) == 1 else "twoStep"] += 1
            for step in steps:
                predicates[step["action"]] = predicates.get(step["action"], 0) + 1
            group = group_of_action(labels, steps[0]["action"])
            groups[group] = groups.get(group, 0) + 1
        sources[row.get("source", "?")] = sources.get(row.get("source", "?"), 0) + 1
        actors[row.get("characterId", "?")] = actors.get(row.get("characterId", "?"), 0) + 1
    total = counts["rows"] or 1
    return {
        "counts": counts,
        "skipRatio": round(counts["skip"] / total, 4),
        "groups": dict(sorted(groups.items())),
        "predicatesUsed": len(predicates),
        "predicatesUnused": [predicate for predicate in labels["predicates"] if predicate not in predicates],
        "sources": dict(sorted(sources.items())),
        "actors": dict(sorted(actors.items())),
        "problems": problems,
    }
