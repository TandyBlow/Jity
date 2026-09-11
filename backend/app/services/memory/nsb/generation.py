"""NSB retrieval scoring and LLM summary generation mixin."""

import logging
from typing import Any

from app.schemas.agent_io import EpisodeSummary

from app.services.memory.nsb.parsing import (
    _safe_dict,
    _safe_float,
    _safe_list,
    _safe_str,
)

logger = logging.getLogger(__name__)


class SummaryGenerationMixin:
    def get_retrieval_context(self, query: str, top_k: int = 5) -> list[EpisodeSummary]:
        """Return the top-k most relevant summaries across all levels for context injection.

        Simple keyword + recency heuristic. Semantic retrieval via FAISS
        is handled externally by MemoryController combining NSB with the
        existing RAGRetriever.
        """
        all_summaries = self._level1 + self._level2 + self._level3
        # Score by recency (most recent first) combined with tag/entity overlap
        scored: list[tuple[EpisodeSummary, float]] = []
        query_lower = query.lower()
        for s in all_summaries:
            score = 0.0
            # Tag overlap
            for tag in s.tags:
                if tag.lower() in query_lower:
                    score += 2.0
            # Entity overlap
            for ent in s.entities_involved:
                if ent.lower() in query_lower:
                    score += 3.0
            # Recency bonus (more recent = higher score)
            score += s.importance
            scored.append((s, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored[:top_k]]

    def export_state(self) -> dict[str, Any]:
        """Serialize internal state for persistence."""
        return {
            "turn_buffer": self._turn_buffer,
            "level1": [s.model_dump() for s in self._level1],
            "level2": [s.model_dump() for s in self._level2],
            "level3": [s.model_dump() for s in self._level3],
            "episode_counter": self._episode_counter,
        }

    def load_state(self, data: dict[str, Any]) -> None:
        """Restore from persisted state."""
        self._turn_buffer = data.get("turn_buffer", [])
        self._level1 = [EpisodeSummary(**d) for d in data.get("level1", [])]
        self._level2 = [EpisodeSummary(**d) for d in data.get("level2", [])]
        self._level3 = [EpisodeSummary(**d) for d in data.get("level3", [])]
        self._episode_counter = data.get("episode_counter", 0)
        if hasattr(self, "_embedding_cache"):
            self._embedding_cache.clear()

    # ── Private ───────────────────────────────────────────────────

    async def _generate_summary(
        self, prompt: str, level: int, turn_start: int, turn_end: int
    ) -> EpisodeSummary | None:
        """Call LLM and parse into EpisodeSummary. Returns None on LLM failure."""
        self._episode_counter += 1
        episode_id = f"ep_L{level}_{self._episode_counter}"

        try:
            raw = await self._llm.generate_json(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.3,
            )
        except Exception:
            logger.warning("NSB level-%d summarization failed", level, exc_info=True)
            return None

        return EpisodeSummary(
            episode_id=episode_id,
            turn_start=turn_start,
            turn_end=turn_end,
            summary=_safe_str(raw, "summary", ""),
            tags=_safe_list(raw, "tags"),
            entities_involved=_safe_list(raw, "entities_involved"),
            causal_links=_safe_list(raw, "causal_links"),
            state_changes=_safe_dict(raw, "state_changes"),
            importance=_safe_float(raw, "importance", 0.5),
            level=level,
        )
