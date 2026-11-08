"""Fail-closed replay boundaries and actual Jity transition integration."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jity_eval.storage import digest
from jity_eval.replay.cassette import RecordedCalls, make_llm
from jity_eval.replay.sandbox import ForbiddenReplayOperation, MissingRecordedCall, replay_sandbox
from jity_eval.replay.transitions import audit_transitions


JITY_ROOT = Path(__file__).resolve().parents[2]


def recorded_call(turn=1, purpose="story_narrator", messages=None, model="offline-test",
                  temperature=0.35, max_tokens=50000, json_object=True, response='{"narration":"历史回复"}'):
    messages = [{"role": "user", "content": "历史请求"}] if messages is None else messages
    request = {"purpose": purpose, "messages": deepcopy(messages), "model": model,
               "temperature": temperature, "max_tokens": max_tokens, "json_object": json_object}
    return {"turn": turn, "purpose": purpose, "request_sha256": digest(request),
            "response_text": response, "provenance": "test-recording"}, request


class ReplayBoundaryTests(unittest.TestCase):
    """Use a disposable stand-in checkout; never try to write real Jity files."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jity-eval-safety-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.jity = self.root / "Jity"
        marker = self.jity / "backend/app/services/memory/memory_controller/controller.py"
        marker.parent.mkdir(parents=True)
        marker.write_text("# disposable checkout marker\n", encoding="utf-8")
        self.source = self.jity / "original-save.json"
        self.source.write_text('{"untouched":true}', encoding="utf-8")
        self.dotenv = self.jity / ".env"
        self.dotenv.write_text("TEST_SENTINEL=do-not-read\n", encoding="utf-8")
        self.run = self.root / "jity-eval/run"

    def guard(self):
        # A previous integration test may have imported real Jity's app. This
        # test exercises the guard's IO boundary, not checkout import binding.
        return replay_sandbox(self.jity, self.run)

    def test_network_connect_connect_ex_and_dns_fail_before_io(self):
        with patch.dict(sys.modules, {"app": None}):
            with self.guard():
                with socket.socket() as client:
                    with self.assertRaises(ForbiddenReplayOperation):
                        client.connect(("127.0.0.1", 9))
                    with self.assertRaises(ForbiddenReplayOperation):
                        client.connect_ex(("127.0.0.1", 9))
                with self.assertRaises(ForbiddenReplayOperation):
                    socket.getaddrinfo("localhost", 9)

    def test_env_reads_and_original_checkout_writes_are_rejected(self):
        before = self.source.read_bytes()
        with patch.dict(sys.modules, {"app": None}):
            with self.guard():
                with self.assertRaises(ForbiddenReplayOperation):
                    self.dotenv.read_text(encoding="utf-8")
                with self.assertRaises(ForbiddenReplayOperation):
                    self.source.write_text("must never replace source", encoding="utf-8")
                with self.assertRaises(ForbiddenReplayOperation):
                    sqlite3.connect(self.jity / "original.sqlite3")
                with self.assertRaises(ForbiddenReplayOperation):
                    self.source.unlink()
                (self.run / "allowed.json").write_text("{}", encoding="utf-8")
                for path in (":memory:", self.run / "allowed.sqlite3"):
                    with sqlite3.connect(path) as db:
                        db.execute("CREATE TABLE local_test(value INTEGER)")
                        db.execute("INSERT INTO local_test VALUES(1)")
                        self.assertEqual(db.execute("SELECT value FROM local_test").fetchone()[0], 1)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse((self.jity / "original.sqlite3").exists())
        self.assertTrue((self.run / "allowed.json").is_file())

    def test_subprocesses_and_runs_inside_jity_are_rejected(self):
        with self.assertRaises(ValueError):
            with replay_sandbox(self.jity, self.jity / "run"):
                self.fail("must reject a run directory inside Jity")
        with patch.dict(sys.modules, {"app": None}):
            with self.guard():
                with self.assertRaises(ForbiddenReplayOperation):
                    subprocess.run(["jity-eval-command-that-must-never-start"], check=False)

    def test_transition_rejects_output_inside_jity_before_creating_any_files(self):
        target = self.jity / "must-not-create" / "audit"
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            audit_transitions({"initial": {}, "turns": []}, self.jity, target, committed_outputs=True)
        self.assertFalse(target.exists())
        self.assertFalse(target.parent.exists())
        self.assertEqual(self.source.read_bytes(), before)

    def test_guard_restores_import_and_bytecode_state_after_boundary_error(self):
        old_path, old_bytecode = list(sys.path), sys.dont_write_bytecode
        with patch.dict(sys.modules, {"app": None}):
            with self.assertRaises(ForbiddenReplayOperation):
                with self.guard():
                    self.assertTrue(sys.dont_write_bytecode)
                    self.source.write_text("forbidden", encoding="utf-8")
        self.assertEqual(sys.path, old_path)
        self.assertEqual(sys.dont_write_bytecode, old_bytecode)
        # A normal write after leaving the guard confirms scope cleanup.
        (self.root / "after-guard.txt").write_text("ok", encoding="utf-8")


class RecordedCallTests(unittest.TestCase):
    def test_exact_call_replays_once_with_provenance_and_audit(self):
        record, request = recorded_call()
        calls = RecordedCalls([record])
        calls.checkpoint_turn = 1
        record["response_text"] = "mutated caller input"
        self.assertEqual(calls.reply(**request), '{"narration":"历史回复"}')
        self.assertEqual(calls.position, 1)
        self.assertEqual(calls.events[0]["status"], "replayed")
        self.assertEqual(calls.events[0]["provenance"], "test-recording")
        self.assertEqual(calls.events[0]["real_model_calls"], 0)
        with self.assertRaises(MissingRecordedCall):
            calls.reply(**request)
        self.assertEqual(calls.position, 1)

    def test_missing_record_bypasses_ordinary_exception_fallback(self):
        calls = RecordedCalls()
        calls.checkpoint_turn = 7
        _, request = recorded_call()
        swallowed = []
        with self.assertRaisesRegex(MissingRecordedCall, "turn=7.*story_narrator"):
            try:
                calls.reply(**request)
            except Exception:
                swallowed.append(True)
        self.assertEqual(swallowed, [])
        self.assertEqual(calls.events[0]["status"], "missing_recorded_call")

    def test_record_turn_purpose_hash_and_response_type_must_all_match(self):
        record, request = recorded_call()
        for field, value in (("turn", 2), ("purpose", "campaign_director"),
                             ("request_sha256", "wrong"), ("response_text", {"narration": "not raw text"})):
            with self.subTest(field=field):
                bad = {**record, field: value}
                calls = RecordedCalls([bad])
                calls.checkpoint_turn = 1
                with self.assertRaises(MissingRecordedCall):
                    calls.reply(**request)
                self.assertEqual(calls.position, 0)
                self.assertEqual(calls.events[0]["status"], "record_mismatch")

    def test_request_changes_cannot_reuse_a_response(self):
        record, request = recorded_call()
        for field, value in (("messages", [{"role": "user", "content": "另一个问题"}]),
                             ("model", "different-model"), ("temperature", 0.1),
                             ("max_tokens", 10), ("json_object", False)):
            with self.subTest(field=field):
                calls = RecordedCalls([record])
                calls.checkpoint_turn = 1
                with self.assertRaises(MissingRecordedCall):
                    calls.reply(**{**request, field: value})
                self.assertEqual(calls.position, 0)

    def test_call_order_is_strict_not_a_search_for_any_matching_record(self):
        first, request = recorded_call(turn=1)
        second, _ = recorded_call(turn=2)
        calls = RecordedCalls([first, second])
        calls.checkpoint_turn = 2
        with self.assertRaises(MissingRecordedCall):
            calls.reply(**request)
        self.assertEqual(calls.position, 0)
        calls.checkpoint_turn = 1
        calls.reply(**request)
        calls.checkpoint_turn = 2
        calls.reply(**request)
        self.assertEqual(calls.position, 2)


class RealJityReplaySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info < (3, 11):
            raise unittest.SkipTest("真实 Jity 集成测试需要 Python 3.11+")
        if not (JITY_ROOT / "backend/app").is_dir():
            raise unittest.SkipTest("旁边没有 Jity checkout")
        for dependency in ("numpy", "pydantic_settings", "tiktoken", "openai", "json_repair"):
            if importlib.util.find_spec(dependency) is None:
                raise unittest.SkipTest("缺少 Jity 依赖：" + dependency)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jity-eval-real-safety-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def dataset(self, pending_turns=0, include_second=False):
        state = {"turn": pending_turns, "sanity": 80, "health": 100,
                 "current_location": "大厅", "items": [], "npcs": [], "quests": [],
                 "world_facts": [], "player_status": {}, "recent_events": []}
        if pending_turns:
            state["_memory_controller"] = {
                "version": "pending-checkpoint", "round_unit": "turn", "pending": True,
                "nsb": {"turn_buffer": ["[T%s 玩家]: 检查\n[T%s 主持人]: 历史事件" % (i, i)
                                         for i in range(1, pending_turns + 1)]},
                "pcb": {"turns_since": 0}, "score_tracker": [], "narrative_pool": []}
        output = {"narration": "你取得一把旧钥匙。", "current_location": "档案室",
                  "sanity_delta": -2, "health_delta": -1,
                  "items_gained": [{"name": "旧钥匙", "status": "owned"}],
                  "memory_updates": {"key_event": "取得旧钥匙"},
                  "action_check": {"check": {"difficulty": "普通"}, "roll": 17,
                                   "outcome": "success", "degree": "成功", "option_index": 0}}
        next_state = {**deepcopy(state), "turn": pending_turns + 1, "sanity": 79, "health": 99,
                      "current_location": "档案室"}
        turn = {"turn": 1, "turn_id": 102, "player_action": "打开抽屉", "output": output,
                "state": next_state, "campaign_progress": {}, "source": "llm", "model_output": {},
                "action_check": deepcopy(output["action_check"])}
        result = {"initial": {"turn_id": 101, "state": state, "campaign_progress": {}}, "turns": [turn]}
        if include_second:
            second = deepcopy(turn)
            second.update(turn=2, turn_id=103)
            result["turns"].append(second)
        return result

    def test_recorded_llm_uses_real_normalizer_without_constructing_client(self):
        response = '```json\n{"narration":"离线历史", "items_gained":["铜钥匙"], "options":["继续"]}\n```'
        record, _ = recorded_call(response=response)
        calls = RecordedCalls([record])
        calls.checkpoint_turn = 1
        with replay_sandbox(JITY_ROOT, self.root / "llm"):
            with patch("app.services.llm_client.client.AsyncOpenAI", side_effect=AssertionError("real client forbidden")):
                llm = make_llm(calls, self.root / "llm")
                output, latency = asyncio.run(llm.generate("历史请求", model="offline-test", temperature=0.9))
                self.assertEqual(output.items_gained, [{"name": "铜钥匙", "description": "AI 生成记录"}])
                self.assertEqual(output.option_checks, [None])
                self.assertEqual(output.narration, "离线历史")
                self.assertIsNone(llm._client)
                with self.assertRaises(ForbiddenReplayOperation):
                    _ = llm.client
        self.assertEqual(calls.position, 1)
        self.assertEqual(calls.events[0]["request"]["temperature"], 0.35)

    def test_missing_transport_record_escapes_jity_llm_fallbacks(self):
        calls = RecordedCalls()
        calls.checkpoint_turn = 4
        with replay_sandbox(JITY_ROOT, self.root / "llm-missing"):
            llm = make_llm(calls, self.root / "llm-missing")
            with self.assertRaises(MissingRecordedCall):
                asyncio.run(llm.generate("历史请求", model="offline-test"))
            self.assertIsNone(llm._client)
        self.assertEqual(len(calls.events), 1)

    def test_committed_mode_invokes_real_state_and_memory_write_and_keeps_die(self):
        dataset = self.dataset()
        original = deepcopy(dataset)
        with replay_sandbox(JITY_ROOT, self.root / "imports"):
            from app.services.game_state import GameStateManager
            from app.services.memory.memory_controller import MemoryController
        apply_original = GameStateManager.apply_output
        feed_original = MemoryController.on_turn_generated
        invoked = {"apply": 0, "write": 0}

        def real_apply(instance, *args, **kwargs):
            invoked["apply"] += 1
            return apply_original(instance, *args, **kwargs)

        def real_feed(instance, *args, **kwargs):
            invoked["write"] += 1
            return feed_original(instance, *args, **kwargs)

        run = self.root / "transition"
        with patch.object(GameStateManager, "apply_output", real_apply), patch.object(MemoryController, "on_turn_generated", real_feed):
            result = audit_transitions(dataset, JITY_ROOT, run, committed_outputs=True)
        self.assertEqual(result["status"], "completed_boundary_audit")
        self.assertEqual(invoked, {"apply": 1, "write": 1})
        trace = json.loads((run / result["steps"][0]["trace_path"]).read_text())
        self.assertEqual(trace["response_provenance"], "normalized_committed_output")
        self.assertEqual(trace["state_after_apply"]["sanity"], 79)
        self.assertEqual(trace["state_after_apply"]["health"], 99)
        self.assertEqual(trace["state_after_apply"]["current_location"], "档案室")
        self.assertEqual(trace["validated_output"]["action_check"]["roll"], 17)
        self.assertEqual(len(trace["memory_after_write"]["nsb"]["turn_buffer"]), 1)
        self.assertIn("打开抽屉", trace["memory_after_write"]["nsb"]["turn_buffer"][0])
        self.assertTrue(trace["parent_checkpoint_unchanged"])
        self.assertEqual(dataset, original)
        with sqlite3.connect(run / "runtime.sqlite3") as db:
            stored = json.loads(db.execute("SELECT state_json FROM game_sessions WHERE id='offline-transition-audit'").fetchone()[0])
        self.assertEqual(stored["turn"], 1)
        self.assertEqual(stored["items"][0]["name"], "旧钥匙")

    def test_missing_auxiliary_response_stops_after_real_write_before_next_turn(self):
        dataset = self.dataset(pending_turns=5, include_second=True)
        original = deepcopy(dataset)
        run = self.root / "missing-summary"
        result = audit_transitions(dataset, JITY_ROOT, run, committed_outputs=True)
        self.assertEqual(result["status"], "blocked_missing_record")
        self.assertEqual(len(result["steps"]), 1)
        trace = json.loads((run / result["steps"][0]["trace_path"]).read_text())
        self.assertEqual(trace["status"], "missing_call")
        self.assertIn("memory_nsb_summary", trace["error"])
        self.assertEqual(trace["state_after_apply"]["turn"], 6)
        self.assertEqual(len(trace["memory_after_write"]["nsb"]["turn_buffer"]), 6)
        self.assertNotIn("memory_after_maintenance", trace)
        self.assertEqual(trace["calls"][0]["status"], "missing_recorded_call")
        self.assertTrue(trace["parent_checkpoint_unchanged"])
        self.assertEqual(dataset, original)
        self.assertFalse((run / "traces/turn-0002.json").exists())

    def test_strict_mode_does_not_substitute_committed_output_for_missing_call(self):
        dataset = self.dataset()
        dataset["turns"][0]["model_output"] = {"prompt_text": "实际请求", "model": "offline-test"}
        run = self.root / "strict"
        result = audit_transitions(dataset, JITY_ROOT, run)
        self.assertEqual(result["status"], "blocked_missing_record")
        trace = json.loads((run / result["steps"][0]["trace_path"]).read_text())
        self.assertNotIn("state_after_apply", trace)
        self.assertEqual(trace["calls"][0]["request"]["purpose"], "story_narrator")

    def test_consumed_inventory_seeds_score_when_memory_snapshot_is_missing(self):
        dataset = self.dataset()
        dataset["initial"]["state"]["items"] = [{"name": "旧钥匙", "status": "consumed"}]
        run = self.root / "legacy-score"
        result = audit_transitions(dataset, JITY_ROOT, run, committed_outputs=True)
        self.assertEqual(result["status"], "completed_boundary_audit")
        trace = json.loads((run / result["steps"][0]["trace_path"]).read_text())
        self.assertEqual(trace["validated_output"]["items_gained"], [])
        self.assertEqual(trace["state_after_apply"]["items"], [])


if __name__ == "__main__":
    unittest.main()
