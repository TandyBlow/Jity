from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class DialogueLine(BaseModel):
    speaker: str = ""
    text: str = ""


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


class CreateSessionRequest(BaseModel):
    game_name: str = "卡塞尔入学档案"
    model: Optional[str] = None


class GenerateRequest(BaseModel):
    player_action: str
    model: Optional[str] = None
    narrative_profile: str = "default"
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


class GenerateResponse(BaseModel):
    session_id: str
    state: dict[str, Any]
    output: StoryOutput
    retrieved_chunks: list[RetrievedChunk]
    model_output_id: Optional[int] = None
    used_model: str
