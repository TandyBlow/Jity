"""Offline unit acceptance for the action-cap amendment attachment."""
import asyncio
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

# The helper is a dataset attachment, intentionally outside frozen package code.
# Tests can travel alongside it, or select a delivery with the environment var.
_candidates = [Path(os.environ["JITY_CAPTURE_CONTINUE_HELPER"])] if os.environ.get("JITY_CAPTURE_CONTINUE_HELPER") else [
    Path(__file__).with_name("jity_capture_continue.py"),
    Path(__file__).resolve().parents[1] / "tools/jity_capture_continue.py",
    Path(__file__).resolve().parents[1] / "runs/full-games-20261106/attachments/jity_capture_continue.py",
]
_helper_path = next((path for path in _candidates if path.is_file()), None)
if _helper_path is None:
    raise unittest.SkipTest("Set JITY_CAPTURE_CONTINUE_HELPER to the delivered continuation attachment")
spec = importlib.util.spec_from_file_location("continue_attachment", _helper_path)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


class FakeRunner:
    def __init__(self, out, manifest):
        self.out, self.manifest = out, manifest
        self.credentials_read = 0
        self.executed = []
        self.replayed = []

    @contextmanager
    def run_lock(self, out):
        with (out / ".run.lock").open("a") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("collector is active")
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def verify_dataset(self, out):
        if helper.read_json(out / "manifest.json") != self.manifest:
            raise ValueError("manifest changed")
        return deepcopy(self.manifest)

    def summary_evidence(self, out):
        return True

    def _credentials(self, root):
        self.credentials_read += 1
        return "offline-unit-test-only"

    def _update_game(self, out, spec, **fields):
        path = out / spec["id"] / "game.json"
        data = helper.read_json(path)
        data.update(fields)
        write(path, data)

    async def execute_game(self, out, spec, api_key):
        self.executed.append(deepcopy(spec))
        assert spec["turn_limit"] == 80
        assert self.manifest["config"]["max_turns_per_campaign"] == 50
        self._update_game(out, spec, status="completed", turns=54, game_over=True, ending="fixture ending")

    def replay_game_subprocess(self, out, game_id):
        self.replayed.append(game_id)
        return {"status": "passed"}

    def refresh_summary(self, out):
        return {"status": "offline_fixture_completed"}


class AmendmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="capture-amendment-test-")
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)
        limits = {"max_cost_usd": 10.0, "max_attempts": 850, "max_input_tokens": 12000000,
                  "max_output_tokens": 3000000, "max_unpriced_attempts": 15}
        self.manifest = {"limits": limits, "prices": {"deepseek-flash": {"input_per_million": .3, "output_per_million": 1.2}},
                         "config": {"max_turns_per_campaign": 50, "max_retries": 2, "llm_model": "deepseek-flash", "thinking": "disabled"},
                         "jity_original_root": "offline-fixture", "games": [{"id": "game-%02d" % i, "kind": "game", "turn_limit": 50, "seed": i, "strategy": "mission"} for i in range(1, 5)]}
        write(self.out / "manifest.json", self.manifest)
        write(self.out / "smoke/game.json", {"replay": {"status": "passed"}})
        for i, game in enumerate(self.manifest["games"]):
            write(self.out / game["id"] / "game.json", {**game, "status": "completed" if i else "incomplete_turn_limit",
                  "turns": 50, "game_over": bool(i), "ending": "fixture ending" if i else None,
                  "replay": {"status": "passed", "all_calls_consumed": True, "reload_match": True}})
            with sqlite3.connect(self.out / game["id"] / "calls.sqlite3") as db:
                db.execute("CREATE TABLE calls(sequence INTEGER,status TEXT)")
                db.execute("INSERT INTO calls VALUES(1,'complete')")
        with sqlite3.connect(self.out / "budget.sqlite3") as db:
            db.executescript("CREATE TABLE budget_config(id INTEGER,value TEXT); CREATE TABLE budget_control(id INTEGER,stop_reason TEXT); CREATE TABLE reservations(input_actual INTEGER,input_reserved INTEGER,output_actual INTEGER,output_reserved INTEGER,cost_actual REAL,cost_reserved REAL,unpriced INTEGER,status TEXT);")
            db.execute("INSERT INTO budget_config VALUES(1,?)", (json.dumps({"limits": limits, "prices": self.manifest["prices"]}),))
            db.execute("INSERT INTO budget_control VALUES(1,NULL)")
            db.execute("INSERT INTO reservations VALUES(100,300,20,50,.000054,.001,0,'settled')")
        self.amendment = {"schema_version": 1, "kind": "jity_action_limit_amendment", "approved": True,
            "approved_by": "user", "approval_text": "Offline unit fixture only", "approved_at": datetime.now(timezone.utc).isoformat(),
            "manifest_sha256": helper.canonical_digest(self.manifest), "original_action_limit": 50,
            "effective_action_limit": 80, "campaign_turn_budget": 50, "max_retries": 2,
            "limits": limits, "config_sha256": helper.canonical_digest(self.manifest["config"]),
            "prices_sha256": helper.canonical_digest(self.manifest["prices"]), "game_ids": sorted(helper.EXPECTED_GAME_IDS)}
        self.approval = self.out / "approvals/action-limit-80.json"
        self.runner = FakeRunner(self.out, self.manifest)
        self.save_approval()

    def save_approval(self):
        write(self.approval, self.amendment)
        self.sha = helper.file_sha256(self.approval)

    def run_helper(self, execute=False):
        return helper.continue_dataset(self.out, self.approval, self.sha, execute=execute, runner=self.runner)

    def test_default_is_read_only_no_credentials_or_new_calls(self):
        budget_bytes = (self.out / "budget.sqlite3").read_bytes()
        manifest_bytes = (self.out / "manifest.json").read_bytes()
        result = self.run_helper()
        self.assertEqual(result["eligible_games"], ["game-01"])
        self.assertFalse(result["new_real_requests_allowed"])
        self.assertEqual(self.runner.credentials_read, 0)
        self.assertEqual(self.runner.executed, [])
        self.assertEqual(budget_bytes, (self.out / "budget.sqlite3").read_bytes())
        self.assertEqual(manifest_bytes, (self.out / "manifest.json").read_bytes())

    def test_cap_only_changes_external_loop_not_manifest_budget_or_game_rules(self):
        original = (self.out / "manifest.json").read_bytes()
        budget_original = (self.out / "budget.sqlite3").read_bytes()
        self.run_helper(execute=True)
        self.assertEqual(self.runner.executed[0]["turn_limit"], 80)
        self.assertEqual(self.manifest["games"][0]["turn_limit"], 50)
        self.assertEqual(self.runner.replayed, ["game-01", "game-01"])
        self.assertEqual((self.out / "manifest.json").read_bytes(), original)
        self.assertEqual((self.out / "budget.sqlite3").read_bytes(), budget_original)
        game = helper.read_json(self.out / "game-01/game.json")
        self.assertEqual((game["turn_limit"], game["original_turn_limit"], game["effective_action_limit"]), (50, 50, 80))

    def test_concurrent_collector_lock_refuses_before_credentials(self):
        with self.runner.run_lock(self.out):
            with self.assertRaisesRegex(ValueError, "collector is active"):
                self.run_helper(execute=True)
        self.assertEqual(self.runner.credentials_read, 0)

    def test_hash_scope_and_budget_amendments_are_rejected(self):
        self.sha = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.run_helper(True)
        for field, bad in [("effective_action_limit", 81), ("campaign_turn_budget", 80), ("approved", False), ("max_retries", 3)]:
            original = self.amendment[field]
            self.amendment[field] = bad
            self.save_approval()
            with self.assertRaises(ValueError):
                self.run_helper(True)
            self.amendment[field] = original
        self.assertEqual(self.runner.credentials_read, 0)

    def test_error_or_unknown_outcomes_are_never_resumed(self):
        game_path = self.out / "game-01/game.json"
        game = helper.read_json(game_path)
        game["status"] = "incomplete_error"
        write(game_path, game)
        with self.assertRaisesRegex(ValueError, "Only incomplete_turn_limit"):
            self.run_helper(True)
        game["status"] = "incomplete_turn_limit"
        write(game_path, game)
        with sqlite3.connect(self.out / "game-01/calls.sqlite3") as db:
            db.execute("UPDATE calls SET status='pending'")
        with self.assertRaisesRegex(ValueError, "Uncertain/incomplete"):
            self.run_helper(True)
        self.assertEqual(self.runner.credentials_read, 0)


if __name__ == "__main__":
    unittest.main()
