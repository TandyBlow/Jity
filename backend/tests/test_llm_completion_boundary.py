"""Reject provider truncation before JSON repair can consume durable inputs."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.services.llm_client import LLMClient, LLMOutputParseError
from app.services.memory.memory_controller import MemoryController


def client(content, reason="stop"):
    llm = LLMClient(Settings(deepseek_api_key="test", prompt_logging_enabled=False))
    create = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=reason,
    )]))
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return llm, create


@pytest.mark.asyncio
@pytest.mark.parametrize("model,budget,disabled", [
    ("deepseek-v4-flash", 1000, True), ("deepseek-flash", 800, True),
    ("deepseek-v4-pro", 1500, True), ("deepseek-v4-flash", 50000, False),
    ("deepseek-reasoner", 1000, False), ("custom-model", 1000, False),
])
async def test_small_auxiliary_deepseek_calls_have_explicit_thinking_mode(model, budget, disabled):
    llm, create = client('{"summary":"完整摘要"}')
    await llm.generate_json("JSON", model=model, max_tokens=budget)
    assert (create.call_args.kwargs.get("extra_body") == {"thinking": {"type": "disabled"}}) == disabled


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["generate", "generate_json", "generate_text"])
async def test_truncated_response_cannot_be_repaired_into_success(method):
    llm, create = client('{"narration":"被截断的文本', "length")
    llm._repair_json_local = MagicMock()
    with pytest.raises(LLMOutputParseError, match="截断"):
        await getattr(llm, method)("JSON")
    llm._repair_json_local.assert_not_called()
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_truncated_real_client_summary_retains_all_input():
    llm, _ = client('{"summary":"不完整', "length")
    memory = MemoryController(llm, None, "test")
    for turn in range(1, 7):
        memory.on_turn_generated("调查", "应当完整保存的线索", turn)
    await memory.maintain("test", 6, dialogues="")
    assert memory.pending
    assert len(memory.nsb._turn_buffer) == 6
    assert not memory.nsb._level1
