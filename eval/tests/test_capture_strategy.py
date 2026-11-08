import copy
import unittest
from jity_eval.capture.strategy import choose, coverage


class StrategyTests(unittest.TestCase):
    def test_deterministic_legal_options_without_state_mutation(self):
        cp = {"output": {"options": ["询问诺诺", "使用通行卡", "强行突破"], "option_checks": [None, None, {"enabled": True}]}}
        before = copy.deepcopy(cp)
        for strategy in ("mission", "explore", "items", "risk"):
            a = choose(cp, strategy, 42, 8)
            self.assertEqual(a, choose(cp, strategy, 42, 8))
            self.assertEqual(a["action"], cp["output"]["options"][a["option_index"]])
        self.assertEqual(cp, before)
        self.assertEqual(choose(cp, "risk", 42, 8)["roll"], choose(cp, "items", 42, 8)["roll"])

    def test_no_coverage_claim_for_intended_policy(self):
        result = coverage([{"turn": 1, "state": {}, "output": {}}])
        self.assertIn("failed_checks", result["uncovered"])
        self.assertIn("ending", result["uncovered"])
