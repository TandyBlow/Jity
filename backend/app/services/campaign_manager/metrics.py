"""CampaignManager facade — token budget, fact extraction and turn metrics."""

import logging
from typing import Any

from app.schemas.game import StoryOutput
from app.services.campaign_manager.fact_prompts import build_fact_extraction

logger = logging.getLogger(__name__)


class MetricsFacade:
    """Token budget checks, fact extraction and per-turn instrumentation."""

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

    # ── Fact extraction ──────────────────────────────────────────────

    async def extract_facts(self, narration_text: str, recent_events: list[str]) -> list[dict]:
        if self.llm_client is None or self.prompt_builder is None:
            return []
        prompt = build_fact_extraction(narration_text, recent_events)
        try:
            facts = await self.llm_client.generate_json(
                prompt, model="deepseek-v4-flash", max_tokens=2000, temperature=0.2
            )
            if isinstance(facts, list):
                return [f for f in facts if isinstance(f, dict) and f.get("name")]
            return []
        except Exception:
            logger.warning("Fact extraction failed for campaign %s", self.progress.campaign_id if self.progress else "?", exc_info=True)
            return []

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
