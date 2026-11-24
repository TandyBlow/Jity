"""SCORE Item State Tracking (Yi et al., 2025).

Implements the continuity error detection from the SCORE framework:
  - Each tracked item has a state: active / lost / destroyed / unknown
  - If an item reappears as 'active' after being 'lost' or 'destroyed',
    that's flagged as a continuity error and the transition is prevented
  - Episode summaries are stored for RAG-based retrieval

Key results from the paper:
  - Item Status baseline: 0% → SCORE: 98% (GPT-4)
  - Consistency improves 2.4-7.8pp across models
"""

import logging
from typing import Any

from app.schemas.agent_io import ItemState, ItemStateRecord

logger = logging.getLogger(__name__)


class ScoreTracker:
    """Tracks item states across turns and flags continuity violations.

    Replaces the flat world_facts + items lists in GameStateManager
    with a SCORE-style state machine per item.
    """

    def __init__(self) -> None:
        # item_name → ItemStateRecord
        self._items: dict[str, ItemStateRecord] = {}

    # ── Public API ────────────────────────────────────────────────

    def get_or_create(self, item_name: str, turn: int, state: ItemState = ItemState.ACTIVE) -> ItemStateRecord:
        """Return existing record or create a new one."""
        if item_name in self._items:
            return self._items[item_name]
        record = ItemStateRecord(item_name=item_name, state=state, last_seen_turn=turn)
        self._items[item_name] = record
        return record

    def propose_transition(
        self, item_name: str, proposed_state: ItemState, turn: int
    ) -> tuple[ItemState, bool]:
        """Attempt a state transition. Returns (accepted_state, is_continuity_error).

        SCORE continuity rule:
          If proposed_state == active AND previous_state in {lost, destroyed}
          → flag as continuity error, keep previous_state.

        All other transitions are allowed.
        """
        record = self.get_or_create(item_name, turn)
        prev = record.state

        # SCORE continuity check
        is_error = False
        if proposed_state == ItemState.ACTIVE and prev in (ItemState.LOST, ItemState.DESTROYED):
            is_error = True
            logger.warning(
                "SCORE continuity error: item '%s' cannot go from %s → active at turn %d",
                item_name, prev.value, turn,
            )
            # Keep the previous state (prevent erroneous transition)
            return prev, True

        # Valid transition — update record
        self._items[item_name] = record.model_copy(
            update={"state": proposed_state, "last_seen_turn": turn}
        )
        return proposed_state, False

    def check_narration_continuity(
        self, narration: str, turn: int, items_from_llm: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Check LLM output for continuity violations and auto-correct.

        Args:
            narration: The narration text from the LLM.
            turn: Current turn number.
            items_from_llm: Parsed items from memory_updates.items_upserted.

        Returns:
            List of continuity violation dicts with correction info.
        """
        violations: list[dict[str, Any]] = []

        for item_data in items_from_llm:
            name = item_data.get("name", "")
            if not name:
                continue

            # Determine proposed state from LLM output
            status = item_data.get("status", "owned").lower()
            proposed = self._status_to_state(status)

            accepted, is_error = self.propose_transition(name, proposed, turn)
            if is_error:
                violations.append({
                    "item_name": name,
                    "previous_state": self._items[name].state.value,
                    "proposed_state": proposed.value,
                    "accepted_state": accepted.value,
                    "turn": turn,
                })

        return violations

    def get_all_states(self) -> dict[str, str]:
        """Return item_name → state string for all tracked items."""
        return {name: rec.state.value for name, rec in self._items.items()}

    def get_record(self, item_name: str) -> ItemStateRecord | None:
        return self._items.get(item_name)

    def all_records(self) -> list[ItemStateRecord]:
        return list(self._items.values())

    def load_from_state(self, records: list[dict[str, Any]]) -> None:
        """Bulk-load item states from persisted data (e.g. DB row)."""
        self._items.clear()
        for r in records:
            name = r.get("item_name", "")
            if not name:
                continue
            state_str = r.get("state", "active")
            try:
                state = ItemState(state_str)
            except ValueError:
                state = ItemState.UNKNOWN
            self._items[name] = ItemStateRecord(
                item_name=name,
                state=state,
                last_seen_turn=r.get("last_seen_turn", 0),
                notes=r.get("notes", ""),
            )

    def export_state(self) -> list[dict[str, Any]]:
        """Export item states for persistence."""
        return [rec.model_dump() for rec in self._items.values()]

    # ── Private ──────────────────────────────────────────────────

    @staticmethod
    def _status_to_state(status: str) -> ItemState:
        """Map LLM status strings to ItemState enum."""
        mapping = {
            "owned": ItemState.ACTIVE,
            "active": ItemState.ACTIVE,
            "lost": ItemState.LOST,
            "missing": ItemState.LOST,
            "destroyed": ItemState.DESTROYED,
            "broken": ItemState.DESTROYED,
            "used": ItemState.DESTROYED,
            "unknown": ItemState.UNKNOWN,
            "observed": ItemState.ACTIVE,
        }
        return mapping.get(status, ItemState.ACTIVE)
