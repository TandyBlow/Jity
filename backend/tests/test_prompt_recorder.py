"""Tests for opt-in generative API prompt archiving."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.services.llm_client import LLMClient
from app.services.prompt_recorder import PromptRecorder


def _completion(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.mark.asyncio
async def test_disabled_recorder_does_not_create_directory(tmp_path):
    output_dir = tmp_path / "prompts"
    recorder = PromptRecorder(
        Settings(prompt_logging_enabled=False, prompt_log_dir=output_dir)
    )

    result = await recorder.record(
        purpose="test",
        api_type="chat.completions",
        model="model",
        service_url="https://example.invalid",
        request={"messages": [{"role": "user", "content": "secret prompt"}]},
    )

    assert result is None
    assert not output_dir.exists()


@pytest.mark.asyncio
async def test_recorder_writes_unique_complete_json_files(tmp_path):
    recorder = PromptRecorder(
        Settings(prompt_logging_enabled=True, prompt_log_dir=tmp_path)
    )
    request = {
        "messages": [{"role": "user", "content": "完整提示词"}],
        "temperature": 0.3,
        "max_tokens": 123,
        "response_format": {"type": "json_object"},
    }

    paths = await asyncio.gather(
        *(
            recorder.record(
                purpose="memory_nsb_summary",
                api_type="chat.completions",
                model="deepseek-test",
                service_url="https://api.example.com",
                request=request,
                context={"session_id": "session-1"},
            )
            for _ in range(4)
        )
    )

    assert len({path.name for path in paths if path is not None}) == 4
    payload = json.loads(paths[0].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["purpose"] == "memory_nsb_summary"
    assert payload["model"] == "deepseek-test"
    assert payload["context"] == {"session_id": "session-1"}
    assert payload["request"] == request
    assert payload["created_at"].endswith("Z")


@pytest.mark.asyncio
async def test_recording_failure_warns_and_model_request_continues(
    tmp_path, monkeypatch, caplog
):
    settings = Settings(
        deepseek_api_key="test-key",
        prompt_logging_enabled=True,
        prompt_log_dir=tmp_path,
    )
    llm = LLMClient(settings)
    create = AsyncMock(return_value=_completion("model response"))
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    def fail_write(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(llm.prompt_recorder, "_write_atomically", fail_write)
    with caplog.at_level(logging.WARNING):
        result = await llm.generate_text("仍然调用模型", purpose="campaign_recap")

    assert result == "model response"
    create.assert_awaited_once()
    assert "Failed to archive prompt request" in caplog.text


@pytest.mark.asyncio
async def test_generate_text_archives_exact_non_json_request(tmp_path):
    settings = Settings(
        deepseek_api_key="test-key",
        llm_base_url="https://api.example.com/v1/",
        prompt_logging_enabled=True,
        prompt_log_dir=tmp_path,
    )
    llm = LLMClient(settings)
    create = AsyncMock(return_value=_completion("recap"))
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    await llm.generate_text(
        "总结本幕",
        model="text-model",
        max_tokens=800,
        temperature=0.2,
        purpose="campaign_recap",
        context={"session_id": "s-1"},
    )

    path = next(tmp_path.rglob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["purpose"] == "campaign_recap"
    assert payload["service_url"] == "https://api.example.com/v1"
    assert payload["request"] == {
        "model": "text-model",
        "messages": [{"role": "user", "content": "总结本幕"}],
        "temperature": 0.2,
        "max_tokens": 800,
    }


@pytest.mark.asyncio
async def test_story_json_repair_is_archived_as_separate_request(tmp_path, monkeypatch):
    settings = Settings(
        deepseek_api_key="test-key",
        prompt_logging_enabled=True,
        prompt_log_dir=tmp_path,
    )
    llm = LLMClient(settings)
    create = AsyncMock(
        side_effect=[
            _completion("not valid json"),
            _completion('{"narration":"修复成功"}'),
        ]
    )
    llm._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(
        llm, "_repair_json_local", lambda _text: (_ for _ in ()).throw(ValueError())
    )

    output, _ = await llm.generate(
        "原始剧情提示",
        purpose="story_narrator",
        context={"session_id": "s-2"},
    )

    assert output.narration == "修复成功"
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in tmp_path.rglob("*.json")
    ]
    assert {payload["purpose"] for payload in payloads} == {
        "story_narrator",
        "story_json_repair",
    }
    repair = next(p for p in payloads if p["purpose"] == "story_json_repair")
    assert "not valid json" in repair["request"]["messages"][0]["content"]
    assert repair["request"]["temperature"] == 0
