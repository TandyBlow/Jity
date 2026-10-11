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
from app.services.prompt_builder import PromptBuilder, PromptInput, PromptMeta


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


def test_prompt_meta_default_temperature_is_the_turn_default():
    # 2026-10-11 用户裁决：回合默认 0.35（等于温度参数修复前的生产行为）。
    assert PromptMeta().temperature == 0.35


def test_builder_does_not_override_temperature_for_campaign_context():
    # 旧的 difficulty→0.7 钩子会把战役会话悄悄抬回 0.7，已被移除；
    # 难度只负责选项检定的四档语义。
    builder = PromptBuilder()
    prompt_input = PromptInput(
        player_action="我去调查巡夜学生的名单",
        game_state={"current_location": "图书馆", "sanity": 80, "health": 100, "turn": 1},
        campaign_context="难度：普通",
    )
    _, meta = builder.build_sections(prompt_input)

    assert meta.temperature == 0.35
