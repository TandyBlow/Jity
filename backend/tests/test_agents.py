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

class TestExaminerAgent:
    def test_parse_ruling_permissible(self):
        raw = {"permissibility": "permissible", "triggered_rules": [], "constraints": "", "rejection_reason": ""}
        ruling = _parse_ruling(raw)
        assert ruling.permissibility == ActionPermissibility.PERMISSIBLE
        assert ruling.triggered_rules == []

    def test_parse_ruling_blocked(self):
        raw = {
            "permissibility": "blocked",
            "triggered_rules": [],
            "constraints": "大门紧锁",
            "rejection_reason": "你尝试推门，但门纹丝不动——似乎需要钥匙。",
        }
        ruling = _parse_ruling(raw)
        assert ruling.permissibility == ActionPermissibility.BLOCKED
        assert ruling.rejection_reason != ""

    def test_parse_ruling_with_triggered_rules(self):
        raw = {
            "permissibility": "conditional",
            "triggered_rules": [
                {"rule_type": "sanity_check", "rule_name": "SAN检定", "rule_details": "1d100 ≤ SAN值"}
            ],
            "constraints": "需要SAN检定",
            "rejection_reason": "",
        }
        ruling = _parse_ruling(raw)
        assert ruling.permissibility == ActionPermissibility.CONDITIONAL
        assert len(ruling.triggered_rules) == 1
        assert ruling.triggered_rules[0].rule_type == "sanity_check"

    def test_compact_entities_empty(self):
        assert _compact_entities([]) == "无"

    def test_compact_entities_with_items(self):
        items = [{"name": "钥匙", "status": "owned"}, {"name": "手电筒"}]
        result = _compact_entities(items)
        assert "钥匙" in result
        assert "手电筒" in result


# ── Director ────────────────────────────────────────────────


class TestDirectorAgent:
    def test_parse_instruction_basic(self):
        raw = {
            "narrative_direction": "引导玩家进入钟楼",
            "anchor_triggered": "anchor-1",
            "redirection_strategy": None,
            "redirection_hint": "",
            "item_continuity_checks": [],
            "health_guidance": "",
        }
        inst = _parse_instruction(raw)
        assert inst.narrative_direction == "引导玩家进入钟楼"
        assert inst.anchor_triggered == "anchor-1"
        assert inst.redirection_strategy is None

    def test_parse_instruction_with_redirection(self):
        raw = {
            "narrative_direction": "重定向玩家回主线",
            "anchor_triggered": "",
            "redirection_strategy": "npc_influence",
            "redirection_hint": "诺诺出现在远处向你招手",
            "item_continuity_checks": [],
            "health_guidance": "",
        }
        inst = _parse_instruction(raw)
        assert inst.redirection_strategy == RedirectionStrategy.NPC_INFLUENCE
        assert inst.redirection_hint == "诺诺出现在远处向你招手"

    def test_parse_instruction_with_item_continuity(self):
        raw = {
            "narrative_direction": "继续",
            "anchor_triggered": "",
            "redirection_strategy": None,
            "redirection_hint": "",
            "item_continuity_checks": [
                {"item_name": "旧式左轮", "previous_state": "lost", "current_state": "active",
                 "is_valid_transition": False, "error_description": "物品状态不一致"}
            ],
            "health_guidance": "",
        }
        inst = _parse_instruction(raw)
        assert len(inst.item_continuity_checks) == 1
        assert inst.item_continuity_checks[0].is_valid_transition is False

    def test_fallback_blocked(self):
        ruling = ActionRuling(permissibility=ActionPermissibility.BLOCKED, constraints="门锁住了")
        inst = _fallback_instruction(ruling)
        assert inst.redirection_strategy == RedirectionStrategy.WORLD_CONSEQUENCES

    def test_fallback_permissible(self):
        ruling = ActionRuling(permissibility=ActionPermissibility.PERMISSIBLE)
        inst = _fallback_instruction(ruling)
        assert inst.redirection_strategy is None


# ── MOOM Forgetting ─────────────────────────────────────────
