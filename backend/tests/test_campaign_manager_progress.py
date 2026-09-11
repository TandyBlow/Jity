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
