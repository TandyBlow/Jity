"""Jity schemas package.

Re-exports all models from game.py and campaign.py for backward compatibility.
"""
from app.schemas.game import (
    CreateSessionRequest,
    DialogueLine,
    GenerateRequest,
    GenerateResponse,
    ItemMemory,
    MemoryUpdates,
    MessageResponse,
    NPCMemory,
    PlayerStatus,
    QuestMemory,
    RetrievedChunk,
    SessionHistoryResponse,
    SessionResponse,
    StoryOutput,
    WorldFactMemory,
)

from app.schemas.campaign import (
    AnchorEvent,
    AnchorTriggerConditions,
    ArcSchema,
    CampaignProgress,
    CampaignSchema,
    HealthGuidanceHint,
    HealthMetrics,
    RecapData,
    SessionSchema,
)

__all__ = [
    # game
    "CreateSessionRequest",
    "DialogueLine",
    "GenerateRequest",
    "GenerateResponse",
    "ItemMemory",
    "MemoryUpdates",
    "MessageResponse",
    "NPCMemory",
    "PlayerStatus",
    "QuestMemory",
    "RetrievedChunk",
    "SessionHistoryResponse",
    "SessionResponse",
    "StoryOutput",
    "WorldFactMemory",
    # campaign
    "AnchorEvent",
    "AnchorTriggerConditions",
    "ArcSchema",
    "CampaignProgress",
    "CampaignSchema",
    "HealthGuidanceHint",
    "HealthMetrics",
    "RecapData",
    "SessionSchema",
]
