"""Tests for campaign.json schema — migration chain, TypeAdapter, JSON Schema."""

import json

import pytest
from pydantic import ValidationError

from app.schemas.campaign import (
    CampaignSchema,
    CampaignProgress,
    migrate,
    campaign_adapter,
    CURRENT_SCHEMA_VERSION,
    _MIGRATIONS,
    _migrate_v1_to_v2,
    _migrate_v2_to_v3,
)


class TestMigrationChain:
    """Tests for version migration chain v1→v2→v3."""

    def test_migrate_v1_to_v3(self):
        """v1 data should be migrated to v3 and pass validation."""
        v1_data = {
            "version": 1,
            "title": "V1 测试",
            "core_conflict": "冲突",
            "arcs": [],
        }
        migrated = migrate(v1_data)
        assert migrated["version"] == 3
        assert migrated["constraints"] == ""  # v2 default
        assert migrated["starting_state"] == {}  # v3 default
        campaign = CampaignSchema.model_validate(migrated)
        assert campaign.version == 3
        assert campaign.title == "V1 测试"

    def test_migrate_v2_to_v3(self):
        """v2 data should be migrated to v3 (adds starting_state)."""
        v2_data = {
            "version": 2,
            "title": "V2 测试",
            "core_conflict": "冲突",
            "arcs": [],
            "constraints": "NPC不能死亡",
        }
        migrated = migrate(v2_data)
        assert migrated["version"] == 3
        assert migrated["constraints"] == "NPC不能死亡"  # preserved
        assert migrated["starting_state"] == {}  # v3 default added
        campaign = CampaignSchema.model_validate(migrated)
        assert campaign.version == 3

    def test_migrate_already_v3_is_idempotent(self):
        """v3 data should remain unchanged by migration."""
        v3_data = {
            "version": 3,
            "title": "V3 测试",
            "core_conflict": "冲突",
            "arcs": [],
            "constraints": "已设置",
            "starting_state": {"sanity": 50},
        }
        migrated = migrate(v3_data)
        assert migrated == v3_data  # exact equality, no changes

    def test_migrate_preserves_existing_fields(self):
        """Existing non-default values should not be overwritten."""
        v1_data = {
            "version": 1,
            "title": "保留测试",
            "core_conflict": "冲突",
            "arcs": [],
            "constraints": "自定义约束",
        }
        migrated = migrate(v1_data)
        assert migrated["constraints"] == "自定义约束"  # NOT overwritten to ""

    def test_migrate_no_version_defaults_to_v1(self):
        """Missing version field should be treated as v1."""
        data = {
            "title": "无版本",
            "core_conflict": "冲突",
            "arcs": [],
        }
        migrated = migrate(data)
        assert migrated["version"] == 3
        assert migrated["constraints"] == ""
        assert migrated["starting_state"] == {}


class TestTypeAdapter:
    """Tests for TypeAdapter independent validation."""

    def test_adapter_validates_same_as_model(self, sample_campaign_json):
        """TypeAdapter should produce same result as model_validate."""
        from_adapter = campaign_adapter.validate_python(sample_campaign_json)
        from_model = CampaignSchema.model_validate(sample_campaign_json)
        assert from_adapter.title == from_model.title
        assert from_adapter.core_conflict == from_model.core_conflict
        assert from_adapter.version == from_model.version
        assert len(from_adapter.arcs) == len(from_model.arcs)

    def test_adapter_dump_json_roundtrip(self, sample_campaign_json):
        """TypeAdapter dump_json -> validate_json should roundtrip."""
        campaign = campaign_adapter.validate_python(sample_campaign_json)
        dumped = campaign_adapter.dump_json(campaign)
        reloaded = campaign_adapter.validate_json(dumped)
        assert reloaded.title == campaign.title

    def test_adapter_rejects_invalid(self):
        """TypeAdapter should raise ValidationError for bad data."""
        with pytest.raises(ValidationError):
            campaign_adapter.validate_python({"not": "valid"})


class TestJSONSchema:
    """Tests for JSON Schema Draft 2020-12 generation."""

    def test_schema_has_draft_2020_12(self):
        """Generated JSON Schema should be a valid Draft 2020-12 schema object."""
        schema = CampaignSchema.model_json_schema()
        # Pydantic v2 generates Draft 2020-12 compatible schemas
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_schema_required_fields(self):
        """Schema should list title and core_conflict as required."""
        schema = CampaignSchema.model_json_schema()
        assert "title" in schema.get("required", [])
        assert "core_conflict" in schema.get("required", [])

    def test_schema_version_field(self):
        """Schema should include version as an integer property with default 1."""
        schema = CampaignSchema.model_json_schema()
        props = schema["properties"]
        assert "version" in props
        assert props["version"]["type"] == "integer"
        assert props["version"].get("default") == 1

    def test_schema_arcs_is_array(self):
        """Schema should define arcs as an array of ArcSchema."""
        schema = CampaignSchema.model_json_schema()
        assert schema["properties"]["arcs"]["type"] == "array"


class TestDefaultCampaign:
    """Tests for the default_campaign.json sample file."""

    @pytest.fixture
    def default_campaign_path(self):
        from pathlib import Path
        return Path(__file__).parent.parent / "data" / "campaigns" / "default_campaign.json"

    def test_default_campaign_file_exists(self, default_campaign_path):
        """default_campaign.json should exist at expected path."""
        assert default_campaign_path.exists(), (
            f"Expected file at {default_campaign_path}"
        )

    def test_default_campaign_is_valid_json(self, default_campaign_path):
        """default_campaign.json should be valid JSON."""
        data = json.loads(default_campaign_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_default_campaign_validates(self, default_campaign_path):
        """default_campaign.json should pass Pydantic validation."""
        data = json.loads(default_campaign_path.read_text(encoding="utf-8"))
        campaign = CampaignSchema.model_validate(data)
        assert campaign.title == "卡塞尔入学档案"
        assert campaign.version == 3
        assert len(campaign.arcs) == 3

    def test_default_campaign_anchor_access(self, default_campaign_path):
        """Navigation path campaign.arcs[0].sessions[0].anchor_events should work."""
        data = json.loads(default_campaign_path.read_text(encoding="utf-8"))
        campaign = CampaignSchema.model_validate(data)
        anchors = campaign.arcs[0].sessions[0].anchor_events
        assert len(anchors) >= 1
        assert anchors[0].priority == 1

    def test_default_campaign_all_anchors_have_ids(self, default_campaign_path):
        """Every anchor event should have a non-empty id and valid priority."""
        data = json.loads(default_campaign_path.read_text(encoding="utf-8"))
        campaign = CampaignSchema.model_validate(data)
        for arc in campaign.arcs:
            for session in arc.sessions:
                for anchor in session.anchor_events:
                    assert anchor.id, f"Empty anchor id in {session.name}"
                    assert anchor.priority >= 1 and anchor.priority <= 5
