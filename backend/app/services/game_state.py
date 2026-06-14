from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.database import Database
from app.schemas import StoryOutput

RECENT_EVENT_LIMIT = 8
RECENT_EVENT_MAX_CHARS = 120


def default_state() -> dict[str, Any]:
    return {
        "sanity": 80,
        "health": 100,
        "turn": 0,
        "current_location": "卡塞尔学院报到处大厅",
        "items": [],
        "npcs": [
            {
                "name": "诺诺",
                "status": "present",
                "relationship": "接应者",
                "current_location": "卡塞尔学院报到处大厅",
                "description": "红发学姐，受古德里安教授委托接路明非报到。",
                "notes": "语气戏谑，知道学院并不普通。",
            }
        ],
        "quests": [],
        "recent_events": ["路明非拖着旧行李箱抵达卡塞尔学院报到处大厅，诺诺前来接应。"],
        "world_facts": [
            {
                "name": "卡塞尔学院异常报到流程",
                "status": "suspected",
                "description": "学院报到大厅有执行部学生、投影新生名单和异常门禁机制。",
                "source": "opening_scene",
                "notes": "这里不像普通大学。",
            }
        ],
        "player_status": {
            "condition": "新生报到中",
            "danger_level": "medium",
            "current_goal": "完成卡塞尔学院入学报到",
            "notes": "刚抵达学院，对规则和风险了解有限。",
        },
    }


class GameStateManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    def create_session(self, game_name: str, model: str) -> dict[str, Any]:
        session_id = str(uuid.uuid4())
        state = default_state()
        self.db.write_session(session_id, game_name, model, state)
        return {"session_id": session_id, "game_name": game_name, "model": model, "state": state}

    def get_session_payload(self, session_id: str) -> dict[str, Any] | None:
        row = self.db.get_session(session_id)
        if not row:
            return None
        return {
            "session_id": row["id"],
            "game_name": row["game_name"],
            "model": row["model"],
            "state": json.loads(row["state_json"]),
        }

    def save_state(self, session_id: str, game_name: str, model: str, state: dict[str, Any]) -> None:
        self.db.write_session(session_id, game_name, model, state)

    def apply_output(self, state: dict[str, Any], action: str, output: StoryOutput) -> dict[str, Any]:
        next_state = self._ensure_state_shape(state)
        next_state["sanity"] = self._clamp(next_state.get("sanity", 80) + output.sanity_delta)
        next_state["health"] = self._clamp(next_state.get("health", 100) + output.health_delta)
        next_state["turn"] = int(next_state.get("turn", 0)) + 1

        memory = output.memory_updates.model_dump()
        current_location = memory.get("current_location") or output.current_location
        if current_location:
            next_state["current_location"] = current_location

        items_upserted = [*output.items_gained, *memory.get("items_upserted", [])]
        items_removed = [*output.items_lost, *memory.get("items_removed", [])]
        npcs_upserted = [*output.npcs_encountered, *memory.get("npcs_upserted", [])]
        quests_upserted = [*output.quests_updated, *memory.get("quests_upserted", [])]
        world_facts = [*memory.get("world_facts_upserted", []), *self._infer_world_facts(action, output)]

        next_state["items"] = self._remove_by_name(
            self._merge_by_name(next_state.get("items", []), items_upserted, kind="item"),
            items_removed,
        )
        next_state["npcs"] = self._merge_by_name(
            next_state.get("npcs", []),
            npcs_upserted,
            kind="npc",
            default_location=next_state.get("current_location", ""),
        )
        next_state["quests"] = self._merge_by_name(next_state.get("quests", []), quests_upserted, kind="quest")
        next_state["world_facts"] = self._merge_by_name(
            next_state.get("world_facts", []),
            world_facts,
            kind="world_fact",
        )
        next_state["player_status"] = self._merge_player_status(
            next_state.get("player_status", {}),
            memory.get("player_status_patch", {}),
            next_state["sanity"],
            next_state["health"],
        )
        next_state["recent_events"] = self._append_recent(
            next_state.get("recent_events", []),
            self._build_key_event(action, output),
        )
        return next_state

    @staticmethod
    def _clamp(value: int) -> int:
        return max(0, min(100, int(value)))

    def _ensure_state_shape(self, state: dict[str, Any]) -> dict[str, Any]:
        base = default_state()
        next_state = dict(base)
        next_state.update(state)
        next_state["items"] = [item for item in (self._normalize_memory(item, "item") for item in next_state.get("items", [])) if item]
        next_state["npcs"] = [
            item
            for item in (
                self._normalize_memory(
                    item,
                    "npc",
                    default_location=next_state.get("current_location", ""),
                )
                for item in next_state.get("npcs", [])
            )
            if item
        ]
        next_state["quests"] = [item for item in (self._normalize_memory(item, "quest") for item in next_state.get("quests", [])) if item]
        next_state["world_facts"] = [
            item
            for item in (self._normalize_memory(item, "world_fact") for item in next_state.get("world_facts", []))
            if item
        ]
        next_state["recent_events"] = [
            self._truncate(self._clean_text(str(event)), RECENT_EVENT_MAX_CHARS)
            for event in next_state.get("recent_events", [])
            if str(event).strip()
        ][-RECENT_EVENT_LIMIT:]
        next_state["player_status"] = self._merge_player_status(
            base["player_status"],
            next_state.get("player_status", {}),
            next_state.get("sanity", 80),
            next_state.get("health", 100),
        )
        return next_state

    def _merge_by_name(
        self,
        current: list[dict[str, Any]],
        updates: list[dict[str, Any]],
        *,
        kind: str,
        default_location: str = "",
    ) -> list[dict[str, Any]]:
        merged = {
            item.get("name"): item
            for item in (self._normalize_memory(item, kind, default_location=default_location) for item in current)
            if item and item.get("name")
        }
        for update in updates:
            normalized = self._normalize_memory(update, kind, default_location=default_location)
            if not normalized:
                continue
            name = normalized.get("name")
            if not name:
                continue
            existing = merged.get(name, {})
            existing.update({key: value for key, value in normalized.items() if value not in (None, "")})
            merged[name] = existing
        return list(merged.values())

    def _remove_by_name(self, current: list[dict[str, Any]], removed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        removed_names = {
            normalized["name"]
            for normalized in (self._normalize_memory(item, "item") for item in removed)
            if normalized and normalized.get("name")
        }
        return [item for item in current if item.get("name") not in removed_names]

    def _normalize_memory(
        self,
        item: Any,
        kind: str,
        *,
        default_location: str = "",
    ) -> dict[str, Any]:
        if isinstance(item, str):
            raw: dict[str, Any] = {"name": item}
        elif isinstance(item, dict):
            raw = dict(item)
        else:
            return {}

        name = self._clean_text(str(raw.get("name", "")))
        if not name:
            return {}

        if kind == "item":
            return {
                "name": name,
                "status": self._normalize_status(str(raw.get("status") or "owned"), kind),
                "description": self._clean_text(str(raw.get("description") or "")),
                "location": self._clean_text(str(raw.get("location") or "")),
                "notes": self._clean_text(str(raw.get("notes") or "")),
            }
        if kind == "npc":
            return {
                "name": name,
                "status": self._normalize_status(str(raw.get("status") or "present"), kind),
                "relationship": self._clean_text(str(raw.get("relationship") or raw.get("disposition") or "")),
                "current_location": self._clean_text(str(raw.get("current_location") or default_location or "")),
                "description": self._clean_text(str(raw.get("description") or "")),
                "notes": self._clean_text(str(raw.get("notes") or "")),
            }
        if kind == "quest":
            return {
                "name": name,
                "status": self._normalize_status(str(raw.get("status") or "active"), kind),
                "description": self._clean_text(str(raw.get("description") or "")),
                "objective": self._clean_text(str(raw.get("objective") or "")),
                "notes": self._clean_text(str(raw.get("notes") or "")),
            }
        return {
            "name": name,
            "status": self._normalize_status(str(raw.get("status") or "known"), kind),
            "description": self._clean_text(str(raw.get("description") or "")),
            "source": self._clean_text(str(raw.get("source") or "")),
            "notes": self._clean_text(str(raw.get("notes") or "")),
        }

    @staticmethod
    def _normalize_status(status: str, kind: str) -> str:
        value = status.strip().lower()
        aliases = {
            "已解锁": "active",
            "进行中": "active",
            "活跃": "active",
            "完成": "completed",
            "已完成": "completed",
            "失败": "failed",
            "持有": "owned",
            "获得": "owned",
            "在场": "present",
            "同行": "following",
            "离开": "away",
            "已知": "known",
            "推测": "suspected",
        }
        if status in aliases:
            return aliases[status]
        if value:
            return value
        defaults = {"item": "owned", "npc": "present", "quest": "active", "world_fact": "known"}
        return defaults.get(kind, "known")

    def _merge_player_status(
        self,
        current: dict[str, Any],
        patch: dict[str, Any],
        sanity: int,
        health: int,
    ) -> dict[str, Any]:
        merged = {
            "condition": self._clean_text(str(current.get("condition") or "新生报到中")),
            "danger_level": self._clean_text(str(current.get("danger_level") or self._danger_level(sanity, health))),
            "current_goal": self._clean_text(str(current.get("current_goal") or "完成卡塞尔学院入学报到")),
            "notes": self._clean_text(str(current.get("notes") or "")),
        }
        for key in ("condition", "danger_level", "current_goal", "notes"):
            value = self._clean_text(str(patch.get(key) or ""))
            if value:
                merged[key] = value
        if patch.get("danger_level") in (None, ""):
            merged["danger_level"] = self._danger_level(sanity, health)
        return merged

    @staticmethod
    def _danger_level(sanity: int, health: int) -> str:
        if health <= 30 or sanity <= 30:
            return "critical"
        if health <= 60 or sanity <= 60:
            return "high"
        return "medium"

    def _infer_world_facts(self, action: str, output: StoryOutput) -> list[dict[str, str]]:
        text = f"{action}\n{output.narration}"
        facts: list[dict[str, str]] = []
        if "红色标记" in text or "红色鳞片" in text:
            facts.append(
                {
                    "name": "红色标记",
                    "status": "known",
                    "description": "玩家名字、临时通行卡或学院系统中出现红色标记，可能代表监控、权限或警告。",
                    "source": "system_inference",
                }
            )
        if "L-13" in text:
            facts.append(
                {
                    "name": "L-13编号",
                    "status": "known",
                    "description": "学院系统或执行部用 L-13 指代玩家，和临时观察流程有关。",
                    "source": "system_inference",
                }
            )
        if "S级观察对象" in text or "S级" in text:
            facts.append(
                {
                    "name": "S级观察对象",
                    "status": "known",
                    "description": "玩家被学院流程标记为 S级观察对象。",
                    "source": "system_inference",
                }
            )
        if "执行部" in text and ("观察" in text or "监视" in text):
            facts.append(
                {
                    "name": "执行部观察玩家",
                    "status": "known",
                    "description": "执行部学生正在观察玩家，但不一定被允许主动接触。",
                    "source": "system_inference",
                }
            )
        if "三年前" in text and "包裹" in text:
            facts.append(
                {
                    "name": "三年前寄出的包裹",
                    "status": "known",
                    "description": "有一份三年前寄出的新生包裹在当前入学流程中出现。",
                    "source": "system_inference",
                }
            )
        return facts

    def _build_key_event(self, action: str, output: StoryOutput) -> str:
        explicit = output.memory_updates.key_event.strip()
        if explicit:
            return self._truncate(self._clean_text(explicit), RECENT_EVENT_MAX_CHARS)
        action_text = self._truncate(self._clean_text(action), 38)
        narration = self._truncate(self._first_sentence(output.narration), 72)
        return self._truncate(f"玩家行动：{action_text}；结果：{narration}", RECENT_EVENT_MAX_CHARS)

    @staticmethod
    def _append_recent(events: list[str], event: str) -> list[str]:
        cleaned_events = [GameStateManager._truncate(GameStateManager._clean_text(str(item)), RECENT_EVENT_MAX_CHARS) for item in events]
        cleaned_event = GameStateManager._truncate(GameStateManager._clean_text(event), RECENT_EVENT_MAX_CHARS)
        if cleaned_events and cleaned_events[-1] == cleaned_event:
            return cleaned_events[-RECENT_EVENT_LIMIT:]
        return [*cleaned_events, cleaned_event][-RECENT_EVENT_LIMIT:]

    @staticmethod
    def _first_sentence(text: str) -> str:
        cleaned = GameStateManager._clean_text(text)
        parts = re.split(r"(?<=[。！？.!?])", cleaned, maxsplit=1)
        return parts[0] if parts and parts[0] else cleaned

    @staticmethod
    def _clean_text(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 1]}…"
