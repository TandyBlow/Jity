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
import re
import unicodedata
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
        self._aliases: dict[str, str] = {}

    @staticmethod
    def normalize_name(name: str) -> str:
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", name)).strip().casefold()

    def canonical_name(self, name: str) -> str:
        key = self.normalize_name(name)
        return self._aliases.get(key, key)

    def resolve_item(self, item: dict[str, Any]) -> str:
        name = self.canonical_name(item.get("name", ""))
        known = {self.canonical_name(alias) for alias in item.get("aliases", [])}
        known.intersection_update(self._items)
        if name not in self._items and len(known) == 1:
            name = known.pop()
        for alias in [item.get("name", ""), *item.get("aliases", [])]:
            key = self.normalize_name(alias)
            if key and key not in self._items:
                self._aliases.setdefault(key, name)
        return name

    def seed(self, items: list[dict[str, Any]], turn: int) -> None:
        for item in items:
            name = self.resolve_item(item)
            if not name:
                continue
            for alias in item.get("aliases", []):
                self._aliases.setdefault(self.normalize_name(alias), name)
            self.get_or_create(name, turn, self._status_to_state(item.get("status", "owned")))

    def reconcile_inventory(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        inventory = {}
        for item in items:
            name = self.canonical_name(item.get("name", ""))
            record = self.get_record(name)
            if name and (record is None or record.state not in (ItemState.LOST, ItemState.DESTROYED)):
                inventory[name] = {**item, "name": name}
        return list(inventory.values())

    def validate_output(self, output, turn: int) -> list[dict[str, Any]]:
        """Normalize both item channels and remove rejected inventory mutations."""
        violations = []
        removals = [dict(item) for item in output.items_lost]
        removals += [item.model_dump() for item in output.memory_updates.items_removed]
        removed_names = set()
        for item in removals:
            name = self.resolve_item(item)
            if not name:
                continue
            item["name"] = name
            proposed = self._status_to_state(item.get("status", "lost"))
            if proposed == ItemState.ACTIVE:
                proposed = ItemState.LOST
            accepted, _ = self.propose_transition(name, proposed, turn)
            item["status"] = accepted.value
            removed_names.add(name)

        def validate(item):
            item = dict(item)
            name = self.resolve_item(item)
            # An explicit alias may refer to an existing identity. Never guess
            # synonyms: two distinct keys can legitimately coexist in a game.
            if not name or name in removed_names:
                return None
            item["name"] = name
            proposed = self._status_to_state(item.get("status", "owned"))
            accepted, error = self.propose_transition(name, proposed, turn, item.get("transition", ""))
            if error:
                violations.append({"item_name": name, "accepted_state": accepted.value, "turn": turn})
                return None
            item["status"] = "owned" if accepted == ItemState.ACTIVE else accepted.value
            if accepted in (ItemState.LOST, ItemState.DESTROYED):
                removals.append(item)
                return None
            return item

        output.items_gained = [value for item in output.items_gained if (value := validate(item))]
        from app.schemas.game.memory import ItemMemory
        output.memory_updates.items_upserted = [
            ItemMemory(**value) for item in output.memory_updates.items_upserted
            if (value := validate(item.model_dump()))
        ]
        output.items_lost = removals
        output.memory_updates.items_removed = []
        return violations

    # ── Public API ────────────────────────────────────────────────

    def get_or_create(self, item_name: str, turn: int, state: ItemState = ItemState.ACTIVE) -> ItemStateRecord:
        """Return existing record or create a new one."""
        item_name = self.canonical_name(item_name)
        if item_name in self._items:
            return self._items[item_name]
        record = ItemStateRecord(item_name=item_name, state=state, last_seen_turn=turn)
        self._items[item_name] = record
        return record

    def propose_transition(
        self, item_name: str, proposed_state: ItemState, turn: int, transition: str = ""
    ) -> tuple[ItemState, bool]:
        """Attempt a state transition. Returns (accepted_state, is_continuity_error).

        SCORE continuity rule:
          If proposed_state == active AND previous_state in {lost, destroyed}
          → flag as continuity error, keep previous_state.

        Explicit recovered/repaired events restore terminal states; unknown
        or repeated loss updates cannot erase a destruction record.
        """
        item_name = self.canonical_name(item_name)
        record = self.get_or_create(item_name, turn)
        prev = record.state
        if prev == ItemState.DESTROYED and proposed_state != ItemState.ACTIVE:
            return prev, False
        if prev == ItemState.LOST and proposed_state == ItemState.UNKNOWN:
            return prev, False

        # SCORE continuity check
        is_error = False
        restored = (prev == ItemState.LOST and transition == "recovered") or (
            prev == ItemState.DESTROYED and transition == "repaired"
        )
        if proposed_state == ItemState.ACTIVE and prev in (ItemState.LOST, ItemState.DESTROYED) and not restored:
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
            name = self.canonical_name(item_data.get("name", ""))
            if not name:
                continue

            # Determine proposed state from LLM output
            status = item_data.get("status", "owned").lower()
            proposed = self._status_to_state(status)

            accepted, is_error = self.propose_transition(name, proposed, turn, item_data.get("transition", ""))
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
        return self._items.get(self.canonical_name(item_name))

    def all_records(self) -> list[ItemStateRecord]:
        return list(self._items.values())

    def load_from_state(self, records: list[dict[str, Any]]) -> None:
        """Bulk-load item states from persisted data (e.g. DB row)."""
        self._items.clear()
        for r in records:
            name = self.canonical_name(r.get("item_name", ""))
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
            "遗失": ItemState.LOST,
            "丢失": ItemState.LOST,
            "损毁": ItemState.DESTROYED,
            "销毁": ItemState.DESTROYED,
            "消耗": ItemState.DESTROYED,
        }
        return mapping.get(status.strip().casefold(), ItemState.ACTIVE)
