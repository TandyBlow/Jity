"""Tests for AI campaign generation."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.campaign_generator import CampaignGenerator, CampaignGenerationError
from app.services.prompt_builder import build_campaign_gen, CAMPAIGN_GEN_PROMPT


class TestCampaignGenPrompt:
    """Tests for campaign generation prompt building."""

    def test_build_campaign_gen_includes_prompt(self):
        """build_campaign_gen should include user prompt in output."""
        result = build_campaign_gen("1920s上海侦探")
        assert "1920s上海侦探" in result
        assert "TRPG" in result

    def test_prompt_has_schema_instructions(self):
        """The campaign gen prompt should describe the expected JSON schema."""
        assert "version" in CAMPAIGN_GEN_PROMPT
        assert "arcs" in CAMPAIGN_GEN_PROMPT
        assert "anchor_events" in CAMPAIGN_GEN_PROMPT


class TestCampaignGenerator:
    """Tests for CampaignGenerator service."""

    def test_ensure_minimal_structure(self):
        """_ensure_minimal_structure should fill missing top-level fields."""
        raw = {"title": "测试"}
        result = CampaignGenerator._ensure_minimal_structure(raw)
        assert result["version"] == 4
        assert result["title"] == "测试"
        assert result["core_conflict"] == "未知冲突"
        assert result["arcs"] == []

    def test_ensure_preserves_existing(self):
        """_ensure_minimal_structure should not overwrite existing fields."""
        raw = {"title": "原创", "core_conflict": "自定义冲突", "arcs": [{"name": "弧"}]}
        result = CampaignGenerator._ensure_minimal_structure(raw)
        assert result["core_conflict"] == "自定义冲突"

    def test_ensure_migrates_version(self):
        """_ensure_minimal_structure should migrate v1 to v3."""
        raw = {"version": 1, "title": "V1", "core_conflict": "冲突"}
        result = CampaignGenerator._ensure_minimal_structure(raw)
        assert result["version"] == 4

    def test_save_writes_file(self, tmp_path):
        """save() should write campaign JSON to output directory."""
        gen = CampaignGenerator(
            llm_client=MagicMock(),
            prompt_builder=MagicMock(),
            db=MagicMock(),
            output_dir=tmp_path,
        )
        data = {"version": 3, "title": "测试战役", "core_conflict": "冲突", "arcs": []}
        path = gen.save(data, filename="test_campaign.json")
        assert path.exists()
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["title"] == "测试战役"
