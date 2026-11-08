"""Context reports must expose evidence without inventing model scores."""
import json
from pathlib import Path
import tempfile
import unittest

from jity_eval.replay.report import render_report, summarize_samples


class ReplayReportTests(unittest.TestCase):
    def sample(self, status="assembled", **values):
        result = {"id": "sample-1", "probe_id": "probe-1", "question": "钥匙放在哪里？", "checkpoint_turn": 42,
                  "source_turn": 2, "delay": 40, "mode": "full", "status": status, "trace_path": None,
                  "error": None, "attempts": 1, "review_required": True}
        result.update(values)
        return result

    def trace(self, **extra):
        result = {"messages": [{"role": "user", "content": "完整实际输入"}],
                  "retrieval_hits": [{"memory_id": "memory-1", "in_final_prompt": True}],
                  "injected_memory_hits": [{"id": "memory-1"}],
                  "channel_policy": {"recent_messages": True, "structured_state": True, "persona": False,
                                     "backend_state_retained": True},
                  "state_injection": {"model_visible_state": {"items": ["钥匙"]}},
                  "truncation": {"tokens_after": 1200, "tokens_before": 2000, "applied": True},
                  "provenance": {"recap": {"source_turn": None}},
                  "leak_audit": {"findings": [], "method": "exact_text_scan"},
                  "real_model_calls": 0, "probe_answer": None}
        result.update(extra)
        return result

    def make_run(self, path, rows):
        path = Path(path)
        (path / "manifest.json").write_text(json.dumps({"kind": "jity_context_replay", "simulation": False,
            "real_model_calls": 0, "config": {"recent_window": 5}, "dataset_summary": {"turns": 54},
            "limitations": ["历史快照恢复"]}), encoding="utf-8")
        (path / "results.json").write_text(json.dumps({"status": "completed", "real_model_calls": 0,
            "total": len(rows), "samples": rows}), encoding="utf-8")
        return path

    def data(self, html):
        start = '<script id="report-data" type="application/json">'
        return json.loads(html.split(start, 1)[1].split("</script>", 1)[0])

    def test_counts_and_context_statistics_have_no_accuracy_or_model_score(self):
        summary = summarize_samples([
            self.sample(trace=self.trace()), self.sample("missing_call"), self.sample("error"),
            self.sample("pending", mode="recent"), self.sample("running", mode="state")])
        group = summary["groups"]["full"]
        self.assertEqual(group["assembled"], 1)
        self.assertEqual(group["errors"], 2)
        self.assertEqual(group["tokens_after_mean"], 1200)
        self.assertEqual(group["retrieved_hits"], 1)
        self.assertEqual(group["injected_hits"], 1)
        self.assertFalse(group["channels"]["persona"])
        self.assertNotIn("backend_state_retained", group["channels"])
        self.assertNotIn("accuracy", group)
        self.assertNotIn("score", group)
        self.assertIsNone(summary["groups"]["recent"]["tokens_after_mean"])

    def test_full_trace_is_embedded_and_hostile_text_cannot_escape(self):
        hostile = '</script><script>alert("unsafe")</script><img src="https://bad.invalid">&\u2028\u2029'
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [self.sample(question=hostile, trace_path="trace.json")])
            trace = self.trace(messages=[{"role": "user", "content": hostile}])
            (path / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
            html = render_report(path).read_text(encoding="utf-8")
            self.assertNotIn(hostile, html)
            self.assertIn("\\u003c/script\\u003e", html)
            self.assertIn("\\u0026", html)
            self.assertIn("\\u2028", html)
            self.assertEqual(self.data(html)["samples"][0]["trace"], trace)
            self.assertNotIn("innerHTML", html)
            self.assertNotIn("fetch(", html)
            self.assertNotIn("XMLHttpRequest", html)
            self.assertNotIn('<script src=', html)
            self.assertIn("未生成探针答案", html)
            self.assertIn("真实向量检索、Director 与记忆维护调用未重放", html)
            self.assertIn("未知的语义重提与同义转述仍待人工复核", html)

    def test_trace_paths_cannot_escape_by_parent_absolute_or_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            secret = base / "secret.json"
            secret.write_text('{"secret":"DO_NOT_EMBED_THIS"}', encoding="utf-8")
            run = base / "run"
            run.mkdir()
            (run / "symlink.json").symlink_to(secret)
            rows = [self.sample(trace_path=path) for path in ("../secret.json", str(secret), "symlink.json")]
            self.make_run(run, rows)
            html = render_report(run).read_text(encoding="utf-8")
            self.assertNotIn("DO_NOT_EMBED_THIS", html)
            data = self.data(html)
            self.assertEqual(data["summary"]["missing_evidence"], 3)
            self.assertTrue(all(row["trace"] is None for row in data["samples"]))

    def test_missing_invalid_and_non_object_trace_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [self.sample(trace_path=name) for name in ("missing.json", "invalid.json", "array.json")])
            (path / "invalid.json").write_text("not-json", encoding="utf-8")
            (path / "array.json").write_text("[]", encoding="utf-8")
            rows = self.data(render_report(path).read_text(encoding="utf-8"))["samples"]
            self.assertTrue(all(row["trace"] is None for row in rows))
            self.assertTrue(all("审计证据不可用" in row["trace_note"] for row in rows))

    def test_wrong_report_kind_and_model_calls_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [])
            manifest_path = path / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["simulation"] = True
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "历史快照"):
                render_report(path)
            manifest["simulation"] = False
            manifest["real_model_calls"] = 1
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "真实模型调用为 0"):
                render_report(path)

    def test_unknown_status_or_mode_is_not_silently_counted(self):
        for values in ({"status": "passed"}, {"mode": "unknown"}):
            with self.subTest(values=values), tempfile.TemporaryDirectory() as tmp:
                path = self.make_run(tmp, [self.sample(**values)])
                with self.assertRaisesRegex(ValueError, "未知状态或实验组"):
                    render_report(path)

    def test_alias_modes_and_error_only_group_have_no_token_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [self.sample("missing_call", mode="B", error="No recorded campaign_director call")])
            data = self.data(render_report(path).read_text(encoding="utf-8"))
            self.assertEqual(data["samples"][0]["mode"], "recent")
            self.assertIsNone(data["summary"]["groups"]["recent"]["tokens_after_mean"])
            self.assertEqual(data["summary"]["counts"]["missing_call"], 1)

    def test_replacement_regenerates_snapshot_without_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.make_run(tmp, [self.sample("pending")])
            report = render_report(path)
            self.make_run(path, [self.sample("assembled")])
            self.assertEqual(render_report(path), report)
            data = self.data(report.read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["counts"]["assembled"], 1)
            self.assertFalse(list(path.glob(".context-report-*")))


if __name__ == '__main__':
    unittest.main()
