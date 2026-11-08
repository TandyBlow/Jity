"""Complete Jity pipeline against recorded HTTP replies; never real APIs."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from jity_eval.capture.runtime import JityRuntime, normalize_checkpoint
from jity_eval.replay.sandbox import replay_sandbox


JITY_ROOT = Path(__file__).resolve().parents[2]


class CaptureRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info < (3, 11) or not (JITY_ROOT / "backend/app").is_dir():
            raise unittest.SkipTest("Jity runtime requires Python 3.11 and the parent Jity checkout")
        for dependency in ("numpy", "pydantic_settings", "tiktoken", "openai", "json_repair", "httpx"):
            if importlib.util.find_spec(dependency) is None:
                raise unittest.SkipTest("Missing Jity dependency: " + dependency)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jity-capture-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        campaigns = self.root / "campaigns"
        campaigns.mkdir()
        knowledge = self.root / "knowledge"
        knowledge.mkdir()
        (knowledge / "locations.json").write_text(json.dumps([{"name": "档案室", "content": "档案室的旧卷宗", "type": "location"}], ensure_ascii=False))
        campaign = {"version": 1, "title": "完整录制测试", "core_conflict": "寻找记录", "max_turns_per_campaign": 50,
                    "arcs": [{"name": "寻访", "goal": "阅读档案", "sessions": [{"name": "档案室", "opening_scene": "你走进档案室。",
                    "anchor_events": [{"id": "never-forced", "name": "尚未抵达", "description": "抵达高塔",
                                       "trigger_conditions": {"location": "高塔"}}]}]}]}
        (campaigns / "default_campaign.json").write_text(json.dumps(campaign, ensure_ascii=False))
        self.config = {"game_id": "test", "session_id": "stable-test-session", "seed": 91, "campaigns_dir": str(campaigns),
                       "knowledge_dir": str(knowledge), "rulebook_file": str(self.root / "absent.md"),
                       "llm_model": "deepseek-flash", "llm_base_url": "https://capture.invalid/v1",
                       "max_retries": 0, "tokenizer": "offline-estimator", "embeddings": True}
        self.requests = []

    def upstream(self):
        import httpx

        async def handler(request):
            body = json.loads(request.content)
            self.requests.append(body)
            if request.url.path.endswith("/embeddings"):
                return httpx.Response(404, json={"error": {"message": "unsupported embedding", "type": "not_found"}})
            prompt = body["messages"][0]["content"]
            if prompt.startswith("你是TRPG叙事摘要系统"):
                result = {"summary": "你检查了档案室的旧卷宗，记住关键记录。", "tags": ["档案"], "importance": .7}
            elif "TRPG叙事导演系统（Director）" in prompt:
                result = {"narrative_direction": "继续调查档案", "anchor_triggered": ""}
            elif len(self.requests) == 1:
                result = {"options": ["查看档案", "继续"], "option_checks": [{"name": "调查", "difficulty": "普通"}, None]}
            else:
                result = {"narration": "你认真查看旧卷宗，记住其中的细节。", "current_location": "档案室",
                          "options": ["继续"], "option_checks": [None], "memory_updates": {"key_event": "检查了卷宗"}}
            return httpx.Response(200, json={"id": "fixture-completion", "object": "chat.completion", "created": 1,
                "model": body["model"], "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}})

        return httpx.MockTransport(handler)

    async def record_six(self):
        from jity_eval.capture.journal import CallJournal
        from jity_eval.capture.transport import CaptureTransport
        journal = CallJournal(self.root / "calls.sqlite3")
        transport = CaptureTransport(journal, upstream=self.upstream(), mode="record")
        runtime = JityRuntime(JITY_ROOT, self.root / "record", config=self.config, transport=transport, event_sink=journal.event)
        checkpoints, payloads = [], []
        try:
            initial = await runtime.start()
            for turn in range(6):
                payload = await runtime.prepare("开始" if turn == 0 else "继续")
                payloads.append(payload)
                await runtime.generate(payload)
                checkpoints.append(runtime.checkpoint())
            reloaded = await runtime.reload()
            self.assertEqual(reloaded, checkpoints[-1])
            runtime.backup(self.root / "captured.sqlite3")
        finally:
            await runtime.close()
        return journal, initial, payloads, checkpoints

    def test_six_turns_cover_background_summary_and_strict_full_replay(self):
        async def run():
            from jity_eval.capture.transport import CaptureTransport
            journal, initial, payloads, checkpoints = await self.record_six()
            self.addCleanup(journal.close)
            purposes = [row["context"].get("purpose") for row in journal.records()]
            self.assertIn("memory_nsb_summary", purposes)
            self.assertIn("campaign_director", purposes)
            self.assertIn("story_narrator", purposes)
            self.assertEqual(purposes.count("embedding"), 2)
            self.assertTrue(checkpoints[-1]["state"]["_memory_controller"]["nsb"]["level1"])
            transport = CaptureTransport(journal, mode="replay")
            before_count = len(self.requests)
            with replay_sandbox(JITY_ROOT, self.root):
                runtime = JityRuntime(JITY_ROOT, self.root / "replay", config=self.config, transport=transport)
                try:
                    self.assertEqual(await runtime.start(), initial)
                    for payload, checkpoint in zip(payloads, checkpoints):
                        await runtime.generate(payload)
                        self.assertEqual(runtime.checkpoint(), checkpoint)
                    self.assertEqual(await runtime.reload(), checkpoints[-1])
                    transport.assert_consumed()
                finally:
                    await runtime.close()
            self.assertEqual(len(self.requests), before_count)
            self.assertTrue(all(body.get("thinking") == {"type": "disabled"}
                                for body in self.requests if "messages" in body))
            kinds = [event["kind"] for event in journal.events()]
            for kind in ("story_parsed", "output_validation", "memory_write", "memory_maintenance_end", "retrieval", "turn_committed", "reload_verified"):
                self.assertIn(kind, kinds)
            warnings = [event["payload"] for event in journal.events() if event["kind"] == "runtime_warning"]
            self.assertTrue(any("falling back" in event["message"] for event in warnings))
            self.assertTrue(all("traceback" not in event for event in warnings))
            self.assertNotIn("app.dependencies.singletons", sys.modules)
        asyncio.run(run())

    def test_missing_background_summary_propagates_beyond_jity_fallbacks(self):
        async def run():
            from jity_eval.capture.journal import MissingCapture
            from jity_eval.capture.transport import CaptureTransport
            journal, _, payloads, _ = await self.record_six()
            self.addCleanup(journal.close)
            with journal.transaction() as db:
                db.execute("DELETE FROM calls WHERE context LIKE '%memory_nsb_summary%'")
            with replay_sandbox(JITY_ROOT, self.root):
                runtime = JityRuntime(JITY_ROOT, self.root / "missing", config=self.config,
                                      transport=CaptureTransport(journal, mode="replay"))
                try:
                    await runtime.start()
                    for payload in payloads[:-1]:
                        await runtime.generate(payload)
                    with self.assertRaises(MissingCapture):
                        await runtime.generate(payloads[-1])
                finally:
                    await runtime.close()
        asyncio.run(run())

    def test_die_is_required_preserved_and_stale_action_cannot_submit_twice(self):
        async def run():
            from jity_eval.capture.journal import CallJournal
            from jity_eval.capture.transport import CaptureTransport
            from app.exceptions import ConcurrentModificationError
            journal = CallJournal(self.root / "dice.sqlite3")
            self.addCleanup(journal.close)
            runtime = JityRuntime(JITY_ROOT, self.root / "dice", config=self.config,
                                  transport=CaptureTransport(journal, upstream=self.upstream(), mode="record"))
            try:
                await runtime.start()
                await runtime.generate(await runtime.prepare("开始"))
                with self.assertRaisesRegex(ValueError, "persisted die"):
                    await runtime.prepare("查看档案", option_index=0)
                payload = await runtime.prepare("查看档案", option_index=0, roll=3)
                response = await runtime.generate(payload)
                self.assertEqual(response["output"]["action_check"]["roll"], 3)
                self.assertEqual(response["output"]["action_check"]["outcome"], "failure")
                before, calls_before = runtime.checkpoint(), len(self.requests)
                with self.assertRaises(ConcurrentModificationError):
                    await runtime.generate(payload)
                self.assertEqual(runtime.checkpoint(), before)
                self.assertEqual(len(self.requests), calls_before)
            finally:
                await runtime.close()
        # Imports occur inside runtime; use the normal startup once first.
        sys.path.insert(0, str(JITY_ROOT / "backend"))
        try:
            asyncio.run(run())
        finally:
            sys.path.pop(0)

    def test_normalization_preserves_real_state_and_revision_identity(self):
        original = {"progress": {"updated_at": "clock", "turns_total": 6},
                    "state": {"_memory_controller": {"version": "unique"}, "updated_at": "game fact"}, "uuid_counter": 9}
        result = normalize_checkpoint(original)
        self.assertNotIn("updated_at", result["progress"])
        self.assertEqual(result["state"], original["state"])
        self.assertEqual(result["uuid_counter"], 9)

    def test_warning_observer_redacts_secrets_and_is_removed_on_close(self):
        async def run():
            import logging
            from jity_eval.capture.journal import CallJournal
            from jity_eval.capture.transport import CaptureTransport
            journal = CallJournal(self.root / "warning.sqlite3")
            self.addCleanup(journal.close)
            logger = logging.getLogger("app.capture_fixture")
            parent = logging.getLogger("app")
            handlers_before = list(parent.handlers)
            propagate_before = parent.propagate
            runtime = JityRuntime(JITY_ROOT, self.root / "warnings", config=self.config,
                                  transport=CaptureTransport(journal, upstream=self.upstream()),
                                  api_key="fixture-private-credential", event_sink=journal.event)
            try:
                try:
                    raise ValueError("fixture-private-credential must not leak")
                except ValueError:
                    logger.warning("fallback fixture-private-credential", exc_info=True)
                events = journal.events()
                warning = [event["payload"] for event in events if event["kind"] == "runtime_warning"][0]
                self.assertEqual(warning["exception_type"], "ValueError")
                self.assertIn("[REDACTED]", warning["message"])
                self.assertNotIn("fixture-private-credential", json.dumps(events))
            finally:
                await runtime.close()
            self.assertEqual(parent.handlers, handlers_before)
            self.assertEqual(parent.propagate, propagate_before)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
