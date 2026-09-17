"""LLMClient — DeepSeek chat client with JSON repair fallbacks."""

import json
import logging
import time

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import Settings
from app.schemas import StoryOutput

from app.services.llm_client.errors import (
    LLMOutputParseError,
    LLMRequestError,
    MissingAPIKeyError,
    request_error_message,
)
from app.services.llm_client.output_normalizer import StoryOutputNormalizer
from app.services.llm_client.repair import JSONRepairMixin
from app.services.llm_client.structured import StructuredGenerationMixin
from app.services.prompt_recorder import PromptRecorder

logger = logging.getLogger(__name__)


class LLMClient(JSONRepairMixin, StoryOutputNormalizer, StructuredGenerationMixin):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        self.prompt_recorder = PromptRecorder(settings)

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
        purpose: str = "story_narrator",
        context: dict | None = None,
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
                purpose=purpose,
                context=context,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            raise LLMRequestError(
                request_error_message(exc),
                status_code=getattr(exc, "status_code", 0),
                response_text=str(exc),
                latency_ms=latency_ms,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        # First attempt: direct parse
        try:
            return self._parse_story_output(raw_text), latency_ms
        except (json.JSONDecodeError, ValidationError, TypeError) as first_exc:
            return await self._regenerate_or_raise(
                raw_text, first_exc, started, model_name, context
            )

    async def _regenerate_or_raise(
        self,
        raw_text: str,
        first_exc: Exception,
        started: float,
        model_name: str,
        context: dict | None = None,
    ) -> tuple[StoryOutput, int]:
        """Repair pipeline: local json_repair, then LLM repair with temperature=0."""
        # Second attempt: json_repair library (local, no API call)
        try:
            repaired = self._repair_json_local(raw_text)
            logger.info("json_repair succeeded — recovered from parse failure")
            return self._parse_story_output(repaired), int(
                (time.perf_counter() - started) * 1000
            )
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
                purpose="story_json_repair",
                context=context,
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
        purpose: str = "chat_completion",
        context: dict | None = None,
    ) -> str:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if _json_object:
            kwargs["response_format"] = {"type": "json_object"}
        await self.prompt_recorder.record(
            purpose=purpose,
            api_type="chat.completions",
            model=model,
            service_url=self.settings.llm_base_url.rstrip("/"),
            request=kwargs,
            context=context,
        )
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
