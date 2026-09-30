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
from app.services.memory.nsb.retrieval import NarrativeRetrievalMixin

logger = logging.getLogger(__name__)


class NarrativeSummarizationBranch(NarrativeRetrievalMixin, SummaryGenerationMixin):
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

        batch = list(self._turn_buffer[:self.theta1])
        dialogue = "\n\n".join(batch)
        import re
        turns = [int(m.group(1)) for text in batch if (m := re.match(r"\[T(\d+)", text))]
        if turns:
            turn_start, turn_end = min(turns), max(turns)

        prompt = _LEVEL1_PROMPT.format(theta1=self.theta1, dialogue=dialogue)
        summary = await self._generate_summary(prompt, level=1, turn_start=turn_start, turn_end=turn_end)
        if summary and summary.summary.strip():
            del self._turn_buffer[:len(batch)]
            return summary
        return None

    async def summarize_level2(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a second-level summary from accumulated level-1 summaries."""
        if not self._level1:
            return None

        # Take theta2 summaries from the buffer
        batch = self._level1[:self.theta2]

        summaries_text = "\n\n---\n\n".join(
            f"[摘要{i+1}]: {s.summary}" for i, s in enumerate(batch)
        )
        schema = '{"summary": "...", "tags": [...], "entities_involved": [...], "causal_links": [...], "state_changes": {...}, "importance": 0.7}'
        prompt = _LEVEL2_PROMPT.format(theta2=self.theta2, schema=schema, summaries=summaries_text)
        summary = await self._generate_summary(prompt, level=2, turn_start=min(s.turn_start for s in batch), turn_end=max(s.turn_end for s in batch))
        if summary and summary.summary.strip():
            self._inherit_sources(summary, batch)
            self._level1 = self._level1[len(batch):]
            return summary
        return None

    async def summarize_level3(self, turn_start: int, turn_end: int) -> EpisodeSummary | None:
        """Produce a third-level summary from accumulated level-2 summaries."""
        if not self._level2:
            return None

        batch = self._level2[:self.theta3]

        summaries_text = "\n\n---\n\n".join(
            f"[摘要{i+1}]: {s.summary}" for i, s in enumerate(batch)
        )
        schema = '{"summary": "...", "tags": [...], "entities_involved": [...], "causal_links": [...], "state_changes": {...}, "importance": 0.7}'
        prompt = _LEVEL3_PROMPT.format(theta3=self.theta3, schema=schema, summaries=summaries_text)
        summary = await self._generate_summary(prompt, level=3, turn_start=min(s.turn_start for s in batch), turn_end=max(s.turn_end for s in batch))
        if summary and summary.summary.strip():
            self._inherit_sources(summary, batch)
            self._level2 = self._level2[len(batch):]
            return summary
        return None

    @staticmethod
    def _inherit_sources(summary, batch):
        summary.source_ids = sorted({source for s in batch for source in (s.source_ids or [s.episode_id])})
        summary.protected = any(s.protected for s in batch)
        # Keep structured consequences even when prose is compressed.
        summary.state_changes = {**{k: v for s in batch for k, v in s.state_changes.items()}, **summary.state_changes}

    async def compact_level3(self) -> None:
        if len(self._level3) < self.theta3:
            return
        batch = list(self._level3[:self.theta3])
        prompt = _LEVEL3_PROMPT.format(theta3=len(batch), schema='{"summary": "...", "importance": 0.8}', summaries="\n".join(s.summary for s in batch))
        summary = await self._generate_summary(prompt, 3, min(s.turn_start for s in batch), max(s.turn_end for s in batch))
        if summary and summary.summary.strip():
            self._inherit_sources(summary, batch)
            self._level3 = [summary, *self._level3[len(batch):]]

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
        return await super().get_retrieval_context_async(query, top_k)
