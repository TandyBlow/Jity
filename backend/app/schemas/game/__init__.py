"""Game-related Pydantic schemas package.

Migrated from schemas.py. Campaign-related schemas are in campaign.py.

Modules:
  - em_dash:            em dash replacement helper
  - memory:             DialogueLine / ItemMemory / NPCMemory / ... models
  - story_output:       StoryOutput with em dash sanitization
  - requests_responses: API request and response models
"""

from app.schemas.game.em_dash import replace_em_dash
from app.schemas.game.memory import (
    DialogueLine,
    ItemMemory,
    MemoryUpdates,
    NPCMemory,
    PlayerStatus,
    QuestMemory,
    WorldFactMemory,
)
from app.schemas.game.requests_responses import (
    CreateSessionRequest,
    GenerateRequest,
    GenerateResponse,
    MessageResponse,
    RetrievedChunk,
    SessionHistoryResponse,
    SessionResponse,
)
from app.schemas.game.story_output import StoryOutput

__all__ = [
    "replace_em_dash",
    "DialogueLine",
    "ItemMemory",
    "MemoryUpdates",
    "NPCMemory",
    "PlayerStatus",
    "QuestMemory",
    "WorldFactMemory",
    "StoryOutput",
    "CreateSessionRequest",
    "GenerateRequest",
    "SessionResponse",
    "RetrievedChunk",
    "MessageResponse",
    "SessionHistoryResponse",
    "GenerateResponse",
]
