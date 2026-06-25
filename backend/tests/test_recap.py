"""Tests for session recap generation and storage."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.prompt_builder import PromptBuilder, RECAP_SYSTEM_PROMPT


class TestRecapPrompt:
    """Tests for PromptBuilder.build_recap()."""

    def test_build_recap_includes_system_prompt(self):
        """build_recap should start with RECAP_SYSTEM_PROMPT text."""
        messages = [
            {"role": "user", "content": "我观察四周"},
            {"role": "assistant", "content": "你看到大厅..."},
        ]
        result = PromptBuilder.build_recap(messages)
        assert "TRPG" in result
        assert "前情提要" in result
        assert "对话历史" in result

    def test_build_recap_formats_messages(self):
        """build_recap should format messages with role labels."""
        messages = [
            {"role": "user", "content": "玩家行动"},
            {"role": "assistant", "content": "主持人回应"},
        ]
        result = PromptBuilder.build_recap(messages)
        assert "[玩家]:" in result
        assert "[主持人]:" in result
        assert "玩家行动" in result
        assert "主持人回应" in result

    def test_build_recap_truncates_long_messages(self):
        """build_recap should truncate messages over 1500 chars."""
        long_content = "A" * 2000
        messages = [{"role": "user", "content": long_content}]
        result = PromptBuilder.build_recap(messages)
        assert "..." in result

    def test_build_recap_empty_messages(self):
        """build_recap should handle empty message list."""
        result = PromptBuilder.build_recap([])
        assert "对话历史" in result


class TestDBRecapColumns:
    """Tests for recap column writes in campaign_progress."""

    def test_write_progress_with_recap(self):
        """write_campaign_progress should accept and persist recap fields."""
        from app.database import Database
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.write_campaign_progress(
                "test-recap", 0, 0, 0, "idle",
                recap_compressed="前情提要：测试摘要",
                recap_full="完整摘要内容...",
            )
            row = db.read_campaign_progress("test-recap")
            assert row is not None
            assert "前情提要" in row["recap_compressed"]
            assert "完整摘要" in row["recap_full"]

    def test_read_nonexistent_recap_returns_empty(self):
        """Non-existent recap should return empty string."""
        from app.database import Database
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(Path(tmpdir) / "test.db")
            db.write_campaign_progress("test-recap2", 0, 0, 0, "idle")
            row = db.read_campaign_progress("test-recap2")
            assert row["recap_compressed"] == ""
            assert row["recap_full"] == ""


class TestCampaignManagerRecap:
    """Tests for CampaignManager recap methods."""

    def test_is_first_turn_of_session(self):
        """_is_first_turn_of_session should return True for turn 0."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        # FSM starts at idle; at turn 0 for session_active
        mgr.fsm.machine.set_state("active/session_active")
        assert mgr._is_first_turn_of_session(0) is True

    def test_is_not_first_turn(self):
        """_is_first_turn_of_session should return False for turn > 0."""
        mgr = CampaignManager(db=MagicMock(), campaigns_dir=Path("/tmp"), scripted_story=MagicMock())
        mgr.fsm.machine.set_state("active/session_active")
        assert mgr._is_first_turn_of_session(5) is False

    def test_inject_context_includes_recap(self, tmp_path):
        """inject_context should include 前情提要 when recap exists and turn is 0."""
        campaign_data = {
            "version": 3, "title": "Recap测试", "core_conflict": "冲突",
            "arcs": [{"name": "A", "goal": "", "sessions": [{"name": "S", "opening_scene": "", "anchor_events": []}]}],
        }
        p = tmp_path / "test.json"
        p.write_text(json.dumps(campaign_data, ensure_ascii=False), encoding="utf-8")

        db = MagicMock()
        db.read_campaign_progress.return_value = {
            "campaign_id": "Recap测试", "arc_index": 0, "session_index": 0,
            "turn_in_session": 0, "fsm_state": "active/session_active",
            "revealed_anchors": "[]", "completed_arcs": "[]",
            "recap_compressed": "前情提要：测试摘要内容", "recap_full": "",
        }
        mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
        mgr.load(p)
        mgr.fsm.machine.set_state("active/session_active")
        result = mgr.inject_context({}, 0)
        assert "前情提要" in result


from app.services.campaign_manager import CampaignManager
