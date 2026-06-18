"""Tests for LLM fact extraction and deviation detection."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.campaign_manager import CampaignManager
from app.services.prompt_builder import build_fact_extraction, FACT_EXTRACTION_PROMPT


class TestFactExtractionPrompt:
    """Tests for fact extraction prompt building."""

    def test_build_fact_extraction_includes_events(self):
        """build_fact_extraction should include recent events."""
        result = build_fact_extraction(
            "最新叙事内容", ["事件1", "事件2"]
        )
        assert "事件1" in result
        assert "事件2" in result
        assert "最新叙事内容" in result

    def test_prompt_has_output_format(self):
        """Fact extraction prompt should specify JSON output format."""
        assert "JSON" in FACT_EXTRACTION_PROMPT
        assert "name" in FACT_EXTRACTION_PROMPT


class TestDeviationDetection:
    """Tests for deviation detection."""

    def test_no_deviation_without_campaign(self):
        """detect_deviation returns False when no campaign loaded."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        assert mgr.detect_deviation({}, 5) is False

    def test_detect_deviation_after_sustained_turns(self, tmp_path):
        """detect_deviation returns True after 3+ turns with no anchor."""
        campaign_data = {
            "version": 3, "title": "Dev测试", "core_conflict": "冲突",
            "arcs": [{
                "name": "A", "goal": "",
                "sessions": [{
                    "name": "S", "opening_scene": "",
                    "anchor_events": [
                        {"id": "a1", "name": "A1", "description": "D", "priority": 1, "trigger_conditions": {}},
                    ],
                }],
            }],
        }
        p = tmp_path / "test.json"
        p.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(p)
        # Turn 5, no anchors triggered
        assert mgr.detect_deviation({}, 5) is True

    def test_no_deviation_early_turns(self, tmp_path):
        """detect_deviation returns False in early turns (< 3)."""
        campaign_data = {
            "version": 3, "title": "Dev测试", "core_conflict": "冲突",
            "arcs": [{
                "name": "A", "goal": "",
                "sessions": [{
                    "name": "S", "opening_scene": "",
                    "anchor_events": [
                        {"id": "a1", "name": "A1", "description": "D", "priority": 1, "trigger_conditions": {}},
                    ],
                }],
            }],
        }
        p = tmp_path / "test.json"
        p.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(p)
        assert mgr.detect_deviation({}, 1) is False


class TestAdaptiveAnchors:
    """Tests for adaptive anchor generation."""

    def test_generate_adaptive_anchors(self, tmp_path):
        """generate_adaptive_anchors should create location-based anchor."""
        campaign_data = {
            "version": 3, "title": "Adaptive测试", "core_conflict": "冲突",
            "arcs": [{"name": "A", "goal": "", "sessions": [{"name": "S", "opening_scene": "", "anchor_events": []}]}],
        }
        p = tmp_path / "test.json"
        p.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(p)
        anchors = mgr.generate_adaptive_anchors({"current_location": "图书馆"})
        assert len(anchors) >= 1
        assert anchors[0].id.startswith("dynamic-")
        assert "图书馆" in anchors[0].name

    def test_adaptive_anchor_cap(self, tmp_path):
        """generate_adaptive_anchors should cap at 3 dynamic anchors."""
        campaign_data = {
            "version": 3, "title": "Cap测试", "core_conflict": "冲突",
            "arcs": [{"name": "A", "goal": "", "sessions": [{"name": "S", "opening_scene": "", "anchor_events": []}]}],
        }
        p = tmp_path / "test.json"
        p.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(p)
        # Simulate 3 existing dynamic anchors
        mgr.progress.revealed_anchors = ["dynamic-0-0-1", "dynamic-0-0-2", "dynamic-0-0-3"]
        anchors = mgr.generate_adaptive_anchors({"current_location": "某地"})
        assert len(anchors) == 0  # cap reached
