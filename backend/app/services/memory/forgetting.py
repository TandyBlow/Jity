"""MOOM Competition-Inhibition Forgetting Algorithm.

Implements the forgetting mechanism from MOOM (Chen et al., 2025):
  S = α · exp(γ(rc−b))⁻¹ + β · Σ_{r∈Rc} 1/(rc−r+ε)

Where:
  rc = current round, b = creation round
  Rc = set of rounds in which the memory was retrieved
  α=0.1 (temporal decay weight), β=0.9 (retrieval reinforcement weight)
  γ=1, ε→very small value

Pipeline per round:
  1. Compute score S for every memory in pool
  2. Retrieve top-2k memories via BGE reranker (or cosine similarity)
  3. Top-k → Rc (reinforcement: record current round into Rc)
  4. Next-k → Nc (suppression: halve their scores)
  5. Unactivated → Uc (unchanged)
  6. Retain only memories above a threshold score (cap the pool)
"""

import logging
import math
from typing import Sequence

from app.schemas.agent_io import MemoryRecord

logger = logging.getLogger(__name__)


# ── Default hyper-parameters (from MOOM paper Appendix D) ─────────

ALPHA = 0.1  # temporal decay weight
BETA = 0.9  # retrieval reinforcement weight
GAMMA = 1.0  # decay rate in exponential
EPSILON = 1e-9  # avoids division by zero
K = 9  # top-k for reinforcement / suppression (2k retrieved total)
SCORE_THRESHOLD = 0.01  # minimum score to retain in pool
MAX_POOL_SIZE = 200  # hard cap on memory pool size


def compute_score(
    record: MemoryRecord,
    current_round: int,
    alpha: float = ALPHA,
    beta: float = BETA,
    gamma: float = GAMMA,
    epsilon: float = EPSILON,
) -> float:
    """Compute importance score S for a single memory record.

    S = α · 1/(exp(γ(rc-b))+1-ε) + β · Σ_{r∈Rc} 1/(rc-r+ε)

    First term: temporal decay — older memories score lower.
    Second term: retrieval reinforcement — frequently recalled memories score higher.
    """
    rc = current_round
    b = record.created_round

    # Temporal decay term
    decay = 1.0 / (math.exp(gamma * (rc - b)) + 1.0 - epsilon)

    # Retrieval reinforcement term
    reinforcement = 0.0
    for r in record.retrieved_rounds:
        reinforcement += 1.0 / (rc - r + epsilon)

    return alpha * decay + beta * reinforcement


def score_all(records: list[MemoryRecord], current_round: int) -> list[tuple[MemoryRecord, float]]:
    """Score every memory record. Returns (record, score) pairs sorted by score descending."""
    scored = [(rec, compute_score(rec, current_round)) for rec in records]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def apply_retrieval_reinforcement(
    scored: list[tuple[MemoryRecord, float]],
    current_round: int,
    k: int = K,
) -> list[MemoryRecord]:
    """Apply reinforcement and suppression to the scored list.

    Top-k → Rc (record current round into retrieved_rounds)
    Next-k → Nc (halve their scores — marked on the record for next round)
    Rest → unchanged

    Returns the updated list of MemoryRecords (with reinforced retrieved_rounds).
    """
    updated: list[MemoryRecord] = []

    for i, (rec, score) in enumerate(scored):
        if i < k:
            # Reinforcement: add current round to retrieved_rounds
            new_rounds = list(rec.retrieved_rounds) + [current_round]
            updated.append(rec.model_copy(update={"retrieved_rounds": new_rounds, "score": score}))
        elif i < 2 * k:
            # Suppression: halve score
            updated.append(rec.model_copy(update={"score": score / 2.0}))
        else:
            # Unactivated
            updated.append(rec)

    return updated


def prune_pool(records: list[MemoryRecord], threshold: float = SCORE_THRESHOLD, max_size: int = MAX_POOL_SIZE) -> list[MemoryRecord]:
    """Prune the memory pool: drop below-threshold, then cap at max_size.

    Records are assumed scored already (score field populated).
    """
    # Drop below threshold
    above = [r for r in records if r.score >= threshold]

    # Cap at max size (keep highest-scored)
    if len(above) > max_size:
        above.sort(key=lambda r: r.score, reverse=True)
        above = above[:max_size]

    return above


def forget_step(
    records: list[MemoryRecord],
    current_round: int,
    similarity_scores: list[float] | None = None,
    k: int = K,
) -> list[MemoryRecord]:
    """Full forgetting step: score → reinforce/suppress → prune.

    similarity_scores: optional pre-computed similarity scores for the top-2k
    retrieval (e.g. from BGE reranker). If None, uses score field directly
    for ordering (which works when scores are already populated from a previous round).

    This is the main entry point called by MemoryController each turn.
    """
    if not records:
        return []

    # Step 1: Compute scores for all records
    scored = score_all(records, current_round)

    # Step 2: If similarity scores provided, re-rank top-2k by similarity
    if similarity_scores is not None and len(similarity_scores) > 0:
        # Re-rank top 2k by similarity (higher similarity → higher rank)
        top_2k = scored[:2 * k]
        rest = scored[2 * k:]

        # Pair each with similarity score and re-sort
        sim_ranked: list[tuple[MemoryRecord, float]] = []
        for i, (rec, base_score) in enumerate(top_2k):
            sim = similarity_scores[i] if i < len(similarity_scores) else 0.0
            sim_ranked.append((rec, base_score, sim))

        # Sort by similarity descending within top-2k
        sim_ranked.sort(key=lambda x: x[2], reverse=True)

        # Rebuild scored list with reranked top-2k + rest
        scored = [(rec, base) for rec, base, _ in sim_ranked] + rest

    # Step 3: Apply reinforcement and suppression
    reinforced = apply_retrieval_reinforcement(scored, current_round, k=k)

    # Step 4: Prune pool
    pruned = prune_pool(reinforced)

    logger.debug(
        "forget_step: round=%d, pool_in=%d, pool_out=%d",
        current_round, len(records), len(pruned),
    )

    return pruned
