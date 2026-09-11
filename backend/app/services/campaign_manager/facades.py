"""CampaignManager facade — anchor, context and rule passthrough concerns."""

from typing import Any

from app.schemas.campaign import AnchorEvent, AnchorTriggerConditions
from app.services.campaign_context import CampaignContextBuilder


class AnchorFacade:
    """Anchor evaluation/commit and context-injection delegations."""

    # ── Anchors ──────────────────────────────────────────────────────

    def evaluate_anchors(self, state: dict[str, Any], turn: int) -> list[AnchorEvent]:
        if self.campaign is None or self.progress is None:
            return []
        return self._anchors.evaluate_anchors(
            self.campaign, self.progress, state, turn,
            revealed_anchors=self.progress.revealed_anchors,
        )

    def commit_pending_anchors(self) -> list[str]:
        def _mark(anchor_id: str, turn: int) -> None:
            self.mark_anchor_triggered(anchor_id, turn)

        return self._anchors.commit_pending_anchors(self.progress, mark_fn=_mark)

    def mark_anchor_triggered(self, anchor_id: str, turn: int) -> None:
        if self.progress is not None:
            if anchor_id not in self.progress.revealed_anchors:
                self.progress.revealed_anchors.append(anchor_id)
        self._anchors.record_cooldown(anchor_id, turn)
        self._persist_progress()

    def detect_deviation(self, state: dict[str, Any], turn: int) -> bool:
        if self.campaign is None or self.progress is None:
            return False
        return self._anchors.detect_deviation(
            self.campaign, self.progress, state, turn,
            revealed_anchors=self.progress.revealed_anchors,
        )

    def generate_adaptive_anchors(self, state: dict[str, Any]) -> list[AnchorEvent]:
        if self.progress is None:
            return []
        return self._anchors.generate_adaptive_anchors(
            state, self.progress, self.progress.revealed_anchors,
        )

    # ── Context injection ────────────────────────────────────────────

    def inject_context(self, state: dict[str, Any], turn: int) -> str:
        return self._context.inject_context(
            self.campaign, self.progress, state, turn, self.slot_name, self._persistence
        )

    def inject_health(self) -> str | None:
        return self._context.inject_health(self.progress)

    def _describe_trigger(self, anchor: AnchorEvent) -> str:
        return CampaignContextBuilder._describe_trigger(anchor)

    # ── Internal passthroughs (tests call these directly) ─────────────

    def _conditions_met(self, conditions: AnchorTriggerConditions, state: dict[str, Any]) -> bool:
        return self._anchors._conditions_met(conditions, state)

    def _check_cooldown(self, anchor_id: str, turn: int) -> bool:
        return self._anchors._check_cooldown(anchor_id, turn)

    def _build_health_guidance(self, health: Any) -> str | None:
        return CampaignContextBuilder._build_health_guidance(health)

    # Expose internal cooldown dict for tests
    @property
    def _anchor_cooldowns(self) -> dict[str, int]:
        return self._anchors._anchor_cooldowns
