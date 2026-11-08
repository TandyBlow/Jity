"""CampaignManager facade — anchor, context and rule passthrough concerns."""

from typing import Any

from app.schemas.campaign import AnchorEvent


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

    def commit_pending_anchors(self, *, persist: bool = True) -> list[str]:
        def _mark(anchor_id: str, turn: int) -> None:
            self.mark_anchor_triggered(anchor_id, turn, persist=persist)

        return self._anchors.commit_pending_anchors(self.progress, mark_fn=_mark)

    def confirm_pending_anchors(self, output, state: dict) -> None:
        self._anchors.confirm_pending_anchors(output, state)

    def stage_forced_completion_anchor(self) -> AnchorEvent | None:
        """Stage the next missing core anchor for the hard-convergence turn.

        This deliberately ignores ordinary location/item trigger filters: at
        the hard threshold the narrator must bring the required event into
        the current scene instead of waiting for the player to wander into it.
        The staged anchor is committed only after the story turn succeeds.
        """
        if self.campaign is None or self.progress is None:
            return None
        try:
            session = self.campaign.arcs[self.progress.arc_index].sessions[
                self.progress.session_index
            ]
        except (AttributeError, IndexError, TypeError):
            return None
        revealed = set(self.progress.revealed_anchors or [])
        required = list(session.completion_anchors or [])
        by_id = {anchor.id: anchor for anchor in session.anchor_events}
        # Replace any ordinary candidate staged during context assembly.  In
        # convergence mode only a required core anchor may consume the turn.
        self._anchors.pending_anchor_triggers = []
        for anchor_id in required:
            if anchor_id in revealed or anchor_id not in by_id:
                continue
            anchor = by_id[anchor_id]
            self._anchors.stage_anchor(anchor, self.progress.turn_in_session)
            return anchor
        return None

    def mark_anchor_triggered(self, anchor_id: str, turn: int, *, persist: bool = True) -> None:
        if self.progress is not None:
            if anchor_id not in self.progress.revealed_anchors:
                self.progress.revealed_anchors.append(anchor_id)
        self._anchors.record_cooldown(anchor_id, turn)
        if persist:
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
