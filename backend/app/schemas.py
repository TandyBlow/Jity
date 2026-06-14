from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class DialogueLine(BaseModel):
    speaker: str = ""
    text: str = ""


class ItemMemory(BaseModel):
    name: str
    status: str = "owned"
    description: str = ""
    location: str = ""
    notes: str = ""


class NPCMemory(BaseModel):
    name: str
    status: str = "present"
    relationship: str = ""
    current_location: str = ""
    description: str = ""
    notes: str = ""


class QuestMemory(BaseModel):
    name: str
    status: str = "active"
    description: str = ""
    objective: str = ""
    notes: str = ""


class WorldFactMemory(BaseModel):
    name: str
    status: str = "known"
    description: str = ""
    source: str = ""
    notes: str = ""


class PlayerStatus(BaseModel):
    condition: str = ""
    danger_level: str = ""
    current_goal: str = ""
    notes: str = ""


class MemoryUpdates(BaseModel):
    current_location: str = ""
    items_upserted: list[ItemMemory] = Field(default_factory=list)
    items_removed: list[ItemMemory] = Field(default_factory=list)
    npcs_upserted: list[NPCMemory] = Field(default_factory=list)
    quests_upserted: list[QuestMemory] = Field(default_factory=list)
    world_facts_upserted: list[WorldFactMemory] = Field(default_factory=list)
    player_status_patch: PlayerStatus = Field(default_factory=PlayerStatus)
    key_event: str = ""


class StoryOutput(BaseModel):
    narration: str
    dialogue: list[DialogueLine] = Field(default_factory=list)
    scene_prompt: str = ""
    sanity_delta: int = 0
    health_delta: int = 0
    options: list[str] = Field(default_factory=list)
    game_over: bool = False
    game_over_reason: str = ""
    current_location: str = ""
    items_gained: list[dict[str, Any]] = Field(default_factory=list)
    items_lost: list[dict[str, Any]] = Field(default_factory=list)
    npcs_encountered: list[dict[str, Any]] = Field(default_factory=list)
    quests_updated: list[dict[str, Any]] = Field(default_factory=list)
    memory_updates: MemoryUpdates = Field(default_factory=MemoryUpdates)


class CreateSessionRequest(BaseModel):
    game_name: str = "卡塞尔入学档案"
    model: Optional[str] = None


class GenerateRequest(BaseModel):
    player_action: str
    model: Optional[str] = None
    style: str = ""
    constraints: str = ""


class SessionResponse(BaseModel):
    session_id: str
    game_name: str
    model: str
    state: dict[str, Any]


class RetrievedChunk(BaseModel):
    id: str
    title: str
    source_type: str
    content: str
    score: float


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageResponse]


class GenerateResponse(BaseModel):
    session_id: str
    state: dict[str, Any]
    output: StoryOutput
    retrieved_chunks: list[RetrievedChunk]
    model_output_id: Optional[int] = None
    used_model: str
    source: Literal["scripted", "llm"]
