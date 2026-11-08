"""Recording reports must never manufacture completeness or replay evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from jity_eval.capture.report import render_capture_report, summarize_games


class CaptureReportTests(unittest.TestCase):
    def game(self, **values):
        row = {"id": "game-01", "kind": "game", "strategy": "任务推进", "seed": 103,
               "status": "completed", "turns": 50, "game_over": True,
               "ending": {"id": "ending-test", "name": "实际结局"},
               "calls_by_purpose": {"story_narrator": 49, "memory_summary": 8},
               "calls_by_model": {"recorded-model": 57},
               "usage": {"input_tokens": 12345, "output_tokens": 9876, "unknown_calls": 0},
               "cost": {"estimated_usd": 0.3, "reserved_usd": 0}, "retries": 1,
               "coverage": {"observed": ["摘要"], "uncovered": ["失败检定"]},
               "errors": [], "replay": {"status": "passed", "network_attempts": 0,
                    "all_calls_consumed": True, "key_state_match": True,
                    "ending_match": True, "reload_match": True, "errors": []}}
        row.update(values)
        return row

    def data(self, html):
        start = '<script id="report-data" type="application/json">'
        return json.loads(html.split(start, 1)[1].split("</script>", 1)[0])

    def write(self, root, games, **extra):
        (root / "manifest.json").write_text(json.dumps({"kind": "full_game_capture"}), encoding="utf-8")
        (root / "summary.json").write_text(json.dumps({"games": games, **extra}), encoding="utf-8")

    def test_complete_requires_actual_game_over_and_ending_not_cap(self):
        result = summarize_games([self.game(), self.game(game_over=False), self.game(ending=""),
                                  self.game(status="turn_limit"), self.game(kind="smoke", status="accepted", game_over=False)])
        self.assertEqual(result["formal_games"], 4)
        self.assertEqual(result["complete_games"], 1)
        self.assertEqual(result["accepted_games"], 1)
        self.assertEqual(result["unfinished_games"], 3)
        self.assertEqual(result["smoke_runs"], 1)
        self.assertEqual(result["findings"], 2)

    def test_strict_replay_cannot_pass_with_missing_state_or_network_evidence(self):
        for key in ("network_attempts", "all_calls_consumed", "key_state_match", "ending_match", "reload_match"):
            with self.subTest(key=key):
                row = self.game()
                del row["replay"][key]
                result = summarize_games([row])
                self.assertEqual(result["accepted_games"], 0)
                self.assertTrue(result["games"][0]["report_findings"])
        row = self.game()
        row["replay"]["errors"] = ["missing original response"]
        self.assertFalse(summarize_games([row])["games"][0]["strict_replay_verified"])

    def test_hostile_text_is_embedded_as_data_and_never_network_content(self):
        hostile = '</script><script>alert(1)</script><img src="https://bad.invalid">&\u2028\u2029'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, [self.game(strategy=hostile, errors=[hostile])])
            html = render_capture_report(root).read_text(encoding="utf-8")
            self.assertNotIn(hostile, html)
            self.assertIn("\\u003c/script\\u003e", html)
            self.assertEqual(self.data(html)["audit"]["games"][0]["strategy"], hostile)
            for forbidden in ("innerHTML", "fetch(", "XMLHttpRequest", "<script src=", "<link href="):
                self.assertNotIn(forbidden, html)
            self.assertIn("connect-src 'none'", html)
            self.assertIn("不重新生成模型响应", html)
            self.assertIn("不生成三组记忆对照的新答案", html)

    def test_local_links_cannot_escape_or_use_remote_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "dataset"
            root.mkdir()
            secret = base / "secret.json"
            secret.write_text('{"secret":"DO_NOT_EMBED"}')
            (root / "link.json").symlink_to(secret)
            (root / "game 01").mkdir()
            names = ("../secret.json", str(secret), "link.json", "https://bad.invalid", "http://[", "javascript:alert(1)", "game 01")
            self.write(root, [self.game(path=name) for name in names])
            html = render_capture_report(root).read_text(encoding="utf-8")
            rows = self.data(html)["audit"]["games"]
            self.assertTrue(all(not row["links"] for row in rows[:-1]))
            self.assertEqual(rows[-1]["links"], {"单局目录": "game%2001"})
            self.assertNotIn("DO_NOT_EMBED", html)

    def test_missing_and_malformed_files_produce_auditable_empty_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.data(render_capture_report(root).read_text(encoding="utf-8"))
            self.assertEqual(data["audit"]["complete_games"], 0)
            self.assertEqual(len(data["missing"]), 2)
            (root / "manifest.json").write_text("[]")
            (root / "summary.json").write_text("invalid")
            data = self.data(render_capture_report(root).read_text(encoding="utf-8"))
            self.assertEqual(len(data["missing"]), 2)

    def test_invalid_game_row_is_visible_not_counted_as_formal(self):
        result = summarize_games([None, self.game()])
        self.assertEqual(result["formal_games"], 1)
        self.assertEqual(result["complete_games"], 1)
        self.assertEqual(result["games"][0]["status"], "invalid")
        self.assertTrue(result["games"][0]["report_findings"])

    def test_report_regenerates_atomically_without_hiding_unknown_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write(root, [], budget={"max_usd": 10})
            target = render_capture_report(root)
            self.write(root, [self.game()], budget={"max_usd": 10})
            self.assertEqual(render_capture_report(root), target)
            data = self.data(target.read_text(encoding="utf-8"))
            self.assertEqual(data["audit"]["accepted_games"], 1)
            self.assertNotIn("known_usd", data["summary"]["budget"])
            self.assertFalse(list(root.glob(".capture-report-*")))


if __name__ == "__main__":
    unittest.main()
