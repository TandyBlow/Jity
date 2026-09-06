"""Memory Controller — L0/L1/L2 memory orchestration core."""

import logging
from typing import Any

from app.database import Database
from app.schemas.agent_io import MemoryRecord
from app.services.embedding_client import EmbeddingClient
from app.services.llm_client import LLMClient
from app.services.memory.memory_controller.maintenance import MemoryMaintenanceMixin
from app.services.memory.nsb import NarrativeSummarizationBranch
from app.services.memory.pcb import PersonaConstructionBranch
from app.services.memory.score_tracker import ScoreTracker

logger = logging.getLogger(__name__)


class MemoryController(MemoryMaintenanceMixin):
    """Orchestrates L0/L1/L2 memory assembly and maintenance."""

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

        # Sub-systems
        self.score_tracker = ScoreTracker()
        self.nsb = NarrativeSummarizationBranch(llm_client)
        self.pcb = PersonaConstructionBranch(llm_client, embedding_client=embedding_client)

        # L1 memory pool (all episode summaries for this session)
        self._narrative_pool: list[MemoryRecord] = []
        # L2 world memory is read from DB on demand (knowledge_chunks)

    # ── Per-turn: build context for prompt injection ───────────────

    def assemble_context(
        self,
        state: dict[str, Any],
        turn: int,
        campaign_context: str,
    ) -> str:
        """Assemble the three-layer context string for prompt injection.

        This is called by ScenarioGenerator BEFORE the LLM call.
        It does NOT make any LLM calls itself — it reads cached data.

        Layers:
          L2: Rules + World Book (keyword triggered from player action + state)
          L1: Relevant episode summaries (keyword + entity overlap)
          L0: Current scene state (always included)
          Campaign context (anchor progress + health guidance)
          Persona context from PCB
        """
        parts: list[str] = []

        # L2 — World Memory (pass through existing campaign_context
        # which already contains RAG chunks from CampaignContextBuilder)
        if campaign_context:
            parts.append(campaign_context)

        # L1 — Narrative Memory (relevant summaries)
        relevant_summaries = self._relevant_summaries(state)
        if relevant_summaries:
            summary_texts: list[str] = ["## 长期叙事记忆"]
            for s in relevant_summaries:
                level_tag = f"L{s.level}"
                summary_texts.append(f"[{level_tag} T{s.turn_start}-{s.turn_end}] {s.summary}")
            parts.append("\n".join(summary_texts))

        # L0 — Working Memory is already in the system prompt via
        # PromptBuilder (location, items, NPCs, recent events).
        # We add persona context here.

        persona_text = self.pcb.get_persona_text()
        if persona_text:
            parts.append(persona_text)

        # SCORE continuity status
        item_states = self.score_tracker.get_all_states()
        if item_states:
            item_lines = ["## 物品状态追踪"]
            for name, st in item_states.items():
                item_lines.append(f"- {name}: {st}")
            parts.append("\n".join(item_lines))

        return "\n\n".join(parts)

    def _relevant_summaries(self, state: dict[str, Any]) -> list:
        recent_events = state.get("recent_events", [])
        action_text = state.get("_last_player_action", "")
        npc_names = [n.get("name", "") for n in state.get("npcs", [])]
        query = f"{action_text} {' '.join(npc_names)} {' '.join(recent_events[-3:])}"
        return self.nsb.get_retrieval_context(query, top_k=5)

    # ── Per-turn: feed data into memory subsystems ────────────────

    def on_turn_generated(
        self,
        player_action: str,
        output_narration: str,
        state: dict[str, Any],
        turn: int,
    ) -> None:
        """Feed a completed turn into NSB/PCB buffers. Called by ScenarioGenerator AFTER LLM generation."""
        # NSB: buffer the turn dialogue
        self.nsb.add_turn(player_action, output_narration, turn)

        # PCB: increment extraction counter
        self.pcb.on_turn()

        # SCORE: check item continuity from LLM output
        items_from_llm = []
        mu = state.get("memory_updates", state.get("_last_memory_updates", {}))
        if isinstance(mu, dict):
            items_from_llm = mu.get("items_upserted", [])
        violations = self.score_tracker.check_narration_continuity(output_narration, turn, items_from_llm)
        if violations:
            logger.warning("SCORE continuity violations at turn %d: %s", turn, violations)
