from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.schemas import StoryOutput


class MissingAPIKeyError(RuntimeError):
    pass


class LLMOutputParseError(RuntimeError):
    def __init__(self, message: str, raw_output: str, cleaned_output: str, latency_ms: int) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.cleaned_output = cleaned_output
        self.latency_ms = latency_ms


class LLMRequestError(RuntimeError):
    def __init__(self, message: str, status_code: int, response_text: str, latency_ms: int) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text
        self.latency_ms = latency_ms


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
    ) -> tuple[StoryOutput, int]:
        if not self.settings.deepseek_api_key:
            raise MissingAPIKeyError("AI 生成需要配置 backend/.env 里的 DEEPSEEK_API_KEY。固定开场结束后不会再使用本地兜底剧情。")

        model_name = model or self.settings.llm_model
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=60) as client:
            raw_text = await self._request_completion(
                client=client,
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.35,
                started=started,
            )

            try:
                return self._parse_story_output(raw_text), int((time.perf_counter() - started) * 1000)
            except (json.JSONDecodeError, ValidationError, TypeError) as first_exc:
                repaired_text = await self._request_completion(
                    client=client,
                    messages=[
                        {
                            "role": "user",
                            "content": self._build_json_repair_prompt(raw_text, str(first_exc)),
                        }
                    ],
                    model=model_name,
                    temperature=0,
                    started=started,
                )

            try:
                return self._parse_story_output(repaired_text), int((time.perf_counter() - started) * 1000)
            except (json.JSONDecodeError, ValidationError, TypeError) as repair_exc:
                raise LLMOutputParseError(
                    "模型返回不是有效剧情 JSON，原始输出和修复输出已保存到 model_outputs。",
                    raw_output=self._format_failed_outputs(raw_text, repaired_text),
                    cleaned_output=self._clean_json_text(repaired_text),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ) from repair_exc

    async def _request_completion(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        started: float,
    ) -> str:
        response = await client.post(
            f"{self.settings.llm_base_url.rstrip('/')}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 50000,
                "response_format": {"type": "json_object"},
            },
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise LLMRequestError(
                f"LLM 请求失败，状态码 {response.status_code}。请检查 API Key、余额或模型权限。",
                status_code=response.status_code,
                response_text=response.text,
                latency_ms=latency_ms,
            ) from exc
        return str(response.json()["choices"][0]["message"]["content"])

    @classmethod
    def _parse_story_output(cls, raw_text: str) -> StoryOutput:
        payload = json.loads(cls._clean_json_text(raw_text))
        return StoryOutput.model_validate(cls._normalize_output(payload))

    @staticmethod
    def _build_json_repair_prompt(raw_text: str, error_text: str) -> str:
        return f"""下面这段内容不是合法的剧情 JSON，可能原因包括字符串里有未转义的双引号、尾部被截断、字段类型不符合 schema。

请在不改变剧情含义和字段结构的前提下修复它。只返回严格合法 JSON，不要 Markdown，不要解释，不要额外文本。
如果 dialogue.text 里需要引用角色原话，不要使用裸双引号；改用中文引号、英文单引号，或改写为间接叙述。

解析错误：
{error_text}

原始输出：
{raw_text}"""

    @staticmethod
    def _format_failed_outputs(original_text: str, repaired_text: str) -> str:
        return f"原始输出：\n{original_text}\n\n修复输出：\n{repaired_text}"

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        return json.loads(LLMClient._clean_json_text(text))

    @staticmethod
    def _clean_json_text(text: str) -> str:
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        return cleaned.replace("```json", "").replace("```", "").strip()

    @staticmethod
    def _normalize_output(payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload["items_gained"] = LLMClient._normalize_named_objects(payload.get("items_gained", []), "description")
        payload["items_lost"] = LLMClient._normalize_named_objects(payload.get("items_lost", []), "description")
        payload["npcs_encountered"] = LLMClient._normalize_named_objects(payload.get("npcs_encountered", []), "notes")
        payload["quests_updated"] = LLMClient._normalize_named_objects(payload.get("quests_updated", []), "description")
        payload["memory_updates"] = LLMClient._normalize_memory_updates(payload.get("memory_updates", {}), payload)
        return payload

    @staticmethod
    def _normalize_memory_updates(memory_updates: Any, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(memory_updates, dict):
            memory_updates = {}
        normalized = dict(memory_updates)
        normalized["current_location"] = str(normalized.get("current_location") or payload.get("current_location") or "")
        normalized["items_upserted"] = LLMClient._normalize_named_objects(
            normalized.get("items_upserted", []),
            "description",
        )
        normalized["items_removed"] = LLMClient._normalize_named_objects(
            normalized.get("items_removed", []),
            "description",
        )
        normalized["npcs_upserted"] = LLMClient._normalize_named_objects(
            normalized.get("npcs_upserted", []),
            "notes",
        )
        normalized["quests_upserted"] = LLMClient._normalize_named_objects(
            normalized.get("quests_upserted", []),
            "description",
        )
        normalized["world_facts_upserted"] = LLMClient._normalize_named_objects(
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
