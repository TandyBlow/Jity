"""Regression tests for campaign runtime wiring."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.database import Database
from app.schemas.campaign import CampaignProgress
from app.services.campaign_manager import CampaignManager
from app.services.context_strategy import SimpleTruncationStrategy


def _campaign_file(tmp_path: Path, *, anchors: list[dict] | None = None, sessions: int = 1) -> Path:
    session_defs = [
        {
            "name": f"S{i + 1}",
            "opening_scene": "",
            "anchor_events": anchors or [],
        }
        for i in range(sessions)
    ]
    campaign = {
        "version": 3,
        "title": "Runtime测试",
        "core_conflict": "冲突",
        "arcs": [{"name": "A1", "goal": "推进", "sessions": session_defs}],
    }
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(campaign, ensure_ascii=False), encoding="utf-8")
    return path


def _state() -> dict:
    return {
        "current_location": "大厅",
        "npcs": [],
        "items": [],
        "sanity": 80,
        "health": 100,
        "turn": 0,
        "player_status": {},
        "recent_events": [],
        "quests": [],
        "world_facts": [],
    }


def test_campaign_progress_tracks_turn_in_session():
    progress = CampaignProgress(campaign_id="s1")
    assert progress.turn_in_session == 0
    progress.turn_in_session += 1
    assert progress.turn_in_session == 1


def test_advance_turn_persists_campaign_local_turn(tmp_path):
    db = Database(tmp_path / "test.db")
    mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
    mgr.load(_campaign_file(tmp_path), campaign_id="session-1")

    assert mgr.advance_turn() == 1

    row = db.read_campaign_progress("session-1")
    assert row is not None
    assert row["turn_in_session"] == 1


@pytest.mark.asyncio
async def test_advance_session_resets_turn_counter(tmp_path):
    db = Database(tmp_path / "test.db")
    mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
    mgr.load(_campaign_file(tmp_path, sessions=2), campaign_id="session-1")
    mgr.progress.turn_in_session = 30
    mgr.save_progress()

    await mgr.advance_session()

    row = db.read_campaign_progress("session-1")
    assert row is not None
    assert row["session_index"] == 1
    assert row["turn_in_session"] == 0


def test_injected_anchor_is_committed_after_successful_turn(tmp_path):
    db = Database(tmp_path / "test.db")
    anchor = {
        "id": "a1",
        "name": "揭示门禁",
        "description": "大厅门禁亮起异常纹路",
        "priority": 1,
        "trigger_conditions": {"location": "大厅"},
    }
    mgr = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
    mgr.load(_campaign_file(tmp_path, anchors=[anchor]), campaign_id="session-1")

    context = mgr.inject_context(_state(), 0)
    triggered = mgr.commit_pending_anchors()

    row = db.read_campaign_progress("session-1")
    assert "揭示门禁" in context
    assert triggered == ["a1"]
    assert row is not None
    assert json.loads(row["revealed_anchors"]) == ["a1"]


def test_progress_slots_are_isolated(tmp_path):
    db = Database(tmp_path / "test.db")
    campaign_path = _campaign_file(tmp_path)

    first = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
    first.load(campaign_path, campaign_id="session-1", slot_name="default")
    first.advance_turn()

    second = CampaignManager(db=db, campaigns_dir=tmp_path, scripted_story=MagicMock())
    second.load(campaign_path, campaign_id="session-1", slot_name="branch")

    assert db.read_campaign_progress("session-1", "default")["turn_in_session"] == 1
    assert db.read_campaign_progress("session-1", "branch")["turn_in_session"] == 0


def test_prompt_sections_truncate_low_priority_context(tmp_path):
    mgr = CampaignManager(db=MagicMock(), campaigns_dir=tmp_path, scripted_story=MagicMock())
    mgr._strategy = SimpleTruncationStrategy(budget_limit=20)
    sections = {
        "rag_chunks": "RAG " + ("noise " * 200),
        "campaign_context": "campaign " + ("hint " * 200),
        "messages": "history " + ("old " * 200),
        "system_prompt": "system rules",
        "player_action": "player acts",
    }

    prompt, _, truncated = mgr.truncate_prompt_sections(sections)

    assert truncated is True
    assert "system rules" in prompt
    assert "player acts" in prompt
    assert "noise" not in prompt
