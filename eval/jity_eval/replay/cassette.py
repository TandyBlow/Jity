"""Recorded completion transport with exact purpose/order/request matching."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ..storage import digest
from .sandbox import ForbiddenReplayOperation, MissingRecordedCall


class RecordedCalls:
    def __init__(self, records=()):
        self.records = deepcopy(list(records))
        self.position = 0
        self.events = []
        self.checkpoint_turn = 0

    def reply(self, purpose, messages, model, temperature, max_tokens=50000, json_object=True):
        request = {"purpose": purpose, "messages": deepcopy(messages), "model": model,
                   "temperature": temperature, "max_tokens": max_tokens, "json_object": json_object}
        fingerprint = digest(request)
        event = {"checkpoint_turn": self.checkpoint_turn, "call_index": self.position,
                 "request": request, "request_sha256": fingerprint, "real_model_calls": 0}
        if self.position >= len(self.records):
            event["status"] = "missing_recorded_call"
            self.events.append(event)
            raise MissingRecordedCall("缺失历史调用记录：turn=%s purpose=%s index=%s；已停止，禁止真实请求" %
                                      (self.checkpoint_turn, purpose, self.position))
        record = self.records[self.position]
        if (record.get("purpose") != purpose or record.get("request_sha256") != fingerprint
                or record.get("turn") != self.checkpoint_turn or not isinstance(record.get("response_text"), str)):
            event["status"] = "record_mismatch"
            self.events.append(event)
            raise MissingRecordedCall("历史调用记录不匹配：turn=%s purpose=%s index=%s" %
                                      (self.checkpoint_turn, purpose, self.position))
        self.position += 1
        event.update(status="replayed", response_text=record["response_text"], provenance=record.get("provenance", "recorded"))
        self.events.append(event)
        return record["response_text"]


def make_llm(calls: RecordedCalls, run_dir: Path):
    """Preserve Jity's parse/repair methods and replace the network transport."""
    from app.config import Settings
    from app.services.llm_client import LLMClient

    class RecordedLLM(LLMClient):
        @property
        def client(self):
            raise ForbiddenReplayOperation("禁止创建真实模型客户端")

        async def _request_completion(self, messages, model, temperature, _json_object=True,
                                      max_tokens=50000, purpose="chat_completion", context=None):
            return calls.reply(purpose, messages, model, temperature, max_tokens, _json_object)

    # model_construct bypasses environment loading altogether; no real credentials.
    settings = Settings.model_construct(
        deepseek_api_key="offline-replay-only", image_api_key="",
        llm_base_url="http://offline.invalid", image_base_url="http://offline.invalid",
        database_file=run_dir / "runtime.sqlite3", prompt_logging_enabled=False,
        prompt_log_dir=run_dir / "disabled-prompt-logs", backgrounds_dir=run_dir / "backgrounds",
        campaigns_dir=run_dir / "campaigns", knowledge_dir=run_dir / "knowledge",
        rulebook_file=run_dir / "rules.md",
    )
    return RecordedLLM(settings)
