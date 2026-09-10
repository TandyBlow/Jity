"""StoryOutput — the per-turn LLM payload with em dash sanitization."""

from typing import Any

from pydantic import BaseModel, Field

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

    def replace_em_dashes(self) -> "StoryOutput":
        """Return a new StoryOutput with all em dashes replaced by Chinese periods."""
        self.narration = replace_em_dash(self.narration)
        self.scene_prompt = replace_em_dash(self.scene_prompt)
        self.game_over_reason = replace_em_dash(self.game_over_reason)
        self.current_location = replace_em_dash(self.current_location)
        self.options = [replace_em_dash(o) for o in self.options]
        self.dialogue = [
            DialogueLine(speaker=replace_em_dash(d.speaker), text=replace_em_dash(d.text))
            for d in self.dialogue
        ]
        # Named-object lists
        self.items_gained = self._replace_in_named_list(self.items_gained)
        self.items_lost = self._replace_in_named_list(self.items_lost)
        self.npcs_encountered = self._replace_in_named_list(self.npcs_encountered)
        self.quests_updated = self._replace_in_named_list(self.quests_updated)
        # Memory updates
        mu = self.memory_updates
        mu.current_location = replace_em_dash(mu.current_location)
        mu.key_event = replace_em_dash(mu.key_event)
        mu.items_upserted = [self._replace_item_memory(i) for i in mu.items_upserted]
        mu.items_removed = [self._replace_item_memory(i) for i in mu.items_removed]
        mu.npcs_upserted = [self._replace_npc_memory(n) for n in mu.npcs_upserted]
        mu.quests_upserted = [self._replace_quest_memory(q) for q in mu.quests_upserted]
        mu.world_facts_upserted = [self._replace_world_fact_memory(w) for w in mu.world_facts_upserted]
        mu.player_status_patch = PlayerStatus(
            condition=replace_em_dash(mu.player_status_patch.condition),
            danger_level=replace_em_dash(mu.player_status_patch.danger_level),
            current_goal=replace_em_dash(mu.player_status_patch.current_goal),
            notes=replace_em_dash(mu.player_status_patch.notes),
        )
        if self.npc_relations_delta is not None:
            self.npc_relations_delta = self._replace_in_named_list(self.npc_relations_delta)
        return self

    @staticmethod
    def _replace_item_memory(item: ItemMemory) -> ItemMemory:
        item.name = replace_em_dash(item.name)
        item.status = replace_em_dash(item.status)
        item.description = replace_em_dash(item.description)
        item.location = replace_em_dash(item.location)
        item.notes = replace_em_dash(item.notes)
        return item

    @staticmethod
    def _replace_npc_memory(npc: NPCMemory) -> NPCMemory:
        npc.name = replace_em_dash(npc.name)
        npc.status = replace_em_dash(npc.status)
        npc.relationship = replace_em_dash(npc.relationship)
        npc.current_location = replace_em_dash(npc.current_location)
        npc.description = replace_em_dash(npc.description)
        npc.notes = replace_em_dash(npc.notes)
        return npc

    @staticmethod
    def _replace_quest_memory(quest: QuestMemory) -> QuestMemory:
        quest.name = replace_em_dash(quest.name)
        quest.status = replace_em_dash(quest.status)
        quest.description = replace_em_dash(quest.description)
        quest.objective = replace_em_dash(quest.objective)
        quest.notes = replace_em_dash(quest.notes)
        return quest

    @staticmethod
    def _replace_world_fact_memory(fact: WorldFactMemory) -> WorldFactMemory:
        fact.name = replace_em_dash(fact.name)
        fact.status = replace_em_dash(fact.status)
        fact.description = replace_em_dash(fact.description)
        fact.source = replace_em_dash(fact.source)
        fact.notes = replace_em_dash(fact.notes)
        return fact

    @staticmethod
    def _replace_in_named_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for item in items:
            for key, value in list(item.items()):
                if isinstance(value, str):
                    item[key] = replace_em_dash(value)
        return items
