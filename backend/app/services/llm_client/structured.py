"""Structured and free-text generation methods for LLMClient."""

import json
import logging
import time

from app.services.llm_client.errors import LLMOutputParseError, LLMRequestError

logger = logging.getLogger(__name__)


class StructuredGenerationMixin:
    async def generate_text(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.3,
    ) -> str:
        """Generate free-text response. No JSON parsing — caller handles the text.

        Used for session recaps and other non-structured LLM calls.
        """
        model = model or self.settings.llm_model
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
        model: str | None = None,
        max_tokens: int = 50000,
        temperature: float = 0.35,
    ) -> dict:
        """Generate and parse JSON output with repair fallback.

        Uses json_object mode. If direct parse fails, applies json_repair.
        Caller must validate with Pydantic/TypeAdapter.

        Used for campaign.json generation, fact extraction, and other
        structured LLM calls.
        """
        model = model or self.settings.llm_model
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
