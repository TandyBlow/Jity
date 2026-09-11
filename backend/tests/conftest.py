"""Shared fixtures for Jity backend tests."""

import sys
from pathlib import Path

import pytest

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_game_state() -> dict:
    """Minimal valid game state dict."""
    return {
        "sanity": 80,
        "health": 90,
        "turn": 3,
        "current_location": "卡塞尔学院报到大厅",
        "items": [],
        "npcs": [],
        "quests": [],
        "world_facts": [],
        "player_status": {
            "condition": "正常",
            "danger_level": "low",
            "current_goal": "找到诺诺",
            "notes": "",
        },
        "recent_events": ["进入了报到大厅", "看到了红色头发的女生"],
    }


@pytest.fixture
def sample_campaign_json() -> dict:
    """Minimal valid campaign dict matching campaign.json schema."""
    return {
        "version": 1,
        "title": "测试战役",
        "core_conflict": "一个古老的邪恶在校园苏醒",
        "arcs": [
            {
                "name": "序幕：疑云",
                "goal": "调查校园中的异常现象",
                "sessions": [
                    {
                        "name": "初入校园",
                        "opening_scene": "你站在卡塞尔学院的大门前...",
                        "anchor_events": [
                            {
                                "id": "anchor-1",
                                "name": "发现红色标记",
                                "description": "玩家注意到墙上的红色神秘符号",
                                "priority": 1,
                                "trigger_conditions": {
                                    "location": "报到大厅",
                                    "npc_present": None,
                                    "item_held": None,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture
def sample_prompt_input(sample_game_state: dict):
    """PromptInput with minimal valid fields."""
    from app.services.prompt_builder import PromptInput

    return PromptInput(
        player_action="观察周围环境",
        game_state=sample_game_state,
        style="horror",
    )
