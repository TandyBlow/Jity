# -*- coding: utf-8 -*-
"""Reference serializer for the narration result-block format v2.

The legacy serializer (`experiments/world-components/narration-dataset-v1/yuyan/
convert_yuyan.py`) never wrote the `本回合状态` block.  This module writes it,
fixes item positions (the legacy place/item line read `位于`, while item rows
carry `位置`), and makes zero / empty-list results explicit.

It is deliberately strict: every problem raises `NarrationSerializeError` with a
stable `code` instead of silently dropping a field.  The same rules are what the
browser adapter (lane 01) has to reproduce byte for byte.
"""

from __future__ import annotations

import json
import collections
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA = "jity-narration-prose-v2"
PROJECTION_VERSION = "narration-result-view-v2"
SERIALIZER_VERSION = "yuyan-prose-result-v2"
MODEL_TEMPLATE_VERSION = "yuyan-raw-completion-v1"
LEGACY_SERIALIZER_VERSION = "yuyan-prose-legacy-v1"
LEGACY_PROJECTION_VERSION = "narration-result-view-v1"

TYPE_ORDER = ("地点", "人物", "物品")
TOP_LEVEL_FIELDS = ("视角", "上回合状态", "本回合变化", "本回合状态")
STATE_FIELDS = ("地点", "人物", "物品")

# Field order inside one result line.  The same order is used by the delta
# sentence builder, except that the delta uses the operation names.
RESULT_FIELDS = {
    "人物": ("位置", "精神值", "外貌", "个性", "任务"),
    "地点": ("位于", "外貌"),
    "物品": ("位置", "外貌"),
}
DELTA_FIELDS = (
    "位置",
    "精神值",
    "解除外貌",
    "新增外貌",
    "解除个性",
    "新增个性",
    "完成任务",
    "新增小任务",
)

BLOCK_VIEW = "视角"
BLOCK_PLACE = "地点"
BLOCK_PERSON = "人物"
BLOCK_ITEM = "物品"
BLOCK_DELTA = "变化"
BLOCK_RESULT = "本回合状态"
BLOCK_BODY = "正文"

HEADERS = {
    BLOCK_VIEW: "【视角】",
    BLOCK_PLACE: "【地点】",
    BLOCK_PERSON: "【人物】",
    BLOCK_ITEM: "【物品】",
    BLOCK_DELTA: "【变化】",
    BLOCK_RESULT: "【本回合状态】",
    BLOCK_BODY: "【正文】",
}

# Whitespace that the data builder is allowed to remove, with a ledger entry.
# Anything else (CR, LF, vertical tab, NBSP, ...) is rejected.
SQUASH_WHITESPACE = " \t\u3000"


class NarrationSerializeError(ValueError):
    """A structured serialization refusal.

    `code` is stable and is part of the golden contract.  `path` points at the
    exact field (for example `本回合状态/周叙白/精神值`).
    """

    def __init__(self, code: str, message: str, path: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path

    def as_dict(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message, "path": self.path}


@dataclass
class Segment:
    kind: str                 # state | delta | result
    block: str                # 地点 / 人物 / 物品 / 变化 / 本回合状态
    entity: str = ""
    entity_type: str = ""
    field: str = ""
    value: Any = None
    start: int = 0            # Unicode code-point offset into text
    end: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "block": self.block,
            "entity": self.entity,
            "entityType": self.entity_type,
            "field": self.field,
            "value": self.value,
            "charStart": self.start,
            "charEnd": self.end,
        }


@dataclass
class Serialized:
    text: str
    blocks: Dict[str, str] = field(default_factory=dict)
    segments: List[Segment] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {"text": self.text, "blocks": self.blocks,
                "segments": [segment.as_dict() for segment in self.segments]}


# --------------------------------------------------------------- utilities

def _fail(code: str, message: str, path: str = "") -> None:
    raise NarrationSerializeError(code, message, path)


def _expect_dict(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        _fail("expected_object", f"{path} must be an object, got {type(value).__name__}", path)
    return value


def _expect_list(value: Any, path: str) -> List[Any]:
    if not isinstance(value, list):
        _fail("expected_array", f"{path} must be an array, got {type(value).__name__}", path)
    return value


def _expect_str(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _fail("expected_string", f"{path} must be a string, got {type(value).__name__}", path)
    return value


def _expect_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("expected_integer", f"{path} must be an integer, got {type(value).__name__}", path)
    return value


def clean_text(text: str, path: str) -> str:
    """Reject whitespace the serializer cannot represent.

    The v2 projection builder removes ordinary space / tab / full-width space
    and records every removal.  The serializer itself refuses to do that, so a
    caller that skipped the builder cannot silently produce a different byte
    sequence.
    """
    if not isinstance(text, str):
        _fail("expected_string", f"{path} must be a string", path)
    if "\r" in text or "\n" in text:
        _fail("newline_not_allowed", f"{path} contains a newline", path)
    for char in text:
        if char in SQUASH_WHITESPACE:
            _fail("whitespace_not_allowed",
                  f"{path} contains whitespace {char!r}; normalize it before serializing", path)
        if char.isspace():
            _fail("unsupported_whitespace",
                  f"{path} contains unsupported whitespace U+{ord(char):04X}", path)
    return text


def clean_identifier(text: str, path: str) -> str:
    """Names and references must not be normalized, because that changes identity."""
    value = clean_text(text, path)
    if not value:
        _fail("empty_identifier", f"{path} is empty", path)
    return value


def join_items(items: Any, path: str) -> str:
    """One list field (`外貌`, `个性`, task goals) as a `、`-joined string.

    The trailing punctuation rule is the legacy rule: entries are records, not
    sentences.  It is part of the serializer version and is recorded in the
    manifest.
    """
    values = _expect_list(items, path)
    parts: List[str] = []
    for index, item in enumerate(values):
        text = clean_text(_expect_str(item, f"{path}[{index}]"), f"{path}[{index}]")
        text = text.rstrip("。；，")
        if text:
            parts.append(text)
    return "、".join(parts)


def task_line(tasks: Any, path: str) -> str:
    tasks = _expect_dict(tasks, path)
    parts: List[str] = []
    big = tasks.get("大任务")
    if big is not None:
        big = _expect_dict(big, f"{path}/大任务")
        goal = clean_text(_expect_str(big.get("目标"), f"{path}/大任务/目标"),
                          f"{path}/大任务/目标")
        status = clean_identifier(str(big.get("状态", "")), f"{path}/大任务/状态")
        if not status:
            _fail("empty_task_status", f"{path}/大任务/状态 is empty", f"{path}/大任务/状态")
        parts.append(f"{goal}（{status}）")
    small = tasks.get("小任务", [])
    small = _expect_list(small, f"{path}/小任务")
    for index, task in enumerate(small):
        task_path = f"{path}/小任务[{index}]"
        task = _expect_dict(task, task_path)
        goal = clean_text(_expect_str(task.get("目标"), f"{task_path}/目标"),
                          f"{task_path}/目标")
        status = clean_identifier(str(task.get("状态", "")), f"{task_path}/状态")
        if not status:
            _fail("empty_task_status", f"{task_path}/状态 is empty", f"{task_path}/状态")
        parts.append(f"{goal}（{status}）")
    if not parts:
        _fail("empty_tasks", f"{path} contains no task entries", path)
    return "；".join(parts)


def _append(text_parts: List[str], value: str) -> Tuple[int, int]:
    start = sum(len(part) for part in text_parts)
    text_parts.append(value)
    return start, start + len(value)


# ----------------------------------------------------------- entity registry

def entity_registry(before: Dict[str, Any], result: Optional[Dict[str, Any]] = None
                    ) -> Dict[str, str]:
    """entity name -> 地点/人物/物品.

    Unknown or ambiguous names are refused.  The registry is the only place
    that decides an entity type; the serializer never guesses from the change
    field names (the legacy `describe_change` guessed "人物" by default).
    """
    registry: Dict[str, str] = {}

    def add(name: str, kind: str, path: str) -> None:
        previous = registry.get(name)
        if previous is not None and previous != kind:
            _fail("ambiguous_entity",
                  f"entity {name!r} is both {previous} and {kind} ({path})", path)
        registry[name] = kind

    for kind, block in (("地点", "地点"), ("人物", "人物"), ("物品", "物品")):
        entries = before.get(block, {})
        entries = _expect_dict(entries, f"上回合状态/{block}")
        for name in entries:
            add(clean_identifier(name, f"上回合状态/{block}/键"), kind,
                f"上回合状态/{block}/{name}")
    if result:
        for kind, block in (("地点", "地点"), ("人物", "人物"), ("物品", "物品")):
            entries = result.get(block, {})
            if entries is None:
                continue
            entries = _expect_dict(entries, f"本回合状态/{block}")
            for name in entries:
                add(clean_identifier(name, f"本回合状态/{block}/键"), kind,
                    f"本回合状态/{block}/{name}")
    return registry


def _resolve_type(registry: Dict[str, str], name: str, path: str) -> str:
    kind = registry.get(name)
    if kind is None:
        _fail("unknown_entity", f"entity {name!r} is not in the before state", path)
    return kind


# ------------------------------------------------------------- state blocks

def _state_place_line(name: str, entry: Dict[str, Any], path: str,
                      text_parts: List[str], segments: List[Segment]) -> None:
    entry = _expect_dict(entry, path)
    start, _ = _append(text_parts, name)
    parent = entry.get("位于")
    if parent:
        parent = clean_identifier(_expect_str(parent, f"{path}/位于"), f"{path}/位于")
        _append(text_parts, f"（在{parent}里）")
    appearance = entry.get("外貌", [])
    looks = join_items(appearance, f"{path}/外貌")
    if looks:
        _append(text_parts, "：")
        _append(text_parts, looks)
    _append(text_parts, "。")
    segments.append(Segment("state", BLOCK_PLACE, name, "地点", "位于", parent,
                            start, start + len(name)))


def _state_person_line(name: str, entry: Dict[str, Any], path: str,
                       text_parts: List[str], segments: List[Segment]) -> None:
    entry = _expect_dict(entry, path)
    start, _ = _append(text_parts, name)
    _append(text_parts, "：")
    pieces: List[str] = []
    position = entry.get("位置")
    if position:
        position = clean_identifier(_expect_str(position, f"{path}/位置"), f"{path}/位置")
        pieces.append(f"在{position}")
    if "精神值" in entry:
        sanity = _expect_int(entry["精神值"], f"{path}/精神值")
        pieces.append(f"精神值{sanity}")
    appearance = entry.get("外貌", [])
    looks = join_items(appearance, f"{path}/外貌")
    if looks:
        pieces.append(f"外貌{looks}")
    personality = entry.get("个性", [])
    traits = join_items(personality, f"{path}/个性")
    if traits:
        pieces.append(f"个性{traits}")
    tasks = entry.get("任务")
    if tasks:
        pieces.append(f"任务{task_line(tasks, f'{path}/任务')}")
    if not pieces:
        _fail("empty_person", f"{path} has no fields", path)
    body_start, body_end = _append(text_parts, "，".join(pieces))
    _append(text_parts, "。")
    segments.append(Segment("state", BLOCK_PERSON, name, "人物", "位置", position,
                            start, start + len(name)))
    segments.append(Segment("state", BLOCK_PERSON, name, "人物", "body", pieces,
                            body_start, body_end))


def _state_item_line(name: str, entry: Dict[str, Any], path: str,
                     text_parts: List[str], segments: List[Segment]) -> None:
    entry = _expect_dict(entry, path)
    start, _ = _append(text_parts, name)
    # The legacy place_line read `位于`; item rows carry `位置`.  v2 reads
    # `位置` first and falls back to `位于` only for old/custom projections.
    position = entry.get("位置")
    if position is None:
        position = entry.get("位于")
    if position:
        position = clean_identifier(_expect_str(position, f"{path}/位置"), f"{path}/位置")
        _append(text_parts, f"（位于{position}）")
    appearance = entry.get("外貌", [])
    looks = join_items(appearance, f"{path}/外貌")
    if looks:
        _append(text_parts, "：")
        _append(text_parts, looks)
    _append(text_parts, "。")
    segments.append(Segment("state", BLOCK_ITEM, name, "物品", "位置", position,
                            start, start + len(name)))


def _render_state_block(kind: str, entries: Dict[str, Any], path: str,
                        segments: List[Segment]) -> Tuple[str, Dict[str, str]]:
    text_parts: List[str] = []
    blocks: Dict[str, str] = {}
    if not entries:
        return "", blocks
    for name in sorted(entries):
        safe_name = clean_identifier(name, f"{path}/键")
        entry = entries[name]
        if kind == "地点":
            _state_place_line(safe_name, entry, f"{path}/{safe_name}", text_parts, segments)
        elif kind == "人物":
            _state_person_line(safe_name, entry, f"{path}/{safe_name}", text_parts, segments)
        else:
            _state_item_line(safe_name, entry, f"{path}/{safe_name}", text_parts, segments)
    blocks[kind] = "".join(text_parts)
    return blocks[kind], blocks


def render_state(state: Dict[str, Any], *, segments: Optional[List[Segment]] = None) -> str:
    """Render the whole state block (legacy three sections, fixed item line)."""
    state = _expect_dict(state, "上回合状态")
    all_text: List[str] = []
    for kind in ("地点", "人物", "物品"):
        entries = state.get(kind, {})
        entries = _expect_dict(entries, f"上回合状态/{kind}")
        text, _ = _render_state_block(kind, entries, f"上回合状态/{kind}",
                                      segments if segments is not None else [])
        if text:
            all_text.append(HEADERS[kind] + text)
    return "".join(all_text)


# -------------------------------------------------------------- delta block

def _delta_entity_sentence(name: str, ops: Dict[str, Any], kind: str, path: str,
                           text_parts: List[str], segments: List[Segment]) -> None:
    ops = _expect_dict(ops, path)
    if not ops:
        _fail("empty_change_entity", f"{path} has no operations", path)
    pieces: List[str] = []
    for field_name in DELTA_FIELDS:
        if field_name not in ops:
            continue
        value = ops[field_name]
        field_path = f"{path}/{field_name}"
        if field_name == "位置":
            value = clean_identifier(_expect_str(value, field_path), field_path)
            pieces.append(f"移动到{value}")
        elif field_name == "精神值":
            sanity = _expect_int(value, field_path)
            pieces.append(f"精神值变成{sanity}")
        elif field_name in ("解除外貌", "新增外貌", "解除个性", "新增个性"):
            joined = join_items(value, field_path)
            if joined:
                prefix = {"解除外貌": "去掉外貌", "新增外貌": "多出外貌",
                          "解除个性": "去掉个性", "新增个性": "多出个性"}[field_name]
                pieces.append(prefix + joined)
        elif field_name == "完成任务":
            joined = join_items(value, field_path)
            if joined:
                pieces.append("完成" + joined)
        elif field_name == "新增小任务":
            tasks = _expect_list(value, field_path)
            goals: List[str] = []
            for index, task in enumerate(tasks):
                task_path = f"{field_path}[{index}]"
                task = _expect_dict(task, task_path)
                goal = clean_text(_expect_str(task.get("目标"), f"{task_path}/目标"),
                                  f"{task_path}/目标")
                goals.append(goal)
            if goals:
                pieces.append("新任务" + "、".join(goals))
    unknown = sorted(set(ops) - set(DELTA_FIELDS))
    if unknown:
        _fail("unknown_change_field",
              f"{path} has unsupported operation(s): {', '.join(unknown)}", path)
    if not pieces:
        _fail("empty_change_sentence", f"{path} operations produce no sentence", path)
    start, _ = _append(text_parts, f"{name}（{kind}）：")
    body_start, body_end = _append(text_parts, "，".join(pieces))
    _append(text_parts, "。")
    segments.append(Segment("delta", BLOCK_DELTA, name, kind, "body", pieces,
                            body_start, body_end))
    segments.append(Segment("delta", BLOCK_DELTA, name, kind, "entity", name,
                            start, start + len(name)))


def render_delta(delta: Dict[str, Any], registry: Dict[str, str],
                 *, segments: Optional[List[Segment]] = None) -> str:
    delta = _expect_dict(delta, "本回合变化")
    time = delta.get("时间推进", "")
    time = clean_text(_expect_str(time, "本回合变化/时间推进"), "本回合变化/时间推进")
    changes = delta.get("变化", {})
    changes = _expect_dict(changes, "本回合变化/变化")
    text_parts: List[str] = []
    _append(text_parts, f"时间推进{time}。")
    if not changes:
        _append(text_parts, "这一回合没有结算出变化。")
        return "".join(text_parts)
    for name in sorted(changes):
        safe_name = clean_identifier(name, "本回合变化/变化/键")
        kind = _resolve_type(registry, safe_name, f"本回合变化/变化/{safe_name}")
        _delta_entity_sentence(safe_name, changes[name], kind,
                               f"本回合变化/变化/{safe_name}", text_parts,
                               segments if segments is not None else [])
    return "".join(text_parts)


# ------------------------------------------------------------- result block

def _result_field_phrase(kind: str, field_name: str, value: Any, path: str) -> str:
    if field_name in ("位置", "位于"):
        if value is None:
            return f"{field_name}（无）"
        value = clean_identifier(_expect_str(value, path), path)
        return f"{field_name}{value}"
    if field_name == "精神值":
        return f"精神值{_expect_int(value, path)}"
    if field_name in ("外貌", "个性"):
        values = _expect_list(value, path)
        if not values:
            return f"{field_name}（空）"
        joined = join_items(values, path)
        if not joined:
            return f"{field_name}（空）"
        return f"{field_name}{joined}"
    if field_name == "任务":
        return f"任务{task_line(value, path)}"
    _fail("unknown_result_field", f"unsupported result field {field_name!r}", path)
    return ""  # unreachable


def render_result(result: Dict[str, Any], registry: Dict[str, str],
                  *, segments: Optional[List[Segment]] = None) -> str:
    result = _expect_dict(result, "本回合状态")
    if not result:
        return ""
    by_type: Dict[str, List[str]] = {kind: [] for kind in TYPE_ORDER}
    for name in result:
        safe_name = clean_identifier(name, "本回合状态/键")
        kind = _resolve_type(registry, safe_name, f"本回合状态/{safe_name}")
        by_type[kind].append(safe_name)

    text_parts: List[str] = []
    for kind in TYPE_ORDER:
        for name in sorted(by_type[kind]):
            view = _expect_dict(result[name], f"本回合状态/{name}")
            allowed = RESULT_FIELDS[kind]
            unknown = sorted(set(view) - set(allowed))
            if unknown:
                _fail("unknown_result_field",
                      f"{name} ({kind}) has unsupported result field(s): {', '.join(unknown)}",
                      f"本回合状态/{name}")
            start, _ = _append(text_parts, f"{name}（{kind}）：")
            phrases: List[Tuple[str, str, Any]] = []
            for field_name in allowed:
                if field_name not in view:
                    continue
                value = view[field_name]
                phrase = _result_field_phrase(kind, field_name, value,
                                              f"本回合状态/{name}/{field_name}")
                phrases.append((field_name, phrase, value))
            if not phrases:
                _fail("empty_result_entity", f"本回合状态/{name} has no fields",
                      f"本回合状态/{name}")
            for index, (field_name, phrase, value) in enumerate(phrases):
                if index:
                    _append(text_parts, "，")
                field_start, field_end = _append(text_parts, phrase)
                segments.append(Segment("result", BLOCK_RESULT, name, kind, field_name,
                                        value, field_start, field_end))
            _append(text_parts, "。")
            segments.append(Segment("result", BLOCK_RESULT, name, kind, "entity", name,
                                    start, start + len(name)))
    return "".join(text_parts)


# ------------------------------------------------------------------ entry

def serialize(projection: Dict[str, Any]) -> Serialized:
    """Serialize one four-field projection to the exact v2 input string.

    The returned `text` ends with `【正文】` and contains no newline.  It is the
    model input, not the target; the target is kept separately by the caller.
    """
    projection = _expect_dict(projection, "projection")
    missing = [name for name in TOP_LEVEL_FIELDS if name not in projection]
    if missing:
        _fail("missing_projection_field",
              f"projection lacks {', '.join(missing)}", "projection")
    unknown = sorted(set(projection) - set(TOP_LEVEL_FIELDS))
    if unknown:
        _fail("unknown_projection_field",
              f"projection has unsupported field(s): {', '.join(unknown)}", "projection")

    segments: List[Segment] = []
    blocks: Dict[str, str] = {}

    viewpoint = projection["视角"]
    viewpoint = clean_text(_expect_str(viewpoint, "视角"), "视角")
    viewpoint = viewpoint.split("；")[0]
    if not viewpoint:
        _fail("empty_viewpoint", "视角 is empty", "视角")
    blocks[BLOCK_VIEW] = viewpoint
    segments.append(Segment("state", BLOCK_VIEW, "", "", "视角", viewpoint,
                            0, len(viewpoint)))

    before = _expect_dict(projection["上回合状态"], "上回合状态")
    result = _expect_dict(projection["本回合状态"], "本回合状态")
    delta = _expect_dict(projection["本回合变化"], "本回合变化")
    registry = entity_registry(before, result)

    text_parts: List[str] = [HEADERS[BLOCK_VIEW] + viewpoint]
    for kind in ("地点", "人物", "物品"):
        entries = before.get(kind, {})
        entries = _expect_dict(entries, f"上回合状态/{kind}")
        block_segments: List[Segment] = []
        text, _ = _render_state_block(kind, entries, f"上回合状态/{kind}", block_segments)
        if text:
            start = sum(len(part) for part in text_parts) + len(HEADERS[kind])
            for segment in block_segments:
                segment.start += start
                segment.end += start
            text_parts.append(HEADERS[kind] + text)
            blocks[kind] = text
            segments.extend(block_segments)

    delta_segments: List[Segment] = []
    delta_text = render_delta(delta, registry, segments=delta_segments)
    delta_start = sum(len(part) for part in text_parts) + len(HEADERS[BLOCK_DELTA])
    for segment in delta_segments:
        segment.start += delta_start
        segment.end += delta_start
    text_parts.append(HEADERS[BLOCK_DELTA] + delta_text)
    blocks[BLOCK_DELTA] = delta_text
    segments.extend(delta_segments)

    result_segments: List[Segment] = []
    result_text = render_result(result, registry, segments=result_segments)
    if result_text:
        result_start = sum(len(part) for part in text_parts) + len(HEADERS[BLOCK_RESULT])
        for segment in result_segments:
            segment.start += result_start
            segment.end += result_start
        text_parts.append(HEADERS[BLOCK_RESULT] + result_text)
        blocks[BLOCK_RESULT] = result_text
        segments.extend(result_segments)

    body_start = sum(len(part) for part in text_parts)
    text_parts.append(HEADERS[BLOCK_BODY])
    segments.append(Segment("state", BLOCK_BODY, "", "", "正文", "",
                            body_start, body_start + len(HEADERS[BLOCK_BODY])))

    text = "".join(text_parts)
    if any(char in "\r\n" or char.isspace() for char in text):
        _fail("serialized_whitespace", "serialized input contains whitespace")
    return Serialized(text=text, blocks=blocks, segments=segments)


def serialize_text(projection: Dict[str, Any]) -> str:
    return serialize(projection).text


def projection_sha256(projection: Dict[str, Any]) -> str:
    """Canonical SHA-256 of the structured projection (for identity records)."""
    import hashlib

    payload = json.dumps(projection, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------- result building

def _task_entries(before_entity: Dict[str, Any], ops: Dict[str, Any],
                  path: str) -> Dict[str, Any]:
    tasks = _expect_dict(before_entity.get("任务"), f"{path}/任务")
    big = _expect_dict(tasks.get("大任务"), f"{path}/任务/大任务")
    small = {task["目标"]: dict(task) for task in
             _expect_list(tasks.get("小任务", []), f"{path}/任务/小任务")}
    out_big = None
    out_small: List[Dict[str, Any]] = []
    for goal in _expect_list(ops.get("完成任务", []), f"{path}/完成任务"):
        if big["目标"] == goal:
            out_big = {"目标": goal, "状态": "已完成"}
        elif goal in small:
            out_small.append({"目标": goal, "状态": "已完成"})
        else:
            _fail("unknown_task", f"{path} completes unknown task {goal!r}",
                  f"{path}/完成任务")
    for index, added in enumerate(_expect_list(ops.get("新增小任务", []),
                                               f"{path}/新增小任务")):
        added = _expect_dict(added, f"{path}/新增小任务[{index}]")
        goal = _expect_str(added.get("目标"), f"{path}/新增小任务[{index}]/目标")
        out_small.append({"目标": goal, "状态": added.get("状态", "未完成")})
    result: Dict[str, Any] = {}
    if out_big:
        result["大任务"] = out_big
    if out_small:
        result["小任务"] = out_small
    return result


def _apply_list_change(before_values: Any, removed: Any, added: Any,
                       path: str) -> List[str]:
    values = list(_expect_list(before_values, f"{path}/before"))
    for index, item in enumerate(_expect_list(removed, f"{path}/removed")):
        if item not in values:
            _fail("remove_missing_item", f"{path} removes missing item {item!r}",
                  f"{path}/removed[{index}]")
        values.remove(item)
    for index, item in enumerate(_expect_list(added, f"{path}/added")):
        values.append(_expect_str(item, f"{path}/added[{index}]"))
    return values


def _same_result_value(field_name: str, existing: Any, computed: Any) -> bool:
    """Whether the stored settled value is a valid result for the declaration.

    List order is the actual settled order (the row's after state), so it may
    differ from the order produced by remove-then-append.  Compare as a
    multiset for lists and as a task mapping for `任务`; scalars must match
    exactly.
    """
    if field_name in ("外貌", "个性"):
        if not isinstance(existing, list) or not isinstance(computed, list):
            return False
        return collections.Counter(existing) == collections.Counter(computed)
    if field_name == "任务":
        if not isinstance(existing, dict) or not isinstance(computed, dict):
            return False

        def canonical(tasks: Dict[str, Any]) -> Any:
            big = tasks.get("大任务")
            big_key = None if big is None else (big.get("目标"), big.get("状态"))
            small = sorted((task.get("目标"), task.get("状态"))
                           for task in tasks.get("小任务", []))
            return big_key, small

        return canonical(existing) == canonical(computed)
    return existing == computed


def build_result(before: Dict[str, Any], delta: Dict[str, Any],
                 existing: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Build the partial result block from before + declared changes.

    `existing` is the row's stored `本回合状态`.  When it already carries a
    settled value, that exact value (including list order) is kept; only
    missing fields are filled from the declaration.  Conflicting values are
    refused instead of silently overwritten.  This is how the v2 data recovers
    the result block that the legacy converter never wrote, and how item
    positions are added, without pretending the block is a full after snapshot.
    """
    before = _expect_dict(before, "上回合状态")
    delta = _expect_dict(delta, "本回合变化")
    existing = {} if existing is None else _expect_dict(existing, "本回合状态")
    changes = _expect_dict(delta.get("变化", {}), "本回合变化/变化")
    registry = entity_registry(before, existing)
    fills: List[Dict[str, Any]] = []
    result: Dict[str, Any] = {}

    unknown_result = sorted(set(existing) - set(changes))
    if unknown_result:
        _fail("result_without_change",
              f"result block has unchanged entities: {', '.join(unknown_result)}",
              "本回合状态")

    for name in sorted(changes):
        kind = _resolve_type(registry, name, f"本回合变化/变化/{name}")
        ops = _expect_dict(changes[name], f"本回合变化/变化/{name}")
        before_entry = (_expect_dict(before[kind], f"上回合状态/{kind}"))[name]
        before_entry = _expect_dict(before_entry, f"上回合状态/{kind}/{name}")
        view = dict(existing.get(name, {}))
        allowed = {"人物": {"位置", "精神值", "外貌", "个性", "任务"},
                   "地点": {"位于", "外貌"},
                   "物品": {"位置", "外貌"}}[kind]
        unknown_fields = sorted(set(view) - allowed)
        if unknown_fields:
            _fail("unknown_result_field",
                  f"{name} ({kind}) has unsupported result field(s): {', '.join(unknown_fields)}",
                  f"本回合状态/{name}")

        def settle(field_name: str, computed: Any) -> None:
            if field_name in view:
                if not _same_result_value(field_name, view[field_name], computed):
                    _fail("result_conflict",
                          f"{name}.{field_name} is {view[field_name]!r} but the "
                          f"declared change gives {computed!r}",
                          f"本回合状态/{name}/{field_name}")
                return
            view[field_name] = computed
            fills.append({"entity": name, "type": kind, "field": field_name,
                          "value": computed, "source": "delta"})

        if "位置" in ops:
            computed = _expect_str(ops["位置"], f"本回合变化/变化/{name}/位置")
            settle("位置", computed)
        if "精神值" in ops:
            computed = _expect_int(ops["精神值"], f"本回合变化/变化/{name}/精神值")
            settle("精神值", computed)
        if "新增外貌" in ops or "解除外貌" in ops:
            computed = _apply_list_change(before_entry.get("外貌", []),
                                          ops.get("解除外貌", []),
                                          ops.get("新增外貌", []),
                                          f"{name}/外貌")
            settle("外貌", computed)
        if "新增个性" in ops or "解除个性" in ops:
            computed = _apply_list_change(before_entry.get("个性", []),
                                          ops.get("解除个性", []),
                                          ops.get("新增个性", []),
                                          f"{name}/个性")
            settle("个性", computed)
        if "完成任务" in ops or "新增小任务" in ops:
            computed = _task_entries(before_entry, ops, name)
            if not computed:
                _fail("empty_tasks", f"{name} has task ops but no task result",
                      f"本回合状态/{name}/任务")
            settle("任务", computed)
        if "位于" in ops:
            computed = ops["位于"]
            settle("位于", computed)

        # Fields present in the stored result but not implied by any op are
        # unchanged fields repeated in the result block.  verify_rows.py already
        # refuses them for the 199 rows; keep the same rule here.
        implied = set()
        if "位置" in ops:
            implied.add("位置")
        if "精神值" in ops:
            implied.add("精神值")
        if "新增外貌" in ops or "解除外貌" in ops:
            implied.add("外貌")
        if "新增个性" in ops or "解除个性" in ops:
            implied.add("个性")
        if "完成任务" in ops or "新增小任务" in ops:
            implied.add("任务")
        if "位于" in ops:
            implied.add("位于")
        extra = sorted(set(view) - implied)
        if extra:
            _fail("unchanged_result_field",
                  f"{name} repeats unchanged field(s): {', '.join(extra)}",
                  f"本回合状态/{name}")
        if not view:
            _fail("empty_result_entity", f"{name} has changes but no result fields",
                  f"本回合状态/{name}")
        result[name] = view

    if not changes and existing:
        _fail("result_without_change",
              "result block is non-empty on a no-change round", "本回合状态")
    return result, fills
