"""Jity schemas package.

Re-exports all models from game.py, campaign.py, and agent_io.py for
backward compatibility.
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

from app.schemas.agent_io import (
    ActionPermissibility,
    ActionRuling,
    DirectorInstruction,
    EpisodeSummary,
    HallucinationFinding,
    HallucinationType,
    ItemContinuityCheck,
    ItemState,
    ItemStateRecord,
    MemoryRecord,
    PersonaKey,
    PersonaSketch,
    PersonaSnapshot,
    PersonaValue,
    RedirectionStrategy,
    TriggeredRule,
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
    # agent_io
    "ActionPermissibility",
    "ActionRuling",
    "DirectorInstruction",
    "EpisodeSummary",
    "HallucinationFinding",
    "HallucinationType",
    "ItemContinuityCheck",
    "ItemState",
    "ItemStateRecord",
    "MemoryRecord",
    "PersonaKey",
    "PersonaSketch",
    "PersonaSnapshot",
    "PersonaValue",
    "RedirectionStrategy",
    "TriggeredRule",
]
