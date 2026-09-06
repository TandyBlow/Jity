"""StoryOutput payload normalization for loosely-typed LLM responses."""

import json
from typing import Any

from app.schemas import StoryOutput


class StoryOutputNormalizer:
    @classmethod
    def _parse_story_output(cls, raw_text: str) -> StoryOutput:
        payload = json.loads(cls._clean_json_text(raw_text))
        return StoryOutput.model_validate(cls._normalize_output(payload))

    @staticmethod
    def _normalize_output(payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload["items_gained"] = StoryOutputNormalizer._normalize_named_objects(
            payload.get("items_gained", []), "description"
        )
        payload["items_lost"] = StoryOutputNormalizer._normalize_named_objects(
            payload.get("items_lost", []), "description"
        )
        payload["npcs_encountered"] = StoryOutputNormalizer._normalize_named_objects(
            payload.get("npcs_encountered", []), "notes"
        )
        payload["quests_updated"] = StoryOutputNormalizer._normalize_named_objects(
            payload.get("quests_updated", []), "description"
        )
        payload["memory_updates"] = StoryOutputNormalizer._normalize_memory_updates(
            payload.get("memory_updates", {}), payload
        )
        return payload

    @staticmethod
    def _normalize_memory_updates(memory_updates: Any, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(memory_updates, dict):
            memory_updates = {}
        normalized = dict(memory_updates)
        normalized["current_location"] = str(
            normalized.get("current_location") or payload.get("current_location") or ""
        )
        normalized["items_upserted"] = StoryOutputNormalizer._normalize_named_objects(
            normalized.get("items_upserted", []),
            "description",
        )
        normalized["items_removed"] = StoryOutputNormalizer._normalize_named_objects(
            normalized.get("items_removed", []),
            "description",
        )
        normalized["npcs_upserted"] = StoryOutputNormalizer._normalize_named_objects(
            normalized.get("npcs_upserted", []),
            "notes",
        )
        normalized["quests_upserted"] = StoryOutputNormalizer._normalize_named_objects(
            normalized.get("quests_upserted", []),
            "description",
        )
        normalized["world_facts_upserted"] = StoryOutputNormalizer._normalize_named_objects(
            normalized.get("world_facts_upserted", []),
            "description",
        )
        if not isinstance(normalized.get("player_status_patch"), dict):
            normalized["player_status_patch"] = {}
        normalized["key_event"] = str(normalized.get("key_event") or "")
        return normalized

    @staticmethod
    def _normalize_named_objects(items: Any, detail_key: str) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str) and item.strip():
                normalized.append({"name": item.strip(), detail_key: "AI 生成记录"})
        return normalized
