"""Report correctness and safe offline rendering."""

import json
import tempfile
import unittest
from pathlib import Path

from jity_eval.report import render_report, summarize_samples


class ReportTests(unittest.TestCase):
    def make_run(self, directory, samples):
        path = Path(directory)
        (path / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "run_id": "report-test", "adapter": "offline",
            "title": "报告测试", "config": {},
        }), encoding="utf-8")
        (path / "results.json").write_text(json.dumps({
            "schema_version": 1, "status": "completed_with_errors", "real_model_calls": 0,
            "samples": samples,
        }), encoding="utf-8")
        return path

    def sample(self, status, **extra):
        row = {"sample_id": status, "case_id": "case", "case_title": "测试", "probe_id": "q",
               "mode": "full", "repeat": 1, "kind": "recall", "delay": 40,
               "checkpoint_turn": 48, "status": status, "attempts": 1,
               "question": "在哪里？", "expected_value": "西塔", "actual_value": None,
               "decision": None, "error": None, "trace_path": None}
        row.update(extra)
        return row

    def read_data(self, html):
        start = '<script id="report-data" type="application/json">'
        return json.loads(html.split(start, 1)[1].split("</script>", 1)[0])

    def test_errors_and_pending_do_not_improve_accuracy(self):
        rows = [self.sample(status) for status in (
            "passed", "failed", "adapter_error", "grading_error", "pending", "running")]
        summary = summarize_samples(rows)
        self.assertEqual(summary["groups"]["full"]["accuracy"], 0.5)
        self.assertEqual(summary["groups"]["full"]["graded"], 2)
        self.assertEqual(summary["groups"]["full"]["unscored"], 4)
        self.assertEqual(summary["groups"]["full"]["errors"], 2)
        self.assertIsNone(summary["groups"]["recent"]["accuracy"])
        self.assertEqual(summary["total"], 6)

    def test_error_only_group_has_no_score(self):
        summary = summarize_samples([self.sample("grading_error")])
        self.assertIsNone(summary["groups"]["full"]["accuracy"])
        self.assertEqual(summary["groups"]["full"]["coverage"], 0)

    def test_html_escapes_hostile_data_and_embeds_traces(self):
        hostile = '</script><script>alert("x")</script>&\u2028\u2029'
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [self.sample("passed", question=hostile, trace_path="traces/one.json")])
            (path / "traces").mkdir()
            (path / "traces/one.json").write_text(json.dumps({"raw_response": hostile}), encoding="utf-8")
            html = render_report(path).read_text(encoding="utf-8")
            self.assertNotIn(hostile, html)
            self.assertNotIn('alert("x")</script>', html)
            self.assertIn("\\u003c/script\\u003e", html)
            self.assertIn("\\u0026", html)
            self.assertIn("\\u2028", html)
            self.assertEqual(self.read_data(html)["samples"][0]["trace"]["raw_response"], hostile)
            self.assertNotIn("innerHTML", html)
            self.assertNotIn("fetch(", html)
            self.assertIn("真实模型调用 0", html)

    def test_missing_and_invalid_trace_do_not_break_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [self.sample("failed", trace_path="traces/missing.json"),
                                       self.sample("grading_error", trace_path="broken.json")])
            (path / "broken.json").write_text("broken", encoding="utf-8")
            data = self.read_data(render_report(path).read_text(encoding="utf-8"))
            self.assertEqual(len(data["samples"]), 2)
            for row in data["samples"]:
                self.assertIsNone(row["trace"])
                self.assertIn("证据暂不可用", row["trace_note"])
            self.assertEqual(data["summary"]["groups"]["full"]["accuracy"], 0)

    def test_trace_cannot_escape_run_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            outside = parent / "secret.json"
            outside.write_text('{"secret":"must not embed"}', encoding="utf-8")
            run = parent / "run"
            run.mkdir()
            self.make_run(run, [self.sample("passed", trace_path="../secret.json")])
            html = render_report(run).read_text(encoding="utf-8")
            self.assertNotIn("must not embed", html)
            self.assertIn("证据文件必须位于本次运行目录内", html)

    def test_non_offline_metadata_cannot_be_mislabelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [])
            result = json.loads((path / "results.json").read_text())
            result["real_model_calls"] = 1
            (path / "results.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError, "真实模型调用必须为 0"):
                render_report(path)

    def test_report_replacement_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [self.sample("pending")])
            report = render_report(path)
            self.make_run(tmp, [self.sample("passed")])
            self.assertEqual(render_report(path), report)
            data = self.read_data(report.read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["counts"]["passed"], 1)
            self.assertFalse(list(path.glob(".report-*")))


if __name__ == "__main__":
    unittest.main()
