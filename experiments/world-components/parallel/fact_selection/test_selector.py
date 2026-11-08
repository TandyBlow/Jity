from __future__ import annotations

import json
import unittest
from pathlib import Path

import selector

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
CASES = selector.load_cases(HERE / "cases-v2.json")
ALL = selector.run_all(CASES)
BY_ID = {row["caseId"]: row for row in ALL["cases"]}
CASES_BY_ID = {case["caseId"]: case for case in CASES["cases"]}


class CaseTests(unittest.TestCase):
    def test_ten_cases_nine_controlled_one_coverage(self):
        self.assertEqual(len(CASES["cases"]), 10)
        self.assertEqual(sum(1 for c in CASES["cases"] if c["groupId"] != "R"), 9)
        self.assertEqual([c["caseId"] for c in CASES["cases"] if c["groupId"] == "R"], ["R1"])

    def test_each_fact_has_provenance(self):
        for case in CASES["cases"]:
            for fact in case["facts"]:
                self.assertIn("source", fact)
                self.assertIn("file", fact["source"])
                self.assertIn("entityId", fact["source"])

    def test_source_fixture_hash(self):
        import hashlib
        import subprocess

        def committed_sha(rel):
            blob = subprocess.run(["git", "show", "HEAD:" + rel], cwd=REPO,
                                  capture_output=True, check=True).stdout
            return hashlib.sha256(blob).hexdigest()

        self.assertEqual(committed_sha(CASES["sourceFixture"]["file"]),
                         CASES["sourceFixture"]["sha256"])
        for source in CASES["sourceReports"]:
            self.assertEqual(committed_sha(source["file"]), source["sha256"])

    def test_target_and_related_are_optional(self):
        for case in CASES["cases"]:
            facts = selector.facts_by_id(case)
            for fid in case["targetOptionalFactIds"] + case["relatedOptionalFactIds"]:
                self.assertEqual(facts[fid]["authorization"], "optional")


class InvariantTests(unittest.TestCase):
    def test_hard_pass_all_arms(self):
        for row in ALL["cases"]:
            for arm, cell in row["arms"].items():
                self.assertEqual(cell["missingMust"], [], (row["caseId"], arm))
                self.assertEqual(cell["forbiddenSelected"], [], (row["caseId"], arm))
                self.assertEqual(cell["uncertainSelected"], [], (row["caseId"], arm))
                self.assertEqual(cell["priorSelected"], [], (row["caseId"], arm))
                self.assertTrue(cell["hardPass"], (row["caseId"], arm))

    def test_selected_ids_in_fact_order(self):
        for row in ALL["cases"]:
            for arm, cell in row["arms"].items():
                self.assertEqual(cell["selected"],
                                 selector.in_fact_order(CASES_BY_ID[row["caseId"]], cell["selected"]),
                                 (row["caseId"], arm))

    def test_manual_is_lenient_oracle(self):
        summary = ALL["summary"]["manual"]
        self.assertEqual(summary["all"]["lenientPass"], 10)
        self.assertEqual(summary["all"]["strictPass"], 9)
        self.assertEqual(summary["all"]["hardPass"], 10)
        # R1's manual keeps the related personality, so strict (target-only) is false.
        self.assertFalse(BY_ID["R1"]["arms"]["manual"]["strictPass"])
        self.assertTrue(BY_ID["R1"]["arms"]["manual"]["lenientPass"])

    def test_legacy_metric_rejects_the_manual_oracle(self):
        for row in ALL["cases"]:
            cell = row["arms"]["manual"]
            self.assertLess(cell["mustPrecision"], 0.85, row["caseId"])
            self.assertFalse(cell["legacyD1Pass"], row["caseId"])
        self.assertEqual(ALL["summary"]["manual"]["all"]["legacyD1Pass"], 0)


class NoAttentionTests(unittest.TestCase):
    def test_no_attention_passes_hard_but_fails_quality(self):
        summary = ALL["summary"]["no_attention"]
        self.assertEqual(summary["all"]["hardPass"], 10)
        self.assertEqual(summary["all"]["lenientPass"], 3)
        self.assertEqual(summary["controlled"]["lenientPass"], 2)
        self.assertEqual(summary["all"]["manualEqual"], 3)

    def test_no_attention_selects_both_competitors_when_prior_is_empty(self):
        for cid in ("P1", "P2"):
            self.assertEqual(BY_ID[cid]["arms"]["no_attention"]["selected"], ["f1", "f2", "f3", "f4"])
        for cid in ("C1", "C2", "C3"):
            self.assertEqual(BY_ID[cid]["arms"]["no_attention"]["selected"], ["f1", "f2", "f3", "f4"])
        for cid in ("H1", "H2"):
            self.assertEqual(BY_ID[cid]["arms"]["no_attention"]["selected"], ["f0", "f1"])

    def test_no_attention_changes_only_when_prior_removes_the_competitor(self):
        # P1 vs P3: same attention, prior removes f4 in P3; the rule changes without attention.
        self.assertEqual(BY_ID["P1"]["arms"]["no_attention"]["selected"], ["f1", "f2", "f3", "f4"])
        self.assertEqual(BY_ID["P3"]["arms"]["no_attention"]["selected"], ["f1", "f2", "f3"])
        self.assertTrue(BY_ID["P3"]["arms"]["no_attention"]["lenientPass"])
        self.assertFalse(BY_ID["P1"]["arms"]["no_attention"]["lenientPass"])

    def test_no_attention_ignores_attention_in_p1_p2(self):
        self.assertEqual(BY_ID["P1"]["arms"]["no_attention"]["selected"],
                         BY_ID["P2"]["arms"]["no_attention"]["selected"])


class LexicalTests(unittest.TestCase):
    def test_lexical_at_false_positive(self):
        for cid in ("P2", "C3"):
            cell = BY_ID[cid]["arms"]["lexical"]
            self.assertIn("f3", cell["selected"])
            self.assertIn("f3", cell["unrelatedSelected"])
            self.assertFalse(cell["lenientPass"])

    def test_content_only_removes_same_location_false_positive(self):
        for cid in ("P2", "C3"):
            cell = BY_ID[cid]["arms"]["lexical_content"]
            self.assertNotIn("f3", cell["selected"])
            self.assertTrue(cell["lenientPass"])

    def test_lexical_misses_indirect_reference(self):
        cell = BY_ID["C2"]["arms"]["lexical"]
        self.assertFalse(cell["targetSelected"])
        self.assertEqual(cell["selected"], ["f1", "f2"])
        content = BY_ID["C2"]["arms"]["lexical_content"]
        self.assertFalse(content["targetSelected"])
        semantic = BY_ID["C2"]["arms"]["semantic"]
        self.assertTrue(semantic["targetSelected"])
        self.assertIn("f3", semantic["selected"])

    def test_summary_counts(self):
        summary = ALL["summary"]
        self.assertEqual(summary["lexical"]["all"]["lenientPass"], 7)
        self.assertEqual(summary["lexical"]["controlled"]["lenientPass"], 6)
        self.assertEqual(summary["lexical_content"]["all"]["lenientPass"], 9)
        self.assertEqual(summary["lexical_content"]["controlled"]["lenientPass"], 8)


class SemanticTests(unittest.TestCase):
    def test_semantic_matches_all_controlled_targets(self):
        summary = ALL["summary"]["semantic"]
        self.assertEqual(summary["controlled"]["lenientPass"], 9)
        self.assertEqual(summary["all"]["lenientPass"], 10)
        self.assertEqual(summary["all"]["strictPass"], 10)
        for cid in ("P1", "P2", "P3", "P4", "C1", "C2", "C3", "H1", "H2"):
            self.assertTrue(BY_ID[cid]["arms"]["semantic"]["targetSelected"], cid)
            self.assertEqual(BY_ID[cid]["arms"]["semantic"]["unrelatedSelected"], [], cid)

    def test_semantic_r1_keeps_only_must(self):
        cell = BY_ID["R1"]["arms"]["semantic"]
        self.assertEqual(cell["selected"], ["r3_sanity", "r3_task"])
        self.assertEqual(cell["relatedSelected"], [])
        self.assertTrue(cell["lenientPass"])
        self.assertTrue(cell["strictPass"])

    def test_semantic_does_not_read_surface_words(self):
        # The semantic arm is given focus; C2's surface targets do not match the fact text.
        self.assertEqual(BY_ID["C2"]["arms"]["semantic"]["selected"], ["f1", "f2", "f3"])


class V1RecheckTests(unittest.TestCase):
    def test_v1_no_attention_reproduces_six_of_six(self):
        v1 = json.loads((REPO / "artifacts/world-components/organize-wording/attention-selection-v1.json").read_text(encoding="utf-8"))
        rows = []
        for group in v1["groups"]:
            must = {f["factId"] for f in group["facts"] if f["authorization"] == "must"}
            for condition in group["conditions"]:
                case = {
                    "caseId": condition["conditionId"],
                    "facts": group["facts"],
                    "alreadyNarratedFactIds": condition["alreadyNarratedFactIds"],
                    "manualSelectedFactIds": condition["manualSelectedFactIds"],
                    "targetOptionalFactIds": sorted(set(condition["manualSelectedFactIds"]) - must),
                    "relatedOptionalFactIds": [],
                }
                selected = selector.select_no_attention(case)
                rows.append((condition["conditionId"], selected, condition["manualSelectedFactIds"],
                             selector.evaluate(case, selected)))
        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(1 for _, selected, manual, _ in rows if set(selected) == set(manual)), 6)
        # Every v1 condition's prior removes the competing optional.
        for group in v1["groups"]:
            for condition in group["conditions"]:
                self.assertEqual(len(condition["alreadyNarratedFactIds"]), 1)
        for _, _, _, score in rows:
            self.assertLess(score["mustPrecision"], 0.85)
        mean = sum(score["mustPrecision"] for _, _, _, score in rows) / len(rows)
        self.assertAlmostEqual(mean, 0.4444444444, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
