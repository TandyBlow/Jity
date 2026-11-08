"""Offline evaluator infrastructure tests. No model API or network is used."""
from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from jity_eval.offline import OfflineSession, grade
from jity_eval.storage import run_lock


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def event(turn, value=None, storage="both", fact_id="key"):
    return {"turn": turn, "text": "正常剧情继续。" if value is None else "事实：" + value,
            "facts": [] if value is None else [{"id": fact_id, "value": value, "storage": storage}]}


def probe(kind="recall", fact_id="key"):
    return {"id": "probe", "fact_id": fact_id, "kind": kind,
            "question": "回忆相关事实并按要求行动。", "source_turn": 1, "delay": 10}


class OfflineAdapterTests(unittest.TestCase):
    def setUp(self):
        self.session = OfflineSession()
        self.session.ingest(event(1, "叙事独有证据", "narrative", "narrative_fact"))
        self.session.ingest(event(2, "旧值"))
        self.session.ingest(event(3, "新值"))
        for turn in range(4, 15):
            self.session.ingest(event(turn))

    def test_full_and_state_obey_channel_visibility(self):
        full = self.session.probe(probe(fact_id="narrative_fact"), "full", 5)
        state = self.session.probe(probe(fact_id="narrative_fact"), "state", 5)
        recent = self.session.probe(probe(fact_id="narrative_fact"), "recent", 5)
        self.assertEqual(full["parsed_draft"]["value"], "叙事独有证据")
        self.assertIsNone(state["parsed_draft"]["value"])
        self.assertIsNone(recent["parsed_draft"]["value"])
        self.assertNotIn("叙事独有证据", json.dumps(state["visible_context"], ensure_ascii=False))
        self.assertNotIn("叙事独有证据", json.dumps(recent["visible_context"], ensure_ascii=False))

    def test_state_update_uses_latest_evidence(self):
        for mode in ("full", "state"):
            answer = self.session.probe(probe(), mode, 5)["parsed_draft"]
            self.assertEqual(answer["value"], "新值")
            self.assertEqual(answer["evidence_turn"], 3)
        self.assertIsNone(self.session.probe(probe(), "recent", 5)["parsed_draft"]["value"])

    def test_recent_window_can_use_recent_fact(self):
        self.session.ingest(event(15, "近期可见值"))
        answer = self.session.probe(probe(), "recent", 5)["parsed_draft"]
        self.assertEqual(answer["value"], "近期可见值")

    def test_unknown_is_abstention_and_action_requests_information(self):
        for kind, expected in (("recall", "abstain"), ("action", "ask_for_information")):
            response = self.session.probe(probe(kind, "unknown"), "full", 5)
            self.assertIsNone(response["parsed_draft"]["value"])
            self.assertEqual(response["parsed_draft"]["decision"], expected)
            self.assertEqual(grade(response["parsed_draft"], None, kind)["status"], "passed")

    def test_backend_truth_and_gold_are_not_answer_sources(self):
        self.assertNotIn("gold", inspect.signature(OfflineSession.probe).parameters)
        self.session.truth["key"]["value"] = "HIDDEN-TRUTH-SENTINEL"
        for mode in ("full", "state", "recent"):
            response = self.session.probe(probe(), mode, 5)
            self.assertNotIn("HIDDEN-TRUTH-SENTINEL", json.dumps(response["visible_context"]))
            self.assertNotIn("HIDDEN-TRUTH-SENTINEL", response["raw_response"])
            self.assertNotIn("expected_value", response["probe_input"])

    def test_snapshot_and_probe_forks_are_deeply_isolated(self):
        checkpoint = self.session.checkpoint()
        original = copy.deepcopy(checkpoint)
        left, right = OfflineSession.fork(checkpoint), OfflineSession.fork(checkpoint)
        left.probe(probe("action"), "full", 5)
        left.ingest(event(15, "左分支新值"))
        self.assertEqual(checkpoint, original)
        self.assertEqual(self.session.checkpoint(), original)
        self.assertEqual(right.checkpoint(), original)
        checkpoint["truth"]["key"]["value"] = "外部篡改"
        self.assertEqual(self.session.truth["key"]["value"], "新值")

    def test_evidence_stages_have_independent_snapshots(self):
        trace = self.session.probe(probe(), "full", 5)
        for key in ("visible_context", "raw_response", "parsed_draft", "validated_output", "committed_state"):
            self.assertIn(key, trace)
        self.assertEqual(trace["real_model_calls"], 0)
        self.assertTrue(trace["simulation"])
        self.assertFalse(trace["validation"]["applied"])
        trace["parsed_draft"]["value"] = "changed"
        self.assertEqual(trace["validated_output"]["value"], "新值")
        self.assertEqual(json.loads(trace["raw_response"])["value"], "新值")

    def test_grading_requires_value_and_correct_action(self):
        result = grade({"value": "新值", "decision": "ask_for_information"}, "新值", "action")
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["is_model_evaluation"])
        for malformed in (None, {}, {"value": "x"}, {"value": 42, "decision": "answer"}):
            with self.assertRaises(ValueError):
                grade(malformed, "x", "recall")


class RunnerIntegrationTests(unittest.TestCase):
    def setUp(self):
        from jity_eval.runner import create_run, execute, read_results
        self.create_run, self.execute, self.read_results = create_run, execute, read_results
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.run = self.directory / "run"

    def create(self, config="pilot.json"):
        self.create_run(EXAMPLES / config, self.run)

    def test_partial_resume_does_not_rerun_completed_samples(self):
        self.create()
        first = self.execute(self.run, max_samples=7)
        self.assertEqual(first["total"], 144)
        self.assertEqual(first["counts"]["pending"], 137)
        completed_ids = {s["sample_id"] for s in first["samples"] if s["attempts"] == 1}
        self.assertEqual(len(completed_ids), 7)
        final = self.execute(self.run)
        self.assertEqual(final["counts"]["passed"] + final["counts"]["failed"], 144)
        self.assertEqual(final["real_model_calls"], 0)
        self.assertTrue(all(s["attempts"] == 1 for s in final["samples"]))
        again = self.execute(self.run)
        self.assertEqual([(s["sample_id"], s["attempts"], s["status"]) for s in final["samples"]],
                         [(s["sample_id"], s["attempts"], s["status"]) for s in again["samples"]])
        sample = next(s for s in final["samples"] if s["status"] == "passed")
        trace = json.loads((self.run / sample["trace_path"]).read_text())
        for key in ("raw_response", "parsed_draft", "validated_output", "committed_state"):
            self.assertIn(key, trace)

    def test_resume_uses_frozen_inputs_not_changed_originals(self):
        source = self.directory / "source"
        shutil.copytree(EXAMPLES, source)
        self.create_run(source / "pilot.json", self.run)
        self.execute(self.run, max_samples=1)
        (source / "pilot.suite.json").write_text("not valid JSON")
        (source / "pilot.gold.json").unlink()
        final = self.execute(self.run, max_samples=1)
        self.assertEqual(final["counts"]["passed"] + final["counts"]["failed"], 2)
        self.assertEqual(final["counts"]["pending"], 142)

    def test_tampered_frozen_input_is_rejected(self):
        self.create()
        target = self.run / "inputs" / "suite.json"
        target.write_text(target.read_text() + "\n ")
        with self.assertRaises(ValueError):
            self.execute(self.run)

    def test_errors_are_terminal_until_explicit_retry(self):
        self.create("faults.json")
        first = self.execute(self.run)
        self.assertEqual(first["counts"]["adapter_error"], 1)
        self.assertEqual(first["counts"]["grading_error"], 1)
        errors = {s["sample_id"] for s in first["samples"] if s["status"].endswith("_error")}
        self.assertEqual(len(errors), 2)
        no_retry = self.execute(self.run)
        self.assertTrue(all(s["attempts"] == 1 for s in no_retry["samples"]))
        retried = self.execute(self.run, retry_errors=True)
        self.assertEqual(retried["counts"]["adapter_error"], 0)
        self.assertEqual(retried["counts"]["grading_error"], 0)
        for sample in retried["samples"]:
            self.assertEqual(sample["attempts"], 2 if sample["sample_id"] in errors else 1)
        with sqlite3.connect(self.run / "run.sqlite3") as connection:
            attempts = connection.execute("SELECT status FROM attempts WHERE attempt=1").fetchall()
        self.assertIn(("adapter_error",), attempts)
        self.assertIn(("grading_error",), attempts)

    def test_running_sample_recovers_as_new_attempt(self):
        self.create()
        with sqlite3.connect(self.run / "run.sqlite3") as connection:
            sample_id = connection.execute("SELECT id FROM samples ORDER BY ordinal LIMIT 1").fetchone()[0]
            connection.execute("UPDATE samples SET status='running', attempts=1 WHERE id=?", (sample_id,))
            connection.execute("INSERT INTO attempts(sample_id,attempt,status,started_at) VALUES(?,1,'running','fixture')", (sample_id,))
        result = self.execute(self.run, max_samples=1)
        recovered = next(s for s in result["samples"] if s["sample_id"] == sample_id)
        self.assertEqual(recovered["attempts"], 2)
        self.assertIn(recovered["status"], ("passed", "failed"))
        self.assertTrue(all(s["attempts"] == 0 for s in result["samples"] if s["sample_id"] != sample_id))

    def test_process_lock_prevents_concurrent_resume(self):
        self.create()
        with run_lock(self.run):
            with self.assertRaises(ValueError):
                self.execute(self.run)

    def test_nonempty_output_directory_is_not_overwritten(self):
        self.run.mkdir()
        marker = self.run / "keep.txt"
        marker.write_text("user content")
        with self.assertRaises((ValueError, FileExistsError)):
            self.create()
        self.assertEqual(marker.read_text(), "user content")


if __name__ == "__main__":
    unittest.main()
