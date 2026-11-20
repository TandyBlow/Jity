"""C6 prototype: N4.0 context adaptation for paragraph generation.

Scope: this module only *designs and demonstrates* the extra model-facing
context N4.0 lacks. It is not imported by the product and does not modify the
shared N4 renderer. See README.md for the hand-off to world-components.

Input: one point fixture with world, player input, previous narration,
committed events, facts and task state.
Output: a deterministic prompt section list / text, or a fail-closed error.

Design rules:
  - every string comes from the fixture; no world facts are invented here;
  - player input is required, and the model may not add player actions;
  - off-screen events are dropped or replaced by their observable result;
  - task blocked reasons are rendered only when the task is pending;
  - output is byte-stable for the same fixture.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

VERSION = "c6-n4-context-v0.1"

EVENT_KINDS = {
    "speech",
    "move",
    "attempt_failed",
    "item_transfer",
    "action",
    "observe",
    "wait",
}

FACT_KINDS = {"moved", "no_change", "outcome"}

STATUS_LABEL = {"pending": "进行中", "achieved": "已完成"}


class AdapterError(ValueError):
    def __init__(self, code: str, detail: Any = None):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail is not None else code)


def _text(obj: dict, key: str, code: str = "missing-field") -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(code, key)
    return value


def _entity(world: dict, entity_id: str) -> dict:
    for group in ("characters", "items", "locations"):
        table = world.get(group) or {}
        if entity_id in table:
            return table[entity_id]
    raise AdapterError("unknown-entity", entity_id)


def _name(world: dict, entity_id: str) -> str:
    return _text(_entity(world, entity_id), "name", "entity-name-missing")


def _location_path(world: dict, location_id: str) -> list[str]:
    locations = world.get("locations") or {}
    if location_id not in locations:
        raise AdapterError("unknown-location", location_id)
    path = [location_id]
    seen = {location_id}
    parent = locations[location_id].get("parent")
    while parent:
        if parent not in locations:
            raise AdapterError("unknown-location", parent)
        if parent in seen:
            raise AdapterError("location-cycle", location_id)
        path.append(parent)
        seen.add(parent)
        parent = locations[parent].get("parent")
    path.reverse()
    return path


def _location_name(world: dict, location_id: str) -> str:
    return _text(_entity(world, location_id), "name", "location-name-missing")


def _place(world: dict, place_id: str) -> str:
    locations = world.get("locations") or {}
    return _location_name(world, place_id) if place_id in locations else _name(world, place_id)


def _event_line(world: dict, event: dict) -> str:
    kind = event.get("kind")
    if kind not in EVENT_KINDS:
        raise AdapterError("unsupported-event-kind", kind)
    eid = _text(event, "id", "event-id-missing")
    actor_id = event.get("actor")
    actor = _name(world, actor_id) if actor_id else "—"

    if kind == "speech":
        text = _text(event, "text")
        manner = event.get("manner")
        suffix = f"（{manner}）" if manner else ""
        return f"{eid}｜说话｜{actor}{suffix}｜{text}"
    if kind == "move":
        src = _location_name(world, _text(event, "from"))
        dst = _location_name(world, _text(event, "to"))
        return f"{eid}｜移动｜{actor}｜{src}→{dst}"
    if kind == "attempt_failed":
        target = _name(world, event["target"]) if event.get("target") else "—"
        return f"{eid}｜受阻｜{actor}｜{target}：{_text(event, 'text')}"
    if kind == "item_transfer":
        item = _name(world, _text(event, "item"))
        src_id = _text(event, "from")
        dst_id = _text(event, "to")

        return f"{eid}｜物品交接｜{actor}｜{item}：{_place(world, src_id)}→{_place(world, dst_id)}"
    if kind == "action":
        return f"{eid}｜动作｜{actor}｜{_text(event, 'text')}"
    if kind == "observe":
        return f"{eid}｜观察｜{_text(event, 'text')}"
    # wait
    text = event.get("text")
    return f"{eid}｜等待｜{actor}｜{text}" if text else f"{eid}｜等待｜{actor}"


def _fact_line(world: dict, fact: dict) -> str:
    kind = fact.get("kind")
    if kind not in FACT_KINDS:
        raise AdapterError("unsupported-fact-kind", kind)
    fid = _text(fact, "id", "fact-id-missing")
    eid = fact.get("entityId")
    name = _name(world, eid) if eid else "—"
    if kind == "moved":
        src = _place(world, _text(fact, "from"))
        dst = _place(world, _text(fact, "to"))
        return f"{fid}｜移动｜{name}｜{src}→{dst}"
    if kind == "outcome":
        return f"{fid}｜结果｜{name}｜{_text(fact, 'resultText')}"
    return f"{fid}｜无变化｜{name}"


def build_point_input(world: dict, point: dict, index: int) -> dict:
    point_id = _text(point, "id", "point-id-missing")
    player_input = _text(point, "playerInput", "player-input-missing")
    location_id = _text(point, "location", "location-missing")
    path = _location_path(world, location_id)

    perspective_id = _text(point, "perspective", "perspective-missing")
    perspective = _name(world, perspective_id)

    previous = point.get("previousNarration")
    if index > 0 and (not isinstance(previous, str) or not previous.strip()):
        raise AdapterError("previous-narration-missing", point_id)
    if index == 0 and previous:
        raise AdapterError("first-point-has-previous-narration", point_id)

    diagnostics: list[dict] = []
    present_ids = point.get("present") or []
    if not isinstance(present_ids, list) or not present_ids:
        raise AdapterError("present-missing", point_id)
    present = [_name(world, eid) for eid in present_ids]

    visible_items = []
    for iid in point.get("visibleItems") or []:
        item = _entity(world, iid)
        visible_items.append(f"{_text(item, 'name')}={item.get('appearance', '')}")

    event_lines: list[str] = []
    seen_events: set[str] = set()
    for event in point.get("events") or []:
        eid = event.get("id")
        if not eid or eid in seen_events:
            raise AdapterError("event-id-duplicate-or-missing", eid)
        seen_events.add(eid)
        visible = event.get("visible")
        if not isinstance(visible, bool):
            raise AdapterError("event-visibility-missing", eid)
        if not visible:
            observable = event.get("observable")
            if observable:
                diagnostics.append({
                    "code": "event-offscreen-observable",
                    "eventId": eid,
                })
                event_lines.append(f"{eid}｜观察｜{observable}")
            else:
                diagnostics.append({
                    "code": "event-offscreen-omitted",
                    "eventId": eid,
                })
            continue
        event_lines.append(_event_line(world, event))

    fact_lines = [_fact_line(world, fact) for fact in point.get("facts") or []]

    task = point.get("task") or {}
    task_line = None
    if task:
        goal = _text(task, "goal", "task-goal-missing")
        status = task.get("status")
        if status not in STATUS_LABEL:
            raise AdapterError("task-status-unsupported", status)
        blocked = task.get("blockedReason")
        if blocked and status != "pending":
            raise AdapterError("achieved-task-with-blocked-reason", point_id)
        parts = [f"任务：{goal}｜{STATUS_LABEL[status]}"]
        if blocked:
            parts.append(f"受阻原因：{blocked}")
        task_line = "｜".join(parts)

    location_path = ">".join(_location_name(world, lid) for lid in path)
    appearance = "；".join(
        _text(_entity(world, lid), "appearance", "location-appearance-missing")
        for lid in path
    )

    lines = [
        "叙事任务。",
        f"视角：{perspective}｜第三人称限知",
        f"玩家输入：{player_input}",
        f"上一段正文：{previous.strip() if previous else '无（本点为首段）'}",
        f"场景：{location_path}",
        f"地点外貌：{appearance}",
        f"在场：{'、'.join(present)}",
        "可见物品：" + ("；".join(visible_items) if visible_items else "无"),
        "人物：",
    ]
    for eid in present_ids:
        char = _entity(world, eid)
        lines.append(
            f"{_text(char, 'name')}｜性格={char.get('personality', '')}"
            f"｜外貌={char.get('appearance', '')}"
        )

    lines.append("事件：")
    lines.extend(event_lines or ["（无）"])
    lines.append("事实：")
    lines.extend(fact_lines or ["（无）"])
    if task_line:
        lines.append(task_line)
    lines.extend([
        "要求：只写正文；不写面板、数值、字段名；"
        "不新增未列人物、物品、地点；不替玩家增加动作或台词；"
        "承接上一段正文；只写视角人物能感知的内容；事件顺序不得改动。",
        "正文：",
    ])

    text = "\n".join(lines) + "\n"
    return {
        "version": VERSION,
        "pointId": point_id,
        "input": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "diagnostics": diagnostics,
    }


def build_fixture(fixture: dict) -> list[dict]:
    world = fixture.get("world")
    points = fixture.get("points")
    if not isinstance(world, dict):
        raise AdapterError("world-missing")
    if not isinstance(points, list) or not points:
        raise AdapterError("points-missing")
    return [build_point_input(world, point, i) for i, point in enumerate(points)]
