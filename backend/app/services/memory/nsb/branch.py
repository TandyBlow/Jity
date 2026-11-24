"""MOOM Narrative Summarization Branch (NSB) — hierarchical summarizer.

Implements hierarchical multi-scale summarization from MOOM (Chen et al., 2025):
  theta1 = 6 : every 6 turns -> first-level summary
  theta2 = 5 : every 5 first-level summaries -> second-level summary
  theta3 = 5 : every 5 second-level summaries -> third-level summary

Summaries are stored with tags, entities, causal links, and state changes
for three-dimensional retrieval (semantic + temporal + entity).

Uses deepseek-v4-flash for summarization (cheap, non-blocking path).
"""

import logging
from typing import Any

import numpy as np

from app.schemas.agent_io import EpisodeSummary
from app.services.embedding_client import EmbeddingClient
from app.services.llm_client import LLMClient

from app.services.memory.nsb.prompts import (
    THETA_1,
    THETA_2,
    THETA_3,
    _LEVEL1_PROMPT,
    _LEVEL2_PROMPT,
    _LEVEL3_PROMPT,
)
from app.services.memory.nsb.generation import SummaryGenerationMixin

logger = logging.getLogger(__name__)


class NarrativeSummarizationBranch(SummaryGenerationMixin):
    """Hierarchical summarization for long-term narrative memory."""

    _LEVEL_WEIGHTS = {1: 1.0, 2: 1.15, 3: 1.3}

    def __init__(
        self,
        llm_client: LLMClient,
        theta1: int = THETA_1,
        theta2: int = THETA_2,
        theta3: int = THETA_3,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self._llm = llm_client
        self.theta1 = theta1
        self.theta2 = theta2
        self.theta3 = theta3
        self._embedding = embedding_client

        # Turn-level buffer (raw dialogue text)
        self._turn_buffer: list[str] = []
        # Hierarchical summary buffers
        self._level1: list[EpisodeSummary] = []
        self._level2: list[EpisodeSummary] = []
        self._level3: list[EpisodeSummary] = []

        # Monotonic counters
        self._episode_counter: int = 0

        # Cached embeddings for semantic retrieval.
        self._embedding_cache: list[tuple[EpisodeSummary, np.ndarray]] = []

    # ── Public API ────────────────────────────────────────────────

    def add_turn(self, player_action: str, narration: str, turn: int) -> None:
        """Buffer one turn's dialogue. Does NOT trigger LLM call."""
        self._turn_buffer.append(f"[T{turn} 玩家]: {player_action}\n[T{turn} 主持人]: {narration}")

    def should_summarize_level1(self) -> bool:
        return len(self._turn_buffer) >= self.theta1

    def should_summarize_level2(self) -> bool:
        return len(self._level1) >= self.theta2

    def should_summarize_level3(self) -> bool:
        return len(self._level2) >= self.theta3

    async def summarize_level1(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a first-level summary from buffered turns. Consumes the buffer."""
        if not self._turn_buffer:
            return None

        dialogue = "\n\n".join(self._turn_buffer)
        self._turn_buffer.clear()

        prompt = _LEVEL1_PROMPT.format(theta1=self.theta1, dialogue=dialogue)
        return await self._generate_summary(prompt, level=1, turn_start=turn_start, turn_end=turn_end)

    async def summarize_level2(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a second-level summary from accumulated level-1 summaries."""
        if not self._level1:
            return None

        # Take theta2 summaries from the buffer
        batch = self._level1[:self.theta2]
        self._level1 = self._level1[self.theta2:]

        summaries_text = "\n\n---\n\n".join(
            f"[摘要{i+1}]: {s.summary}" for i, s in enumerate(batch)
        )
        schema = '{"summary": "...", "tags": [...], "entities_involved": [...], "causal_links": [...], "state_changes": {...}, "importance": 0.7}'
        prompt = _LEVEL2_PROMPT.format(theta2=self.theta2, schema=schema, summaries=summaries_text)
        return await self._generate_summary(prompt, level=2, turn_start=turn_start, turn_end=turn_end)

    async def summarize_level3(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a third-level summary from accumulated level-2 summaries."""
        if not self._level2:
            return None

        batch = self._level2[:self.theta3]
        self._level2 = self._level2[self.theta3:]

        summaries_text = "\n\n---\n\n".join(
            f"[摘要{i+1}]: {s.summary}" for i, s in enumerate(batch)
        )
        schema = '{"summary": "...", "tags": [...], "entities_involved": [...], "causal_links": [...], "state_changes": {...}, "importance": 0.7}'
        prompt = _LEVEL3_PROMPT.format(theta3=self.theta3, schema=schema, summaries=summaries_text)
        return await self._generate_summary(prompt, level=3, turn_start=turn_start, turn_end=turn_end)

    def accept_level1(self, summary: EpisodeSummary) -> None:
        """Store a level-1 summary (called after successful LLM generation)."""
        self._level1.append(summary)

    def accept_level2(self, summary: EpisodeSummary) -> None:
        """Store a level-2 summary."""
        self._level2.append(summary)

    def accept_level3(self, summary: EpisodeSummary) -> None:
        """Store a level-3 summary."""
        self._level3.append(summary)

    def remove_episode(self, episode_id: str) -> None:
        """Drop a level-1 episode — called when MOOM forgetting prunes it from the pool."""
        self._level1 = [s for s in self._level1 if s.episode_id != episode_id]

    async def cache_summary_embedding(self, summary: EpisodeSummary) -> None:
        """Cache an embedding for a newly accepted summary when available."""
        if self._embedding is None:
            return
        try:
            vectors = await self._embedding.embed([summary.summary])
            if len(vectors):
                self._embedding_cache.append((summary, vectors[0]))
        except Exception:
            logger.debug("Failed to cache embedding for %s", summary.episode_id, exc_info=True)

    def invalidate_embedding_cache(self) -> None:
        """Clear cached vectors after restoring summaries from persisted state."""
        self._embedding_cache.clear()

    async def get_retrieval_context_async(self, query: str, top_k: int = 5) -> list[EpisodeSummary]:
        """Retrieve summaries using a semantic/keyword hybrid score."""
        all_summaries = self._level1 + self._level2 + self._level3
        if not all_summaries:
            return []

        query_lower = query.lower()
        keyword_scores: list[float] = []
        for summary in all_summaries:
            score = summary.importance
            score += sum(2.0 for tag in summary.tags if tag.lower() in query_lower)
            score += sum(3.0 for entity in summary.entities_involved if entity.lower() in query_lower)
            keyword_scores.append(min(score / 10.0, 1.0))

        semantic_scores = [0.0] * len(all_summaries)
        if self._embedding is not None and self._embedding_cache:
            try:
                query_vectors = await self._embedding.embed([query])
                query_vector = query_vectors[0] / (np.linalg.norm(query_vectors[0]) + 1e-9)
                for summary, vector in self._embedding_cache:
                    try:
                        index = all_summaries.index(summary)
                    except ValueError:
                        continue
                    normalized_vector = vector / (np.linalg.norm(vector) + 1e-9)
                    semantic_scores[index] = float(np.dot(query_vector, normalized_vector))
            except Exception:
                logger.debug("Semantic retrieval failed; using keyword scores", exc_info=True)

        scored = [
            (
                summary,
                (0.7 * semantic_scores[index] + 0.3 * keyword_scores[index])
                * self._LEVEL_WEIGHTS.get(summary.level, 1.0),
            )
            for index, summary in enumerate(all_summaries)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [summary for summary, _ in scored[:top_k]]
