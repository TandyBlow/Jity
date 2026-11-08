"""Narrow, explicit recovery attachment for known precommit JSON parse failures.

Install in both recording and offline replay processes. Frozen application and
capture sources stay untouched; every original bad response is still consumed.
"""
from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
import hashlib
import json


MAX_PARSE_RETRIES = 2
MAX_HTTP_ATTEMPTS = 3


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def authoritative_checkpoint(value):
    """Ignore only opaque identity counters/revisions, never gameplay values."""
    result = deepcopy(value)
    result.pop("uuid_counter", None)
    memory = result.get("state", {}).get("_memory_controller")
    if isinstance(memory, dict):
        memory.pop("version", None)
    return result


def _revision(checkpoint):
    return {"uuid_counter": checkpoint.get("uuid_counter"),
            "memory_version": checkpoint.get("state", {}).get("_memory_controller", {}).get("version")}


def _body_group(method, url, body, scope):
    return _digest({"game_id": scope.get("game_id"), "operation_id": scope.get("operation_id"),
                    "purpose": scope.get("purpose"), "method": method, "url": url, "body": body})


def _record_group(row):
    request = row["request"]
    body = request.get("body")
    if body is None:
        body = {"raw_base64": request.get("body_base64")}
    return _body_group(request["method"], request["url"], body, row["context"])


class Installation:
    def __init__(self, runtime_class, transport_class, runtime_original, transport_original):
        self.runtime_class, self.transport_class = runtime_class, transport_class
        self.runtime_original, self.transport_original = runtime_original, transport_original
        self.metadata = {"kind": "known_precommit_parse_failure_adapter", "version": 1,
                         "max_parse_retries": MAX_PARSE_RETRIES, "max_identical_http_attempts": MAX_HTTP_ATTEMPTS,
                         "ignored_checkpoint_revision_fields": ["uuid_counter", "state._memory_controller.version"],
                         "rewinds_state": False, "substitutes_responses": False}

    def uninstall(self):
        if getattr(self.runtime_class, "_known_parse_adapter", None) is self:
            self.runtime_class.generate = self.runtime_original
            delattr(self.runtime_class, "_known_parse_adapter")
        if getattr(self.transport_class, "_known_parse_adapter", None) is self:
            self.transport_class.handle_async_request = self.transport_original
            delattr(self.transport_class, "_known_parse_adapter")


def install_adapter(runtime_class=None, transport_class=None, *, parse_error_types=None):
    """Install idempotently; return a handle with metadata/uninstall().

    Optional classes and error types are dependency injection solely for offline
    tests. Production callers use install_adapter() with the frozen evaluator
    already selected on sys.path. Application exception types are imported lazily
    because Jity's import path is established by JityRuntime construction.
    """
    from jity_eval.capture.journal import BudgetExceeded, CaptureBoundaryError, UncertainCapture
    from jity_eval.capture import transport as transport_module
    if runtime_class is None:
        from jity_eval.capture.runtime import JityRuntime
        runtime_class = JityRuntime
    if transport_class is None:
        transport_class = transport_module.CaptureTransport
    existing = getattr(runtime_class, "_known_parse_adapter", None)
    if existing is not None:
        if existing.transport_class is not transport_class:
            raise ValueError("Recovery adapter is already installed with another transport")
        return existing
    if getattr(transport_class, "_known_parse_adapter", None) is not None:
        raise ValueError("Transport already has a different recovery adapter installation")
    original_generate = runtime_class.generate
    original_handle = transport_class.handle_async_request

    def fatal(runtime, error):
        runtime.transport.fatal = error
        raise error

    async def retry_generate(runtime, payload):
        request = deepcopy(payload)
        before = deepcopy(runtime.checkpoint())
        stable_before = authoritative_checkpoint(before)
        for attempt in range(MAX_PARSE_RETRIES + 1):
            runtime.transport.raise_if_failed()
            try:
                result = await original_generate(runtime, deepcopy(request))
            except CaptureBoundaryError:
                raise
            except Exception as exc:
                if parse_error_types is None:
                    from app.services.scenario_generator.errors import ScenarioGenerationError
                    from app.services.llm_client.errors import LLMOutputParseError
                    scenario_type, parse_type = ScenarioGenerationError, LLMOutputParseError
                else:
                    scenario_type, parse_type = parse_error_types
                # A timeout, connection error, budget failure, unknown provider
                # outcome or merely similarly named exception is never retried.
                if not isinstance(exc, scenario_type) or not isinstance(exc.__cause__, parse_type):
                    raise
                runtime.transport.raise_if_failed()
                after = deepcopy(runtime.checkpoint())
                if authoritative_checkpoint(after) != stable_before:
                    fatal(runtime, UncertainCapture("Known parse failure changed authoritative checkpoint; action retry refused"))
                uncertain = [r for r in runtime.transport.journal.records()
                             if r.get("status") not in {"complete", "error"}]
                if uncertain:
                    fatal(runtime, UncertainCapture("Unknown/incomplete provider response exists; action retry refused"))
                event = {"adapter_version": 1, "game_id": getattr(runtime, "game_id", None),
                         "turn": before.get("turn", 0) + 1, "head": before.get("head"),
                         "failed_application_attempt": attempt + 1, "max_parse_retries": MAX_PARSE_RETRIES,
                         "exception_type": type(exc).__name__, "cause_type": type(exc.__cause__).__name__,
                         "state_verified_unchanged": True, "authoritative_checkpoint_sha256": _digest(stable_before),
                         "payload_sha256": _digest(request), "action_check": deepcopy(request.get("action_check")),
                         "revision_before": _revision(before), "revision_after": _revision(after),
                         "rewound": False, "raw_response_substitution": False}
                if attempt >= MAX_PARSE_RETRIES:
                    runtime._event("known_parse_retry_exhausted", event)
                    raise
                event["retry_index"] = attempt + 1
                runtime._event("known_parse_retry", event)
                continue
            runtime.transport.raise_if_failed()
            return result
        raise AssertionError("Unreachable retry state")

    async def limited_handle(transport, request):
        transport.raise_if_failed()
        # The original transport decides exact request/order/fingerprint matches
        # and recreates known errors. Reusing history never spends an attempt.
        if transport.position < len(transport._prefix) or transport.mode == "replay":
            return await original_handle(transport, request)
        raw = await request.aread()
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = {"raw_base64": base64.b64encode(raw).decode("ascii")}
        scope = transport_module.current_scope()
        group = _body_group(request.method, transport_module._url(request.url), body, scope)
        # Serialize only newly paid HTTP attempts. This closes the check/start
        # race; existing prefix playback and all state transitions are unchanged.
        lock = getattr(transport, "_known_parse_attempt_lock", None)
        if lock is None:
            lock = transport._known_parse_attempt_lock = asyncio.Lock()
        async with lock:
            transport.raise_if_failed()
            count = sum(_record_group(row) == group for row in transport.journal.records())
            if count >= MAX_HTTP_ATTEMPTS:
                transport.journal.event("http_attempt_limit_stop", {
                    "group_sha256": group, "game_id": scope.get("game_id"),
                    "operation_id": scope.get("operation_id"), "purpose": scope.get("purpose"),
                    "recorded_attempts": count, "max_attempts": MAX_HTTP_ATTEMPTS,
                    "includes_sdk_and_application_retries": True})
                error = BudgetExceeded("Per-request attempt limit reached (initial + two retries); no new HTTP request sent")
                transport.fatal = error
                raise error
            return await original_handle(transport, request)

    handle = Installation(runtime_class, transport_class, original_generate, original_handle)
    runtime_class.generate, transport_class.handle_async_request = retry_generate, limited_handle
    runtime_class._known_parse_adapter = transport_class._known_parse_adapter = handle
    return handle
