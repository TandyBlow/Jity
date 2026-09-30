"""Explainable retrieval shared by synchronous and embedding-backed callers."""

import logging
import numpy as np

from app.schemas.agent_io import MemoryHit

logger = logging.getLogger(__name__)


class NarrativeRetrievalMixin:
    def rank_hits(self, query: str, turn: int = 0, semantic=None) -> list[MemoryHit]:
        semantic = semantic or {}
        summaries = self._level1 + self._level2 + self._level3
        now = max([turn, *(s.turn_end for s in summaries)])
        scored = []
        query = query.casefold()
        for summary in summaries:
            entities = [e for e in summary.entities_involved if e and e.casefold() in query]
            tags = [t for t in summary.tags if t and t.casefold() in query]
            entity_score = min(1.0, len(entities) / 2)
            recency = 1 / (1 + max(0, now - summary.turn_end) / 20)
            sem = max(0.0, semantic.get(summary.episode_id, 0.0))
            score = .45 * sem + .3 * entity_score + .1 * summary.importance + .1 * recency + .05 * min(1, len(tags))
            reasons = [*(f"entity:{e}" for e in entities), *(f"tag:{t}" for t in tags)]
            if sem > 0:
                reasons.append("semantic")
            hit = MemoryHit(memory_id=summary.episode_id, summary=summary.summary,
                            level=summary.level, score=score, semantic_score=sem,
                            entity_match=entity_score, importance=summary.importance,
                            recency=recency, reasons=reasons or ["importance/recency"],
                            turn_start=summary.turn_start, turn_end=summary.turn_end)
            scored.append((hit, summary))
        scored.sort(key=lambda pair: (-pair[0].score, -pair[0].turn_end, pair[0].memory_id))
        selected = []
        seen_sources = set()
        seen_text = set()
        for hit, summary in scored:
            sources = set(summary.source_ids or [summary.episode_id])
            content = "".join(summary.summary.split()).casefold()
            if sources & seen_sources or content in seen_text:
                continue
            # Old snapshots have no provenance; contained cross-level ranges
            # are the conservative fallback for duplicate abstractions.
            if any(h.level != hit.level and max(h.turn_start, hit.turn_start) <= min(h.turn_end, hit.turn_end)
                   for h in selected):
                continue
            selected.append(hit)
            seen_sources.update(sources)
            seen_text.add(content)
        self.last_candidates = selected
        return selected

    async def retrieve_hits(self, query: str, turn: int = 0, top_k: int = 5) -> list[MemoryHit]:
        summaries = self._level1 + self._level2 + self._level3
        semantic = {}
        if self._embedding is not None and summaries:
            try:
                live = {s.episode_id for s in summaries}
                self._embedding_cache = [(s, v) for s, v in self._embedding_cache if s.episode_id in live]
                cached = {s.episode_id for s, _ in self._embedding_cache}
                missing = [s for s in summaries if s.episode_id not in cached]
                if missing:
                    vectors = await self._embedding.embed([s.summary for s in missing])
                    self._embedding_cache.extend(zip(missing, vectors))
                query_vectors = await self._embedding.embed([query])
                q = np.asarray(query_vectors[0])
                q = q / (np.linalg.norm(q) + 1e-9)
                for summary, vector in self._embedding_cache:
                    v = np.asarray(vector)
                    semantic[summary.episode_id] = float(np.dot(q, v / (np.linalg.norm(v) + 1e-9)))
            except Exception:
                logger.debug("Embedding retrieval unavailable; using entity ranking", exc_info=True)
        return self.rank_hits(query, turn, semantic)[:top_k]

    def get_retrieval_context(self, query: str, top_k: int = 5):
        by_id = {s.episode_id: s for s in self._level1 + self._level2 + self._level3}
        return [by_id[h.memory_id] for h in self.rank_hits(query)[:top_k]]

    async def get_retrieval_context_async(self, query: str, top_k: int = 5):
        by_id = {s.episode_id: s for s in self._level1 + self._level2 + self._level3}
        return [by_id[h.memory_id] for h in await self.retrieve_hits(query, top_k=top_k)]
