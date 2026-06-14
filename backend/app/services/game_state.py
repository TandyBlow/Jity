from __future__ import annotations

import json
import uuid
from typing import Any

from app.database import Database
from app.schemas import StoryOutput


def default_state() -> dict[str, Any]:
    return {
        "sanity": 80,
        "health": 100,
        "turn": 0,
        "current_location": "卡塞尔学院报到处大厅",
        "items": [],
        "npcs": [],
        "quests": [],
        "recent_events": ["路明非拖着旧行李箱抵达卡塞尔学院报到处大厅，诺诺前来接应。"],
        "world_facts": [],
    }


class GameStateManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_session(self, game_name: str, model: str) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        state = default_state()
        self.db.write_session(session_id, game_name, model, state)
        return {"session_id": session_id, "game_name": game_name, "model": model, "state": state}

    def get_session_payload(self, session_id: str) -> dict[str, Any] | None:
        row = self.db.get_session(session_id)
        if not row:
            return None
        return {
            "session_id": row["id"],
            "game_name": row["game_name"],
            "model": row["model"],
            "state": json.loads(row["state_json"]),
        }

    def save_state(self, session_id: str, game_name: str, model: str, state: dict[str, Any]) -> None:
        self.db.write_session(session_id, game_name, model, state)

    def apply_output(self, state: dict[str, Any], action: str, output: StoryOutput) -> dict[str, Any]:
        next_state = dict(state)
        next_state["sanity"] = self._clamp(next_state.get("sanity", 80) + output.sanity_delta)
        next_state["health"] = self._clamp(next_state.get("health", 100) + output.health_delta)
        next_state["turn"] = int(next_state.get("turn", 0)) + 1
        if output.current_location:
            next_state["current_location"] = output.current_location

        next_state["items"] = self._merge_items(next_state.get("items", []), output.items_gained, output.items_lost)
        next_state["npcs"] = self._merge_by_name(next_state.get("npcs", []), output.npcs_encountered)
        next_state["quests"] = self._merge_by_name(next_state.get("quests", []), output.quests_updated)
        next_state["recent_events"] = self._append_recent(
            next_state.get("recent_events", []),
            f"玩家行动：{action}；结果：{output.narration[:90]}",
        )
        return next_state

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, int(value)))

    @staticmethod
    def _merge_items(
        current: list[dict[str, Any]],
        gained: list[dict[str, Any]],
        lost: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        lost_names = {item.get("name") for item in lost}
        merged = [item for item in current if item.get("name") not in lost_names]
        existing = {item.get("name") for item in merged}
        for item in gained:
            if item.get("name") and item.get("name") not in existing:
                merged.append(item)
                existing.add(item.get("name"))
        return merged

    @staticmethod
    def _merge_by_name(current: list[dict[str, Any]], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged = {item.get("name"): dict(item) for item in current if item.get("name")}
        for update in updates:
            name = update.get("name")
            if not name:
                continue
            existing = merged.get(name, {})
            existing.update({key: value for key, value in update.items() if value not in (None, "")})
            merged[name] = existing
        return list(merged.values())

    @staticmethod
    def _append_recent(events: list[str], event: str) -> list[str]:
        return [*events, event][-8:]
