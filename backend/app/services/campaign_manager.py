"""CampaignManager — thin facade delegating to focused campaign services.

Owns the lifecycle state (campaign, progress, slot_name, fsm) and delegates
each concern to a dedicated service:
  - CampaignLoader: loading, FSM init, validation
  - CampaignPersistence: DB read/write
  - CampaignAnchorEvaluator: anchor evaluation, commit, conditions, cooldown
  - CampaignRecapGenerator: LLM recap, storage, structural fallback
  - CampaignContextBuilder: prompt injection string assembly
  - CampaignSessionAdvancer: turn/session/arc advancement

All public method signatures are preserved so callers (ScenarioGenerator,
routes, tests) remain unchanged.
"""

import json
import logging
from pathlib import Path
from typing import Any

from app.database import Database
from app.schemas.campaign import (
    AnchorEvent,
    AnchorTriggerConditions,
    CampaignSchema,
    CampaignProgress,
    CURRENT_SCHEMA_VERSION,
    campaign_adapter,
    migrate,
)
from app.schemas.game import StoryOutput
from app.services.campaign_advancer import CampaignSessionAdvancer
from app.services.campaign_anchors import CampaignAnchorEvaluator
from app.services.campaign_context import CampaignContextBuilder
from app.services.campaign_fsm import CampaignStateMachine
from app.services.campaign_loader import CampaignLoader
from app.services.campaign_persistence import CampaignPersistence
from app.services.campaign_recap import CampaignRecapGenerator
from app.services.context_strategy import (
    ContextStrategy,
    SimpleTruncationStrategy,
)

# ── Local prompt helper (moved from prompt_builder.py — sole consumer ──

_FACT_EXTRACTION_PROMPT = """你是一个TRPG叙事分析系统。从以下最近5个回合的叙事内容中提取新发现的世界事实。

要求：
1. 只提取本轮新发现的事实——不要重复已经知道的信息
2. 每个事实包含：name（简短名称）、description（详细描述）、status（已知known/推测suspected/确认resolved）
3. 如果未发现新事实，返回空数组
4. 关注异常、悬疑、重要叙事元素

输出格式（严格的JSON数组）：
[
  {"name": "事实名", "description": "详细描述", "status": "known"}
]"""


def build_fact_extraction(narration_text: str, recent_events: list[str]) -> str:
    """Build prompt for batch fact extraction from recent turns."""
    events_text = "\n".join(f"- {e}" for e in recent_events[-5:])
    return (
        f"{_FACT_EXTRACTION_PROMPT}\n\n"
        f"## 最近事件\n{events_text}\n\n"
        f"## 最新叙事\n{narration_text}"
    )

logger = logging.getLogger(__name__)


class CampaignManager:
    """Thin facade — delegates each concern to a focused service."""

    def __init__(
        self,
        db: Database,
        campaigns_dir: Path,
        scripted_story,
        prompt_builder=None,
        llm_client=None,
        health_monitor=None,
    ) -> None:
        self.db = db
        self.campaigns_dir = campaigns_dir
        self.scripted_story = scripted_story
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self._health_monitor = health_monitor

        # ── Sub-services ──
        self._persistence = CampaignPersistence(db)
        self._loader = CampaignLoader(db, self._persistence)
        self._anchors = CampaignAnchorEvaluator()
        self._recap = CampaignRecapGenerator(db, llm_client, prompt_builder)
        self._advancer = CampaignSessionAdvancer(self._persistence, self._recap)
        self._context = CampaignContextBuilder(
            db, self._anchors, self._recap, health_monitor
        )
        self._strategy: ContextStrategy = SimpleTruncationStrategy()  # public for tests

    # ── Properties (preserve old API) ────────────────────────────────

    @property
    def campaign(self) -> CampaignSchema | None:
        return self._loader.campaign

    @campaign.setter
    def campaign(self, value: CampaignSchema | None) -> None:
        self._loader.campaign = value

    @property
    def progress(self) -> CampaignProgress | None:
        return self._loader.progress

    @progress.setter
    def progress(self, value: CampaignProgress | None) -> None:
        self._loader.progress = value

    @property
    def slot_name(self) -> str:
        return self._loader.slot_name

    @slot_name.setter
    def slot_name(self, value: str) -> None:
        self._loader.slot_name = value

    @property
    def fsm(self) -> CampaignStateMachine:
        return self._loader.fsm

    @fsm.setter
    def fsm(self, value: CampaignStateMachine) -> None:
        self._loader.fsm = value

    # ── Loading / Init ───────────────────────────────────────────────

    def load(
        self,
        campaign_path: Path,
        campaign_id: str | None = None,
        start_arc_index: int = 0,
        start_session_index: int = 0,
        slot_name: str = "default",
    ) -> CampaignSchema:
        return self._loader.load(
            campaign_path, campaign_id, start_arc_index, start_session_index, slot_name
        )

    def is_loaded(self) -> bool:
        return self._loader.is_loaded()

    def get_opening_scene(self) -> str | None:
        return self._loader.get_opening_scene()

    # ── Persistence ──────────────────────────────────────────────────

    def save_progress(self) -> None:
        if self.progress is None:
            return
        self._persistence.save(
            campaign_id=self.progress.campaign_id,
            slot_name=self.slot_name,
            arc_index=self.progress.arc_index,
            session_index=self.progress.session_index,
            turn_in_session=getattr(self.progress, "turn_in_session", 0),
            fsm_state=str(self.fsm.state) if self.fsm.state else "idle",
            revealed_anchors=self.progress.revealed_anchors,
            completed_arcs=self.progress.completed_arcs,
        )

    def _persist_progress(self) -> None:
        self.save_progress()

    def load_progress(self, campaign_id: str) -> CampaignProgress | None:
        return self._loader.load_progress(campaign_id)

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

    # ── Recap ────────────────────────────────────────────────────────

    async def generate_recap(self, session_id: str) -> str | None:
        return self._recap.generate_recap(session_id)

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

    DEFAULT_MAX_TURNS = 30

    def resolve_max_turns(self) -> int:
        return self._advancer.resolve_max_turns(self.campaign, self.progress)

    async def advance_session(self) -> str:
        return await self._advancer.advance_session(
            self.campaign, self.progress, self.fsm, self.slot_name
        )

    async def advance_arc(self) -> str:
        return await self._advancer.advance_arc(
            self.campaign, self.progress, self.fsm, self.slot_name
        )

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

    # ── Token budget ─────────────────────────────────────────────────

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
