"""Game-related Pydantic schemas — request/response, state memory, story output.

Migrated from schemas.py. Campaign-related schemas are in campaign.py.
"""

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# U+2014 em dash — the character we strip from all player-facing text
_EM_DASH = "—"


def strip_em_dash(text: str) -> str:
    """Remove all em dashes (—, U+2014) from *text*."""
    if not text:
        return text
    return text.replace(_EM_DASH, "")


# ── Memory models ──

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


# ── Core output ──

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
    npc_relations_delta: list[dict[str, Any]] | None = None

    def strip_em_dashes(self) -> "StoryOutput":
        """Return a new StoryOutput with all em dashes removed from every text field."""
        self.narration = strip_em_dash(self.narration)
        self.scene_prompt = strip_em_dash(self.scene_prompt)
        self.game_over_reason = strip_em_dash(self.game_over_reason)
        self.current_location = strip_em_dash(self.current_location)
        self.options = [strip_em_dash(o) for o in self.options]
        self.dialogue = [
            DialogueLine(speaker=strip_em_dash(d.speaker), text=strip_em_dash(d.text))
            for d in self.dialogue
        ]
        # Named-object lists: strip any string value
        self.items_gained = self._strip_named_list(self.items_gained)
        self.items_lost = self._strip_named_list(self.items_lost)
        self.npcs_encountered = self._strip_named_list(self.npcs_encountered)
        self.quests_updated = self._strip_named_list(self.quests_updated)
        # Memory updates
        mu = self.memory_updates
        mu.current_location = strip_em_dash(mu.current_location)
        mu.key_event = strip_em_dash(mu.key_event)
        mu.items_upserted = [self._strip_item_memory(i) for i in mu.items_upserted]
        mu.items_removed = [self._strip_item_memory(i) for i in mu.items_removed]
        mu.npcs_upserted = [self._strip_npc_memory(n) for n in mu.npcs_upserted]
        mu.quests_upserted = [self._strip_quest_memory(q) for q in mu.quests_upserted]
        mu.world_facts_upserted = [self._strip_world_fact_memory(w) for w in mu.world_facts_upserted]
        mu.player_status_patch = PlayerStatus(
            condition=strip_em_dash(mu.player_status_patch.condition),
            danger_level=strip_em_dash(mu.player_status_patch.danger_level),
            current_goal=strip_em_dash(mu.player_status_patch.current_goal),
            notes=strip_em_dash(mu.player_status_patch.notes),
        )
        # npc_relations_delta
        if self.npc_relations_delta is not None:
            self.npc_relations_delta = self._strip_named_list(self.npc_relations_delta)
        return self

    @staticmethod
    def _strip_item_memory(item: ItemMemory) -> ItemMemory:
        item.name = strip_em_dash(item.name)
        item.status = strip_em_dash(item.status)
        item.description = strip_em_dash(item.description)
        item.location = strip_em_dash(item.location)
        item.notes = strip_em_dash(item.notes)
        return item

    @staticmethod
    def _strip_npc_memory(npc: NPCMemory) -> NPCMemory:
        npc.name = strip_em_dash(npc.name)
        npc.status = strip_em_dash(npc.status)
        npc.relationship = strip_em_dash(npc.relationship)
        npc.current_location = strip_em_dash(npc.current_location)
        npc.description = strip_em_dash(npc.description)
        npc.notes = strip_em_dash(npc.notes)
        return npc

    @staticmethod
    def _strip_quest_memory(quest: QuestMemory) -> QuestMemory:
        quest.name = strip_em_dash(quest.name)
        quest.status = strip_em_dash(quest.status)
        quest.description = strip_em_dash(quest.description)
        quest.objective = strip_em_dash(quest.objective)
        quest.notes = strip_em_dash(quest.notes)
        return quest

    @staticmethod
    def _strip_world_fact_memory(fact: WorldFactMemory) -> WorldFactMemory:
        fact.name = strip_em_dash(fact.name)
        fact.status = strip_em_dash(fact.status)
        fact.description = strip_em_dash(fact.description)
        fact.source = strip_em_dash(fact.source)
        fact.notes = strip_em_dash(fact.notes)
        return fact

    @staticmethod
    def _strip_named_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for item in items:
            for key, value in list(item.items()):
                if isinstance(value, str):
                    item[key] = strip_em_dash(value)
        return items


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
