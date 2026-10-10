"""GameStateManager — session persistence and state transitions."""

import json
import re
import uuid
from typing import Any

from app.database import Database
from app.schemas import StoryOutput

from app.services.game_state.defaults import (
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


_MEMORY_KINDS = {
    "items": "item",
    "npcs": "npc",
    "quests": "quest",
    "world_facts": "world_fact",
}


class GameStateManager(MemoryNormalizationMixin, StateInferenceMixin, EntryStateMixin):
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_session(self, game_name: str, model: str) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        state = default_state()
        self.db.write_session(session_id, game_name, model, state)
        active_turn_id = self.db.ensure_timeline_root(session_id, state, model)
        return {
            "session_id": session_id,
            "game_name": game_name,
            "model": model,
            "state": state,
            "active_turn_id": active_turn_id,
        }

    def get_session_payload(self, session_id: str) -> dict[str, Any] | None:
        row = self.db.get_session(session_id)
        if not row:
            return None
        return {
            "session_id": row["id"],
            "game_name": row["game_name"],
            "model": row["model"],
            "state": json.loads(row["state_json"]),
            "campaign_filename": row["campaign_filename"],
            "active_turn_id": row["active_turn_id"],
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

        updates = self.declared_updates(memory, output.model_dump())
        world_facts = [*updates["world_facts"]["upserted"], *self._infer_world_facts(action, output)]

        next_state["items"] = self._remove_by_name(
            self.merge_by_name(next_state.get("items", []), updates["items"]["upserted"], kind="item"),
            updates["items"]["removed"],
        )
        next_state["npcs"] = self.merge_by_name(
            next_state.get("npcs", []),
            updates["npcs"]["upserted"],
            kind="npc",
            default_location=next_state.get("current_location", ""),
        )
        next_state["quests"] = self.merge_by_name(
            next_state.get("quests", []), updates["quests"]["upserted"], kind="quest"
        )
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
    def declared_updates(memory: dict[str, Any], output: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """Every upsert and removal a turn declares, legacy fields folded in.

        Later entries win, which is the order apply_output merges them in. The
        trace view reports this same mapping, so a change here cannot silently
        desync what is stored from what the observation surface claims.
        """
        return {
            "items": {
                "upserted": [*(output.get("items_gained") or []), *(memory.get("items_upserted") or [])],
                "removed": [*(output.get("items_lost") or []), *(memory.get("items_removed") or [])],
            },
            "npcs": {
                "upserted": [*(output.get("npcs_encountered") or []), *(memory.get("npcs_upserted") or [])],
                "removed": [],
            },
            "quests": {
                "upserted": [*(output.get("quests_updated") or []), *(memory.get("quests_upserted") or [])],
                "removed": [],
            },
            "world_facts": {
                "upserted": list(memory.get("world_facts_upserted") or []),
                "removed": [],
            },
        }

    def memory_trace_entry(self, output: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
        """Per turn: the names the model declared, and the names state kept.

        A declared name absent from state was dropped — by the cap, by an empty
        name, or by a removal in the same turn. The difference is the whole
        point of watching a long run.
        """
        memory = (output or {}).get("memory_updates") or {}
        updates = self.declared_updates(memory, output or {})
        entry: dict[str, Any] = {}
        for category, kind in _MEMORY_KINDS.items():
            declared: list[str] = []
            for item in updates[category]["upserted"]:
                normalized = self._normalize_memory(item, kind)
                name = normalized.get("name") if normalized else ""
                if name and name not in declared:
                    declared.append(name)
            held = [
                item["name"]
                for item in (state.get(category) or [])
                if isinstance(item, dict) and item.get("name")
            ]
            entry[category] = {"declared": declared, "held": held}
        return entry

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
    def sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
        """Remove server-only state before returning a response to the client."""
        state.pop("_memory_controller", None)
        state.pop("_campaign_session_index", None)
        return state

    @staticmethod
    def enforce_state_caps(state: dict[str, Any]) -> dict[str, Any]:
        """Apply defensive caps to prevent 270-turn state bloat.

        Caps: 15 NPCs, 10 quests, 15 world_facts.
        Inventory is authoritative and must not silently drop acquired items.
        Excess entries are trimmed from the end (FIFO — oldest first kept).
        """
        state["npcs"] = state.get("npcs", [])[:MAX_NPCS]
        state["quests"] = state.get("quests", [])[:MAX_QUESTS]
        state["world_facts"] = state.get("world_facts", [])[:MAX_WORLD_FACTS]
        return state
