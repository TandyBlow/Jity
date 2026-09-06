"""GameStateManager — session persistence and state transitions."""

import json
import re
import uuid
from typing import Any

from app.database import Database
from app.schemas import StoryOutput

from app.services.game_state.defaults import (
    MAX_ITEMS,
    MAX_NPCS,
    MAX_QUESTS,
    MAX_WORLD_FACTS,
    RECENT_EVENT_LIMIT,
    RECENT_EVENT_MAX_CHARS,
    SANITY_RECOVERY_PER_TURN,
    default_state,
)
from app.services.game_state.entry_state import EntryStateMixin
from app.services.game_state.inference import StateInferenceMixin
from app.services.game_state.normalization import MemoryNormalizationMixin


class GameStateManager(MemoryNormalizationMixin, StateInferenceMixin, EntryStateMixin):
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
        next_state = self._ensure_state_shape(state)
        next_state["sanity"] = self._clamp(next_state.get("sanity", 80) + output.sanity_delta + SANITY_RECOVERY_PER_TURN)
        next_state["health"] = self._clamp(next_state.get("health", 100) + output.health_delta)
        next_state["turn"] = int(next_state.get("turn", 0)) + 1

        memory = output.memory_updates.model_dump()
        current_location = memory.get("current_location") or output.current_location
        if current_location:
            next_state["current_location"] = current_location

        items_upserted = [*output.items_gained, *memory.get("items_upserted", [])]
        items_removed = [*output.items_lost, *memory.get("items_removed", [])]
        npcs_upserted = [*output.npcs_encountered, *memory.get("npcs_upserted", [])]
        quests_upserted = [*output.quests_updated, *memory.get("quests_upserted", [])]
        world_facts = [*memory.get("world_facts_upserted", []), *self._infer_world_facts(action, output)]

        next_state["items"] = self._remove_by_name(
            self.merge_by_name(next_state.get("items", []), items_upserted, kind="item"),
            items_removed,
        )
        next_state["npcs"] = self.merge_by_name(
            next_state.get("npcs", []),
            npcs_upserted,
            kind="npc",
            default_location=next_state.get("current_location", ""),
        )
        next_state["quests"] = self.merge_by_name(next_state.get("quests", []), quests_upserted, kind="quest")
        next_state["world_facts"] = self.merge_by_name(
            next_state.get("world_facts", []),
            world_facts,
            kind="world_fact",
        )
        next_state["player_status"] = self._merge_player_status(
            next_state.get("player_status", {}),
            memory.get("player_status_patch", {}),
            next_state["sanity"],
            next_state["health"],
        )
        next_state["recent_events"] = self._append_recent(
            next_state.get("recent_events", []),
            self._build_key_event(action, output),
        )
        next_state = self.enforce_state_caps(next_state)
        return next_state

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, int(value)))

    def _ensure_state_shape(self, state: dict[str, Any]) -> dict[str, Any]:
        base = default_state()
        next_state = dict(base)
        next_state.update(state)
        next_state["items"] = [item for item in (self._normalize_memory(item, "item") for item in next_state.get("items", [])) if item]
        next_state["npcs"] = [
            item
            for item in (
                self._normalize_memory(
                    item,
                    "npc",
                    default_location=next_state.get("current_location", ""),
                )
                for item in next_state.get("npcs", [])
            )
            if item
        ]
        next_state["quests"] = [item for item in (self._normalize_memory(item, "quest") for item in next_state.get("quests", [])) if item]
        next_state["world_facts"] = [
            item
            for item in (self._normalize_memory(item, "world_fact") for item in next_state.get("world_facts", []))
            if item
        ]
        next_state["recent_events"] = [
            self._truncate(self._clean_text(str(event)), RECENT_EVENT_MAX_CHARS)
            for event in next_state.get("recent_events", [])
            if str(event).strip()
        ][-RECENT_EVENT_LIMIT:]
        next_state["player_status"] = self._merge_player_status(
            base["player_status"],
            next_state.get("player_status", {}),
            next_state.get("sanity", 80),
            next_state.get("health", 100),
        )
        return next_state

    @staticmethod
    def _append_recent(events: list[str], event: str) -> list[str]:
        cleaned_events = [GameStateManager._truncate(GameStateManager._clean_text(str(item)), RECENT_EVENT_MAX_CHARS) for item in events]
        cleaned_event = GameStateManager._truncate(GameStateManager._clean_text(event), RECENT_EVENT_MAX_CHARS)
        if cleaned_events and cleaned_events[-1] == cleaned_event:
            return cleaned_events[-RECENT_EVENT_LIMIT:]
        return [*cleaned_events, cleaned_event][-RECENT_EVENT_LIMIT:]

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 1]}…"

    @staticmethod
    def enforce_state_caps(state: dict[str, Any]) -> dict[str, Any]:
        """Apply defensive caps to prevent 270-turn state bloat.

        Caps: 20 items, 15 NPCs, 10 quests, 15 world_facts.
        Excess entries are trimmed from the end (FIFO — oldest first kept).
        """
        state["items"] = state.get("items", [])[:MAX_ITEMS]
        state["npcs"] = state.get("npcs", [])[:MAX_NPCS]
        state["quests"] = state.get("quests", [])[:MAX_QUESTS]
        state["world_facts"] = state.get("world_facts", [])[:MAX_WORLD_FACTS]
        return state
