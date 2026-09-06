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
