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

class TestScoreTracker:
    def test_create_new_item(self):
        st = ScoreTracker()
        r = st.get_or_create("旧式左轮", turn=0)
        assert r.item_name == "旧式左轮"
        assert r.state == ItemState.ACTIVE

    def test_valid_transition(self):
        st = ScoreTracker()
        st.get_or_create("钥匙", turn=0, state=ItemState.ACTIVE)
        new_state, is_error = st.propose_transition("钥匙", ItemState.LOST, turn=5)
        assert new_state == ItemState.LOST
        assert not is_error

    def test_continuity_error_active_after_lost(self):
        st = ScoreTracker()
        st.get_or_create("钥匙", turn=0, state=ItemState.LOST)
        new_state, is_error = st.propose_transition("钥匙", ItemState.ACTIVE, turn=5)
        assert is_error  # Should flag as continuity error
        assert new_state == ItemState.LOST  # Should keep previous state

    def test_continuity_error_active_after_destroyed(self):
        st = ScoreTracker()
        st.get_or_create("信件", turn=0, state=ItemState.DESTROYED)
        new_state, is_error = st.propose_transition("信件", ItemState.ACTIVE, turn=5)
        assert is_error
        assert new_state == ItemState.DESTROYED

    def test_check_narration_detects_violation(self):
        st = ScoreTracker()
        st.get_or_create("神秘钥匙", turn=0, state=ItemState.LOST)
        items = [{"name": "神秘钥匙", "status": "owned"}]
        violations = st.check_narration_continuity("你找到了神秘钥匙", turn=5, items_from_llm=items)
        assert len(violations) > 0
        assert violations[0]["item_name"] == "神秘钥匙"

    def test_load_export_roundtrip(self):
        st = ScoreTracker()
        st.get_or_create("旧式左轮", turn=0, state=ItemState.ACTIVE)
        st.get_or_create("警徽", turn=0, state=ItemState.ACTIVE)
        exported = st.export_state()
        st2 = ScoreTracker()
        st2.load_from_state(exported)
        assert len(st2.all_records()) == 2
        assert st2.get_record("旧式左轮").state == ItemState.ACTIVE

    def test_get_all_states(self):
        st = ScoreTracker()
        st.propose_transition("A", ItemState.ACTIVE, 0)
        st.propose_transition("B", ItemState.LOST, 1)
        states = st.get_all_states()
        assert states["A"] == "active"
        assert states["B"] == "lost"


# ── NSB ──────────────────────────────────────────────────────


class TestScoreTrackerCampaign:
    """Realistic campaign-style SCORE tracker tests."""

    def test_multi_item_campaign_flow(self):
        st = ScoreTracker()
        turns = [
            (0, [("钥匙", "owned"), ("旧式左轮", "owned"), ("警徽", "owned")]),
            (5, [("钥匙", "lost"), ("弹药", "owned")]),
            (10, [("钥匙", "owned")]),  # ← continuity error!
            (15, [("旧式左轮", "lost"), ("弹药", "lost")]),
            (20, [("弹药", "owned")]),  # ← continuity error!
        ]
        violations_all = []
        for turn, items in turns:
            items_parsed = [{"name": name, "status": status} for name, status in items]
            v = st.check_narration_continuity(f"T{turn} 叙事", turn, items_parsed)
            violations_all.extend(v)

        assert len(violations_all) >= 2  # Two continuity errors detected
        # Key: after T10 violation, key state should remain 'lost'
        assert st.get_record("钥匙").state == ItemState.LOST

    def test_state_consistency_across_sessions(self):
        """Simulate state persistence across multiple sessions."""
        # Session 1
        st = ScoreTracker()
        st.propose_transition("神秘信件", ItemState.ACTIVE, 0)
        st.propose_transition("神秘信件", ItemState.LOST, 8)
        export = st.export_state()

        # Session 2 — load and continue
        st2 = ScoreTracker()
        st2.load_from_state(export)
        assert st2.get_record("神秘信件").state == ItemState.LOST

        # Continuity error should still fire
        items = [{"name": "神秘信件", "status": "owned"}]
        violations = st2.check_narration_continuity("你找到了神秘信件", 5, items)
        assert len(violations) == 1


# ── HaluMem Evaluator ──────────────────────────────────────────
