"""Default game state, tunable limits and defensive caps."""

from typing import Any

RECENT_EVENT_LIMIT = 8
RECENT_EVENT_MAX_CHARS = 120
SANITY_RECOVERY_PER_TURN = 1

# State bloat prevention (HARD-03): defensive caps to prevent
# unbounded list growth over 270-turn campaigns
MAX_ITEMS = 20
MAX_NPCS = 15
MAX_QUESTS = 10
MAX_WORLD_FACTS = 15
STALE_TURN_THRESHOLD = 30  # prune entries unchanged for 30+ turns


def default_state() -> dict[str, Any]:
    return {
        "sanity": 80,
        "health": 100,
        "turn": 0,
        "current_location": "卡塞尔学院报到处大厅",
        "items": [],
        "npcs": [
            {
                "name": "诺诺",
                "status": "present",
                "relationship": "接应者",
                "current_location": "卡塞尔学院报到处大厅",
                "description": "红发学姐，受古德里安教授委托接路明非报到。",
                "notes": "语气戏谑，知道学院并不普通。",
            }
        ],
        "quests": [],
        "recent_events": ["路明非拖着旧行李箱抵达卡塞尔学院报到处大厅，诺诺前来接应。"],
        "world_facts": [
            {
                "name": "卡塞尔学院异常报到流程",
                "status": "suspected",
                "description": "学院报到大厅有执行部学生、投影新生名单和异常门禁机制。",
                "source": "opening_scene",
                "notes": "这里不像普通大学。",
            }
        ],
        "player_status": {
            "condition": "新生报到中",
            "danger_level": "medium",
            "current_goal": "完成卡塞尔学院入学报到",
            "notes": "刚抵达学院，对规则和风险了解有限。",
        },
    }
