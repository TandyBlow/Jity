"""CampaignAnchorEvaluator — anchor evaluation, commit, conditions, cooldown.

Pure logic + cooldown tracking. Takes campaign/progress/state as method
parameters so it remains decoupled from the CampaignManager lifecycle.
"""

import logging
from typing import Any

from app.schemas.campaign import AnchorEvent, AnchorTriggerConditions

logger = logging.getLogger(__name__)


class CampaignAnchorEvaluator:
    """Stateless anchor evaluation (except cooldown tracking)."""

    def __init__(self) -> None:
        self._anchor_cooldowns: dict[str, int] = {}
        self._pending_anchor_triggers: list[tuple[str, int]] = []

    # ── Public API ───────────────────────────────────────────────────

    def evaluate_anchors(
        self,
        campaign: Any,
        progress: Any,
        state: dict[str, Any],
        turn: int,
        *,
        revealed_anchors: list[str],
    ) -> list[AnchorEvent]:
        """Evaluate pending anchors; returns 0 or 1 candidate.

        All state (campaign, progress, revealed_anchors) is passed in so
        the evaluator doesn't depend on the CampaignManager instance.
        """
        if campaign is None or progress is None:
            return []

        # Get current session's anchor events
        try:
            arc = campaign.arcs[progress.arc_index]
            session = arc.sessions[progress.session_index]
            anchors = list(session.anchor_events)
        except IndexError:
            return []

        if self.detect_deviation(campaign, progress, state, turn, revealed_anchors) or (
            turn >= 3 and not anchors
        ):
            anchors.extend(self.generate_adaptive_anchors(state, progress, revealed_anchors))

        # Filter: not already revealed
        candidates = [a for a in anchors if a.id not in revealed_anchors]

        # Filter: hard conditions met
        candidates = [a for a in candidates if self._conditions_met(a.trigger_conditions, state)]

        # Filter: cooldown (>=3 turns since same anchor type)
        candidates = [a for a in candidates if self._check_cooldown(a.id, turn)]

        if not candidates:
            return []

        # Sort by priority (lower number = higher priority)
        candidates.sort(key=lambda a: a.priority)
        return candidates[:1]

    def commit_pending_anchors(self, progress: Any, *, mark_fn) -> list[str]:
        """Mark anchors that were injected into a successful turn prompt.

        Args:
            mark_fn: Callable(anchor_id, turn) that records the trigger
                     on the progress object and persists.
        """
        if not self._pending_anchor_triggers:
            return []
        triggered: list[str] = []
        for anchor_id, turn in self._pending_anchor_triggers:
            mark_fn(anchor_id, turn)
            triggered.append(anchor_id)
        self._pending_anchor_triggers = []
        return triggered

    @property
    def pending_anchor_triggers(self) -> list[tuple[str, int]]:
        return self._pending_anchor_triggers

    @pending_anchor_triggers.setter
    def pending_anchor_triggers(self, value: list[tuple[str, int]]) -> None:
        self._pending_anchor_triggers = value

    # ── Deviation detection ──────────────────────────────────────────

    def detect_deviation(
        self,
        campaign: Any,
        progress: Any,
        state: dict[str, Any],
        turn: int,
        revealed_anchors: list[str],
    ) -> bool:
        """Return True if player has deviated from expected anchor path."""
        if progress is None or campaign is None:
            return False

        try:
            arc = campaign.arcs[progress.arc_index]
            session = arc.sessions[progress.session_index]
            total_session_anchors = len(session.anchor_events)
            revealed_in_session = [
                a_id for a_id in revealed_anchors if any(a.id == a_id for a in session.anchor_events)
            ]
            if turn >= 3 and total_session_anchors > 0 and len(revealed_in_session) == 0:
                return True
        except IndexError:
            pass

        return False

    def generate_adaptive_anchors(
        self,
        state: dict[str, Any],
        progress: Any,
        revealed_anchors: list[str],
    ) -> list[AnchorEvent]:
        """Generate adaptive anchors when player deviates from planned path."""
        if progress is None or not hasattr(progress, "arc_index"):
            return []

        dynamic_count = sum(1 for a_id in revealed_anchors if a_id.startswith("dynamic-"))
        if dynamic_count >= 3:
            return []

        location = state.get("current_location", "")
        new_anchors: list[AnchorEvent] = []
        idx = dynamic_count + 1

        if location:
            new_anchors.append(
                AnchorEvent(
                    id=f"dynamic-{progress.arc_index}-{progress.session_index}-{idx}",
                    name=f"探索：{location}",
                    description=f"玩家在当前地点 '{location}' 的探索中发现了新的线索",
                    priority=3,
                    trigger_conditions=AnchorTriggerConditions(location=location),
                )
            )

        return new_anchors[:3]

    # ── Private ──────────────────────────────────────────────────────

    def _conditions_met(self, conditions: AnchorTriggerConditions, state: dict[str, Any]) -> bool:
        """Check if all non-None hard-filter conditions match current state."""
        if conditions.location is not None:
            current_location = state.get("current_location", "")
            if conditions.location not in current_location:
                return False

        if conditions.npc_present is not None:
            npc_names = [npc.get("name", "") for npc in state.get("npcs", [])]
            if conditions.npc_present not in npc_names:
                return False

        if conditions.item_held is not None:
            item_names = [item.get("name", "") for item in state.get("items", [])]
            if conditions.item_held not in item_names:
                return False

        return True

    def _check_cooldown(self, anchor_id: str, turn: int) -> bool:
        """Return True if the anchor is off cooldown (>=3 turns since last trigger)."""
        last_triggered = self._anchor_cooldowns.get(anchor_id, -999)
        return (turn - last_triggered) >= 3

    def record_cooldown(self, anchor_id: str, turn: int) -> None:
        """Record that an anchor was triggered at a given turn."""
        self._anchor_cooldowns[anchor_id] = turn
