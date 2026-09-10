"""Background maintenance and persistence for MemoryController."""

import logging
from typing import Any

from app.schemas.agent_io import EpisodeSummary, MemoryRecord
from app.services.memory.forgetting import forget_step

logger = logging.getLogger(__name__)


class MemoryMaintenanceMixin:
    async def maintain(self, session_id: str, turn: int) -> None:
        """Run NSB, PCB, and forgetting independently so one failure is isolated."""
        try:
            if self.nsb.should_summarize_level1():
                start = max(0, turn - self.nsb.theta1)
                summary = await self.nsb.summarize_level1(start, turn)
                if summary:
                    self.nsb.accept_level1(summary)
                    await self.nsb.cache_summary_embedding(summary)
                    self._persist_episode(summary)
                    self._record_episode_memory(summary, turn)
                    self._nsb_consecutive_failures = 0

                    if self.nsb.should_summarize_level2():
                        start = max(0, turn - self.nsb.theta1 * self.nsb.theta2)
                        level2 = await self.nsb.summarize_level2(start, turn)
                        if level2:
                            self.nsb.accept_level2(level2)
                            await self.nsb.cache_summary_embedding(level2)
                            self._persist_episode(level2)
                            if self.nsb.should_summarize_level3():
                                start = max(
                                    0,
                                    turn - self.nsb.theta1 * self.nsb.theta2 * self.nsb.theta3,
                                )
                                level3 = await self.nsb.summarize_level3(start, turn)
                                if level3:
                                    self.nsb.accept_level3(level3)
                                    await self.nsb.cache_summary_embedding(level3)
                                    self._persist_episode(level3)
                else:
                    self._nsb_consecutive_failures += 1
        except Exception:
            self._nsb_consecutive_failures += 1
            logger.warning("NSB maintenance failed", exc_info=True)

        try:
            if self.pcb.should_extract():
                dialogues = self._get_recent_dialogues(session_id)
                if dialogues:
                    snapshots = await self.pcb.extract_snapshot(dialogues, turn)
                    if snapshots:
                        for snapshot in snapshots.values():
                            if self._embedding is not None:
                                await self.pcb.merge_snapshot_with_embedding(snapshot)
                            else:
                                self.pcb.merge_snapshot(snapshot)
        except Exception:
            logger.warning("PCB persona extraction failed", exc_info=True)

        try:
            if self._narrative_pool:
                before = {record.memory_id for record in self._narrative_pool}
                self._narrative_pool = forget_step(self._narrative_pool, turn // 2)
                removed = before - {record.memory_id for record in self._narrative_pool}
                for episode_id in removed:
                    self.nsb.remove_episode(episode_id)
                if removed:
                    logger.info("MOOM pruned %d episode(s)", len(removed))
        except Exception:
            logger.warning("MOOM forgetting step failed", exc_info=True)

    def _persist_episode(self, summary: EpisodeSummary) -> None:
        try:
            self._db.add_knowledge_chunk(
                chunk_id=summary.episode_id,
                title=f"episode_{summary.episode_id}",
                source_type="narrative_memory",
                content=summary.summary,
                keywords=summary.tags + summary.entities_involved,
                importance=int(summary.importance * 5),
            )
        except Exception:
            logger.debug("Failed to persist episode %s", summary.episode_id, exc_info=True)

    def _record_episode_memory(self, summary: EpisodeSummary, turn: int) -> None:
        self._narrative_pool.append(
            MemoryRecord(
                memory_id=summary.episode_id,
                content=summary.summary,
                created_round=turn // 2,
                memory_type="narrative",
            )
        )

    def _get_recent_dialogues(self, session_id: str, limit: int = 10) -> str:
        messages = self._db.get_recent_messages(session_id, limit=limit)
        lines: list[str] = []
        for message in messages:
            role = "玩家" if message.get("role") == "user" else "主持人"
            lines.append(f"[{role}]: {message.get('content', '')[:500]}")
        return "\n\n".join(lines)

    def export_state(self) -> dict[str, Any]:
        return {
            "nsb": self.nsb.export_state(),
            "pcb": self.pcb.export_state(),
            "score_tracker": self.score_tracker.export_state(),
            "narrative_pool": [record.model_dump() for record in self._narrative_pool],
        }

    def load_state(self, data: dict[str, Any]) -> None:
        self.nsb.load_state(data.get("nsb", {}))
        self.nsb.invalidate_embedding_cache()
        self.pcb.load_state(data.get("pcb", {}))
        self.score_tracker.load_from_state(data.get("score_tracker", []))
        self._narrative_pool = [
            MemoryRecord(**record) for record in data.get("narrative_pool", [])
        ]
        if not self.nsb._level1 and not self.nsb._level2 and not self.nsb._level3:
            self._load_episodes_from_db()

    def _load_episodes_from_db(self) -> None:
        try:
            episodes = self._db.get_narrative_episodes()
        except Exception:
            logger.warning("Failed to load narrative episodes from DB", exc_info=True)
            return
        max_counter = 0
        for episode in episodes:
            episode_id = str(episode.get("id", ""))
            level = 1
            if "_L2_" in episode_id:
                level = 2
            elif "_L3_" in episode_id:
                level = 3
            try:
                summary = EpisodeSummary(
                    episode_id=episode_id,
                    turn_start=0,
                    turn_end=0,
                    summary=str(episode.get("content", "")),
                    tags=episode.get("keywords", []),
                    importance=max(0.1, min(1.0, float(episode.get("importance", 3)) / 5.0)),
                    level=level,
                )
            except Exception:
                logger.debug("Skipping malformed episode %s", episode_id, exc_info=True)
                continue
            if level == 1:
                self.nsb.accept_level1(summary)
            elif level == 2:
                self.nsb.accept_level2(summary)
            else:
                self.nsb.accept_level3(summary)
            try:
                max_counter = max(max_counter, int(episode_id.rsplit("_", 1)[-1]))
            except (ValueError, IndexError):
                pass
        self.nsb._episode_counter = max(self.nsb._episode_counter, max_counter)
