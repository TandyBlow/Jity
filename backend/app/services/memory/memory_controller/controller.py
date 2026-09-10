"""Core orchestration for the L0/L1/L2 memory subsystem."""

import logging
from typing import Any

from app.database import Database
from app.schemas.agent_io import MemoryRecord
from app.schemas.game.memory import MemoryUpdates
from app.services.embedding_client import EmbeddingClient
from app.services.llm_client import LLMClient
from app.services.memory.memory_controller.maintenance import MemoryMaintenanceMixin
from app.services.memory.nsb import NarrativeSummarizationBranch
from app.services.memory.pcb import PersonaConstructionBranch
from app.services.memory.score_tracker import ScoreTracker

logger = logging.getLogger(__name__)


class MemoryController(MemoryMaintenanceMixin):
    """Coordinate retrieval, continuity tracking, and background maintenance."""

    def __init__(
        self,
        llm_client: LLMClient,
        db: Database,
        session_id: str,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._llm = llm_client
        self._db = db
        self._session_id = session_id
        self._embedding = embedding_client
        self.score_tracker = ScoreTracker()
        self.nsb = NarrativeSummarizationBranch(
            llm_client, embedding_client=embedding_client
        )
        self.pcb = PersonaConstructionBranch(
            llm_client, embedding_client=embedding_client
        )
        self._narrative_pool: list[MemoryRecord] = []
        self._nsb_consecutive_failures = 0

    def assemble_context(
        self,
        state: dict[str, Any],
        turn: int,
        campaign_context: str = "",
        player_action: str = "",
    ) -> str:
        """Build context synchronously from cached summaries.

        This method remains synchronous for callers that use the original
        controller API.  Prompt assembly can use ``assemble_context_async``
        when the embedding-backed retrieval path is available.
        """
        summaries = self.nsb.get_retrieval_context(
            self._build_retrieval_query(state, player_action), top_k=5
        )
        return self._render_context(state, campaign_context, summaries)

    async def assemble_context_async(
        self,
        state: dict[str, Any],
        turn: int,
        campaign_context: str = "",
        player_action: str = "",
    ) -> str:
        """Build context with semantic retrieval when embeddings are enabled."""
        summaries = await self.nsb.get_retrieval_context_async(
            self._build_retrieval_query(state, player_action), top_k=5
        )
        return self._render_context(state, campaign_context, summaries)

    @staticmethod
    def _build_retrieval_query(state: dict[str, Any], player_action: str) -> str:
        recent_events = state.get("recent_events", [])
        npc_names = [npc.get("name", "") for npc in state.get("npcs", [])]
        return f"{player_action} {' '.join(npc_names)} {' '.join(recent_events[-3:])}"

    def _render_context(
        self,
        state: dict[str, Any],
        campaign_context: str,
        summaries: list[Any],
    ) -> str:
        parts: list[str] = []
        if campaign_context:
            parts.append(campaign_context)
        if summaries:
            lines = ["## 长期叙事记忆"]
            lines.extend(
                f"[L{summary.level} T{summary.turn_start}-{summary.turn_end}] {summary.summary}"
                for summary in summaries
            )
            parts.append("\n".join(lines))

        npc_names = [npc.get("name", "") for npc in state.get("npcs", [])]
        persona_text = self.pcb.get_persona_text(npc_names=npc_names[:5])
        # Preserve the original empty-context behavior: an empty persona
        # sketch should not add a placeholder block to every prompt.
        if persona_text and persona_text != "角色档案：暂无记录":
            parts.append(persona_text)

        item_states = self.score_tracker.get_all_states()
        if item_states:
            lines = ["## 物品状态追踪"]
            lines.extend(f"- {name}: {value}" for name, value in item_states.items())
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def on_turn_generated(
        self,
        player_action: str,
        output_narration: str,
        turn: int,
        memory_updates: MemoryUpdates | dict[str, Any] | None = None,
    ) -> None:
        """Feed one completed turn into NSB, PCB, and SCORE."""
        self.nsb.add_turn(player_action, output_narration, turn)
        self.pcb.on_turn()
        if isinstance(memory_updates, MemoryUpdates):
            items = [item.model_dump() for item in memory_updates.items_upserted]
        elif isinstance(memory_updates, dict):
            items = memory_updates.get("items_upserted", [])
        else:
            items = []
        violations = self.score_tracker.check_narration_continuity(
            output_narration, turn, items
        )
        if violations:
            logger.warning("SCORE continuity violations at turn %d: %s", turn, violations)
