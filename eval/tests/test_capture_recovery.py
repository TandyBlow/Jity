import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import httpx
from jity_eval.capture.recovery import install_adapter
from jity_eval.capture.journal import CallJournal, BudgetExceeded, UncertainCapture
from jity_eval.capture.transport import CaptureTransport, capture_scope


class ParseError(Exception):
    pass


class ScenarioError(Exception):
    pass


def failure():
    error = ScenarioError("known parser failure")
    error.__cause__ = ParseError("invalid JSON")
    return error


class FakeJournal:
    def __init__(self, statuses=("complete",)):
        self.statuses = statuses
    def records(self):
        return [{"status": s} for s in self.statuses]


class FakeTransport:
    def __init__(self):
        self.fatal = None
        self.journal = FakeJournal()
    def raise_if_failed(self):
        if self.fatal:
            raise self.fatal
    async def handle_async_request(self, request):
        raise AssertionError("No network in runtime tests")


def runtime_class():
    class Runtime:
        def __init__(self, outcomes, mutation=None):
            self.transport, self.game_id = FakeTransport(), "game-test"
            self.outcomes, self.mutation = list(outcomes), mutation
            self.state = {"head": 22, "turn": 22, "session_id": "game-test", "uuid_counter": 93,
                          "state": {"health": 100, "_memory_controller": {"version": "revision-old", "facts": ["kept"]}},
                          "progress": {"turns_total": 20}, "output": {"narration": "previous"}}
            self.payloads, self.events = [], []
        def checkpoint(self):
            return deepcopy(self.state)
        def _event(self, kind, payload):
            self.events.append((kind, deepcopy(payload)))
        async def generate(self, payload):
            self.payloads.append(deepcopy(payload))
            next_value = self.outcomes.pop(0)
            if isinstance(next_value, BaseException):
                self.state["uuid_counter"] += 2
                self.state["state"]["_memory_controller"]["version"] = "revision-new"
                if self.mutation:
                    self.mutation(self)
                raise next_value
            self.state["head"] += 1
            self.state["turn"] += 1
            return next_value
    return Runtime


class RuntimeRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.Runtime = runtime_class()
        self.handle = install_adapter(self.Runtime, FakeTransport, parse_error_types=(ScenarioError, ParseError))
        self.addCleanup(self.handle.uninstall)
        self.payload = {"player_action": "follow the offered route", "timeline_node_id": 22,
                        "action_check": {"roll": 4, "option_index": 1}}

    async def test_known_parse_failure_reuses_identical_action_die_without_rewind(self):
        runtime = self.Runtime([failure(), {"output": "original successful result"}])
        result = await runtime.generate(self.payload)
        self.assertEqual(result, {"output": "original successful result"})
        self.assertEqual(runtime.payloads, [self.payload, self.payload])
        self.assertEqual(runtime.state["uuid_counter"], 95)
        self.assertEqual(runtime.state["head"], 23)
        self.assertEqual(runtime.events[0][0], "known_parse_retry")
        self.assertTrue(runtime.events[0][1]["state_verified_unchanged"])
        self.assertFalse(runtime.events[0][1]["rewound"])

    async def test_only_two_application_retries_and_error_history_retained(self):
        runtime = self.Runtime([failure(), failure(), failure(), {"must": "not reach"}])
        with self.assertRaises(ScenarioError):
            await runtime.generate(self.payload)
        self.assertEqual(len(runtime.payloads), 3)
        self.assertEqual([x[0] for x in runtime.events], ["known_parse_retry", "known_parse_retry", "known_parse_retry_exhausted"])
        self.assertEqual(runtime.state["head"], 22)

    async def test_actual_state_change_and_commit_prevent_retry(self):
        for mutate in (lambda r: r.state["state"].update(health=99),
                       lambda r: r.state.update(head=23),
                       lambda r: r.state["progress"].update(turns_total=21),
                       lambda r: r.state["state"]["_memory_controller"]["facts"].append("new")):
            runtime = self.Runtime([failure(), {}], mutation=mutate)
            with self.assertRaises(UncertainCapture):
                await runtime.generate(self.payload)
            self.assertEqual(len(runtime.payloads), 1)
            self.assertIsInstance(runtime.transport.fatal, UncertainCapture)

    async def test_unknown_pending_response_prevents_retry(self):
        runtime = self.Runtime([failure(), {}])
        runtime.transport.journal = FakeJournal(("complete", "pending"))
        with self.assertRaises(UncertainCapture):
            await runtime.generate(self.payload)
        self.assertEqual(len(runtime.payloads), 1)

    async def test_timeout_generic_error_and_budget_error_are_never_retried(self):
        plain = ScenarioError("not a parse failure")
        plain.__cause__ = httpx.ReadTimeout("timeout")
        for exc in (plain, httpx.ReadTimeout("timeout"), ValueError("different"), BudgetExceeded("stop")):
            runtime = self.Runtime([exc, {}])
            with self.assertRaises(type(exc)):
                await runtime.generate(self.payload)
            self.assertEqual(len(runtime.payloads), 1)

    async def test_installation_is_idempotent(self):
        self.assertIs(install_adapter(self.Runtime, FakeTransport, parse_error_types=(ScenarioError, ParseError)), self.handle)
        runtime = self.Runtime([failure(), {}])
        await runtime.generate(self.payload)
        self.assertEqual(len(runtime.payloads), 2)

    def test_summary_deduplicates_prefix_observations_of_one_logical_retry(self):
        from jity_eval.capture.runner import _call_summary
        one = {"game_id": "game-03", "turn": 23, "retry_index": 1, "payload_sha256": "same"}
        two = {**one, "retry_index": 2}
        class Journal:
            def stats(self):
                return {}
            def records(self):
                return []
            def events(self):
                return [{"kind": "known_parse_retry", "payload": p} for p in (one, one, two)]
        self.assertEqual(_call_summary(Journal())["known_parse_retries"], [one, two])


class HTTPAttemptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="capture-recovery-adapter-test-")
        self.addCleanup(self.temp.cleanup)
        self.journal = CallJournal(Path(self.temp.name) / "calls.sqlite3")
        self.addCleanup(self.journal.close)
        self.handle = install_adapter(runtime_class(), CaptureTransport, parse_error_types=(ScenarioError, ParseError))
        self.addCleanup(self.handle.uninstall)
        self.sent = 0

    def recording(self, recover=False):
        def upstream(request):
            self.sent += 1
            return httpx.Response(200, json={"choices": [{"message": {"content": "recorded result"}, "finish_reason": "stop"}]})
        return CaptureTransport(self.journal, httpx.MockTransport(upstream), mode="record", recover=recover)

    async def request(self, transport, retry="0", purpose="story_narrator", operation="turn-23"):
        request = httpx.Request("POST", "https://api.example.test/chat/completions", json={"model": "test", "messages": [{"role": "user", "content": "same request"}], "max_tokens": 100},
                                headers={"Authorization": "Bearer TEST_SECRET", "x-stainless-retry-count": retry})
        with capture_scope(game_id="game-03", operation_id=operation, purpose=purpose, turn=23):
            response = await transport.handle_async_request(request)
            return await response.aread()

    async def test_sdk_and_application_retry_headers_share_three_attempt_cap(self):
        transport = self.recording()
        for retry in ("0", "1", "2"):
            await self.request(transport, retry)
        with self.assertRaises(BudgetExceeded):
            await self.request(transport, "0")
        self.assertEqual(self.sent, 3)
        self.assertEqual(len(self.journal.records()), 3)
        self.assertIsInstance(transport.fatal, BudgetExceeded)
        self.assertEqual(self.journal.events()[-1]["kind"], "http_attempt_limit_stop")

    async def test_prefix_reuse_consumes_original_bad_or_good_calls_without_new_attempt(self):
        transport = self.recording()
        for retry in ("0", "1", "2"):
            await self.request(transport, retry)
        replay = CaptureTransport(self.journal, mode="replay")
        for retry in ("0", "1", "2"):
            await self.request(replay, retry)
        replay.assert_consumed()
        self.assertEqual(self.sent, 3)
        recovery = self.recording(recover=True)
        for retry in ("0", "1", "2"):
            await self.request(recovery, retry)
        with self.assertRaises(BudgetExceeded):
            await self.request(recovery, "0")
        self.assertEqual(self.sent, 3)

    async def test_distinct_purpose_and_operation_have_separate_counts(self):
        transport = self.recording()
        for retry in ("0", "1", "2"):
            await self.request(transport, retry)
        await self.request(transport, purpose="story_json_repair")
        await self.request(transport, operation="turn-24")
        self.assertEqual(self.sent, 5)


if __name__ == "__main__":
    unittest.main()
