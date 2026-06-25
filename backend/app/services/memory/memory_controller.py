"""Memory Controller — Nyarlathotep 3-layer memory orchestration.

Orchestrates the three memory layers:
  L0 Working Memory  (~3K tokens, always in context):
    current scene + active NPC cards + last 6 turns + active quests
  L1 Narrative Memory (~2K tokens, vector retrieval):
    NSB episode summaries (semantic + temporal + entity retrieval)
  L2 World Memory    (~2K tokens, keyword trigger + semantic retrieval):
    Rules KG + World Book + NPC reference profiles

Integration points:
  - SCORE tracker validates item state continuity at L0 → L1 boundary
  - NSB hierarchical summaries populate L1
  - PCB persona profiles injectNPC context into L0
  - MOOM forgetting prunes L1 and L2 pools
  - CampaignContextBuilder consumes assembled context for prompt injection
"""

import logging
from typing import Any

from app.database import Database
from app.schemas.agent_io import EpisodeSummary, MemoryRecord
from app.services.embedding_client import EmbeddingClient
from app.services.llm_client import LLMClient
from app.services.memory.forgetting import forget_step
from app.services.memory.nsb import NarrativeSummarizationBranch
from app.services.memory.pcb import PersonaConstructionBranch
from app.services.memory.score_tracker import ScoreTracker

logger = logging.getLogger(__name__)


class MemoryController:
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

        # NSB failure tracking (for retry logic)
        self._nsb_consecutive_failures = 0

    # ── Per-turn: build context for prompt injection ───────────────

    def assemble_context(
        self,
        state: dict[str, Any],
        turn: int,
        player_action: str = "",
    ) -> str:
        """Assemble L1+L0 memory context for prompt injection.

        Called by ScenarioGenerator BEFORE the LLM call.
        Does NOT make any LLM calls — reads cached NSB/PCB/SCORE data.

        Returns the narrative memory section (NSB summaries + persona +
        SCORE item states). Campaign context (L2) is injected separately
        via PromptBuilder to avoid duplication.
        """
        parts: list[str] = []

        # L1 — Narrative Memory (relevant summaries)
        recent_events = state.get("recent_events", [])
        npc_names = [n.get("name", "") for n in state.get("npcs", [])]
        query = f"{player_action} {' '.join(npc_names)} {' '.join(recent_events[-3:])}"

        relevant_summaries = self.nsb.get_retrieval_context(query, top_k=5)
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

    # ── Async maintenance (called fire-and-forget by ScenarioGenerator) ─

    async def maintain(self, session_id: str, turn: int) -> None:
        """Run periodic memory maintenance: NSB summaries, PCB extraction, forgetting.

        Called via asyncio.create_task — does not block the player-facing turn.
        Failures in one subsystem do not cascade to others.
        """
        # ── NSB summarization ────────────────────────────────────
        try:
            if self.nsb.should_summarize_level1():
                turn_start = max(0, turn - self.nsb.theta1)
                summary = await self.nsb.summarize_level1(turn_start, turn)
                if summary:
                    self.nsb.accept_level1(summary)
                    self._persist_episode(summary)
                    self._nsb_consecutive_failures = 0
                    logger.info("NSB level-1 summary generated: %s", summary.episode_id)

                    # Check if level-2 should fire
                    if self.nsb.should_summarize_level2():
                        l2_start = max(0, turn - self.nsb.theta1 * self.nsb.theta2)
                        l2 = await self.nsb.summarize_level2(l2_start, turn)
                        if l2:
                            self.nsb.accept_level2(l2)
                            self._persist_episode(l2)

                            if self.nsb.should_summarize_level3():
                                l3_start = max(0, turn - self.nsb.theta1 * self.nsb.theta2 * self.nsb.theta3)
                                l3 = await self.nsb.summarize_level3(l3_start, turn)
                                if l3:
                                    self.nsb.accept_level3(l3)
                                    self._persist_episode(l3)
                else:
                    self._nsb_consecutive_failures += 1
                    if self._nsb_consecutive_failures >= 3:
                        logger.warning(
                            "NSB summarization failed %d consecutive times — "
                            "check LLM API availability",
                            self._nsb_consecutive_failures,
                        )
        except Exception:
            self._nsb_consecutive_failures += 1
            logger.warning(
                "NSB maintenance error (failures=%d)", self._nsb_consecutive_failures,
                exc_info=True,
            )

        # ── PCB persona extraction ───────────────────────────────
        try:
            if self.pcb.should_extract():
                dialogues = self._get_recent_dialogues(session_id)
                if dialogues:
                    snapshot = await self.pcb.extract_snapshot(dialogues, turn)
                    if snapshot:
                        if self._embedding is not None:
                            await self.pcb.merge_snapshot_with_embedding(snapshot)
                        else:
                            self.pcb.merge_snapshot(snapshot)
        except Exception:
            logger.warning("PCB persona extraction failed", exc_info=True)

        # ── MOOM forgetting on narrative pool ────────────────────
        try:
            if self._narrative_pool:
                self._narrative_pool = forget_step(self._narrative_pool, turn // 2)
        except Exception:
            logger.warning("MOOM forgetting step failed", exc_info=True)

    # ── Persistence ───────────────────────────────────────────────

    def _persist_episode(self, summary: EpisodeSummary) -> None:
        """Store an episode summary in the DB as a knowledge chunk for RAG retrieval."""
        try:
            self._db.add_knowledge_chunk(
                title=f"episode_{summary.episode_id}",
                source_type="narrative_memory",
                content=summary.summary,
                keywords=summary.tags + summary.entities_involved,
                importance=int(summary.importance * 5),  # 0-5 scale
            )
        except Exception:
            logger.debug("Failed to persist episode %s", summary.episode_id, exc_info=True)

    def _get_recent_dialogues(self, session_id: str, limit: int = 10) -> str:
        """Fetch recent dialogue from session_messages for PCB extraction."""
        messages = self._db.get_recent_messages(session_id, limit=limit)
        lines: list[str] = []
        for msg in messages:
            role = "玩家" if msg.get("role") == "user" else "主持人"
            content = msg.get("content", "")[:500]
            lines.append(f"[{role}]: {content}")
        return "\n\n".join(lines)

    # ── State export/import for session persistence ───────────────

    def export_state(self) -> dict[str, Any]:
        return {
            "nsb": self.nsb.export_state(),
            "pcb": self.pcb.export_state(),
            "score_tracker": self.score_tracker.export_state(),
            "narrative_pool": [r.model_dump() for r in self._narrative_pool],
        }

    def load_state(self, data: dict[str, Any]) -> None:
        self.nsb.load_state(data.get("nsb", {}))
        self.pcb.load_state(data.get("pcb", {}))
        self.score_tracker.load_from_state(data.get("score_tracker", []))
        self._narrative_pool = [MemoryRecord(**d) for d in data.get("narrative_pool", [])]
