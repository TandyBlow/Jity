"""Offline boundary tests for curated banks; never touch real recordings."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jity_eval import question_bank as qb
from jity_eval.storage import atomic_json, digest_bytes


class QuestionBankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.bank = self.root / "bank"
        self.spec_path = self.root / "spec.json"
        self.dataset_audit = self.root / "dataset-audit.json"
        self.source.mkdir()
        self.heads = [10, 18, 31, 45, 58, 72]
        campaign = [0, 1, 1, 2, 3, 4]
        for t in range(6):
            cp = {
                "turn": t, "head": self.heads[t],
                "progress": {"turns_total": campaign[t], "recap_compressed": "早先档案放在西塔。"},
                "state": {
                    "turn": t, "health": 100, "sanity": 80,
                    "items": [{"name": "钥匙", "status": "owned"}],
                    "world_facts": [{"name": "档案位置", "description": "西塔"}],
                    "recent_events": ["已检查门口。"],
                    "_private_runtime_detail": "must_not_be_exported",
                    "_memory_controller": {
                        "score_tracker": [{"item_name": "钥匙", "state": "active"}],
                        "nsb": {"level1": [{"summary": "早先档案放在西塔。"}], "turn_buffer": []},
                        "pcb": {"sketches": {"守卫": {"description": "负责门口"}}},
                    },
                },
                "output": {"narration": "档案放在西塔。" if t == 1 else "继续查看四周。",
                           "dialogue": [], "options": ["检查档案。"] if t == 3 else ["继续。"]},
            }
            atomic_json(self.source / qb.source_name("game-01", t), cp)
            if t:
                atomic_json(self.source / qb.source_name("game-01", t, "intents"),
                            {"turn": t, "request": {"player_action": "查看四周。",
                                                    "timeline_node_id": self.heads[t - 1]}})
        atomic_json(self.source / "manifest.json", {"synthetic": True})
        atomic_json(self.source / "validation/final-acceptance.json", {"status": "passed", "synthetic": True})
        (self.source / "DATASET.md").write_text("Synthetic offline fixture; not game evidence.\n")
        self.seal_source()
        atomic_json(self.dataset_audit, {"games": [{"game_id": "game-01",
            "eligibility": "formal_source_pending_question_review", "status": "completed",
            "game_over": True, "ending": "synthetic", "errors": [],
            "strict_replay": {"status": "passed", "all_calls_consumed": True,
                              "key_state_match": True, "ending_match": True,
                              "reload_match": True, "network_attempts": 0, "errors": []}}]})
        self.spec = {
            "schema_version": qb.SCHEMA, "bank_id": "synthetic-bank", "bank_version": "0.1",
            "recent_window": 2, "coverage": {"note": "synthetic tests only"},
            "questions": [self.question("Q01")],
            "candidates": [{"id": "C01", "game_id": "game-01", "checkpoint_action": 5,
                            "status": "candidate", "reason": "Freeze a later checkpoint for future-reference tests."}],
        }

    def question(self, qid):
        return {
            "id": qid, "game_id": "game-01", "checkpoint_action": 4,
            "question": "之前把档案放在哪里？", "kind": "recall", "category": "early_fact",
            "test_target": "remember prior location", "first_action": 1, "update_actions": [],
            "mention_terms": ["档案"],
            "gold": {"standard_answer": "西塔", "private_marker": "PRIVATE_GOLD_ONLY_7d95",
                     "required_points": ["西塔"]},
            "evidence": [{"action_index": 1, "json_pointer": "/output/narration", "excerpt": "档案放在西塔。"}],
            "channels": {"expected": ["historical_narrative", "structured_state"]},
            "validity": {"through_action": 4}, "review": {"status": "pending_human_review"},
        }

    def seal_source(self):
        files = {str(p.relative_to(self.source)): digest_bytes(p.read_bytes())
                 for p in self.source.rglob("*") if p.is_file() and p.name not in {"seal.json", "seal.sha256"}}
        atomic_json(self.source / "seal.json", {"files": files})
        (self.source / "seal.sha256").write_text(digest_bytes((self.source / "seal.json").read_bytes()) + "\n")

    def build(self):
        atomic_json(self.spec_path, self.spec)
        return qb.build(self.source, self.spec_path, self.bank, self.dataset_audit)

    def resign_manifest(self, changed_paths=(), frozen_paths=()):
        """Refresh incidental file hashes to exercise structural checks too."""
        m = qb.read(self.bank / "manifest.json")
        for name in changed_paths:
            m["files"][name] = digest_bytes((self.bank / name).read_bytes())
        for name in frozen_paths:
            sha = digest_bytes((self.bank / "frozen/source" / name).read_bytes())
            m["frozen_source_files"][name] = sha
            m["files"]["frozen/source/" + name] = sha
        atomic_json(self.bank / "manifest.json", m)
        (self.bank / "manifest.sha256").write_text(digest_bytes((self.bank / "manifest.json").read_bytes()) + "\n")

    def change_collection(self, name, change):
        obj = qb.read(self.bank / name)
        change(obj["records"])
        atomic_json(self.bank / name, obj)
        self.resign_manifest([name])

    def test_build_is_offline_readonly_and_gold_is_separate(self):
        before = {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        with patch("socket.socket.connect", side_effect=AssertionError("No network permitted")), \
             patch("subprocess.Popen", side_effect=AssertionError("No game process permitted")):
            self.build()
            result = qb.validate(self.bank, source_check=True)
        after = {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["model_answers"], 0)
        self.assertIsNone(result["scores"])
        for path in (self.bank / "public").rglob("*.json"):
            self.assertNotIn("PRIVATE_GOLD_ONLY_7d95", path.read_text())
            self.assertNotIn("must_not_be_exported", path.read_text())
        self.assertIn("PRIVATE_GOLD_ONLY_7d95", (self.bank / "private/answers.json").read_text())

    def test_modes_share_question_checkpoint_and_recent_window(self):
        self.build()
        inputs = {mode: qb.read(self.bank / f"public/inputs/Q01/{mode}.json") for mode in qb.MODES}
        for mode, item in inputs.items():
            self.assertEqual(item["question"], inputs["full"]["question"])
            self.assertEqual(item["checkpoint"], inputs["full"]["checkpoint"])
            self.assertEqual([r["action_index"] for r in item["context"]["recent_context"]], [3, 4])
            self.assertEqual(item["context"]["recent_context"], inputs["full"]["context"]["recent_context"])
        self.assertEqual(set(inputs["recent"]["context"]), {"recent_context"})
        self.assertEqual(set(inputs["state"]["context"]), {"recent_context", "structured_state"})
        self.assertEqual(set(inputs["full"]["context"]), {"recent_context", "structured_state", "historical_narrative_memory"})
        self.assertEqual(inputs["full"]["checkpoint"]["campaign_turn"], 3)
        self.assertEqual(inputs["full"]["checkpoint"]["timeline_node"], 58)

    def test_rementions_include_unselected_options_and_not_snapshot_copies(self):
        self.build()
        audit = qb.read(self.bank / "audit/items.json")["records"][0]
        self.assertEqual(audit["chronology"]["last_public_topic_mention_action"], 3)
        self.assertEqual(audit["interval"]["since_last_public_mention_actions"], 1)
        self.assertEqual({m["action_index"] for m in audit["chronology"]["public_mentions"]}, {1, 3})

    def test_extra_private_field_in_public_question_is_rejected(self):
        self.build()
        self.change_collection("public/questions.json", lambda rows: rows[0].update(expected_value="西塔"))
        with self.assertRaises(ValueError):
            qb.validate(self.bank)

    def test_private_context_injection_is_rejected_even_with_updated_file_hash(self):
        self.build()
        name = "public/inputs/Q01/recent.json"
        item = qb.read(self.bank / name)
        item["context"]["gold"] = "PRIVATE_GOLD_ONLY_7d95"
        atomic_json(self.bank / name, item)
        self.resign_manifest([name])
        with self.assertRaisesRegex(ValueError, "source-only reconstruction"):
            qb.validate(self.bank)

    def test_question_change_in_one_mode_is_rejected(self):
        self.build()
        name = "public/inputs/Q01/state.json"
        item = qb.read(self.bank / name)
        item["question"] = "A different question"
        atomic_json(self.bank / name, item)
        self.resign_manifest([name])
        with self.assertRaises(ValueError):
            qb.validate(self.bank)

    def test_coordinated_public_question_change_is_bound_to_authoring(self):
        self.build()
        self.change_collection("public/questions.json", lambda rows: rows[0].update(question="PRIVATE_GOLD_ONLY_7d95"))
        changed = []
        for mode in qb.MODES:
            name = f"public/inputs/Q01/{mode}.json"
            item = qb.read(self.bank / name)
            item["question"] = "PRIVATE_GOLD_ONLY_7d95"
            atomic_json(self.bank / name, item)
            changed.append(name)
        self.resign_manifest(changed)
        with self.assertRaises(ValueError):
            qb.validate(self.bank)

    def test_duplicate_ids_are_rejected(self):
        self.spec["questions"].append(deepcopy(self.spec["questions"][0]))
        with self.assertRaises(ValueError):
            self.build()

    def test_invalid_id_cannot_write_outside_bank(self):
        self.spec["questions"][0]["id"] = "../../../escaped"
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse((self.root / "escaped").exists())

    def test_future_evidence_is_rejected_even_when_frozen_file_exists(self):
        self.spec["questions"][0]["evidence"] = [
            {"action_index": 5, "json_pointer": "/output/narration", "excerpt": "继续查看四周。"}]
        with self.assertRaises(ValueError):
            self.build()

    def test_future_chronology_is_rejected(self):
        self.spec["questions"][0]["update_actions"] = [5]
        with self.assertRaises(ValueError):
            self.build()

    def test_bad_pointer_or_invented_quote_is_rejected(self):
        for field, val in (("json_pointer", "/output/missing"), ("excerpt", "不存在的引文")):
            with self.subTest(field=field):
                self.bank = self.root / ("bank-" + field)
                self.spec["questions"][0]["evidence"] = [{"action_index": 1,
                    "json_pointer": "/output/narration", "excerpt": "档案放在西塔。", field: val}]
                with self.assertRaises((ValueError, KeyError)):
                    self.build()

    def test_broken_ancestor_chain_is_rejected(self):
        path = self.source / qb.source_name("game-01", 3, "intents")
        item = qb.read(path)
        item["request"]["timeline_node_id"] = 999
        atomic_json(path, item)
        self.seal_source()
        with self.assertRaisesRegex(ValueError, "ancestor chain"):
            self.build()

    def test_repeated_timeline_node_is_rejected(self):
        path = self.source / qb.source_name("game-01", 3)
        item = qb.read(path)
        item["head"] = self.heads[1]
        atomic_json(path, item)
        self.seal_source()
        with self.assertRaises(ValueError):
            self.build()

    def test_manifest_and_frozen_input_tampering_fail(self):
        self.build()
        path = self.bank / "public/inputs/Q01/full.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "Frozen file changed"):
            qb.validate(self.bank)
        path.write_bytes(original)
        manifest = self.bank / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "Manifest fingerprint"):
            qb.validate(self.bank)

    def test_original_recording_change_detected_by_optional_check(self):
        self.build()
        path = self.source / qb.source_name("game-01", 1)
        path.write_bytes(path.read_bytes() + b" ")
        self.assertEqual(qb.validate(self.bank)["status"], "passed")
        with self.assertRaises(ValueError):
            qb.validate(self.bank, source_check=True)

    def test_uninventoried_public_file_is_rejected(self):
        self.build()
        (self.bank / "public/accidental-gold.txt").write_text("PRIVATE_GOLD_ONLY_7d95")
        with self.assertRaisesRegex(ValueError, "Unexpected public file"):
            qb.validate(self.bank)

    def test_unknown_question_cannot_omit_history_review(self):
        self.spec["questions"][0]["kind"] = "unknown"
        self.spec["questions"][0]["gold"]["standard_answer"] = None
        with self.assertRaises(ValueError):
            self.build()

    def test_unknown_question_with_bounded_review_is_allowed(self):
        self.spec["questions"][0]["kind"] = "unknown"
        self.spec["questions"][0]["question"] = "记录中明确给出守卫的生日了吗？"
        self.spec["questions"][0]["gold"]["standard_answer"] = None
        self.spec["questions"][0]["unknown_audit"] = {
            "range": [0, 4], "status": "editor_reviewed_pending_human",
            "reviewed_fields": ["output", "state", "player_action"],
            "inference_review": "No calendar information or unique derivation exists in this synthetic prefix.",
            "search_terms": ["守卫", "生日"]}
        self.build()
        self.assertEqual(qb.validate(self.bank)["status"], "passed")
        public = qb.read(self.bank / "public/questions.json")["records"][0]
        self.assertEqual(public["kind"], "recall")
        self.assertNotIn("unknown_audit", public)

    def test_evidence_node_and_value_fingerprints_are_checked(self):
        self.build()
        self.change_collection("audit/evidence.json", lambda rows: rows[0].update(timeline_node=999))
        with self.assertRaisesRegex(ValueError, "Evidence node mismatch"):
            qb.validate(self.bank)
        self.change_collection("audit/evidence.json", lambda rows: rows[0].update(
            timeline_node=self.heads[1], value_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "Evidence fingerprint"):
            qb.validate(self.bank)

    def test_unknown_question_requires_bounded_review(self):
        self.spec["questions"][0]["unknown_audit"] = {"range": [0, 5],
            "status": "editor_reviewed_pending_human", "reviewed_fields": ["output"],
            "inference_review": "No unique identity", "search_terms": ["名字"]}
        with self.assertRaises(ValueError):
            self.build()

    def test_semantic_mentions_must_refer_to_real_source_quotes(self):
        self.build()
        def forge(rows):
            rows[0]["chronology"]["public_mentions"].append({
                "action_index": 2, "timeline_node": 31, "json_pointer": "/output/narration",
                "excerpt": "This quote was invented", "method": "editor_semantic"})
        self.change_collection("audit/items.json", forge)
        with self.assertRaises(ValueError):
            qb.validate(self.bank)

    def test_existing_output_and_recording_destination_are_rejected(self):
        self.build()
        before = (self.bank / "manifest.json").read_bytes()
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual((self.bank / "manifest.json").read_bytes(), before)
        self.bank = self.source / "new-bank"
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.bank.exists())

    def test_duplicate_json_keys_and_path_escape_are_rejected(self):
        path = self.root / "duplicate.json"
        path.write_text('{"a": 1, "a": 2}')
        with self.assertRaises(ValueError):
            qb.read(path)
        with self.assertRaises(ValueError):
            qb.safe_path(self.root, "../escape")


if __name__ == "__main__":
    unittest.main()
