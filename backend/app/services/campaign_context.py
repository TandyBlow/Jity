"""CampaignContextBuilder — campaign context injection for prompt assembly.

Builds the campaign_context string that PromptBuilder.injects into the
system prompt.  Depends on anchor evaluator + recap generator + health
monitor, injected via constructor.
"""

import json
import logging
from typing import Any

from app.database import Database
from app.services.campaign_anchors import CampaignAnchorEvaluator
from app.services.campaign_recap import CampaignRecapGenerator
from app.services.health_monitor import HealthMonitor
from app.schemas.campaign import AnchorEvent

logger = logging.getLogger(__name__)


class CampaignContextBuilder:
    """Builds the campaign context string for every-turn prompt injection."""

    def __init__(
        self,
        db: Database,
        anchor_evaluator: CampaignAnchorEvaluator,
        recap_generator: CampaignRecapGenerator,
        health_monitor: HealthMonitor | None,
    ) -> None:
        self.db = db
        self.anchors = anchor_evaluator
        self.recap = recap_generator
        self._health_monitor = health_monitor

    def inject_context(
        self,
        campaign: Any,
        progress: Any,
        state: dict[str, Any],
        turn: int,
        slot_name: str,
        persistence: Any,
    ) -> str:
        """Build full campaign_context string for prompt injection.

        Includes: arc/session position, anchor progress, recap at session start,
        NPC relations, candidate triggers, health guidance.
        """
        if campaign is None or progress is None:
            return ""
        row = persistence.load(progress.campaign_id, slot_name)
        try:
            relations = json.loads(row.get("npc_relations", "[]")) if row else []
        except (json.JSONDecodeError, KeyError):
            relations = []
        text, candidate = self.render_context(
            campaign, progress, state, turn, slot_name, relations,
            (row or {}).get("recap_compressed", ""),
            anchor_evaluator=self.anchors,
        )
        # The ONLY shared-state mutation of context injection: registering the
        # candidate anchor for the commit flow to merge (review round 6: the
        # turn-context path renders on a snapshot copy and must NOT touch it).
        self.anchors.pending_anchor_triggers = [(candidate, turn)] if candidate else []
        return text

    def render_context(
        self,
        campaign: Any,
        progress: Any,
        state: dict[str, Any],
        turn: int,
        slot_name: str,
        relations: list[dict[str, Any]],
        recap_compressed: str,
        *,
        anchor_evaluator: CampaignAnchorEvaluator | None = None,
    ) -> tuple[str, str | None]:
        """PURE campaign-context render on the passed progress (a copy).

        Returns (context text, candidate anchor id or None). Shared state is
        never mutated: pending-anchor registration is the caller's job, so a
        read-only snapshot render (commit-turn turn-context) can reuse this
        without leaking anchors into the shared manager.
        """
        parts: list[str] = []
        parts.append(f"当前战役：{campaign.title}")
        if campaign.constraints:
            parts.append(f"战役限制：{campaign.constraints}")

        # Arc/session position
        try:
            current_arc = campaign.arcs[progress.arc_index]
            current_session = current_arc.sessions[progress.session_index]
            parts.append(f"当前章节：{current_arc.name} — {current_session.name}")
            parts.append(f"章节目标：{current_arc.goal or '无'}")
            if current_session.opening_scene:
                parts.append("本幕开场背景：\n" + current_session.opening_scene)
                parts.append("从本幕开场和最近行动的结果继续，保持当前时间、地点和人物连续；不要重新开始故事或跳到其他章节。")
        except IndexError:
            parts.append("当前章节：无")

        # Anchor progress
        total_anchors = sum(
            len(s.anchor_events) for a in campaign.arcs for s in a.sessions
        )
        dynamic_revealed = sum(
            1 for a_id in progress.revealed_anchors if a_id.startswith("dynamic-")
        )
        total_anchors += dynamic_revealed
        revealed_count = len(progress.revealed_anchors)
        parts.append(f"锚点进度：{revealed_count}/{total_anchors} 已揭示")

        # Recap layer at session start
        turn_in_session = getattr(progress, "turn_in_session", 0)
        if self.recap.is_first_turn_of_session(turn_in_session):
            if recap_compressed:
                parts.insert(0, "## 前情提要\n" + recap_compressed)

        # NPC relations block (top-3 by absolute affinity)
        if relations:
            sorted_rels = sorted(
                relations, key=lambda r: abs(r.get("affinity", 0)), reverse=True
            )
            top3 = sorted_rels[:3]
            rel_lines = ["## 人物关系变化"]
            for r in top3:
                name = r.get("name", "未知")
                affinity = r.get("affinity", 0)
                if affinity > 0:
                    change_desc = "信任上升"
                elif affinity < 0:
                    change_desc = "敌意加深"
                else:
                    change_desc = "中性"
                rel_lines.append(f"- {name}: {change_desc} (当前好感: {affinity:+d})")
            parts.append("\n".join(rel_lines))

        # Candidate triggers this turn — evaluated on the PASSED progress
        # (a copy for snapshot renders); pending-anchor registration is the
        # caller's job, keeping this function side-effect free.
        turn_in_session = getattr(progress, "turn_in_session", turn) if progress else turn
        evaluator = anchor_evaluator if anchor_evaluator is not None else CampaignAnchorEvaluator()
        candidates = evaluator.evaluate_anchors(
            campaign, progress, state, turn_in_session,
            revealed_anchors=progress.revealed_anchors,
        )
        candidate_id: str | None = candidates[0].id if candidates else None
        if candidates:
            anchor = candidates[0]
            parts.append(self._describe_trigger(anchor))

        # Health guidance layer
        health_context = self.inject_health(progress)
        if health_context:
            parts.append(health_context)

        return "\n".join(parts), candidate_id

    def inject_health(self, progress: Any) -> str | None:
        """Return health guidance context string, or None."""
        monitor = self._health_monitor
        if monitor is None or progress is None:
            return None

        turn = getattr(progress, "turn_in_session", 0)
        try:
            metrics = monitor.compute(progress.campaign_id, turn)
        except Exception:
            logger.warning("Health metric computation failed for campaign %s", progress.campaign_id, exc_info=True)
            return None

        if not metrics.needs_guidance:
            return None

        return self._build_health_guidance(metrics)

    # ── Private ──────────────────────────────────────────────────────

    @staticmethod
    def _describe_trigger(anchor: AnchorEvent) -> str:
        """Build a diegetic redirection instruction for the anchor."""
        return (
            f"叙事引导：玩家即将触发锚点事件「{anchor.name}」。\n"
            f"锚点描述：{anchor.description}\n"
            "请通过环境线索、NPC暗示、或剧情推动自然地引导玩家接近该事件。\n"
            "不要直接告诉玩家发生了什么，让玩家自己的选择引领他们到达那里。\n"
            "如果玩家的当前行动与该锚点方向完全不同，等待更好的时机——今天的线索终将浮现。"
        )

    @staticmethod
    def _build_health_guidance(health: Any) -> str | None:
        """Map each HealthGuidanceHint to a narrative instruction."""
        hints_map = {
            "pacing_slow": "叙事节奏提示：当前剧情进展较慢，可适当引入新的环境变化或NPC行动来推动局面。",
            "pacing_fast": "叙事节奏提示：当前事件推进较快，可适当放慢节奏，让玩家有时间消化线索和角色互动。",
            "dialogue_heavy": "叙事平衡提示：对话占比较高，可适当增加环境描写和行动后果，保持叙事与互动的平衡。",
            "tension_plateau": "叙事张力提示：当前局势趋于平稳，可在背景中埋设新的悬念或暗示即将到来的变化。",
            "clue_starvation": "叙事线索提示：最近揭示的线索较少，可通过环境细节、NPC对话或意外发现提供新的调查方向。",
        }

        parts = ["## 叙事健康引导"]
        for hint in health.guidance_hints:
            hint_name = hint.value if hasattr(hint, "value") else str(hint)
            if hint_name in hints_map:
                parts.append(hints_map[hint_name])
        return "\n".join(parts) if len(parts) > 1 else None
