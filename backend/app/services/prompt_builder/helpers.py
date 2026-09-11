"""Static formatting helpers for prompt sections."""

from typing import Any


class SectionHelpers:
    @staticmethod
    def _compact_list(items: list[dict[str, Any]], *, kind: str) -> str:
        if not items:
            return "无"
        return "；".join(
            SectionHelpers._compact_item(item, kind=kind) for item in items[:8]
        )

    @staticmethod
    def _compact_item(item: dict[str, Any], *, kind: str) -> str:
        name = item.get("name", "未命名")
        status = item.get("status") or item.get("disposition") or "已记录"
        if kind == "npc":
            detail = (
                item.get("relationship")
                or item.get("description")
                or item.get("notes")
                or item.get("current_location")
            )
        elif kind == "quest":
            detail = item.get("objective") or item.get("description") or item.get("notes")
        elif kind == "world_fact":
            detail = item.get("description") or item.get("notes")
        else:
            detail = item.get("description") or item.get("notes") or item.get("location")
        return f"{name}({status}{f'：{detail}' if detail else ''})"

    @staticmethod
    def _compact_player_status(player_status: dict[str, Any]) -> str:
        if not player_status:
            return "无"
        parts = [
            player_status.get("condition", ""),
            (
                f"危险等级 {player_status.get('danger_level')}"
                if player_status.get("danger_level")
                else ""
            ),
            (
                f"目标：{player_status.get('current_goal')}"
                if player_status.get("current_goal")
                else ""
            ),
            player_status.get("notes", ""),
        ]
        return "；".join(part for part in parts if part) or "无"

    @staticmethod
    def _bullet_list(items: list[str]) -> str:
        if not items:
            return "- 无"
        return "\n".join(f"- {item}" for item in items)
