"""LLMClient.generate temperature handling — the parameter must reach the API call.

2026-10-11 review finding: generate() hardcoded 0.35 and ignored its
temperature parameter, so agent_pipeline's meta.temperature never took
effect. Semantics (user-directed): an omitted value falls back to 0.35; a
passed value is used as-is.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm_client import LLMClient


def _client() -> LLMClient:
    return LLMClient(
        SimpleNamespace(deepseek_api_key="k", llm_model="test-model", llm_base_url="http://x")
    )


@pytest.mark.asyncio
async def test_generate_falls_back_to_default_temperature():
    client = _client()
    client._request_completion = AsyncMock(return_value='{"narration": "正文"}')

    await client.generate("提示词")

    assert client._request_completion.call_args.kwargs["temperature"] == 0.35


@pytest.mark.asyncio
async def test_generate_uses_the_passed_temperature():
    client = _client()
    client._request_completion = AsyncMock(return_value='{"narration": "正文"}')

    await client.generate("提示词", temperature=0.7)

    assert client._request_completion.call_args.kwargs["temperature"] == 0.7
