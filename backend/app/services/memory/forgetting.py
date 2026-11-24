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


# ── Adaptive hyper-parameters ─────────────────────────────────────

ALPHA = 0.1  # temporal decay weight
BETA = 0.9  # retrieval reinforcement weight
GAMMA = 1.0  # decay rate in exponential
EPSILON = 1e-9  # avoids division by zero
K = 9  # top-k for reinforcement / suppression (2k retrieved total)
SCORE_THRESHOLD_BASE = 0.01  # minimum score when pool is far from cap
POOL_SIZE_MIN = 200  # floor for dynamic pool size
POOL_SIZE_PER_TURN = 2  # additional slots per turn


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


def compute_dynamic_pool_size(current_round: int) -> int:
    """Return the dynamic max pool size for the given round.

    Scales linearly from POOL_SIZE_MIN at round 0 to POOL_SIZE_MIN
    + POOL_SIZE_PER_TURN * current_round at higher rounds.
    This prevents long campaigns (>150 turns) from being bottlenecked
    by a fixed 200-slot memory pool.
    """
    return max(POOL_SIZE_MIN, current_round * POOL_SIZE_PER_TURN)


def compute_adaptive_threshold(pool_size: int, max_size: int) -> float:
    """Return an adaptive score threshold based on pool pressure.

    When the pool is close to its max size, the threshold rises to
    aggressively prune low-scored memories and make room for new ones.
    Formula: threshold = base * (1 + 3 * fill_ratio), capped at 0.2.
    """
    if max_size <= 0:
        return SCORE_THRESHOLD_BASE
    fill_ratio = max(0.0, min(1.0, pool_size / max_size))
    return min(SCORE_THRESHOLD_BASE * (1.0 + 3.0 * fill_ratio), 0.2)


def prune_pool(
    records: list[MemoryRecord],
    threshold: float = SCORE_THRESHOLD_BASE,
    max_size: int = POOL_SIZE_MIN,
) -> list[MemoryRecord]:
    """Prune the memory pool: drop below-threshold, then cap at max_size.

    Records are assumed scored already (score field populated).
    """
    above = [r for r in records if r.score >= threshold]

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

    Pool size and prune threshold adapt to current_round:
    - max_size = max(200, current_round * 2) — scales with campaign length
    - threshold rises when pool is near max (pressure-based pruning)

    similarity_scores: optional BGE reranker scores for top-2k re-ranking.
    """
    if not records:
        return []

    max_pool_size = compute_dynamic_pool_size(current_round)
    threshold = compute_adaptive_threshold(len(records), max_pool_size)

    # Step 1: Compute scores for all records
    scored = score_all(records, current_round)

    # Step 2: If similarity scores provided, re-rank top-2k by similarity
    if similarity_scores is not None and len(similarity_scores) > 0:
        top_2k = scored[:2 * k]
        rest = scored[2 * k:]
        sim_ranked: list[tuple[MemoryRecord, float, float]] = []
        for i, (rec, base_score) in enumerate(top_2k):
            sim = similarity_scores[i] if i < len(similarity_scores) else 0.0
            sim_ranked.append((rec, base_score, sim))
        sim_ranked.sort(key=lambda x: x[2], reverse=True)
        scored = [(rec, base) for rec, base, _ in sim_ranked] + rest

    # Step 3: Apply reinforcement and suppression
    reinforced = apply_retrieval_reinforcement(scored, current_round, k=k)

    # Step 4: Prune pool with adaptive parameters
    pruned = prune_pool(reinforced, threshold=threshold, max_size=max_pool_size)

    prune_count = len(reinforced) - len(pruned)
    prune_rate = prune_count / len(reinforced) if reinforced else 0.0

    logger.debug(
        "forget_step: round=%d pool_in=%d pool_out=%d pruned=%d (%.0f%%) "
        "max_size=%d threshold=%.4f",
        current_round, len(records), len(pruned),
        prune_count, prune_rate * 100,
        max_pool_size, threshold,
    )

    return pruned
