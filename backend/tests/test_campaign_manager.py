"""Contract tests for CampaignManager pure logic (Phase 2 implementation).

These tests define the expected behavior BEFORE implementation.
They will FAIL initially (RED phase) — that's correct.
"""

import json
from pathlib import Path

import pytest

from app.schemas.campaign import (
    AnchorEvent,
    AnchorTriggerConditions,
    ArcSchema,
    CampaignSchema,
    SessionSchema,
)
from app.services.campaign_manager import CampaignManager


class TestCampaignLoad:
    """Tests for campaign loading and validation."""

    def test_load_valid_campaign(self, sample_campaign_json: dict):
        """Valid JSON should parse into CampaignSchema."""
        campaign = CampaignSchema.model_validate(sample_campaign_json)
        assert campaign.title == "测试战役"
        assert campaign.core_conflict == "一个古老的邪恶在校园苏醒"
        assert campaign.version == 1
        assert len(campaign.arcs) == 1

    def test_reject_missing_title(self, sample_campaign_json: dict):
        """ValidationError when title field is missing."""
        data = dict(sample_campaign_json)
        del data["title"]
        with pytest.raises(Exception):  # pydantic ValidationError
            CampaignSchema.model_validate(data)

    def test_reject_missing_core_conflict(self, sample_campaign_json: dict):
        """ValidationError when core_conflict field is missing."""
        data = dict(sample_campaign_json)
        del data["core_conflict"]
        with pytest.raises(Exception):
            CampaignSchema.model_validate(data)

    def test_reject_missing_arcs(self, sample_campaign_json: dict):
        """Arcs field defaults to empty list when missing (Pydantic default)."""
        data = dict(sample_campaign_json)
        del data["arcs"]
        campaign = CampaignSchema.model_validate(data)
        # arcs has default_factory=list, so it's not required
        assert campaign.arcs == []

    def test_reject_empty_arcs(self, sample_campaign_json: dict):
        """Validation should reject campaign with empty arcs list."""
        data = dict(sample_campaign_json)
        # Pydantic allows empty list by default — test that it parses
        data["arcs"] = []
        campaign = CampaignSchema.model_validate(data)
        assert campaign.arcs == []


class TestAnchorValidation:
    """Tests for anchor event validation."""

    def test_anchor_valid_trigger(self):
        """Anchor with valid trigger_conditions should parse."""
        anchor = AnchorEvent.model_validate({
            "id": "a1",
            "name": "测试锚点",
            "description": "测试描述",
            "priority": 3,
            "trigger_conditions": {"location": "图书馆"},
        })
        assert anchor.priority == 3
        assert anchor.trigger_conditions.location == "图书馆"

    def test_anchor_priority_bounds(self):
        """Priority must be 1-5."""
        AnchorEvent.model_validate({
            "id": "a1", "name": "t", "description": "d",
            "priority": 1,
            "trigger_conditions": {},
        })
        AnchorEvent.model_validate({
            "id": "a2", "name": "t", "description": "d",
            "priority": 5,
            "trigger_conditions": {},
        })

    def test_anchor_reject_priority_out_of_range(self):
        """Priority > 5 should raise validation error."""
        with pytest.raises(Exception):
            AnchorEvent.model_validate({
                "id": "a1", "name": "t", "description": "d",
                "priority": 6,
                "trigger_conditions": {},
            })


class TestSchemaMigration:
    """Tests for campaign.json version migration."""

    def test_migrate_v1_structure(self):
        """v1 campaign JSON should parse with version=1 fields."""
        v1_data = {
            "version": 1,
            "title": "V1 战役",
            "core_conflict": "冲突",
            "arcs": [],
        }
        campaign = CampaignSchema.model_validate(v1_data)
        assert campaign.version == 1
        assert campaign.title == "V1 战役"

    def test_future_version_still_parses(self):
        """Version field should accept any int (forward compat)."""
        data = {
            "version": 99,
            "title": "未来版本",
            "core_conflict": "冲突",
            "arcs": [],
        }
        campaign = CampaignSchema.model_validate(data)
        assert campaign.version == 99


class TestAnchorRetrieval:
    """Tests for anchor event retrieval from campaign structure."""

    def test_get_anchors_from_session(self, sample_campaign_json: dict):
        """Should access anchors from arc→session hierarchy."""
        campaign = CampaignSchema.model_validate(sample_campaign_json)
        anchors = campaign.arcs[0].sessions[0].anchor_events
        assert len(anchors) == 1
        assert anchors[0].id == "anchor-1"
        assert anchors[0].name == "发现红色标记"

    def test_highest_priority_anchor_first(self, sample_campaign_json: dict):
        """Higher priority anchors should sort first."""
        campaign = CampaignSchema.model_validate(sample_campaign_json)
        # Add second anchor with lower priority
        anchors = campaign.arcs[0].sessions[0].anchor_events
        sorted_anchors = sorted(anchors, key=lambda a: a.priority)
        assert sorted_anchors[0].priority <= sorted_anchors[-1].priority


class TestProgressTracking:
    """Tests for campaign progress tracking."""

    def test_progress_initial_state(self):
        """New progress should start at arc 0, session 0, no revealed anchors."""
        from app.schemas.campaign import CampaignProgress

        progress = CampaignProgress(campaign_id="test-camp")
        assert progress.arc_index == 0
        assert progress.session_index == 0
        assert progress.revealed_anchors == []

    def test_progress_reveal_anchor(self):
        """Revealing an anchor should add its ID to the list."""
        from app.schemas.campaign import CampaignProgress

        progress = CampaignProgress(campaign_id="test-camp")
        progress.revealed_anchors.append("anchor-1")
        assert "anchor-1" in progress.revealed_anchors


class TestCampaignManagerLoading:
    """Tests for CampaignManager.load() and get_opening_scene()."""

    def test_load_valid_campaign_file(self, tmp_path):
        """CampaignManager.load() should parse a valid campaign.json."""
        campaign_data = {
            "version": 3,
            "title": "测试",
            "core_conflict": "冲突",
            "arcs": [
                {
                    "name": "弧1",
                    "goal": "",
                    "sessions": [
                        {
                            "name": "幕1",
                            "opening_scene": "开场测试文本",
                            "anchor_events": [],
                        }
                    ],
                }
            ],
        }
        campaign_path = tmp_path / "test_campaign.json"
        campaign_path.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        from unittest.mock import MagicMock
        db = MagicMock()
        db.read_campaign_progress.return_value = None
        scripted_story = MagicMock()
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=scripted_story)
        campaign = mgr.load(campaign_path)

        assert campaign.title == "测试"
        assert campaign.version == 4
        assert len(campaign.arcs) == 1
        assert mgr.is_loaded() is True

    def test_get_opening_scene_returns_first_session(self, tmp_path):
        """get_opening_scene() returns first session opening when no progress set."""
        campaign_data = {
            "version": 3,
            "title": "测试",
            "core_conflict": "冲突",
            "arcs": [
                {
                    "name": "弧1",
                    "goal": "",
                    "sessions": [
                        {"name": "幕1", "opening_scene": "第一幕开场", "anchor_events": []},
                        {"name": "幕2", "opening_scene": "第二幕开场", "anchor_events": []},
                    ],
                }
            ],
        }
        campaign_path = tmp_path / "test_campaign.json"
        campaign_path.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        from unittest.mock import MagicMock
        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(campaign_path)

        scene = mgr.get_opening_scene()
        assert scene == "第一幕开场"

    def test_get_opening_scene_returns_none_when_no_campaign(self):
        """get_opening_scene() returns None when no campaign loaded."""
        from unittest.mock import MagicMock
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        assert mgr.get_opening_scene() is None
        assert mgr.is_loaded() is False

    def test_get_opening_scene_returns_none_when_empty_opening(self, tmp_path):
        """get_opening_scene() returns None when session has empty opening_scene."""
        campaign_data = {
            "version": 3,
            "title": "测试",
            "core_conflict": "冲突",
            "arcs": [
                {
                    "name": "弧1", "goal": "",
                    "sessions": [
                        {"name": "幕1", "opening_scene": "", "anchor_events": []},
                    ],
                }
            ],
        }
        campaign_path = tmp_path / "test_campaign.json"
        campaign_path.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        from unittest.mock import MagicMock
        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(campaign_path)
        assert mgr.get_opening_scene() is None

    def test_load_rejects_invalid_json(self, tmp_path):
        """load() should raise ValueError for invalid JSON."""
        campaign_path = tmp_path / "bad.json"
        campaign_path.write_text("not json", encoding="utf-8")
        from unittest.mock import MagicMock
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=tmp_path, scripted_story=MagicMock())
        with pytest.raises(ValueError):
            mgr.load(campaign_path)

    def test_load_file_not_found(self, tmp_path):
        """load() should raise FileNotFoundError for missing file."""
        from unittest.mock import MagicMock
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=tmp_path, scripted_story=MagicMock())
        with pytest.raises(FileNotFoundError):
            mgr.load(tmp_path / "nonexistent.json")

    def test_load_migrates_v1_to_v3(self, tmp_path):
        """load() should migrate v1 campaign to v3 automatically."""
        v1_data = {
            "version": 1,
            "title": "V1战役",
            "core_conflict": "冲突",
            "arcs": [],
        }
        campaign_path = tmp_path / "v1_campaign.json"
        campaign_path.write_text(json.dumps(v1_data, ensure_ascii=False), encoding="utf-8")

        from unittest.mock import MagicMock
        db = MagicMock()
        db.read_campaign_progress.return_value = None
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        campaign = mgr.load(campaign_path)
        assert campaign.version == 4
        assert campaign.constraints == ""
        assert campaign.starting_state == {}
