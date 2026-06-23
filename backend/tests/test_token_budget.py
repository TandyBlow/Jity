"""Tests for context injection, token budget, and per-turn instrumentation."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.schemas.game import StoryOutput
from app.services.campaign_manager import CampaignManager


def _make_output(narration="测试叙事文本", dialogue=None, options=None, sanity_delta=0, health_delta=0, location=""):
    return StoryOutput(
        narration=narration,
        dialogue=dialogue or [],
        scene_prompt="test",
        sanity_delta=sanity_delta,
        health_delta=health_delta,
        options=options or ["选项1", "选项2"],
        current_location=location,
    )


def _make_state(location="卡塞尔学院报到大厅", npcs=None, items=None, turn=5, sanity=80, health=100):
    return {
        "current_location": location,
        "npcs": npcs or [{"name": "诺诺", "status": "present"}],
        "items": items or [],
        "sanity": sanity,
        "health": health,
        "turn": turn,
        "player_status": {"condition": "正常", "danger_level": "medium"},
        "recent_events": [],
        "quests": [],
        "world_facts": [],
    }


class TestContextInjection:
    """Tests for CampaignManager.inject_context()."""

    def test_inject_returns_empty_when_no_campaign(self):
        """inject_context() returns empty string when no campaign loaded."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        result = mgr.inject_context(_make_state(), 0)
        assert result == ""

    def test_inject_returns_context_when_campaign_loaded(self, tmp_path):
        """inject_context() returns non-empty context string when campaign is loaded."""
        campaign_data = {
            "version": 3,
            "title": "测试战役",
            "core_conflict": "冲突",
            "arcs": [
                {
                    "name": "弧1",
                    "goal": "测试目标",
                    "sessions": [
                        {
                            "name": "幕1",
                            "opening_scene": "",
                            "anchor_events": [],
                        }
                    ],
                }
            ],
        }
        campaign_path = tmp_path / "test.json"
        campaign_path.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(campaign_path)

        result = mgr.inject_context(_make_state(), 5)
        assert "弧1" in result
        assert "幕1" in result
        assert "锚点进度" in result

    def test_inject_context_includes_anchor_progress(self, tmp_path):
        """inject_context() should include anchor progress counts."""
        campaign_data = {
            "version": 3,
            "title": "进度测试",
            "core_conflict": "冲突",
            "arcs": [
                {
                    "name": "弧",
                    "goal": "",
                    "sessions": [
                        {
                            "name": "幕",
                            "opening_scene": "",
                            "anchor_events": [
                                {
                                    "id": "a1",
                                    "name": "锚点1",
                                    "description": "测试",
                                    "priority": 1,
                                    "trigger_conditions": {},
                                },
                                {
                                    "id": "a2",
                                    "name": "锚点2",
                                    "description": "测试",
                                    "priority": 2,
                                    "trigger_conditions": {},
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        campaign_path = tmp_path / "test.json"
        campaign_path.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(campaign_path)

        result = mgr.inject_context(_make_state(), 5)
        assert "0/2" in result  # 0 revealed, 2 total


class TestTokenBudget:
    """Tests for CampaignManager.check_token_budget()."""

    def test_short_prompt_within_budget(self):
        """A short prompt should be within token budget."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        ok, count, warning = mgr.check_token_budget("Hello, this is a short prompt.")
        assert ok is True
        assert count > 0
        assert warning == ""

    def test_token_count_is_positive(self):
        """Token count should be a positive integer."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        _, count, _ = mgr.check_token_budget("测试中文 prompt")
        assert count > 0
        assert isinstance(count, int)

    def test_budget_limit_is_configured(self):
        """TOKEN_BUDGET_LIMIT should be set to 102400 (80% of 128K)."""
        assert CampaignManager.TOKEN_BUDGET_LIMIT == 102400

    def test_encoding_uses_cl100k_base(self):
        """Token budget should use cl100k_base encoder."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        enc = mgr._get_encoder()
        assert enc.name == "cl100k_base"


class TestInstrumentation:
    """Tests for CampaignManager.record_turn()."""

    def test_record_turn_word_count(self):
        """record_turn should count characters in narration."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        output = _make_output(narration="这是一个测试叙事文本，包含多个汉字。")
        metrics = mgr.record_turn(output, _make_state(), 500)
        assert metrics["word_count"] == len("这是一个测试叙事文本，包含多个汉字。")

    def test_record_turn_option_count(self):
        """record_turn should count options."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        output = _make_output(options=["选项A", "选项B", "选项C", "选项D"])
        metrics = mgr.record_turn(output, _make_state(), 500)
        assert metrics["option_count"] == 4

    def test_record_turn_dialogue_lines(self):
        """record_turn should count dialogue lines."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        output = _make_output(dialogue=[
            {"speaker": "A", "text": "Hello"},
            {"speaker": "B", "text": "World"},
            {"speaker": "A", "text": "!"},
        ])
        metrics = mgr.record_turn(output, _make_state(), 500)
        assert metrics["dialogue_lines"] == 3

    def test_record_turn_sanity_delta(self):
        """record_turn should capture sanity_delta from output."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        output = _make_output(sanity_delta=-5)
        metrics = mgr.record_turn(output, _make_state(), 500)
        assert metrics["sanity_delta"] == -5

    def test_record_turn_health_delta(self):
        """record_turn should capture health_delta from output."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        output = _make_output(health_delta=10)
        metrics = mgr.record_turn(output, _make_state(), 500)
        assert metrics["health_delta"] == 10

    def test_record_turn_location_changed_false(self):
        """location_changed should be 0 when location unchanged."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        output = _make_output(location="卡塞尔学院报到大厅")
        state = _make_state(location="卡塞尔学院报到大厅")
        metrics = mgr.record_turn(output, state, 500)
        assert metrics["location_changed"] == 0

    def test_record_turn_location_changed_true(self):
        """location_changed should be 1 when location changes."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        output = _make_output(location="旧档案室")
        state = _make_state(location="卡塞尔学院报到大厅")
        metrics = mgr.record_turn(output, state, 500)
        assert metrics["location_changed"] == 1


class TestOptionConfig:
    def test_resolve_max_turns_is_independent_of_cwd(self, tmp_path):
        """The repository option config should load from any working directory."""
        mgr = CampaignManager(
            db=MagicMock(),
            campaigns_dir=Path("/tmp"),
            scripted_story=MagicMock(),
        )
        previous_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            assert mgr._resolve_max_turns() == 30
        finally:
            os.chdir(previous_cwd)
