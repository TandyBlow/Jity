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
from app.services.agents.examiner import (
    ExaminerAgent,
    is_passive_continuation_action,
)
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
    @pytest.mark.parametrize("action", ["继续", "继续剧情。", "接着", " 接着讲！ "])
    def test_passive_continuation_action(self, action):
        assert is_passive_continuation_action(action)

    @pytest.mark.parametrize("action", ["继续调查档案", "打开没有钥匙的门", "攻击诺诺"])
    def test_non_passive_action_still_needs_examination(self, action):
        assert not is_passive_continuation_action(action)


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
