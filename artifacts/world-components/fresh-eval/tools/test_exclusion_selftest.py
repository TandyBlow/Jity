"""Regression checks for note-only containment and incomplete baseline parses."""
import unittest

from exclusion_selftest import baseline_checks, screen


class ExclusionRegressionTests(unittest.TestCase):
    def test_note_interrupting_the_only_shared_substring_is_blocked(self):
        row = screen({"texts": ["寒枝从南堤来到旧坊"]},
                     {"寒枝（旧题注记）从南堤来到旧坊": ["source"]}, set(), {})
        self.assertEqual([r["rule"] for r in row["reasons"]], ["R1-substring"])

    def test_empty_partial_duplicate_and_wrong_id_baselines_fail(self):
        items = [{"id": str(i)} for i in range(10)]
        rows = [{"id": i["id"], "reasons": [{"rule": "R1-substring"},
                                               {"rule": "R3-signature"}]}
                for i in items]
        scope = {"threeArmItems": items}
        self.assertEqual(baseline_checks(items, rows, scope), (True, True))
        for parsed, results in (([], []), (items[:9], rows[:9]),
                                (items[:9] + [items[0]], rows[:9] + [rows[0]]),
                                (items[:9] + [{"id": "unexpected"}], rows)):
            with self.subTest(ids=[i["id"] for i in parsed]):
                self.assertFalse(baseline_checks(parsed, results, scope)[0])

    def test_one_rule_missing_on_any_old_item_fails_independence(self):
        items = [{"id": str(i)} for i in range(10)]
        rows = [{"id": i["id"], "reasons": [{"rule": "R1-substring"},
                                               {"rule": "R3-signature"}]}
                for i in items]
        rows[-1]["reasons"] = [{"rule": "R1-substring"}]
        self.assertEqual(baseline_checks(items, rows, {"threeArmItems": items}),
                         (True, False))


if __name__ == "__main__":
    unittest.main()
