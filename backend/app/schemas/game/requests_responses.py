"""Request and response API models."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.game.story_output import StoryOutput


# ── Request models ──

class CreateSessionRequest(BaseModel):
    game_name: str = "卡塞尔入学档案"
    model: Optional[str] = None
    campaign_filename: Optional[str] = None
    arc_index: int = 0
    session_index: int = 0
    slot_name: str = "default"


class GenerateRequest(BaseModel):
    player_action: str
    model: Optional[str] = None
    style: str = ""
    constraints: str = ""
    slot_name: str = ""


# ── Response models ──

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
    keywords: list[str] = Field(default_factory=list)
    importance: int = 3


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
    source: Literal["scripted", "llm", "examiner_blocked"]
