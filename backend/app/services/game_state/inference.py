"""State inference: world-fact detection, key events and player status."""

import re
from typing import Any

from app.schemas import StoryOutput

from app.services.game_state.defaults import RECENT_EVENT_MAX_CHARS


class StateInferenceMixin:
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
    def _first_sentence(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        parts = re.split(r"(?<=[。！？.!?])", cleaned, maxsplit=1)
        return parts[0] if parts and parts[0] else cleaned
