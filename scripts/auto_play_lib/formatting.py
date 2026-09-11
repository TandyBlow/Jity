"""Markdown formatting helpers for playtest logs."""

import json
from typing import Any


def format_options(options: list[str], selected_index: int | None) -> list[str]:
    if not options:
        return ["- 无"]
    lines = []
    for index, option in enumerate(options, start=1):
        marker = " [SELECTED]" if selected_index == index else ""
        lines.append(f"{index}. {option}{marker}")
    return lines


def format_dialogue(dialogue: list[dict[str, Any]]) -> list[str]:
    if not dialogue:
        return ["- 无"]
    return [f"- **{line.get('speaker') or '未知'}**：{line.get('text') or ''}" for line in dialogue]


def format_state(state: dict[str, Any]) -> list[str]:
    if not state:
        return ["- 无"]
    player_status = state.get("player_status") or {}
    lines = [
        f"- turn: `{state.get('turn', 0)}`",
        f"- current_location: {state.get('current_location') or '未知'}",
        f"- sanity: `{state.get('sanity', '')}`",
        f"- health: `{state.get('health', '')}`",
        f"- player_status: {compact_mapping(player_status)}",
        f"- items: {compact_named_list(state.get('items', []))}",
        f"- npcs: {compact_named_list(state.get('npcs', []))}",
        f"- quests: {compact_named_list(state.get('quests', []))}",
        f"- world_facts: {compact_named_list(state.get('world_facts', []))}",
        "- recent_events:",
    ]
    recent_events = state.get("recent_events", [])
    if recent_events:
        lines.extend(f"  - {event}" for event in recent_events)
    else:
        lines.append("  - 无")
    return lines


def compact_named_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return "无"
    parts = []
    for item in items[:12]:
        name = item.get("name") or "未命名"
        status = item.get("status") or item.get("relationship") or item.get("objective") or item.get("description") or "已记录"
        parts.append(f"{name}({status})")
    suffix = f"；另有 {len(items) - 12} 项" if len(items) > 12 else ""
    return "；".join(parts) + suffix


def compact_mapping(mapping: dict[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in mapping.items() if value]
    return "；".join(parts) if parts else "无"


def format_rag_hits(chunks: list[dict[str, Any]]) -> list[str]:
    if not chunks:
        return ["- 无"]
    lines = []
    for chunk in chunks:
        keywords = ", ".join(chunk.get("keywords", [])) or "无"
        content = str(chunk.get("content") or "").replace("\n", " ").strip()
        if len(content) > 180:
            content = f"{content[:177]}..."
        lines.append(
            f"- `{chunk.get('source_type')}` score `{chunk.get('score')}` importance `{chunk.get('importance', 3)}` "
            f"**{chunk.get('title')}** keywords: {keywords}；{content}"
        )
    return lines


def fenced_json(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"

