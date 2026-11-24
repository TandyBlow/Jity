"""CampaignManager facade — recap and session/arc advancement concerns."""


class RecapAdvancerFacade:
    """Recap generation/storage and turn/session/arc advancement delegations."""

    # ── Recap ────────────────────────────────────────────────────────

    async def generate_recap(self, session_id: str) -> str | None:
        return await self._recap.generate_recap(session_id)

    def store_recap(self, recap_text: str) -> None:
        if self.progress is None:
            return
        self._recap.store_recap(
            self._persistence,
            self.progress.campaign_id, self.slot_name, self.progress,
            str(self.fsm.state) if self.fsm.state else "idle",
            recap_text,
        )

    def _is_first_turn_of_session(self, turn_in_session: int) -> bool:
        return self._recap.is_first_turn_of_session(turn_in_session)

    def _load_recap_compressed(self) -> str:
        if self.progress is None:
            return ""
        return self._recap.load_recap_compressed(
            self._persistence, self.progress.campaign_id, self.slot_name
        )

    def _build_structural_recap(self) -> str:
        if self.progress is None or self.campaign is None:
            return ""
        return self._recap.build_structural_recap(self.campaign, self.progress)

    # ── Session advancement ──────────────────────────────────────────

    def advance_turn(self) -> int:
        return self._advancer.advance_turn(self.progress, self.fsm, self.slot_name)

    async def advance_session(self, pending_messages: list[dict[str, str]] | None = None) -> str:
        return await self._advancer.advance_session(
            self.campaign, self.progress, self.fsm, self.slot_name, pending_messages
        )

    async def advance_arc(self, pending_messages: list[dict[str, str]] | None = None) -> str:
        return await self._advancer.advance_arc(
            self.campaign, self.progress, self.fsm, self.slot_name, pending_messages
        )
