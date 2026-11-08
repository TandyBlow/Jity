"""Contract checks that prevent misleading or unsafe offline experiments."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from jity_eval.schema import SchemaError, load_config, load_gold, load_suite, validate_bundle


ROOT = Path(__file__).resolve().parents[1]


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.suite = {
            "schema_version": 1, "suite_id": "test-suite", "title": "离线测试",
            "cases": [{
                "id": "case-1", "title": "状态更新与未知信息",
                "history": [
                    {"turn": turn, "text": f"事件 {turn}", "facts": []}
                    for turn in range(1, 50)
                ],
                "probes": [
                    {"id": "known", "fact_id": "key", "kind": "recall", "question": "钥匙状态？", "source_turn": 8, "delay": 40},
                    {"id": "unknown", "fact_id": "birthday", "kind": "action", "question": "生日何时？", "source_turn": 8, "delay": 40},
                ],
            }],
        }
        self.case = self.suite["cases"][0]
        self.case["history"][1]["facts"] = [{"id": "key", "value": "持有", "storage": "both"}]
        self.case["history"][7]["facts"] = [{"id": "key", "value": "已交出", "storage": "both"}]
        self.gold = {"schema_version": 1, "records": [
            {"case_id": "case-1", "probe_id": "known", "expected_value": "已交出"},
            {"case_id": "case-1", "probe_id": "unknown", "expected_value": None},
        ]}
        self.config = {
            "schema_version": 1, "suite": "suite.json", "gold": "gold.json",
            "adapter": "offline", "modes": ["full", "recent", "state"],
            "repeats": 1, "seed": 42, "recent_window": 5,
        }

    def write(self, name, value):
        path = self.base / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def bundle(self):
        self.write("suite.json", self.suite)
        self.write("gold.json", self.gold)
        return validate_bundle(self.write("config.json", self.config))

    def test_valid_bundle_resolves_paths_and_indexes_private_gold(self):
        config, suite, gold = self.bundle()
        self.assertEqual(config["suite"], str((self.base / "suite.json").resolve()))
        self.assertEqual(config["gold"], str((self.base / "gold.json").resolve()))
        self.assertEqual(gold["case-1/known"]["expected_value"], "已交出")
        self.assertIsNone(gold["case-1/unknown"]["expected_value"])
        self.assertNotIn("expected_value", json.dumps(suite))

    def test_example_has_144_samples_and_never_selects_a_live_adapter(self):
        config, suite, gold = validate_bundle(ROOT / "examples" / "pilot.json")
        count = sum(len(case["probes"]) for case in suite["cases"])
        self.assertEqual(count * len(config["modes"]) * config["repeats"], 144)
        self.assertEqual(len(gold), 48)
        self.assertEqual(config["adapter"], "offline")
        self.assertTrue(all(len(case["history"]) == 49 for case in suite["cases"]))

    def test_failure_demo_references_real_samples(self):
        config, _, _ = validate_bundle(ROOT / "examples" / "faults.json")
        self.assertEqual({i["stage"] for i in config["failure_injections"]}, {"adapter", "grader"})

    def test_live_adapter_is_rejected(self):
        self.config["adapter"] = "deepseek"
        with self.assertRaisesRegex(SchemaError, "offline"):
            self.bundle()

    def test_boolean_is_not_an_integer(self):
        for field in ["repeats", "seed", "recent_window", "schema_version"]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.config)
                changed[field] = True
                with self.assertRaises(SchemaError):
                    load_config(self.write("bad-config.json", changed))
        self.case["probes"][0]["delay"] = True
        with self.assertRaises(SchemaError):
            self.bundle()

    def test_unknown_fields_cannot_hide_answer_keys_in_public_probes(self):
        self.case["probes"][0]["expected_value"] = "已交出"
        with self.assertRaisesRegex(SchemaError, "unknown fields"):
            self.bundle()

    def test_unknown_config_fields_are_rejected(self):
        self.config["api_key"] = "not-a-real-secret"
        with self.assertRaisesRegex(SchemaError, "unknown fields"):
            self.bundle()

    def test_duplicate_json_keys_are_not_silently_overwritten(self):
        path = self.base / "bad.json"
        path.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
        with self.assertRaisesRegex(SchemaError, "duplicate key"):
            load_config(path)

    def test_invalid_json_and_missing_file_raise_schema_error(self):
        path = self.base / "bad.json"
        path.write_text('{"schema_version": NaN}', encoding="utf-8")
        with self.assertRaises(SchemaError):
            load_config(path)
        with self.assertRaises(SchemaError):
            load_config(self.base / "does-not-exist.json")

    def test_duplicate_identifiers_are_rejected(self):
        for what in ["case", "probe", "fact"]:
            with self.subTest(what=what):
                changed = copy.deepcopy(self.suite)
                case = changed["cases"][0]
                if what == "case":
                    changed["cases"].append(copy.deepcopy(case))
                elif what == "probe":
                    case["probes"].append(copy.deepcopy(case["probes"][0]))
                else:
                    case["history"][7]["facts"].append(copy.deepcopy(case["history"][7]["facts"][0]))
                with self.assertRaisesRegex(SchemaError, "duplicate"):
                    load_suite(self.write("bad-suite.json", changed))

    def test_turn_order_and_probe_range_are_enforced(self):
        changed = copy.deepcopy(self.suite)
        changed["cases"][0]["history"][2]["turn"] = 2
        with self.assertRaisesRegex(SchemaError, "strictly increasing"):
            load_suite(self.write("bad-suite.json", changed))
        self.case["probes"][0]["delay"] = 42
        with self.assertRaisesRegex(SchemaError, "beyond"):
            self.bundle()

    def test_history_cannot_skip_turns_to_fake_a_long_delay(self):
        self.case["history"].pop(1)
        with self.assertRaisesRegex(SchemaError, "contiguous"):
            self.bundle()

    def test_history_must_start_at_turn_one(self):
        self.case["history"].pop(0)
        with self.assertRaisesRegex(SchemaError, "starting at 1"):
            self.bundle()

    def test_later_restatement_invalidates_claimed_delay(self):
        self.case["history"][29]["facts"] = [{"id": "key", "value": "已交出", "storage": "both"}]
        with self.assertRaisesRegex(SchemaError, "repeated facts reset the delay"):
            self.bundle()

    def test_old_value_cannot_be_used_as_current_gold(self):
        self.gold["records"][0]["expected_value"] = "持有"
        with self.assertRaisesRegex(SchemaError, "disagrees"):
            self.bundle()

    def test_unknown_question_cannot_have_fabricated_gold(self):
        self.gold["records"][1]["expected_value"] = "五月一日"
        with self.assertRaisesRegex(SchemaError, "disagrees"):
            self.bundle()

    def test_missing_extra_and_duplicate_gold_records_are_rejected(self):
        for what in ["missing", "extra", "duplicate"]:
            with self.subTest(what=what):
                changed = copy.deepcopy(self.gold)
                if what == "missing":
                    changed["records"].pop()
                elif what == "extra":
                    changed["records"].append({"case_id": "case-1", "probe_id": "not-present", "expected_value": None})
                else:
                    changed["records"].append(copy.deepcopy(changed["records"][0]))
                with self.assertRaises(SchemaError):
                    load_gold(self.write("bad-gold.json", changed), self.suite)

    def test_future_fact_does_not_answer_a_current_unknown_question(self):
        self.case["history"][48]["facts"] = [{"id": "birthday", "value": "五月一日", "storage": "both"}]
        _, _, gold = self.bundle()
        self.assertIsNone(gold["case-1/unknown"]["expected_value"])

    def test_failure_injections_require_valid_reference_and_repeat(self):
        injection = {"case_id": "case-1", "probe_id": "known", "mode": "full", "repeat": 1, "stage": "adapter", "attempt": 1}
        self.config["failure_injections"] = [injection]
        self.bundle()
        injection["probe_id"] = "missing"
        with self.assertRaisesRegex(SchemaError, "missing case/probe"):
            self.bundle()
        injection["probe_id"] = "known"
        injection["repeat"] = 2
        with self.assertRaisesRegex(SchemaError, "exceeds"):
            self.bundle()


if __name__ == "__main__":
    unittest.main()
