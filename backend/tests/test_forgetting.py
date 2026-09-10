"""Tests for multi-agent pipeline: examiner, director, forgetting, SCORE tracker, NSB, PCB."""

import math
import pytest

from app.schemas.agent_io import (
    ActionPermissibility,
    ActionRuling,
    DirectorInstruction,
    EpisodeSummary,
    HallucinationFinding,
    HallucinationType,
    ItemState,
    ItemStateRecord,
    MemoryRecord,
    PersonaSnapshot,
    PersonaValue,
    RedirectionStrategy,
    TriggeredRule,
)
from app.services.agents.director import DirectorAgent, _parse_instruction, _fallback_instruction
from app.services.agents.examiner import ExaminerAgent, _parse_ruling, _compact_entities
from app.services.memory.forgetting import (
    compute_score,
    score_all,
    apply_retrieval_reinforcement,
    prune_pool,
    forget_step,
    ALPHA,
    BETA,
    GAMMA,
    K,
)
from app.services.memory.score_tracker import ScoreTracker
from app.services.memory.nsb import NarrativeSummarizationBranch
from app.services.memory.pcb import PersonaConstructionBranch, _approx_equal
from app.services.memory.memory_controller import MemoryController


# ── Examiner ────────────────────────────────────────────────

class TestForgetting:
    def test_compute_score_new_memory(self):
        r = MemoryRecord(memory_id="m1", content="test", created_round=0, retrieved_rounds=[])
        s = compute_score(r, current_round=0)
        assert s > 0

    def test_compute_score_old_memory_decays(self):
        r = MemoryRecord(memory_id="m1", content="test", created_round=0, retrieved_rounds=[])
        s0 = compute_score(r, current_round=0)
        s10 = compute_score(r, current_round=10)
        # Older memory should score lower
        assert s10 < s0

    def test_compute_score_frequently_retrieved_reinforced(self):
        r1 = MemoryRecord(memory_id="m1", content="test", created_round=0, retrieved_rounds=[1, 3, 5])
        r2 = MemoryRecord(memory_id="m2", content="test", created_round=0, retrieved_rounds=[])
        s1 = compute_score(r1, current_round=10)
        s2 = compute_score(r2, current_round=10)
        # Frequently retrieved memory should score higher
        assert s1 > s2

    def test_score_all_sorts_descending(self):
        records = [
            MemoryRecord(memory_id="m1", content="a", created_round=5, retrieved_rounds=[]),
            MemoryRecord(memory_id="m2", content="b", created_round=0, retrieved_rounds=[]),
            MemoryRecord(memory_id="m3", content="c", created_round=10, retrieved_rounds=[11]),
        ]
        scored = score_all(records, current_round=12)
        scores = [s for _, s in scored]
        # Should be sorted descending
        assert scores == sorted(scores, reverse=True)

    def test_apply_reinforcement_adds_rounds(self):
        records = [
            MemoryRecord(memory_id="m1", content="a", created_round=0),
            MemoryRecord(memory_id="m2", content="b", created_round=0),
            MemoryRecord(memory_id="m3", content="c", created_round=0),
        ]
        scored = score_all(records, current_round=5)
        reinforced = apply_retrieval_reinforcement(scored, current_round=5, k=1)
        # Top-k should have retrieved_rounds updated
        assert 5 in reinforced[0].retrieved_rounds  # top-1 got recorded

    def test_prune_pool_drops_below_threshold(self):
        records = [
            MemoryRecord(memory_id="m1", content="a", score=0.5),
            MemoryRecord(memory_id="m2", content="b", score=0.001),
        ]
        pruned = prune_pool(records, threshold=0.01)
        assert len(pruned) == 1
        assert pruned[0].memory_id == "m1"

    def test_prune_pool_caps_max_size(self):
        records = [MemoryRecord(memory_id=f"m{i}", content="x", score=0.5) for i in range(300)]
        pruned = prune_pool(records, threshold=0.01, max_size=200)
        assert len(pruned) == 200

    def test_forget_step_idempotent_on_empty(self):
        result = forget_step([], current_round=0)
        assert result == []

    def test_forget_step_returns_fewer_or_equal(self):
        records = [MemoryRecord(memory_id=f"m{i}", content="x", created_round=i) for i in range(50)]
        result = forget_step(records, current_round=60)
        # Some old records may be pruned, pool shrinks or stays same
        assert len(result) <= len(records)

    def test_alpha_beta_sum_to_1(self):
        # From MOOM paper: α=0.1, β=0.9
        assert ALPHA + BETA == pytest.approx(1.0)
        assert K == pytest.approx(9)


# ── SCORE Tracker ───────────────────────────────────────────


class TestForgettingFullPipeline:
    """Test the MOOM forgetting pipeline end-to-end with realistic data."""

    def test_30_rounds_no_overflow(self):
        """Simulate 30 rounds: pool should not grow unbounded."""
        records: list[MemoryRecord] = []
        for round_num in range(30):
            # Add new memory each round
            new = MemoryRecord(
                memory_id=f"m{round_num}",
                content=f"场景{round_num}的叙事记忆",
                created_round=round_num,
                retrieved_rounds=[round_num - 1] if round_num > 0 else [],
            )
            records.append(new)
            # Run forgetting step
            records = forget_step(records, current_round=round_num)
            # Pool should never exceed MAX_POOL_SIZE
            assert len(records) <= 200, f"Pool overflow at round {round_num}"

    def test_important_memories_survive(self):
        """Memories with high retrieval reinforcement should survive pruning."""
        records: list[MemoryRecord] = []
        # Create one important memory retrieved every round
        important = MemoryRecord(
            memory_id="important",
            content="关键剧情转折",
            created_round=0,
            retrieved_rounds=list(range(50)),
        )
        records.append(important)
        # Create 100 low-value memories
        for i in range(100):
            records.append(MemoryRecord(
                memory_id=f"noise_{i}",
                content=f"噪音记忆{i}",
                created_round=i,
                retrieved_rounds=[],
            ))
        result = forget_step(records, current_round=55)
        ids = {r.memory_id for r in result}
        assert "important" in ids, "High-value memory should survive after 55 rounds"
