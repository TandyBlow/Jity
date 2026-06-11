from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.config import Settings
from app.schemas import StoryOutput


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, prompt: str, model: str | None = None) -> tuple[StoryOutput, int]:
        if not self.settings.deepseek_api_key:
            return self._fallback_output()

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.llm_base_url.rstrip('/')}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model or self.settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.35,
                    "max_tokens": 1200,
                },
            )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response.raise_for_status()
        raw_text = response.json()["choices"][0]["message"]["content"]
        return StoryOutput.model_validate(self._parse_json(raw_text)), latency_ms

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)

    @staticmethod
    def _fallback_output() -> tuple[StoryOutput, int]:
        return (
            StoryOutput(
                narration="你把行动说出口后，报到大厅短暂安静了一秒。诺诺看向你，像是在判断这是不是勇气，芬格尔则已经开始往旁边挪，给即将出现的麻烦留出位置。",
                dialogue=[
                    {"speaker": "诺诺", "text": "可以。那就按你的办法走，但你最好记住，卡塞尔的规则通常写在事故报告里。"},
                    {"speaker": "芬格尔", "text": "师弟，我负责精神支持，物理支持看情况。"},
                ],
                scene_prompt="rainy gothic academy hall, nervous freshman, red uniform girl, cinematic dark fantasy",
                sanity_delta=0,
                health_delta=0,
                options=["继续推进这个计划", "先询问相关规则", "观察 NPC 的反应"],
                current_location="卡塞尔学院报到大厅",
                npcs_encountered=[
                    {"name": "诺诺", "disposition": "关注", "notes": "正在观察玩家的判断力"},
                    {"name": "芬格尔", "disposition": "协助", "notes": "提供吐槽和非正式情报"},
                ],
            ),
            0,
        )
