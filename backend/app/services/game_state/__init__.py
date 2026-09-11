"""GameStateManager package — session state persistence and transitions.

Modules:
  - defaults:      default state template, limits and defensive caps
  - manager:       GameStateManager core (sessions, apply_output, caps)
  - normalization: memory-entry normalization and name-keyed merging
  - inference:     world-fact inference, key events, player status
"""

from app.services.game_state.defaults import (
    MAX_ITEMS,
    MAX_NPCS,
    MAX_QUESTS,
    MAX_WORLD_FACTS,
    RECENT_EVENT_LIMIT,
    RECENT_EVENT_MAX_CHARS,
    SANITY_RECOVERY_PER_TURN,
    STALE_TURN_THRESHOLD,
    default_state,
)
from app.services.game_state.manager import GameStateManager

__all__ = [
    "GameStateManager",
    "default_state",
    "MAX_ITEMS",
    "MAX_NPCS",
    "MAX_QUESTS",
    "MAX_WORLD_FACTS",
    "RECENT_EVENT_LIMIT",
    "RECENT_EVENT_MAX_CHARS",
    "SANITY_RECOVERY_PER_TURN",
    "STALE_TURN_THRESHOLD",
]
