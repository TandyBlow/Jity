"""Similarity computation utilities for memory retrieval.

Provides cosine similarity computation using EmbeddingClient,
with SHA-256 hash fallback when the embedding API is unavailable.
Used by PCB (contradictory key merging) and forgetting (top-2k reranking).
"""

import logging
from typing import Sequence

import numpy as np

from app.services.embedding_client import EmbeddingClient

logger = logging.getLogger(__name__)


async def cosine_similarity(
    texts_a: list[str],
    texts_b: list[str],
    embedding_client: EmbeddingClient | None = None,
) -> np.ndarray:
    """Compute pairwise cosine similarity between two lists of texts.

    Returns a matrix of shape (len(texts_a), len(texts_b)).
    If embedding_client is None or fails, falls back to character-level
    Jaccard similarity (better than nothing for Chinese text).
    """
    if embedding_client is not None:
        try:
            emb_a = await embedding_client.embed(texts_a)
            emb_b = await embedding_client.embed(texts_b)
            # Normalize
            emb_a = emb_a / (np.linalg.norm(emb_a, axis=1, keepdims=True) + 1e-9)
            emb_b = emb_b / (np.linalg.norm(emb_b, axis=1, keepdims=True) + 1e-9)
            return emb_a @ emb_b.T
        except Exception:
            logger.debug("Embedding similarity failed, falling back to Jaccard", exc_info=True)

    # Fallback: character-level Jaccard similarity
    return _jaccard_matrix(texts_a, texts_b)


async def top_k_similar(
    query: str,
    candidates: list[str],
    embedding_client: EmbeddingClient | None = None,
    k: int = 9,
) -> list[tuple[int, float]]:
    """Return top-k (index, similarity_score) pairs for query vs candidates.

    Used by forgetting mechanism for BGE-style reranking of the top-2k
    scored memories.
    """
    if not candidates:
        return []

    sim_matrix = await cosine_similarity([query], candidates, embedding_client)
    scores = sim_matrix[0]  # shape (len(candidates),)

    # Get top-k indices
    indices = np.argsort(-scores)[:k]  # descending
    return [(int(i), float(scores[i])) for i in indices]


def _jaccard_matrix(texts_a: list[str], texts_b: list[str]) -> np.ndarray:
    """Character-level Jaccard similarity matrix."""
    result = np.zeros((len(texts_a), len(texts_b)), dtype=np.float32)
    for i, a in enumerate(texts_a):
        set_a = set(a)
        if not set_a:
            continue
        for j, b in enumerate(texts_b):
            set_b = set(b)
            if not set_b:
                continue
            result[i, j] = len(set_a & set_b) / len(set_a | set_b)
    return result
