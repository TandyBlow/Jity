"""Tests for anchor event hybrid trigger system."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.schemas.campaign import AnchorEvent, AnchorTriggerConditions
from app.services.campaign_manager import CampaignManager
from app.services.campaign_anchors import CampaignAnchorEvaluator
from app.services.campaign_context import CampaignContextBuilder


def _make_state(location="卡塞尔学院报到大厅", npcs=None, items=None, turn=5):
    """Helper to build a minimal game state dict for anchor testing."""
    return {
        "current_location": location,
        "npcs": npcs or [],
        "items": items or [],
        "sanity": 80,
        "health": 100,
        "turn": turn,
        "player_status": {},
        "recent_events": [],
        "quests": [],
        "world_facts": [],
    }


def _make_anchor(id="a1", name="测试", desc="测试锚点", priority=3, location=None, npc=None, item=None):
    """Helper to build an AnchorEvent for testing."""
    return AnchorEvent(
        id=id,
        name=name,
        description=desc,
        priority=priority,
        trigger_conditions=AnchorTriggerConditions(
            location=location,
            npc_present=npc,
            item_held=item,
        ),
    )


class TestAnchorHardFilter:
    """Tests for hard-filter conditions matching."""

    def test_location_match(self):
        """Anchor with location='报到大厅' should match state at that location."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(location="报到大厅")
        state = _make_state(location="卡塞尔学院报到大厅")
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is True

    def test_location_no_match(self):
        """Anchor with location='图书馆' should NOT match state at '报到大厅'."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(location="图书馆")
        state = _make_state(location="卡塞尔学院报到大厅")
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is False

    def test_npc_match(self):
        """Anchor requiring '诺诺' should match when NPC is present."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(npc="诺诺")
        state = _make_state(npcs=[{"name": "诺诺", "status": "present"}])
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is True

    def test_npc_no_match(self):
        """Anchor requiring '诺诺' should NOT match when NPC absent."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(npc="诺诺")
        state = _make_state(npcs=[{"name": "芬格尔", "status": "present"}])
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is False

    def test_item_match(self):
        """Anchor requiring '通行卡' should match when player has the item."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(item="通行卡")
        state = _make_state(items=[{"name": "临时通行卡", "description": "..."}])
        # Item requirements use exact names, not substring matches.
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is False

    def test_item_exact_match(self):
        """Anchor with exact item name should match."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(item="临时通行卡")
        state = _make_state(items=[{"name": "临时通行卡", "description": "..."}])
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is True

    def test_all_conditions_met(self):
        """When all conditions (location + NPC) are met, should pass."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(location="报到大厅", npc="诺诺")
        state = _make_state(
            location="卡塞尔学院报到大厅",
            npcs=[{"name": "诺诺", "status": "present"}],
        )
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is True

    def test_partial_conditions_not_met(self):
        """When only one of two conditions is met, should fail."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor(location="报到大厅", npc="诺诺")
        state = _make_state(
            location="卡塞尔学院报到大厅",
            npcs=[{"name": "芬格尔", "status": "present"}],
        )
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is False

    def test_none_condition_always_true(self):
        """When trigger_conditions has all None, any state matches."""
        evaluator = CampaignAnchorEvaluator()
        anchor = _make_anchor()  # all conditions None
        state = _make_state()
        assert evaluator._conditions_met(anchor.trigger_conditions, state) is True


class TestAnchorPriority:
    """Tests for priority sorting."""

    def test_lowest_priority_number_wins(self):
        """Priority 1 should sort before priority 5."""
        anchors = [
            _make_anchor(id="a5", priority=5, location="报到大厅"),
            _make_anchor(id="a1", priority=1, location="报到大厅"),
            _make_anchor(id="a3", priority=3, location="报到大厅"),
        ]
        anchors.sort(key=lambda a: a.priority)
        assert anchors[0].id == "a1"
        assert anchors[1].id == "a3"
        assert anchors[2].id == "a5"


class TestAnchorCooldown:
    """Tests for anchor cooldown tracking."""

    def test_cooldown_allows_after_3_turns(self):
        """Anchor should be allowed after >=3 turns since last trigger."""
        evaluator = CampaignAnchorEvaluator()
        evaluator.record_cooldown("a1", 0)  # triggered at turn 0
        assert evaluator._check_cooldown("a1", 3) is True

    def test_cooldown_blocks_within_3_turns(self):
        """Anchor should be blocked within 3 turns of last trigger."""
        evaluator = CampaignAnchorEvaluator()
        evaluator.record_cooldown("a1", 2)  # triggered at turn 2
        assert evaluator._check_cooldown("a1", 4) is False  # turn 4 - turn 2 = 2 < 3

    def test_never_triggered_always_allowed(self):
        """Anchor with no cooldown entry should always be allowed."""
        evaluator = CampaignAnchorEvaluator()
        assert evaluator._check_cooldown("new_anchor", 0) is True
        assert evaluator._check_cooldown("new_anchor", 100) is True


class TestMarkAnchorTriggered:
    """Tests for mark_anchor_triggered()."""

    def test_mark_adds_to_revealed_and_cooldown(self):
        """Triggering an anchor should add to revealed list and set cooldown."""
        from app.schemas.campaign import CampaignProgress

        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"))
        mgr.progress = CampaignProgress(campaign_id="test")
        mgr.mark_anchor_triggered("a1", 5)
        assert "a1" in mgr.progress.revealed_anchors
        assert not mgr._anchors._check_cooldown("a1", 7)
        assert mgr._anchors._check_cooldown("a1", 8)


class TestDescribeTrigger:
    """Tests for _describe_trigger() diegetic redirection."""

    def test_describe_includes_anchor_name(self):
        """The redirection instruction should include the anchor's Chinese name."""
        anchor = _make_anchor(id="a1", name="发现红色标记", desc="玩家注意到红色标记")
        instruction = CampaignContextBuilder._describe_trigger(anchor)
        assert "发现红色标记" in instruction
        assert "红色标记" in instruction

    def test_describe_is_diegetic(self):
        """The instruction should use diegetic language (环境线索, NPC暗示)."""
        anchor = _make_anchor()
        instruction = CampaignContextBuilder._describe_trigger(anchor)
        assert "环境线索" in instruction or "NPC暗示" in instruction or "剧情推动" in instruction

    def test_describe_no_hard_denial(self):
        """The instruction should NOT contain hard denial language."""
        anchor = _make_anchor()
        instruction = CampaignContextBuilder._describe_trigger(anchor)
        assert "不能" not in instruction
        assert "禁止" not in instruction
        assert "必须" not in instruction
