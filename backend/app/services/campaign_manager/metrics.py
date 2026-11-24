"""CampaignManager facade — token budget and turn metrics."""

from typing import Any

from app.schemas.game import StoryOutput


class MetricsFacade:
    """Token budget checks and per-turn instrumentation."""

    DEFAULT_MAX_TURNS = 30

    # ── Token budget (dead in production, kept for test compat) ───────

    TOKEN_BUDGET_LIMIT = 102400

    def check_token_budget(self, prompt: str) -> tuple[bool, int, str]:
        """Check if prompt exceeds token budget. Delegates to strategy."""
        token_count = self._strategy.count_tokens(prompt)
        if self._strategy.should_truncate(token_count):
            return (
                False,
                token_count,
                f"警告：token计数 {token_count} 超过预算 {self._strategy.budget_limit}",
            )
        return True, token_count, ""

    def resolve_max_turns(self) -> int:
        return self._advancer.resolve_max_turns(self.campaign, self.progress)

    def truncate_prompt_sections(self, sections: dict[str, str]) -> tuple[str, int, bool]:
        prompt = "\n\n".join(sections.values())
        token_count = self._strategy.count_tokens(prompt)
        if not self._strategy.should_truncate(token_count):
            return prompt, token_count, False
        truncated = self._strategy.truncate(sections)
        return truncated, self._strategy.count_tokens(truncated), True

    # ── Per-turn instrumentation ─────────────────────────────────────

    def record_turn(self, output: StoryOutput, state: dict[str, Any], latency_ms: int) -> dict[str, int]:
        narration = output.narration
        dialogue = output.dialogue or []
        options = output.options or []
        location_before = state.get("current_location", "")
        location_after = output.current_location or location_before
        return {
            "word_count": len(narration),
            "option_count": len(options),
            "sanity_delta": output.sanity_delta,
            "health_delta": output.health_delta,
            "dialogue_lines": len(dialogue),
            "location_changed": 1 if location_after != location_before else 0,
            "token_count": 0,
        }
