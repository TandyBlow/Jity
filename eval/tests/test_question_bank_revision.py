"""Offline artifact contracts; these tests never grade model responses."""
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from jity_eval import question_bank_revision as rev
from jity_eval.question_bank import read
from jity_eval.storage import atomic_json

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "question_banks/full-games-20261106-v1.2"
PREVIOUS = ROOT / "question_banks/full-games-20261106-v1.1"


class RevisionContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jity-v12-contract-")
        self.bank = Path(self.temp.name) / "bank"
        shutil.copytree(BANK, self.bank)
        self.previous = Path(self.temp.name) / PREVIOUS.name
        shutil.copytree(PREVIOUS, self.previous)

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, name, change):
        value = read(self.bank / name)
        change(value)
        atomic_json(self.bank / name, value)
        # Re-sign the changed file to test semantic contracts beyond checksums.
        m = read(self.bank / "manifest.json")
        m["files"][name] = rev.file_sha(self.bank / name)
        atomic_json(self.bank / "manifest.json", m)
        (self.bank / "manifest.sha256").write_text(rev.file_sha(self.bank / "manifest.json") + "  manifest.json\n")

    def test_valid_bank_and_counts(self):
        result = rev.validate(self.bank)
        self.assertEqual((result["questions"], result["inputs"], result["scoring_points"]), (12, 36, 33))
        self.assertEqual(result["model_experiments"], "not_run")

    def test_relocated_banks_do_not_read_original_machine_paths(self):
        manifest = read(self.bank / "manifest.json")
        original_roots = [Path(manifest[key]) for key in ("previous_bank", "source_root")]
        original_open = Path.open

        def relocated_open(path, *args, **kwargs):
            if any(path == root or root in path.parents for root in original_roots):
                raise FileNotFoundError("Original machine paths unavailable")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", relocated_open):
            result = rev.validate(self.bank)
            self.assertFalse(result["original_seal_checked"])
            with self.assertRaisesRegex(FileNotFoundError, "Original machine paths unavailable"):
                rev.validate(self.bank, check_original=True)

    def test_changed_adjacent_delivery_cannot_fall_back_to_original(self):
        (self.previous / "delivery.sha256.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Previous delivery changed"):
            rev.validate(self.bank)

    def test_changed_adjacent_manifest_is_rejected(self):
        (self.previous / "manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Previous manifest changed"):
            rev.validate(self.bank)

    def test_question_must_change_in_all_groups(self):
        self.edit("public/inputs/JLC-20261106-G01-Q01/recent.json", lambda x: x.update(question="另一问题"))
        with self.assertRaisesRegex(ValueError, "Input changed"):
            rev.validate(self.bank)

    def test_memory_cannot_be_repaired_from_gold(self):
        def add(x):
            x["context"]["historical_narrative_memory"]["recap_compressed"] += " 七枚，三枚较新。"
        self.edit("public/inputs/JLC-20261106-G02-Q03/full.json", add)
        with self.assertRaisesRegex(ValueError, "Input changed"):
            rev.validate(self.bank)

    def test_private_label_cannot_enter_input(self):
        self.edit("public/inputs/JLC-20261106-G03-Q03/recent.json", lambda x: x.update(category="unknown"))
        with self.assertRaisesRegex(ValueError, "Input changed"):
            rev.validate(self.bank)

    def test_unexpected_public_file_rejected(self):
        atomic_json(self.bank / "public/gold.json", {"answer": "secret"})
        with self.assertRaisesRegex(ValueError, "Unexpected public file"):
            rev.validate(self.bank)

    def test_future_reference_rejected_after_resigning(self):
        def change(x):
            x["records"][0]["action_index"] = 25  # G01-Q01 checkpoint is 24.
        self.edit("audit/evidence.json", change)
        with self.assertRaisesRegex(ValueError, "Future/cross-game"):
            rev.validate(self.bank)

    def test_incorrect_excerpt_rejected_after_resigning(self):
        self.edit("audit/evidence.json", lambda x: x["records"][0].update(excerpt="不存在的私有答案"))
        with self.assertRaisesRegex(ValueError, "Inaccurate excerpt"):
            rev.validate(self.bank)

    def test_audit_cannot_be_silently_upgraded(self):
        self.edit("audit/points.json", lambda x: x["records"][5]["points"][0]["inputs"]["full"].update(support="full"))
        with self.assertRaisesRegex(ValueError, "authored judgments"):
            rev.validate(self.bank)

    def test_fixed_contract_and_diagnostic_gaps(self):
        a = {x["id"][-7:]: x for x in read(self.bank / "audit/points.json")["records"]}
        for p in a["G02-Q03"]["points"]:
            self.assertTrue(p["historical_evidence_exists"])
            self.assertTrue(all(s["support"] == "not_provided" for s in p["inputs"].values()))
        for p in a["G04-Q03"]["points"][-2:]:
            self.assertEqual(p["inputs"]["full"]["support"], "not_provided")
        self.assertEqual(a["G03-Q03"]["purpose"], "recent_unknown_control")
        self.assertEqual(a["G04-Q02"]["purpose"], "recent_state_control")
        self.assertTrue(all(p["chronology"]["latest_explicit"]["gap_actions"] == 0 for p in a["G04-Q02"]["points"]))
        it = next(x for x in read(self.bank / "audit/items.json")["records"] if x["id"].endswith("G03-Q01"))
        self.assertEqual(it["chronology"]["first_action"], 0)
        self.assertEqual(it["chronology"]["first_narrative_action"], 1)
        self.assertEqual(it["interval"]["since_first_actions"], 35)

    def test_review_is_not_automatic_human_approval(self):
        self.edit("audit/points.json", lambda x: x["records"][0].update(status="human_approved"))
        with self.assertRaisesRegex(ValueError, "Review status"):
            rev.validate(self.bank)

    def test_build_refuses_existing_directory(self):
        with self.assertRaisesRegex(ValueError, "Output exists"):
            rev.build(BANK, BANK / "private/revision-spec.json", self.bank)


if __name__ == "__main__":
    unittest.main()
