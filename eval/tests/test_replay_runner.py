"""Recovery and evidence-boundary tests for offline context replay jobs."""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from jity_eval.replay import runner
from jity_eval.replay.probes import extract_probes
from jity_eval.replay.sandbox import MissingRecordedCall
from jity_eval.storage import digest


JITY_ROOT = Path(__file__).resolve().parents[2]


def small_dataset():
    initial = {"turn": 0, "sanity": 80, "health": 100, "current_location": "档案馆",
               "items": [], "npcs": [], "quests": [], "world_facts": [], "player_status": {}}
    dataset = {"source": {"session_id": "synthetic-runner-fixture"},
               "initial": {"turn_id": 100, "state": deepcopy(initial), "campaign_progress": {}},
               "turns": [], "call_records": []}
    for turn in range(1, 5):
        state = deepcopy(initial)
        state["turn"] = turn
        state["world_facts"] = [{"name": "备用钥匙位置", "description": "蓝色门楣的夹层"}]
        state["_memory_controller"] = {"version": "v%s" % turn, "round_unit": "turn", "pending": False,
                                       "nsb": {}, "pcb": {}, "score_tracker": [], "narrative_pool": []}
        output = {"narration": "你继续整理值班登记。", "dialogue": [], "memory_updates": {}}
        if turn == 1:
            output["narration"] = "你确认备用钥匙位置是蓝色门楣的夹层。"
            output["memory_updates"] = {"world_facts_upserted": deepcopy(state["world_facts"])}
        dataset["turns"].append({"turn": turn, "turn_id": 100 + turn, "player_action": "整理值班登记。",
                                 "state": state, "output": output, "campaign_progress": {}, "source": "llm"})
    return dataset


def fake_context(dataset, checkpoint, question, mode, recent_window, budget):
    snapshot = dataset["turns"][checkpoint - 1]
    state_hash = digest(snapshot["state"])
    return {"mode": mode, "checkpoint_input_hash": digest(snapshot),
            "backend_state_hash_before": state_hash, "backend_state_hash_after": state_hash,
            "messages": [{"role": "user", "content": question}], "probe_answer": None,
            "real_model_calls": 0, "retrieval_hits": [], "injected_memory_hits": [],
            "channel_policy": {}, "truncation": {"tokens_after": 10, "applied": False},
            "leak_audit": {"passed": True, "findings": []}}


class ReplayRunnerTests(unittest.TestCase):
    """No Jity dependency or network required for scheduler boundary tests."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="jity-eval-runner-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fake_jity = self.root / "fake-jity"
        self.source = self.fake_jity / "backend/app/code.py"
        self.source.parent.mkdir(parents=True)
        self.source.write_text("VERSION = 1\n", encoding="utf-8")
        self.dataset = small_dataset()
        self.document = extract_probes(self.dataset, delays=(1,))
        self.run = self.root / "run"
        self.guard = patch.object(runner, "replay_sandbox", side_effect=lambda *_: nullcontext())
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def create(self, path=None, document=None, repeats=1):
        with patch.object(runner, "load_dataset", return_value=deepcopy(self.dataset)):
            return runner.create_context_run(self.root / "source-dataset.json", self.fake_jity,
                                             path or self.run, document or self.document, repeats=repeats)

    def trace(self, row):
        return json.loads((self.run / row["trace_path"]).read_text(encoding="utf-8"))

    def attempts(self):
        with sqlite3.connect(self.run / "run.sqlite3") as db:
            return db.execute("SELECT id,attempt,status FROM attempts ORDER BY id,attempt").fetchall()

    def test_pause_resume_keeps_completed_jobs_and_probe_answers_unset(self):
        self.create()
        with patch("jity_eval.replay.context.build_context", side_effect=fake_context) as builder:
            first = runner.execute_context_run(self.run, max_samples=2)
            self.assertEqual(first["status"], "paused")
            self.assertEqual(first["counts"]["assembled"], 2)
            finished = {row["id"]: (row["trace_path"], (self.run / row["trace_path"]).read_bytes())
                        for row in first["samples"] if row["status"] == "assembled"}
            final = runner.execute_context_run(self.run)
            self.assertEqual(builder.call_count, 6)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(final["counts"]["assembled"], final["total"])
            self.assertEqual(final["total"], 6)
            for row in final["samples"]:
                self.assertEqual(row["attempts"], 1)
                if row["id"] in finished:
                    relative, content = finished[row["id"]]
                    self.assertEqual(row["trace_path"], relative)
                    self.assertEqual((self.run / relative).read_bytes(), content)
                trace = self.trace(row)
                self.assertIsNone(trace["probe_answer"])
                self.assertEqual(trace["real_model_calls"], 0)
            self.assertNotIn("passed", final["counts"])
            self.assertNotIn("accuracy", final)
            self.assertNotIn("score", final)
        self.assertTrue((self.run / "report.html").is_file())

    def test_all_modes_share_checkpoint_hash_and_repeats_have_distinct_jobs(self):
        self.create(repeats=2)
        with patch("jity_eval.replay.context.build_context", side_effect=fake_context):
            result = runner.execute_context_run(self.run)
        self.assertEqual(result["total"], 12)
        self.assertEqual(len({row["id"] for row in result["samples"]}), 12)
        groups = {}
        for row in result["samples"]:
            trace = self.trace(row)
            self.assertEqual(trace["backend_state_hash_before"], trace["backend_state_hash_after"])
            groups.setdefault((row["probe_id"], row["repeat"]), []).append(trace)
        self.assertTrue(all(len(group) == 3 for group in groups.values()))
        self.assertTrue(all(len({trace["checkpoint_input_hash"] for trace in group}) == 1
                            for group in groups.values()))

    def test_missing_call_and_error_require_explicit_retry_and_keep_history(self):
        self.create()
        invocation = 0

        def failing(*args):
            nonlocal invocation
            invocation += 1
            if invocation == 1:
                raise MissingRecordedCall("Missing recorded NSB response")
            if invocation == 2:
                raise ValueError("Bad context fixture")
            return fake_context(*args)

        with patch("jity_eval.replay.context.build_context", side_effect=failing):
            first = runner.execute_context_run(self.run)
        self.assertEqual(first["status"], "completed_with_errors")
        self.assertEqual(first["counts"]["missing_call"], 1)
        self.assertEqual(first["counts"]["error"], 1)
        error_traces = {row["id"]: (row["trace_path"], (self.run / row["trace_path"]).read_bytes())
                        for row in first["samples"] if row["status"] in ("missing_call", "error")}
        with patch("jity_eval.replay.context.build_context", side_effect=fake_context) as builder:
            still_failed = runner.execute_context_run(self.run)
            self.assertEqual(still_failed["status"], "completed_with_errors")
            builder.assert_not_called()
            final = runner.execute_context_run(self.run, retry_errors=True)
            self.assertEqual(builder.call_count, 2)
        self.assertEqual(final["counts"]["assembled"], 6)
        self.assertEqual(final["status"], "completed")
        self.assertEqual(sum(row["attempts"] == 2 for row in final["samples"]), 2)
        statuses = [row[2] for row in self.attempts()]
        self.assertIn("missing_call", statuses)
        self.assertIn("error", statuses)
        for _, (path, content) in error_traces.items():
            self.assertEqual((self.run / path).read_bytes(), content)

    def test_keyboard_interrupt_recovers_only_inflight_work(self):
        self.create()
        invocation = 0

        def interrupting(*args):
            nonlocal invocation
            invocation += 1
            if invocation == 2:
                raise KeyboardInterrupt()
            return fake_context(*args)

        with patch("jity_eval.replay.context.build_context", side_effect=interrupting):
            with self.assertRaises(KeyboardInterrupt):
                runner.execute_context_run(self.run)
        paused = json.loads((self.run / "results.json").read_text())
        self.assertEqual(paused["counts"]["assembled"], 1)
        self.assertEqual(paused["counts"]["running"], 1)
        completed = next(row for row in paused["samples"] if row["status"] == "assembled")
        original_trace = (self.run / completed["trace_path"]).read_bytes()
        with patch("jity_eval.replay.context.build_context", side_effect=fake_context) as builder:
            final = runner.execute_context_run(self.run)
        self.assertEqual(builder.call_count, 5)
        self.assertEqual(final["counts"]["assembled"], 6)
        self.assertEqual(sum(row["attempts"] == 2 for row in final["samples"]), 1)
        self.assertIn("interrupted", [row[2] for row in self.attempts()])
        self.assertEqual((self.run / completed["trace_path"]).read_bytes(), original_trace)

    def test_private_gold_is_not_passed_to_context_builder_or_model_messages(self):
        document = deepcopy(self.document)
        for answer in document["gold"]:
            answer["private_review_note"] = "GOLD_ONLY_SENTINEL_DO_NOT_EXPOSE"
        self.create(document=document)
        calls = []

        def spy(*args, **kwargs):
            calls.append((deepcopy(args), deepcopy(kwargs)))
            self.assertEqual(len(args), 6)
            self.assertFalse(kwargs)
            self.assertNotIn("GOLD_ONLY_SENTINEL_DO_NOT_EXPOSE", json.dumps([args, kwargs], ensure_ascii=False))
            self.assertNotIn("gold", args[0])
            self.assertNotIn("expected_value", args[0])
            return fake_context(*args)

        with patch("jity_eval.replay.context.build_context", side_effect=spy):
            result = runner.execute_context_run(self.run)
        self.assertEqual(len(calls), 6)
        for row in result["samples"]:
            self.assertNotIn("GOLD_ONLY_SENTINEL_DO_NOT_EXPOSE", json.dumps(self.trace(row)))
            self.assertNotIn("expected_value", row)
        self.assertIn("GOLD_ONLY_SENTINEL_DO_NOT_EXPOSE", (self.run / "inputs/gold.json").read_text())

    def test_frozen_input_tampering_is_rejected_before_building(self):
        for name in ("dataset", "probes", "gold", "source"):
            with self.subTest(input=name):
                run = self.create(path=self.root / ("tamper-" + name))
                path = run / "inputs" / (name + ".json")
                path.write_text(path.read_text() + "\n", encoding="utf-8")
                with patch("jity_eval.replay.context.build_context") as builder:
                    with self.assertRaisesRegex(ValueError, "冻结输入"):
                        runner.execute_context_run(run)
                    builder.assert_not_called()

    def test_source_change_is_rejected_and_does_not_touch_real_jity(self):
        self.create()
        runner.verify_run(self.run)
        self.source.write_text("VERSION = 2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "源码已变化"):
            runner.verify_run(self.run)
        with patch("jity_eval.replay.context.build_context") as builder:
            with self.assertRaisesRegex(ValueError, "源码已变化"):
                runner.execute_context_run(self.run)
            builder.assert_not_called()

    def test_manifest_and_job_plan_tampering_are_rejected(self):
        self.create()
        path = self.run / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["config"]["repeats"] = 99
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "manifest"):
            runner.verify_run(self.run)
        other = self.create(path=self.root / "changed-plan")
        with sqlite3.connect(other / "run.sqlite3") as db:
            identifier, raw = db.execute("SELECT id,spec FROM jobs LIMIT 1").fetchone()
            spec = json.loads(raw)
            spec["mode"] = "unknown"
            db.execute("UPDATE jobs SET spec=? WHERE id=?", (json.dumps(spec), identifier))
        with self.assertRaisesRegex(ValueError, "计划"):
            runner.verify_run(other)


class ReplayRunnerRealJityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info < (3, 11):
            raise unittest.SkipTest("真实 Jity 集成需要 Python 3.11+")
        if not (JITY_ROOT / "backend/app").is_dir():
            raise unittest.SkipTest("缺少旁边的 Jity checkout")
        for dependency in ("numpy", "pydantic_settings", "tiktoken", "openai", "json_repair"):
            if importlib.util.find_spec(dependency) is None:
                raise unittest.SkipTest("缺少 Jity 依赖：" + dependency)

    def test_real_contexts_are_isolated_unanswered_and_resumable(self):
        dataset = small_dataset()
        before = deepcopy(dataset)
        document = extract_probes(dataset, delays=(1,))
        with tempfile.TemporaryDirectory(prefix="jity-eval-real-runner-") as temporary:
            run = Path(temporary) / "run"
            with patch.object(runner, "load_dataset", return_value=dataset):
                runner.create_context_run(Path(temporary) / "dataset.json", JITY_ROOT, run, document)
            first = runner.execute_context_run(run, max_samples=3)
            self.assertEqual(first["counts"]["assembled"], 3)
            first_paths = {row["id"]: (row["trace_path"], (run / row["trace_path"]).read_bytes())
                           for row in first["samples"] if row["status"] == "assembled"}
            final = runner.execute_context_run(run)
            self.assertEqual(final["counts"]["assembled"], 6)
            self.assertEqual(final["counts"]["error"], 0)
            self.assertEqual(final["counts"]["missing_call"], 0)
            groups = {}
            for row in final["samples"]:
                trace = json.loads((run / row["trace_path"]).read_text())
                groups.setdefault(row["probe_id"], []).append(trace)
                self.assertEqual(trace["backend_state_hash_before"], trace["backend_state_hash_after"])
                self.assertIsNone(trace["probe_answer"])
                self.assertEqual(trace["real_model_calls"], 0)
                self.assertTrue(trace["leak_audit"]["passed"])
                self.assertEqual(row["attempts"], 1)
                if row["id"] in first_paths:
                    original_path, content = first_paths[row["id"]]
                    self.assertEqual(row["trace_path"], original_path)
                    self.assertEqual((run / original_path).read_bytes(), content)
            for contexts in groups.values():
                self.assertEqual(len(contexts), 3)
                self.assertEqual(len({c["checkpoint_input_hash"] for c in contexts}), 1)
            self.assertEqual(dataset, before)
            self.assertNotIn("accuracy", final)
            self.assertTrue((run / "report.html").is_file())


if __name__ == "__main__":
    unittest.main()
