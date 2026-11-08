"""Network-free regression coverage for complete HTTP capture and recovery."""
import asyncio
import gzip
import base64
import json
from pathlib import Path
import sqlite3
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx

from jity_eval.capture.journal import (BudgetExceeded, BudgetLedger, CallJournal,
                                      CaptureBoundaryError, MissingCapture, UncertainCapture)
from jity_eval.capture.transport import CaptureTransport, capture_scope, current_scope, network_allowed, network_dns_hosts


LIMITS = {"max_attempts": 20, "max_input_tokens": 100000, "max_output_tokens": 10000, "max_cost_usd": 1.0}
PRICES = {"test-model": {"input_per_million": .30, "output_per_million": 1.20}}
BODY = {"model": "test-model", "messages": [{"role": "user", "content": "Summarize the game"}], "max_tokens": 100}
RAW = json.dumps({"model": "test-model", "choices": [{"message": {"content": "summary"}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16}}).encode()


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks, error=None):
        self.chunks, self.error = chunks, error

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error


class CaptureTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jity-capture-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.journal = CallJournal(self.root / "calls.sqlite3")
        self.addCleanup(self.journal.close)
        self.budget = BudgetLedger(self.root / "budget.sqlite3", LIMITS, PRICES)
        self.addCleanup(self.budget.close)

    async def request(self, transport, body=None, purpose="memory_nsb_summary", operation="game:turn-6"):
        async with httpx.AsyncClient(transport=transport) as client:
            with capture_scope(game_id="game", operation_id=operation, turn=6, purpose=purpose):
                return await client.post("https://api.example.test/v1/chat/completions", json=body or BODY,
                                         headers={"Authorization": "Bearer TEST_SECRET_DO_NOT_SAVE"})

    def record(self, handler=None, **kwargs):
        if handler is None:
            handler = lambda request: httpx.Response(200, content=RAW, headers={"x-request-id": "req-123", "set-cookie": "private"})
        return CaptureTransport(self.journal, httpx.MockTransport(handler), self.budget,
                                allowed_hosts=["api.example.test"], **kwargs)

    async def test_summary_raw_request_response_usage_and_exact_replay(self):
        transport = self.record()
        response = await self.request(transport)
        self.assertEqual(response.content, RAW)
        records = self.journal.records()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["context"]["purpose"], "memory_nsb_summary")
        self.assertEqual(records[0]["request"]["body"], BODY)
        self.assertEqual(base64.b64decode(records[0]["response"]["body_base64"]), RAW)
        self.assertEqual(records[0]["response"]["usage"]["total_tokens"], 16)
        self.assertEqual(self.budget.stats()["attempts"], 1)
        self.assertEqual(self.budget.stats()["input_tokens"], 12)
        self.assertEqual(self.budget.stats()["output_tokens"], 4)
        self.assertNotIn("TEST_SECRET_DO_NOT_SAVE", json.dumps(records))
        self.assertNotIn("authorization", json.dumps(records).lower())
        self.assertNotIn("private", json.dumps(records))
        replay = CaptureTransport(self.journal, mode="replay")
        self.assertEqual((await self.request(replay)).content, RAW)
        self.assertEqual(replay.assert_consumed()["network_attempts"], 0)
        self.assertEqual(self.budget.stats()["attempts"], 1)

    async def test_missing_response_and_request_mismatch_are_fatal(self):
        with self.assertRaises(MissingCapture):
            await self.request(CaptureTransport(self.journal, mode="replay"))
        await self.request(self.record())
        replay = CaptureTransport(self.journal, mode="replay")
        with self.assertRaises(MissingCapture):
            await self.request(replay, body={**BODY, "max_tokens": 101})
        with self.assertRaises(MissingCapture):
            replay.raise_if_failed()

    async def test_purpose_order_and_unused_tail_are_enforced(self):
        await self.request(self.record())
        replay = CaptureTransport(self.journal, mode="replay")
        with self.assertRaises(MissingCapture):
            await self.request(replay, purpose="story_narrator")
        replay = CaptureTransport(self.journal, mode="replay")
        with self.assertRaises(MissingCapture):
            replay.assert_consumed()

    async def test_raw_response_tampering_is_rejected(self):
        await self.request(self.record())
        record = self.journal.records()[0]
        record["response"]["body_base64"] = base64.b64encode(b'{"fabricated":true}').decode()
        with self.journal.transaction() as db:
            db.execute("UPDATE calls SET response=?", (json.dumps(record["response"]),))
        with self.assertRaises(MissingCapture):
            await self.request(CaptureTransport(self.journal, mode="replay"))

    async def test_known_response_recovery_reuses_prefix_without_spending(self):
        await self.request(self.record())
        actual = []
        def handler(request):
            actual.append(request)
            return httpx.Response(200, content=RAW)
        recovering = self.record(handler, recover=True)
        self.assertEqual((await self.request(recovering)).content, RAW)
        self.assertEqual(actual, [])
        self.assertEqual(self.budget.stats()["attempts"], 1)
        self.assertEqual((await self.request(recovering, operation="game:turn-7")).content, RAW)
        self.assertEqual(len(actual), 1)
        self.assertEqual(len(self.journal.records()), 2)

    async def test_recovery_cannot_skip_old_prefix_to_new_operation(self):
        await self.request(self.record())
        sent = []
        recovering = self.record(lambda request: sent.append(request), recover=True)
        with self.assertRaises(MissingCapture):
            await self.request(recovering, operation="game:turn-7")
        self.assertEqual(sent, [])

    async def test_existing_capture_requires_explicit_recovery(self):
        await self.request(self.record())
        with self.assertRaises(UncertainCapture):
            self.record()

    async def test_pending_provider_outcome_never_resends(self):
        await self.request(self.record())
        with self.journal.transaction() as db:
            db.execute("UPDATE calls SET status='pending',response=NULL,finished_at=NULL")
        sent = []
        recovering = self.record(lambda request: sent.append(request), recover=True)
        with self.assertRaises(UncertainCapture):
            await self.request(recovering)
        self.assertEqual(sent, [])

    async def test_timeout_records_and_replays_same_error_without_network(self):
        def handler(request):
            raise httpx.ReadTimeout("timeout Bearer TEST_SECRET_DO_NOT_SAVE", request=request)
        with self.assertRaises(httpx.ReadTimeout):
            await self.request(self.record(handler))
        record = self.journal.records()[0]
        self.assertEqual(record["status"], "error")
        self.assertNotIn("TEST_SECRET_DO_NOT_SAVE", json.dumps(record))
        self.assertEqual(self.budget.stats()["unknown_usage"], 1)
        replay = CaptureTransport(self.journal, mode="replay")
        with self.assertRaises(httpx.ReadTimeout):
            await self.request(replay)
        replay.assert_consumed()

    async def test_stream_chunks_are_durable_and_done_required(self):
        chunks = [b'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null}]}\n\n',
                  b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":12,"completion_tokens":1,"total_tokens":13}}\n\n',
                  b'data: [DONE]\n\n']
        transport = self.record(lambda request: httpx.Response(200, stream=ChunkStream(chunks)))
        response = await self.request(transport, body={**BODY, "stream": True})
        self.assertEqual(response.content, b"".join(chunks))
        stored = self.journal.records()[0]["response"]
        self.assertEqual(stored["assembled_text"], "hello")
        self.assertTrue(stored["eof_observed"])
        self.assertTrue(stored["stream_done"])
        self.assertEqual(stored["chunk_count"], 3)
        self.assertEqual(sum(e["kind"] == "http_response_chunk" for e in self.journal.events()), 3)
        replay = CaptureTransport(self.journal, mode="replay")
        self.assertEqual((await self.request(replay, body={**BODY, "stream": True})).content, response.content)

    async def test_truncated_stream_is_not_a_successful_response(self):
        raw = b'data: {"choices":[{"delta":{"content":"half"},"finish_reason":null}]}\n\n'
        with self.assertRaises(UncertainCapture):
            await self.request(self.record(lambda request: httpx.Response(200, stream=ChunkStream([raw]))),
                               body={**BODY, "stream": True})
        self.assertEqual(self.journal.records()[0]["status"], "incomplete")
        with self.assertRaises(UncertainCapture):
            await self.request(CaptureTransport(self.journal, mode="replay"), body={**BODY, "stream": True})

    async def test_secret_echo_split_across_chunks_is_never_persisted(self):
        chunks = [b'{"error":"TEST_SECRET_', b'DO_NOT_SAVE"}']
        with self.assertRaises(UncertainCapture):
            await self.request(self.record(lambda request: httpx.Response(400, stream=ChunkStream(chunks))))
        record = self.journal.records()[0]
        self.assertEqual(base64.b64decode(record["response"]["body_base64"]), b"")
        self.assertEqual(record["status"], "incomplete")
        events = self.journal.events()
        self.assertTrue(all("body_base64" not in e["payload"] for e in events))
        self.assertNotIn("TEST_SECRET_", json.dumps(events))
        self.assertNotIn("DO_NOT_SAVE", json.dumps(events))

    async def test_gzip_secret_echo_is_not_saved_in_compressed_form(self):
        raw = gzip.compress(b'{"error":"TEST_SECRET_DO_NOT_SAVE"}')
        with self.assertRaises(UncertainCapture):
            await self.request(self.record(lambda request: httpx.Response(400, headers={"content-encoding": "gzip"},
                                                                          stream=ChunkStream([raw]))))
        record = self.journal.records()[0]
        self.assertEqual(record["response"]["body_base64"], "")
        self.assertTrue(record["response"]["redacted"])
        self.assertNotIn(base64.b64encode(raw).decode(), json.dumps(self.journal.events()))

    async def test_embedding_raw_vectors_are_exactly_replayed(self):
        payload = {"model": "test-model", "input": ["查询人物与物品"], "encoding_format": "float"}
        raw = b'{"data":[{"index":0,"embedding":[0.1,-0.2,0.3]}],"usage":{"prompt_tokens":8,"total_tokens":8}}'
        await self.request(self.record(lambda request: httpx.Response(200, content=raw)), payload, "embeddings")
        replay = CaptureTransport(self.journal, mode="replay")
        response = await self.request(replay, payload, "embeddings")
        self.assertEqual(response.content, raw)
        self.assertEqual(self.budget.stats()["output_tokens"], 0)

    async def test_network_scope_only_during_upstream(self):
        observed = []
        def handler(request):
            observed.append(network_allowed.get())
            return httpx.Response(200, content=RAW)
        self.assertFalse(network_allowed.get())
        await self.request(self.record(handler))
        self.assertEqual(observed, [True])
        self.assertFalse(network_allowed.get())

    async def test_background_fatal_remains_visible_after_gather(self):
        transport = CaptureTransport(self.journal, mode="replay")
        results = await asyncio.gather(self.request(transport), return_exceptions=True)
        self.assertIsInstance(results[0], MissingCapture)
        with self.assertRaises(MissingCapture):
            transport.raise_if_failed()

    async def test_interruption_leaves_durable_pending_and_stops_recovery(self):
        class Interrupted(BaseException):
            pass
        def handler(request):
            raise Interrupted()
        transport = self.record(handler)
        with self.assertRaises(Interrupted):
            await self.request(transport)
        self.assertEqual(self.journal.records()[0]["status"], "pending")
        self.assertEqual(self.budget.stats()["outstanding_reservations"], 1)
        with self.assertRaises(UncertainCapture):
            transport.raise_if_failed()
        with self.assertRaises(UncertainCapture):
            await self.request(self.record(lambda request: self.fail("must not resend"), recover=True))

    async def test_crash_after_response_persistence_recovers_original_budget_reservation(self):
        class Interrupted(BaseException):
            pass
        with patch.object(self.budget, "settle", side_effect=Interrupted):
            with self.assertRaises(Interrupted):
                await self.request(self.record())
        self.assertEqual(self.journal.records()[0]["status"], "complete")
        self.assertEqual(self.budget.stats()["outstanding_reservations"], 1)
        recovering = self.record(lambda request: self.fail("must not resend"), recover=True)
        await self.request(recovering)
        self.assertEqual(self.budget.stats()["attempts"], 1)
        self.assertEqual(self.budget.stats()["outstanding_reservations"], 0)
        self.assertEqual(self.budget.stats()["input_tokens"], 12)

    async def test_unrecorded_socket_dns_and_http_client_are_blocked(self):
        from jity_eval.capture.safety import capture_network_guard
        with capture_network_guard():
            with socket.socket() as client:
                with self.assertRaises(CaptureBoundaryError):
                    client.connect(("127.0.0.1", 9))
                with self.assertRaises(CaptureBoundaryError):
                    client.connect_ex(("127.0.0.1", 9))
            with self.assertRaises(CaptureBoundaryError):
                socket.getaddrinfo("never-resolve.invalid", 443)
            async with httpx.AsyncClient(trust_env=False) as client:
                with self.assertRaises(BaseException) as caught:
                    await client.get("https://127.0.0.1:9/")
                def leaves(error):
                    for item in getattr(error, "exceptions", (error,)):
                        if item is error:
                            yield item
                        else:
                            yield from leaves(item)
                self.assertTrue(all(isinstance(e, CaptureBoundaryError) for e in leaves(caught.exception)))

    async def test_unrecorded_executor_dns_is_blocked_before_resolution(self):
        from jity_eval.capture.safety import capture_network_guard
        with capture_network_guard():
            with self.assertRaises(CaptureBoundaryError):
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: sys.audit("socket.getaddrinfo", "never-resolve.invalid", 443, 0, 0, 0))

    async def test_only_current_recorded_hostname_is_authorized_for_executor_dns(self):
        from jity_eval.capture.safety import capture_network_guard
        async def handler(request):
            self.assertEqual(network_dns_hosts["api.example.test"], 1)
            loop = asyncio.get_running_loop()
            # Audit events exercise the decision before native DNS/socket IO.
            await loop.run_in_executor(None, lambda: sys.audit("socket.getaddrinfo", "api.example.test", 443, 0, 0, 0))
            with self.assertRaises(CaptureBoundaryError):
                await loop.run_in_executor(None, lambda: sys.audit("socket.getaddrinfo", "unexpected.invalid", 443, 0, 0, 0))
            with self.assertRaises(CaptureBoundaryError):
                await loop.run_in_executor(None, lambda: sys.audit("socket.connect", None, ("127.0.0.1", 9)))
            return httpx.Response(200, content=RAW)
        with capture_network_guard():
            await self.request(self.record(handler))
        self.assertEqual(dict(network_dns_hosts), {})

    async def test_host_rejection_occurs_before_request_and_budget(self):
        transport = CaptureTransport(self.journal, httpx.MockTransport(lambda request: self.fail("sent")),
                                     self.budget, allowed_hosts=["different.test"])
        with self.assertRaises(UncertainCapture):
            await self.request(transport)
        self.assertEqual(self.budget.stats()["attempts"], 0)
        self.assertEqual(self.journal.records(), [])

    async def test_budget_stop_is_sticky_and_prevents_request(self):
        budget = BudgetLedger(self.root / "tiny.sqlite3", {**LIMITS, "max_attempts": 1}, PRICES)
        self.addCleanup(budget.close)
        sent = []
        def handler(request):
            sent.append(request)
            return httpx.Response(200, content=RAW)
        transport = CaptureTransport(self.journal, httpx.MockTransport(handler), budget)
        await self.request(transport)
        with self.assertRaises(BudgetExceeded):
            await self.request(transport, operation="game:turn-7")
        self.assertEqual(len(sent), 1)
        with self.assertRaises(BudgetExceeded):
            transport.raise_if_failed()

    async def test_sdk_retries_every_attempt_recorded(self):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            self.skipTest("OpenAI dependency not installed")
        sent = []
        def handler(request):
            sent.append(request)
            if len(sent) == 1:
                return httpx.Response(429, json={"error": {"message": "slow down", "type": "rate_limit"}},
                                      headers={"retry-after-ms": "1"})
            return httpx.Response(200, content=RAW)
        transport = self.record(handler)
        client = AsyncOpenAI(api_key="TEST_SECRET_DO_NOT_SAVE", base_url="https://api.example.test/v1", max_retries=1,
                             http_client=httpx.AsyncClient(transport=transport))
        with capture_scope(operation_id="game:turn-1", purpose="story_narrator"):
            reply = await client.chat.completions.create(**BODY)
        await client.close()
        self.assertEqual(reply.choices[0].message.content, "summary")
        self.assertEqual(len(self.journal.records()), 2)
        self.assertEqual(self.journal.stats()["repeated_request_attempts"], 1)
        self.assertEqual(self.journal.stats()["sdk_retry_attempts"], 1)
        replay = CaptureTransport(self.journal, mode="replay")
        client = AsyncOpenAI(api_key="offline-placeholder", base_url="https://api.example.test/v1", max_retries=1,
                             http_client=httpx.AsyncClient(transport=replay))
        with capture_scope(operation_id="game:turn-1", purpose="story_narrator"):
            reply = await client.chat.completions.create(**BODY)
        await client.close()
        self.assertEqual(reply.choices[0].message.content, "summary")
        replay.assert_consumed()
        self.assertEqual(len(sent), 2)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jity-budget-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def ledger(self, name="budget.sqlite3", limits=None, prices=None):
        result = BudgetLedger(self.root / name, limits or LIMITS, PRICES if prices is None else prices)
        self.addCleanup(result.close)
        return result

    def test_all_limits_reserve_before_spending_and_survive_reopen(self):
        ledger = self.ledger(limits={**LIMITS, "max_attempts": 1})
        ledger.reserve(BODY)
        same = self.ledger(limits={**LIMITS, "max_attempts": 1})
        with self.assertRaises(BudgetExceeded):
            same.reserve(BODY)
        self.assertEqual(same.stats()["attempts"], 1)
        self.assertEqual(same.stats()["outstanding_reservations"], 1)

    def test_input_output_cost_and_unpriced_are_independent_stops(self):
        for field, value in (("max_input_tokens", 10), ("max_output_tokens", 5), ("max_cost_usd", .00001)):
            with self.subTest(field=field):
                ledger = self.ledger(field + ".sqlite3", {**LIMITS, field: value})
                with self.assertRaises(BudgetExceeded):
                    ledger.reserve(BODY)
                self.assertEqual(ledger.stats()["attempts"], 0)
        ledger = self.ledger("unpriced.sqlite3", prices={})
        with self.assertRaises(BudgetExceeded):
            ledger.reserve(BODY)

    def test_explicit_unpriced_allowance_is_counted_and_limited(self):
        ledger = self.ledger(limits={**LIMITS, "max_unpriced_attempts": 1}, prices={})
        reservation = ledger.reserve(BODY)
        ledger.settle(reservation, {"prompt_tokens": 10, "completion_tokens": 2})
        self.assertEqual(ledger.stats()["unpriced_attempts"], 1)
        self.assertEqual(ledger.stats()["known_usage_cost_usd"], 0)
        with self.assertRaises(BudgetExceeded):
            ledger.reserve(BODY)

    def test_unknown_usage_keeps_full_reservation_and_config_is_frozen(self):
        ledger = self.ledger()
        reservation = ledger.reserve(BODY)
        before = ledger.stats()
        ledger.settle(reservation)
        self.assertEqual(ledger.stats()["cost_usd"], before["cost_usd"])
        self.assertEqual(ledger.stats()["output_tokens"], 100)
        with self.assertRaises(BudgetExceeded):
            self.ledger(limits={**LIMITS, "max_attempts": 21})

    def test_per_game_cost_and_usage_do_not_mix_other_games(self):
        ledger = self.ledger()
        first = ledger.reserve(BODY, {"game_id": "one"})
        second = ledger.reserve(BODY, {"game_id": "two"})
        ledger.settle(first, {"prompt_tokens": 10, "completion_tokens": 2})
        ledger.settle(second, {"prompt_tokens": 30, "completion_tokens": 8})
        self.assertEqual(ledger.stats("one")["input_tokens"], 10)
        self.assertEqual(ledger.stats("two")["output_tokens"], 8)
        self.assertEqual(ledger.stats()["attempts"], 2)
        self.assertEqual(ledger.stats("absent")["attempts"], 0)

    def test_settlement_is_idempotent_and_underestimated_usage_stops(self):
        ledger = self.ledger()
        reservation = ledger.reserve(BODY)
        ledger.settle(reservation, {"prompt_tokens": 10, "completion_tokens": 2})
        ledger.settle(reservation, {"prompt_tokens": 90, "completion_tokens": 20})
        self.assertEqual(ledger.stats()["input_tokens"], 10)
        other = ledger.reserve(BODY)
        with self.assertRaises(BudgetExceeded):
            ledger.settle(other, {"prompt_tokens": 10, "completion_tokens": 101})
        self.assertEqual(ledger.stats()["output_tokens"], 103)
        self.assertTrue(ledger.stats()["stopped"])
        reopened = self.ledger()
        with self.assertRaises(BudgetExceeded):
            reopened.reserve(BODY)
        with self.assertRaises(BudgetExceeded):
            reopened.settle(other, {"prompt_tokens": 1, "completion_tokens": 1})

    def test_partial_chat_usage_retains_output_and_cost_reservation(self):
        ledger = self.ledger()
        reservation = ledger.reserve(BODY)
        before = ledger.stats()
        ledger.settle(reservation, {"prompt_tokens": 10})
        self.assertEqual(ledger.stats()["output_tokens"], 100)
        self.assertEqual(ledger.stats()["cost_usd"], before["cost_usd"])
        self.assertEqual(ledger.stats()["unknown_usage"], 1)

    def test_fatal_boundary_cannot_be_swallowed_by_exception_fallback(self):
        swallowed = False
        with self.assertRaises(CaptureBoundaryError):
            try:
                raise BudgetExceeded("stop")
            except Exception:
                swallowed = True
        self.assertFalse(swallowed)

    def test_nested_scope_restores_parent(self):
        self.assertEqual(current_scope(), {})
        with capture_scope(operation_id="outer", turn=1):
            with capture_scope(purpose="summary"):
                self.assertEqual(current_scope()["operation_id"], "outer")
                self.assertEqual(current_scope()["purpose"], "summary")
            self.assertNotIn("purpose", current_scope())
        self.assertEqual(current_scope(), {})


if __name__ == "__main__":
    unittest.main()
