"""Tests for schema validation and compatibility."""

from app.schemas import (
    CampaignSchema,
    CreateSessionRequest,
    GenerateRequest,
    GenerateResponse,
    StoryOutput,
)


class TestGameSchemas:
    """Existing game schemas should still work after package split."""

    def test_create_session_defaults(self):
        """CreateSessionRequest should have default game_name."""
        req = CreateSessionRequest()
        assert req.game_name == "卡塞尔入学档案"

    def test_generate_request_required_fields(self):
        """GenerateRequest requires player_action."""
        req = GenerateRequest(player_action="观察四周")
        assert req.player_action == "观察四周"
        assert req.style == ""
        assert req.constraints == ""

    def test_story_output_minimal(self):
        """StoryOutput can be constructed with just narration."""
        output = StoryOutput(narration="你看到了红色的标记。")
        assert output.narration == "你看到了红色的标记。"
        assert output.sanity_delta == 0
        assert output.health_delta == 0
        assert output.game_over is False
        assert output.dialogue == []


class TestCampaignSchemas:
    """Campaign schemas should validate correctly."""

    def test_campaign_minimal(self):
        """Minimal campaign with title + core_conflict + arcs should parse."""
        campaign = CampaignSchema.model_validate({
            "version": 1,
            "title": "测试",
            "core_conflict": "冲突",
            "arcs": [],
        })
        assert campaign.title == "测试"

    def test_campaign_with_constraints(self):
        """Campaign should accept constraints string."""
        campaign = CampaignSchema.model_validate({
            "version": 1,
            "title": "有约束的战役",
            "core_conflict": "冲突",
            "arcs": [],
            "constraints": "NPC不能死亡",
        })
        assert campaign.constraints == "NPC不能死亡"

    def test_campaign_starting_state(self):
        """Campaign should accept starting_state dict."""
        campaign = CampaignSchema.model_validate({
            "version": 1,
            "title": "初始状态战役",
            "core_conflict": "冲突",
            "arcs": [],
            "starting_state": {"sanity": 50, "current_location": "钟楼"},
        })
        assert campaign.starting_state["sanity"] == 50
