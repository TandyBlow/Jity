"""Markdown playtest log writers."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_play_lib.formatting import (
    compact_mapping,
    compact_named_list,
    fenced_json,
    format_dialogue,
    format_options,
    format_rag_hits,
    format_state,
)


def write_header(path: Path, args: argparse.Namespace) -> None:
    append_block(
        path,
        [
            "# Jity 自动跑剧情记录",
            "",
            f"- started_at: `{datetime.now().isoformat(timespec='seconds')}`",
            f"- api_base_url: `{args.api_base_url}`",
            f"- model: `{args.model}`",
            f"- runs: `{args.runs}`",
            f"- turns_per_run: `{args.turns}`",
            f"- seed: `{args.seed}`",
            f"- campaign: `{getattr(args, 'campaign', '') or '自由模式'}`",
            f"- browser_mode: `{getattr(args, 'browser', False)}`",
            "",
            "选择策略：结合当前目标和未完成任务目标进行中文短语匹配，并优先推进、调查、询问、检查等主动选项；降低等待、拒绝、逃跑、沉默等被动选项权重。",
            "",
        ],
    )


def append_turn(
    path: Path,
    run_number: int,
    turn: int,
    session_id: str,
    previous_options: list[str],
    selected_index: int | None,
    action: str,
    score: int,
    response: dict[str, Any],
    active_goals: list[str] | None = None,
) -> None:
    output = response.get("output", {})
    state = response.get("state", {})
    # Write every turn immediately so a long 900-turn run still leaves a useful partial log.
    lines = [
        f"## Run {run_number} / Turn {turn}",
        "",
        f"- session_id: `{session_id}`",
        f"- source: `{response.get('source', '')}`",
        f"- model_output_id: `{response.get('model_output_id')}`",
        f"- used_model: `{response.get('used_model', '')}`",
        f"- selected_option: `{selected_index if selected_index is not None else 'fallback'}`",
        f"- selection_score: `{score}`",
        f"- selected_action: {action}",
        f"- active_goals: {'；'.join(active_goals or []) or '无'}",
        "",
        "### 本轮可选项",
        "",
        *format_options(previous_options, selected_index),
        "",
        "### 生成剧情",
        "",
        output.get("narration", "").strip() or "无",
        "",
        "### 对话",
        "",
        *format_dialogue(output.get("dialogue", [])),
        "",
        "### 状态变化",
        "",
        f"- current_location: {output.get('current_location') or state.get('current_location') or '未知'}",
        f"- sanity_delta: `{output.get('sanity_delta', 0)}`",
        f"- health_delta: `{output.get('health_delta', 0)}`",
        f"- game_over: `{output.get('game_over', False)}`",
        f"- game_over_reason: {output.get('game_over_reason') or '无'}",
        "",
        "### Context Memory 快照",
        "",
        *format_state(state),
        "",
        "### RAG Hits",
        "",
        *format_rag_hits(response.get("retrieved_chunks", [])),
        "",
        "### 下一轮选项",
        "",
        *format_options(output.get("options", []), None),
        "",
    ]
    append_block(path, lines)


def append_turn_error(
    path: Path,
    run_number: int,
    turn: int,
    session_id: str,
    previous_options: list[str],
    selected_index: int | None,
    action: str,
    score: int,
    exc: Exception,
) -> None:
    append_block(
        path,
        [
            f"## Run {run_number} / Turn {turn} 生成失败",
            "",
            f"- session_id: `{session_id}`",
            f"- selected_option: `{selected_index if selected_index is not None else 'fallback'}`",
            f"- selection_score: `{score}`",
            f"- selected_action: {action}",
            f"- error: `{exc}`",
            "",
            "### 本轮可选项",
            "",
            *format_options(previous_options, selected_index),
            "",
        ],
    )


def append_block(path: Path, lines: list[str]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines))
        if not lines or lines[-1] != "":
            file.write("\n")
