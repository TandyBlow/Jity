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

class TestAgentIOSchemas:
    def test_action_ruling_defaults(self):
        r = ActionRuling()
        assert r.permissibility == ActionPermissibility.PERMISSIBLE
        assert r.triggered_rules == []

    def test_director_instruction_defaults(self):
        d = DirectorInstruction(narrative_direction="继续叙事")
        assert d.narrative_direction == "继续叙事"
        assert d.anchor_triggered == ""
        assert d.anchor_triggered == ""

    def test_episode_summary_defaults(self):
        e = EpisodeSummary(episode_id="test", turn_start=0, turn_end=5, summary="测试")
        assert e.importance > 0.0
        assert e.level == 1

    def test_memory_record_score_initial(self):
        r = MemoryRecord(memory_id="m1", content="test")
        assert r.score == 0.0

    def test_item_state_enum_values(self):
        assert ItemState.ACTIVE.value == "active"
        assert ItemState.LOST.value == "lost"
        assert ItemState.DESTROYED.value == "destroyed"

    def test_redirection_strategy_enum_values(self):
        assert RedirectionStrategy.NPC_INFLUENCE.value == "npc_influence"
        assert RedirectionStrategy.WORLD_CONSEQUENCES.value == "world_consequences"

    def test_triggered_rule_fields(self):
        rule = TriggeredRule(rule_type="sanity_check", rule_name="测试", rule_details="1d100")
        assert rule.rule_type == "sanity_check"
        assert rule.rule_name == "测试"

    def test_item_continuity_check(self):
        from app.schemas.agent_io import ItemContinuityCheck
        ic = ItemContinuityCheck(
            item_name="钥匙", previous_state="lost", current_state="active",
            is_valid_transition=False, error_description="测试",
        )
        assert not ic.is_valid_transition

    def test_hallucination_finding(self):
        from app.schemas.agent_io import HallucinationFinding, HallucinationType
        hf = HallucinationFinding(
            hallucination_type=HallucinationType.FABRICATION,
            description="LLM fabricated an item",
        )
        assert hf.hallucination_type == HallucinationType.FABRICATION


# ── Integration: pipe through the full call chain in memory ──
