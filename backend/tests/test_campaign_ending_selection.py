"""Deterministic ending selection and finale prerequisites."""

import json
from pathlib import Path

import pytest

from app.schemas.campaign import CampaignProgress, campaign_adapter, migrate
from app.services.agents.examiner import ExaminerAgent
from app.services.campaign_endings import select_ending
from app.services.game_state.manager import GameStateManager


def _campaign(filename: str):
    path = Path(__file__).parents[1] / "data" / "campaigns" / filename
    return campaign_adapter.validate_python(migrate(json.loads(path.read_text(encoding="utf-8"))))


def test_explicit_player_choice_selects_one_ending():
    campaign = _campaign("default_campaign.json")
    progress = CampaignProgress(campaign_id="test", arc_index=2, session_index=1)

    route = select_ending(
        campaign, progress, {
            "health": 100,
            "sanity": 80,
            "items": [{"name": "黄铜钥匙", "status": "owned"}],
        },
        "我拒绝力量，选择继承封印并让其他新生离开。",
    )

    assert route is not None
    assert route.id == "ending-watchman"


@pytest.mark.parametrize("action", [
    "我不想成为守钟人",
    "我拒绝继承封印",
    "我没有继承封印",
])
def test_negated_choice_does_not_select_ending(action):
    campaign = _campaign("default_campaign.json")
    progress = CampaignProgress(campaign_id="test", arc_index=2, session_index=1)
    state = {
        "health": 100,
        "sanity": 80,
        "items": [{"name": "黄铜钥匙", "status": "owned"}],
    }

    assert select_ending(campaign, progress, state, action) is None


def test_ambiguous_positive_choices_require_clarification():
    campaign = _campaign("default_campaign.json")
    progress = CampaignProgress(campaign_id="test", arc_index=2, session_index=1)
    state = {
        "health": 100,
        "sanity": 80,
        "items": [{"name": "黄铜钥匙", "status": "owned"}],
    }

    route = select_ending(
        campaign,
        progress,
        state,
        "我要继承封印，同时控制筛选核心。",
    )

    assert route is None


def test_hypothetical_phrase_does_not_count_as_explicit_choice():
    campaign = _campaign("default_campaign.json")
    progress = CampaignProgress(campaign_id="test", arc_index=2, session_index=1)
    state = {
        "health": 100,
        "sanity": 80,
        "items": [{"name": "黄铜钥匙", "status": "owned"}],
    }

    route = select_ending(
        campaign,
        progress,
        state,
        "如果继承封印，其他人会安全吗？",
    )

    assert route is None


def test_machine_required_item_blocks_unavailable_route():
    campaign = _campaign("default_campaign.json")
    progress = CampaignProgress(campaign_id="test", arc_index=2, session_index=1)

    route = select_ending(
        campaign,
        progress,
        {"health": 100, "sanity": 80, "items": []},
        "继承封印",
    )

    assert route is None


def test_true_ending_requires_configured_story_anchors():
    campaign = _campaign("default_campaign.json")
    state = {
        "health": 100,
        "sanity": 80,
        "items": [{"name": "黄铜钥匙", "status": "owned"}],
    }
    progress = CampaignProgress(campaign_id="test", arc_index=2, session_index=1)

    assert select_ending(campaign, progress, state, "共同关闭封印") is None

    progress.revealed_anchors = ["anchor-seal-truth", "anchor-impostor-truth"]
    route = select_ending(campaign, progress, state, "共同关闭封印")

    assert route is not None
    assert route.id == "ending-dawn-conspiracy"


def test_non_final_session_cannot_trigger_ending():
    campaign = _campaign("default_campaign.json")
    progress = CampaignProgress(campaign_id="test", arc_index=0, session_index=0)
    assert select_ending(campaign, progress, {"health": 0}, "继承封印") is None


def test_exhausted_stats_select_bad_ending():
    campaign = _campaign("龙族Ⅱ_悼亡者之瞳_campaign.json")
    progress = CampaignProgress(campaign_id="test", arc_index=3, session_index=1)
    route = select_ending(campaign, progress, {"health": 0, "sanity": 50}, "继续")
    assert route is not None
    assert route.id == "ending-shiva-dance"


def test_finale_entry_items_are_owned():
    campaign = _campaign("龙族Ⅲ_黑月之潮_campaign.json")
    state = GameStateManager.merge_entry_state(
        GameStateManager.__new__(GameStateManager),
        {
            "health": 100, "sanity": 80, "turn": 0, "current_location": "",
            "items": [], "npcs": [], "quests": [], "world_facts": [],
            "recent_events": [], "player_status": {},
        },
        campaign, len(campaign.arcs) - 1, len(campaign.arcs[-1].sessions) - 1,
        initialize=True,
    )
    assert state["items"]
    assert {item["status"] for item in state["items"]} == {"owned"}


@pytest.mark.asyncio
async def test_npc_in_same_scene_subarea_is_reachable():
    ruling = await ExaminerAgent().examine(
        "我询问上杉绘梨衣是否还能听见我。",
        {
            "current_location": "红井白王复活仪式场",
            "items": [],
            "npcs": [{
                "name": "上杉绘梨衣", "status": "present",
                "current_location": "红井仪式核心",
            }],
        },
    )
    assert ruling.permissibility.value != "blocked"


@pytest.mark.asyncio
async def test_npc_in_different_academy_location_is_not_reachable():
    ruling = await ExaminerAgent().examine(
        "我询问诺诺是否找到线索。",
        {
            "current_location": "学院外广场",
            "items": [],
            "npcs": [{
                "name": "诺诺",
                "status": "present",
                "current_location": "学院宿舍",
            }],
        },
    )

    assert ruling.permissibility.value == "blocked"
