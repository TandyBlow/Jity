"""Memory maintenance (async) and state persistence for MemoryController."""

import logging
from typing import Any

from app.schemas.agent_io import EpisodeSummary, MemoryRecord
from app.services.memory.forgetting import forget_step

logger = logging.getLogger(__name__)


class MemoryMaintenanceMixin:
    # ── Async maintenance (called fire-and-forget by ScenarioGenerator) ─

    async def maintain(self, session_id: str, turn: int) -> None:
        """Run periodic memory maintenance: NSB summaries, PCB extraction, forgetting.

        Called via asyncio.create_task — does not block the player-facing turn.
        """
        # NSB level-1 summarization
        if self.nsb.should_summarize_level1():
            turn_start = max(0, turn - self.nsb.theta1)
            summary = await self.nsb.summarize_level1(turn_start, turn)
            if summary:
                self.nsb.accept_level1(summary)
                self._persist_episode(summary)
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

        # PCB persona extraction
        if self.pcb.should_extract():
            dialogues = self._get_recent_dialogues(session_id)
            if dialogues:
                snapshot = await self.pcb.extract_snapshot(dialogues, turn)
                if snapshot:
                    if self._embedding is not None:
                        await self.pcb.merge_snapshot_with_embedding(snapshot)
                    else:
                        self.pcb.merge_snapshot(snapshot)

        # MOOM forgetting on narrative pool
        if self._narrative_pool:
            self._narrative_pool = forget_step(self._narrative_pool, turn // 2)  # rounds ≈ half of turns

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
