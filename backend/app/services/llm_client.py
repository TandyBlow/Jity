
import json
import logging
import re
import time
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import Settings
from app.schemas import StoryOutput

logger = logging.getLogger(__name__)


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
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.llm_base_url.rstrip("/"),
                max_retries=3,
                timeout=60.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> tuple[StoryOutput, int]:
        if not self.settings.deepseek_api_key:
            raise MissingAPIKeyError(
                "AI 生成需要配置 backend/.env 里的 DEEPSEEK_API_KEY。"
                "固定开场结束后不会再使用本地兜底剧情。"
            )

        model_name = model or self.settings.llm_model
        started = time.perf_counter()

        try:
            raw_text = await self._request_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.35,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            raise LLMRequestError(
                f"LLM 请求失败。请检查 API Key、余额或模型权限。原始错误: {exc}",
                status_code=getattr(exc, "status_code", 0),
                response_text=str(exc),
                latency_ms=latency_ms,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        # First attempt: direct parse
        try:
            return self._parse_story_output(raw_text), latency_ms
        except (json.JSONDecodeError, ValidationError, TypeError) as first_exc:
            # Second attempt: json_repair library (local, no API call)
            try:
                repaired = self._repair_json_local(raw_text)
                logger.info("json_repair succeeded — recovered from parse failure")
                return self._parse_story_output(repaired), latency_ms
            except Exception:
                logger.debug("generate: json_repair local fallback failed", exc_info=True)
                pass

            # Third attempt: LLM repair with temperature=0
            try:
                repaired_text = await self._request_completion(
                    messages=[
                        {
                            "role": "user",
                            "content": self._build_json_repair_prompt(raw_text, str(first_exc)),
                        }
                    ],
                    model=model_name,
                    temperature=0,
                )
                return self._parse_story_output(repaired_text), int(
                    (time.perf_counter() - started) * 1000
                )
            except (json.JSONDecodeError, ValidationError, TypeError) as repair_exc:
                raise LLMOutputParseError(
                    "模型返回不是有效剧情 JSON，原始输出和修复输出已保存到 model_outputs。",
                    raw_output=self._format_failed_outputs(raw_text, ""),
                    cleaned_output=self._clean_json_text(raw_text),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                ) from repair_exc

    async def _request_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        _json_object: bool = True,
        max_tokens: int = 50000,
    ) -> str:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if _json_object:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def _repair_json_local(self, raw_text: str) -> str:
        """Attempt local JSON repair before falling back to LLM repair."""
        from json_repair import repair_json

        cleaned = self._clean_json_text(raw_text)
        return repair_json(cleaned)

    async def generate_text(
        self,
        prompt: str,
        model: str = "deepseek-v4-flash",
        max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> str:
        """Generate free-text response. No JSON parsing — caller handles the text.

        Used for session recaps and other non-structured LLM calls.
        """
        started = time.perf_counter()
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            raise LLMRequestError(
                f"LLM text generation failed. Original error: {exc}",
                status_code=getattr(exc, "status_code", 0),
                response_text=str(exc),
                latency_ms=latency_ms,
            ) from exc

    async def generate_json(
        self,
        prompt: str,
        model: str = "deepseek-v4-flash",
        max_tokens: int = 50000,
        temperature: float = 0.35,
    ) -> dict:
        """Generate and parse JSON output with repair fallback.

        Uses json_object mode. If direct parse fails, applies json_repair.
        Caller must validate with Pydantic/TypeAdapter.

        Used for campaign.json generation, fact extraction, and other
        structured LLM calls.
        """
        started = time.perf_counter()

        try:
            raw_text = await self._request_completion(
                messages=[{"role": "user", "content": prompt}],
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                _json_object=True,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            raise LLMRequestError(
                f"LLM JSON generation failed. Original error: {exc}",
                status_code=getattr(exc, "status_code", 0),
                response_text=str(exc),
                latency_ms=latency_ms,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        # First attempt: direct JSON parse
        try:
            return json.loads(self._clean_json_text(raw_text))
        except json.JSONDecodeError:
            # Second attempt: json_repair
            try:
                repaired = self._repair_json_local(raw_text)
                logger.info("generate_json: json_repair succeeded")
                return json.loads(self._clean_json_text(repaired))
            except Exception:
                logger.debug("generate_json: json_repair local fallback failed", exc_info=True)
                pass

        raise LLMOutputParseError(
            "generate_json: failed to parse JSON after repair",
            raw_output=raw_text,
            cleaned_output=self._clean_json_text(raw_text),
            latency_ms=latency_ms,
        )

    # ── static helpers (unchanged from original) ──

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
    def _clean_json_text(text: str) -> str:
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
        return cleaned.replace("```json", "").replace("```", "").strip()

    @staticmethod
    def _normalize_output(payload: dict[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload["items_gained"] = LLMClient._normalize_named_objects(
            payload.get("items_gained", []), "description"
        )
        payload["items_lost"] = LLMClient._normalize_named_objects(
            payload.get("items_lost", []), "description"
        )
        payload["npcs_encountered"] = LLMClient._normalize_named_objects(
            payload.get("npcs_encountered", []), "notes"
        )
        payload["quests_updated"] = LLMClient._normalize_named_objects(
            payload.get("quests_updated", []), "description"
        )
        payload["memory_updates"] = LLMClient._normalize_memory_updates(
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
