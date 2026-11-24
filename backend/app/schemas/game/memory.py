"""Structured memory models extracted from each story turn."""

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
