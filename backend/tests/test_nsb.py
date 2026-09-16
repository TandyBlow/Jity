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

class TestNarrativeSummarizationBranch:
    def test_should_summarize_level1_after_theta1_turns(self):
        nsb = NarrativeSummarizationBranch(llm_client=None, theta1=6)
        assert not nsb.should_summarize_level1()
        for i in range(6):
            nsb.add_turn(f"行动{i}", f"叙事{i}", turn=i)
        assert nsb.should_summarize_level1()

    def test_should_not_summarize_level2_prematurely(self):
        nsb = NarrativeSummarizationBranch(llm_client=None, theta2=5)
        assert not nsb.should_summarize_level2()

    def test_accept_level1_stores_and_enables_level2(self):
        nsb = NarrativeSummarizationBranch(llm_client=None, theta2=5)
        for i in range(5):
            nsb.accept_level1(EpisodeSummary(
                episode_id=f"ep1_{i}", turn_start=i*6, turn_end=i*6+5,
                summary=f"摘要{i}", tags=["悬疑"], entities_involved=["玩家"],
            ))
        assert nsb.should_summarize_level2()

    def test_get_retrieval_context_by_query(self):
        nsb = NarrativeSummarizationBranch(llm_client=None)
        nsb.accept_level1(EpisodeSummary(
            episode_id="ep1", turn_start=0, turn_end=5,
            summary="战斗场景", tags=["战斗"], entities_involved=["老汤姆"],
            importance=0.8,
        ))
        nsb.accept_level1(EpisodeSummary(
            episode_id="ep2", turn_start=6, turn_end=11,
            summary="探索场景", tags=["探索"], entities_involved=["钟楼"],
            importance=0.5,
        ))
        results = nsb.get_retrieval_context("老汤姆")
        assert len(results) > 0
        # Entity match should rank higher
        assert results[0].episode_id == "ep1"

    def test_export_load_roundtrip(self):
        nsb = NarrativeSummarizationBranch(llm_client=None)
        nsb.add_turn("行动", "叙事", turn=0)
        nsb.accept_level1(EpisodeSummary(
            episode_id="ep1", turn_start=0, turn_end=5,
            summary="测试", tags=["测试"],
        ))
        state = nsb.export_state()
        nsb2 = NarrativeSummarizationBranch(llm_client=None)
        nsb2.load_state(state)
        assert len(nsb2._turn_buffer) == 1
        assert len(nsb2._level1) == 1


# ── PCB ──────────────────────────────────────────────────────
