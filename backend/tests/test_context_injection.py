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
