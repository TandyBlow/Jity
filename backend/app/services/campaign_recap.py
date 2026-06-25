"""CampaignRecapGenerator — LLM recap generation, storage, structural fallback."""

import logging
from typing import Any

from app.database import Database
from app.services.llm_client import LLMClient
from app.services.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class CampaignRecapGenerator:
    """LLM-driven recap generation + storage + structural fallback."""

    def __init__(self, db: Database, llm_client: LLMClient | None, prompt_builder: PromptBuilder | None) -> None:
        self.db = db
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder

    # ── Generation ───────────────────────────────────────────────────

    async def generate_recap(self, session_id: str) -> str | None:
        """Generate LLM-compressed recap from session_messages history.

        Uses deepseek-v4-flash (cheap) for non-real-time boundary call.
        Returns the compressed recap string, or None on failure.
        """
        if self.llm_client is None or self.prompt_builder is None:
            return None

        messages = self.db.get_messages(session_id)
        if not messages:
            return None

        try:
            recap_prompt = self.prompt_builder.build_recap(messages)
            recap_text = await self.llm_client.generate_text(
                recap_prompt, model="deepseek-v4-flash", max_tokens=800
            )
            return recap_text.strip()
        except Exception:
            logger.warning("Recap generation failed", exc_info=True)
            return None

    # ── Storage ──────────────────────────────────────────────────────

    def store_recap(
        self,
        persistence: Any,
        campaign_id: str,
        slot_name: str,
        progress: Any,
        fsm_state: str,
        recap_text: str,
    ) -> None:
        """Store both compressed (latest) and full (cumulative) recap.

        Full recap appends to existing full recap (cumulative history).
        Compressed recap is the latest single-session summary.
        """
        row = persistence.load(campaign_id, slot_name)
        existing_full = row.get("recap_full", "") if row else ""
        persistence.save_with_recap(
            campaign_id=campaign_id,
            slot_name=slot_name,
            arc_index=progress.arc_index,
            session_index=progress.session_index,
            turn_in_session=getattr(progress, "turn_in_session", 0),
            fsm_state=fsm_state,
            revealed_anchors=progress.revealed_anchors,
            completed_arcs=progress.completed_arcs,
            recap_compressed=recap_text,
            recap_full=(existing_full + "\n\n" + recap_text).strip() if existing_full else recap_text,
        )

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def is_first_turn_of_session(turn_in_session: int) -> bool:
        """Return True if this is the first turn of a campaign session."""
        return turn_in_session == 0

    def load_recap_compressed(self, persistence: Any, campaign_id: str, slot_name: str) -> str:
        """Load compressed recap from campaign_progress."""
        return persistence.read_recap_compressed(campaign_id, slot_name)

    @staticmethod
    def build_structural_recap(campaign: Any, progress: Any) -> str:
        """Build fallback structural recap from campaign data when LLM recap fails."""
        if progress is None or campaign is None:
            return ""

        parts = ["## 前情提要（结构摘要）", ""]
        try:
            arc = campaign.arcs[progress.arc_index]
            parts.append(f"完成了 {progress.arc_index} 个叙事弧")
            parts.append(f"当前弧：{arc.name}")
            parts.append(f"弧目标：{arc.goal or '无'}")
        except IndexError:
            parts.append("战役完成")

        if progress.revealed_anchors:
            parts.append(f"已揭示锚点：{len(progress.revealed_anchors)} 个")

        parts.append("（LLM 前情提要生成失败，此处为结构摘要。）")
        return "\n".join(parts)
