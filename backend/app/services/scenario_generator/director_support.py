"""Director-facing support helpers for the agent pipeline.

Collects rules, anchor candidates and item-state summaries fed to the
DirectorAgent, injects the resulting direction into the narrator prompt,
and owns the per-session MemoryController cache.
"""

import asyncio
import logging

from app.services.embedding_client import EmbeddingClient
from app.services.memory.memory_controller import MemoryController
from app.schemas.agent_io import DirectorInstruction

logger = logging.getLogger(__name__)


class DirectorSupportMixin:
    # ── Agent pipeline helpers ─────────────────────────────────────────

    def _collect_relevant_rules(
        self, state: dict, campaign_manager
    ) -> list[str]:
        """Collect L2 rule snippets relevant to current player context.

        Extracts rules from the knowledge base that match the current
        game state (location hazards, NPC special rules, item mechanics).
        Falls back to generic TRPG rules when no specific matches found.
        """
        rules: list[str] = []

        # Generic CoC/TRPG rules (always applicable)
        rules.append(
            "规则：SAN值检定——当玩家遭遇神话生物或极度恐怖场景时，"
            "进行SAN检定（1d100 ≤ 当前SAN值）。失败扣除1d6 SAN值。"
        )
        rules.append(
            "规则：技能检定——当玩家尝试需要专业能力的行动时，"
            "进行技能检定（1d100 ≤ 技能值）。大失败（96-100）产生严重后果。"
        )

        # Location-specific hazards
        loc = state.get("current_location", "")
        if "墓" in loc or "教堂" in loc or "地下" in loc:
            rules.append(f"规则：当前地点({loc})可能存在超自然现象，注意环境线索。")

        return rules

    def _describe_anchor_candidates(
        self, campaign_manager, state: dict, turn: int
    ) -> str:
        """Format anchor candidate info for Director consumption."""
        if campaign_manager is None or not campaign_manager.is_loaded():
            return "无锚点"

        try:
            candidates = campaign_manager.evaluate_anchors(state, turn)
            if not candidates:
                return "无候选锚点"

            lines = []
            for a in candidates[:3]:
                lines.append(f"- [{a.id}] {a.name} (优先级{a.priority}): {a.description}")
            return "\n".join(lines)
        except Exception:
            return "锚点信息不可用"

    def _get_memory_controller(self, session_id: str) -> MemoryController:
        """Get or create a persistent MemoryController for this session.

        MemoryControllers persist across turns within a session,
        maintaining NSB/PCB/ScoreTracker state. Eviction based on
        simple dict size cap (oldest entries removed).
        """
        if session_id in self._memory_controllers:
            return self._memory_controllers[session_id]

        # Evict oldest if too many
        if len(self._memory_controllers) >= 50:
            oldest = next(iter(self._memory_controllers))
            del self._memory_controllers[oldest]

        # Lazy import embedding_client from dependencies (avoid circular)
        embedding: EmbeddingClient | None = None
        try:
            from app.dependencies import embedding_client
            embedding = embedding_client
        except Exception:
            pass

        mc = MemoryController(
            llm_client=self.llm_client,
            db=self.db,
            session_id=session_id,
            embedding_client=embedding,
        )
        self._memory_controllers[session_id] = mc
        return mc

    def _log_memory_task_done(self, task: asyncio.Task) -> None:
        """Discard a finished maintenance task, logging unexpected failures."""
        self._memory_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("Memory maintenance task failed", exc_info=task.exception())

    def _format_score_item_states(self, campaign_manager) -> str:
        """Build SCORE item state summary string for Director.

        Pulls from persistent MemoryController's ScoreTracker when available.
        """
        # ScoreTracker state is maintained in MemoryController.
        # For the Director call, we provide a summary from campaign_manager's
        # world_facts and items which the campaign already tracks.
        if campaign_manager is None or not campaign_manager.is_loaded():
            return ""
        campaign = campaign_manager.campaign
        if campaign is None:
            return ""
        parts = ["## 关键物品状态"]
        # Use campaign starting_state items as tracked items
        starting = campaign.starting_state or {}
        items = starting.get("items", [])
        if not items:
            return ""
        for item in items[:10]:
            name = item.get("name", "未知物品")
            parts.append(f"- {name}: 追踪中")
        return "\n".join(parts)

    @staticmethod
    def _inject_direction(
        prompt: str,
        direction: DirectorInstruction,
        ruling,  # ActionRuling
    ) -> str:
        """Inject director instruction and examiner ruling into the narrator prompt.

        Prepends the direction as a narrative instruction section, replacing
        the raw campaign_context anchor hints with concrete director guidance.
        """
        parts: list[str] = []

        # Examiner ruling summary
        if ruling.constraints:
            parts.append(f"[行动约束] {ruling.constraints}")

        # Director narrative direction
        if direction.narrative_direction:
            parts.append(f"[导演指令] {direction.narrative_direction}")

        # Anchor trigger
        if direction.anchor_triggered:
            parts.append(f"[锚点触发] {direction.anchor_triggered}")

        # Redirection hint
        if direction.redirection_strategy and direction.redirection_hint:
            parts.append(
                f"[叙事引导] 策略={direction.redirection_strategy.value}. "
                f"提示={direction.redirection_hint}"
            )

        # Item continuity
        for ic in direction.item_continuity_checks:
            if not ic.is_valid_transition:
                parts.append(
                    f"[物品连续性] {ic.item_name}: {ic.previous_state}→{ic.current_state} "
                    f"无效. {ic.error_description}"
                )

        # Health guidance
        if direction.health_guidance:
            parts.append(f"[健康引导] {direction.health_guidance}")

        if not parts:
            return prompt

        # Inject direction BEFORE the system prompt section
        direction_block = "## 导演指令\n" + "\n".join(parts) + "\n"
        return direction_block + prompt
