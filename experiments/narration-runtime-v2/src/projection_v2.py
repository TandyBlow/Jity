# -*- coding: utf-8 -*-
"""Field-aware normalization of the legacy four-field projection.

The 199 legacy rows have ordinary spaces in `时间推进` (`2 分钟`).  The YuYan
character vocabulary has no space or newline token, so the legacy converter
removed spaces from every string.  v2 keeps that behaviour for free text but
records each removal, and refuses to normalize names or references because that
would change entity identity.

Rules:

* free text (视角, 外貌, 个性, task goals, 时间推进): remove U+0020, U+0009,
  U+3000 and record the removal; refuse CR/LF and every other whitespace.
* names and references (entity keys, 位置, 位于, 状态): refuse any whitespace.
* numbers: integers only, bool is refused.

The normalized projection is what the serializer and the training data use.
The raw projection is kept in the dataset record for audit.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from v2_render import (
    NarrationSerializeError,
    SQUASH_WHITESPACE,
    _expect_dict,
    _expect_int,
    _expect_list,
    _expect_str,
)


def _fail(code: str, message: str, path: str) -> None:
    raise NarrationSerializeError(code, message, path)


def _check_no_other_whitespace(text: str, path: str) -> None:
    if "\r" in text or "\n" in text:
        _fail("newline_not_allowed", f"{path} contains a newline", path)
    for char in text:
        if char.isspace() and char not in SQUASH_WHITESPACE:
            _fail("unsupported_whitespace",
                  f"{path} contains unsupported whitespace U+{ord(char):04X}", path)


def normalize_free_text(text: Any, path: str, ledger: List[Dict[str, Any]]) -> str:
    text = _expect_str(text, path)
    _check_no_other_whitespace(text, path)
    removed = [char for char in text if char in SQUASH_WHITESPACE]
    normalized = "".join(char for char in text if char not in SQUASH_WHITESPACE)
    if removed:
        ledger.append({"path": path, "action": "remove_whitespace",
                       "removed": removed, "before": text, "after": normalized})
    return normalized


def normalize_identifier(text: Any, path: str) -> str:
    text = _expect_str(text, path)
    _check_no_other_whitespace(text, path)
    for char in text:
        if char in SQUASH_WHITESPACE:
            _fail("whitespace_in_identifier",
                  f"{path} contains whitespace {char!r}; identifiers are not normalized",
                  path)
    if not text:
        _fail("empty_identifier", f"{path} is empty", path)
    return text


def normalize_list(values: Any, path: str, ledger: List[Dict[str, Any]]) -> List[str]:
    values = _expect_list(values, path)
    return [normalize_free_text(item, f"{path}[{index}]", ledger)
            for index, item in enumerate(values)]


def normalize_tasks(tasks: Any, path: str, ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    tasks = _expect_dict(tasks, path)
    out: Dict[str, Any] = {}
    big = tasks.get("大任务")
    if big is not None:
        big = _expect_dict(big, f"{path}/大任务")
        out["大任务"] = {
            "目标": normalize_free_text(big.get("目标"), f"{path}/大任务/目标", ledger),
            "状态": normalize_identifier(big.get("状态"), f"{path}/大任务/状态"),
        }
    small = _expect_list(tasks.get("小任务", []), f"{path}/小任务")
    out["小任务"] = []
    for index, task in enumerate(small):
        task_path = f"{path}/小任务[{index}]"
        task = _expect_dict(task, task_path)
        out["小任务"].append({
            "目标": normalize_free_text(task.get("目标"), f"{task_path}/目标", ledger),
            "状态": normalize_identifier(task.get("状态"), f"{task_path}/状态"),
        })
    return out


def normalize_places(entries: Any, path: str, ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    entries = _expect_dict(entries, path)
    out: Dict[str, Any] = {}
    for name, entry in entries.items():
        safe_name = normalize_identifier(name, f"{path}/键")
        entry_path = f"{path}/{safe_name}"
        entry = _expect_dict(entry, entry_path)
        normalized: Dict[str, Any] = {
            "位于": (None if entry.get("位于") is None
                    else normalize_identifier(entry.get("位于"), f"{entry_path}/位于")),
            "外貌": normalize_list(entry.get("外貌", []), f"{entry_path}/外貌", ledger),
        }
        unknown = sorted(set(entry) - {"位于", "外貌"})
        if unknown:
            _fail("unknown_state_field",
                  f"{entry_path} has unsupported field(s): {', '.join(unknown)}", entry_path)
        out[safe_name] = normalized
    return out


def normalize_people(entries: Any, path: str, ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    entries = _expect_dict(entries, path)
    out: Dict[str, Any] = {}
    for name, entry in entries.items():
        safe_name = normalize_identifier(name, f"{path}/键")
        entry_path = f"{path}/{safe_name}"
        entry = _expect_dict(entry, entry_path)
        normalized: Dict[str, Any] = {
            "位置": normalize_identifier(entry.get("位置"), f"{entry_path}/位置"),
            "精神值": _expect_int(entry.get("精神值"), f"{entry_path}/精神值"),
            "外貌": normalize_list(entry.get("外貌", []), f"{entry_path}/外貌", ledger),
            "个性": normalize_list(entry.get("个性", []), f"{entry_path}/个性", ledger),
            "任务": normalize_tasks(entry.get("任务"), f"{entry_path}/任务", ledger),
        }
        unknown = sorted(set(entry) - {"位置", "精神值", "外貌", "个性", "任务"})
        if unknown:
            _fail("unknown_state_field",
                  f"{entry_path} has unsupported field(s): {', '.join(unknown)}", entry_path)
        out[safe_name] = normalized
    return out


def normalize_things(entries: Any, path: str, ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    entries = _expect_dict(entries, path)
    out: Dict[str, Any] = {}
    for name, entry in entries.items():
        safe_name = normalize_identifier(name, f"{path}/键")
        entry_path = f"{path}/{safe_name}"
        entry = _expect_dict(entry, entry_path)
        normalized: Dict[str, Any] = {
            "位置": normalize_identifier(entry.get("位置"), f"{entry_path}/位置"),
            "外貌": normalize_list(entry.get("外貌", []), f"{entry_path}/外貌", ledger),
        }
        unknown = sorted(set(entry) - {"位置", "外貌"})
        if unknown:
            _fail("unknown_state_field",
                  f"{entry_path} has unsupported field(s): {', '.join(unknown)}", entry_path)
        out[safe_name] = normalized
    return out


def normalize_state(state: Any, path: str, ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    state = _expect_dict(state, path)
    unknown = sorted(set(state) - {"地点", "人物", "物品"})
    if unknown:
        _fail("unknown_state_block",
              f"{path} has unsupported block(s): {', '.join(unknown)}", path)
    return {
        "地点": normalize_places(state.get("地点", {}), f"{path}/地点", ledger),
        "人物": normalize_people(state.get("人物", {}), f"{path}/人物", ledger),
        "物品": normalize_things(state.get("物品", {}), f"{path}/物品", ledger),
    }


def normalize_delta(delta: Any, path: str, ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    delta = _expect_dict(delta, path)
    unknown = sorted(set(delta) - {"时间推进", "变化"})
    if unknown:
        _fail("unknown_delta_field",
              f"{path} has unsupported field(s): {', '.join(unknown)}", path)
    changes = _expect_dict(delta.get("变化", {}), f"{path}/变化")
    out_changes: Dict[str, Any] = {}
    for name, ops in changes.items():
        safe_name = normalize_identifier(name, f"{path}/变化/键")
        ops_path = f"{path}/变化/{safe_name}"
        ops = _expect_dict(ops, ops_path)
        out_ops: Dict[str, Any] = {}
        allowed = {"位置", "精神值", "解除外貌", "新增外貌", "解除个性",
                   "新增个性", "完成任务", "新增小任务"}
        unknown_ops = sorted(set(ops) - allowed)
        if unknown_ops:
            _fail("unknown_change_field",
                  f"{ops_path} has unsupported operation(s): {', '.join(unknown_ops)}",
                  ops_path)
        if "位置" in ops:
            out_ops["位置"] = normalize_identifier(ops["位置"], f"{ops_path}/位置")
        if "精神值" in ops:
            out_ops["精神值"] = _expect_int(ops["精神值"], f"{ops_path}/精神值")
        for field_name in ("解除外貌", "新增外貌", "解除个性", "新增个性", "完成任务"):
            if field_name in ops:
                out_ops[field_name] = normalize_list(ops[field_name],
                                                     f"{ops_path}/{field_name}", ledger)
        if "新增小任务" in ops:
            tasks = _expect_list(ops["新增小任务"], f"{ops_path}/新增小任务")
            out_tasks: List[Dict[str, Any]] = []
            for index, task in enumerate(tasks):
                task_path = f"{ops_path}/新增小任务[{index}]"
                task = _expect_dict(task, task_path)
                normalized = {
                    "目标": normalize_free_text(task.get("目标"), f"{task_path}/目标", ledger),
                    "属于大任务": normalize_free_text(task.get("属于大任务"),
                                                     f"{task_path}/属于大任务", ledger),
                    "状态": normalize_identifier(task.get("状态", "未完成"),
                                                 f"{task_path}/状态"),
                }
                unknown_task = sorted(set(task) - {"目标", "属于大任务", "状态"})
                if unknown_task:
                    _fail("unknown_task_field",
                          f"{task_path} has unsupported field(s): {', '.join(unknown_task)}",
                          task_path)
                out_tasks.append(normalized)
            out_ops["新增小任务"] = out_tasks
        if not out_ops:
            _fail("empty_change_entity", f"{ops_path} has no operations", ops_path)
        out_changes[safe_name] = out_ops
    return {
        "时间推进": normalize_free_text(delta.get("时间推进"), f"{path}/时间推进", ledger),
        "变化": out_changes,
    }


def normalize_result(result: Any, path: str, ledger: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalize the stored partial result block.

    The result block is filled after normalization by `build_result`, so this
    function only handles the fields the legacy rows already carry.  It accepts
    every result field; a field that is not a result field is refused.
    """
    result = _expect_dict(result, path)
    out: Dict[str, Any] = {}
    for name, view in result.items():
        safe_name = normalize_identifier(name, f"{path}/键")
        view_path = f"{path}/{safe_name}"
        view = _expect_dict(view, view_path)
        normalized: Dict[str, Any] = {}
        for field_name, value in view.items():
            field_path = f"{view_path}/{field_name}"
            if field_name in ("位置", "位于"):
                normalized[field_name] = normalize_identifier(value, field_path)
            elif field_name == "精神值":
                normalized[field_name] = _expect_int(value, field_path)
            elif field_name in ("外貌", "个性"):
                normalized[field_name] = normalize_list(value, field_path, ledger)
            elif field_name == "任务":
                normalized[field_name] = normalize_tasks(value, field_path, ledger)
            else:
                _fail("unknown_result_field",
                      f"{view_path} has unsupported result field {field_name!r}",
                      field_path)
        out[safe_name] = normalized
    return out


def normalize_projection(raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Return `(normalized_projection, ledger)`.

    The ledger records every removed whitespace character and the path it came
    from; it is written into the dataset manifest so a reviewer can see that no
    name or number was silently rewritten.
    """
    raw = _expect_dict(raw, "projection")
    unknown = sorted(set(raw) - {"视角", "上回合状态", "本回合变化", "本回合状态"})
    if unknown:
        _fail("unknown_projection_field",
              f"projection has unsupported field(s): {', '.join(unknown)}", "projection")
    ledger: List[Dict[str, Any]] = []
    projection = {
        "视角": normalize_free_text(raw.get("视角"), "视角", ledger),
        "上回合状态": normalize_state(raw.get("上回合状态"), "上回合状态", ledger),
        "本回合变化": normalize_delta(raw.get("本回合变化"), "本回合变化", ledger),
        "本回合状态": normalize_result(raw.get("本回合状态"), "本回合状态", ledger),
    }
    return projection, ledger
