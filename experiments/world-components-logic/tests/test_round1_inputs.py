"""Input-authoring engineering checks; no model/semantic/human approval."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import lab
import prepare_round1_inputs as inputs


class InputDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.materials = inputs.build_materials()

    def materials_copy(self):
        return copy.deepcopy(self.materials)

    def case(self, case_id):
        return copy.deepcopy(next(case for case in self.materials[1] if case["caseId"] == case_id))

    def supplement(self, case_id):
        return copy.deepcopy(next(row for row in self.materials[2] if row["caseId"] == case_id))

    def test_original_revision_two_bytes_are_pinned_not_rewritten(self):
        for name, expected in inputs.SOURCE_FILE_SHA256.items():
            self.assertEqual(lab.sha256_file(inputs.SOURCE / name), expected)
        with mock.patch.object(inputs.lab, "sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "byte identity changed"):
                inputs.build_materials()

    def test_counts_distinguish_groups_cases_guards_and_chain_plans(self):
        status, summary = inputs.validate_materials(*self.materials)
        self.assertEqual(summary["sourceGroupCount"], 90)
        self.assertEqual(summary["independentTaskAnchors"], 80)
        self.assertEqual(summary["shortChainInitialPlans"], 10)
        self.assertEqual(summary["taskCaseCount"], 84)
        self.assertEqual(summary["guardReasons"]["ready"], 70)
        self.assertEqual(sum(not row["guard"]["shouldCall"] for row in status.values()), 14)
        self.assertEqual(summary["structurallyValidTaskCases"], 83)
        self.assertFalse(summary["modelExecutionAuthorized"])
        self.assertEqual(summary["trainingQuota"], 0)
        for task in ("D02", "D03", "D04", "D05"):
            for split in inputs.SPLITS:
                self.assertEqual(sum(c["task"] == task and c["split"] == split and c["anchorCase"] for c in self.materials[1]), 10)

    def test_projection_preserves_full_world_and_excludes_review_metadata(self):
        for case in self.materials[1]:
            if case["caseId"] == "r1-sealed-d04-10":
                continue
            visible = lab.build_model_input(case)
            self.assertEqual(visible, case["input"])
            self.assertNotIn("sourceCard", visible)
            self.assertNotIn("sourceGroup", visible)
            self.assertNotIn("assumptions", visible)
            self.assertNotIn("draftExpected", visible)
            for person in visible["world"]["characters"]:
                self.assertTrue(person["tasks"])
                self.assertTrue(person["personality"])
                self.assertTrue(all(task["text"].strip() for task in person["tasks"]))
            visible["world"]["characters"][0]["tasks"][0]["text"] = "mutated copy"
            self.assertNotEqual(visible, case["input"])

    def test_d03_cannot_observe_a_current_source_future_roll(self):
        for case in self.materials[1]:
            if case["task"] == "D03":
                current = case["input"]["source"]["memberId"]
                self.assertTrue(all(row["sourceId"] != current for row in case["input"]["knownPriorJudgments"]))
                self.assertEqual(set(case["input"]["candidateIds"]), {p["id"] for p in case["input"]["world"]["characters"]})
        case = self.case("r1-dev-d03-09")
        case["input"]["knownPriorJudgments"].append(inputs.judgment(case["caseId"], "b", "a", 19))
        with self.assertRaisesRegex(lab.LabValidationError, "future judgment leakage"):
            lab.build_model_input(case)

    def test_d04_raw_missing_target_is_not_repaired_or_projected(self):
        case = self.case("r1-sealed-d04-10")
        record = inputs.inspect_case(case)
        self.assertNotIn("targetId", case["input"]["judgments"][0])
        self.assertEqual(record["guard"]["reason"], "invalid_input")
        self.assertIsNone(record["modelProjectionSha256"])
        supplement = self.supplement(case["caseId"])
        self.assertEqual(supplement["damage"]["rawJudgment"], case["input"]["judgments"][0])
        self.assertIsNone(supplement["judgmentBindings"][0]["triggerKey"])
        self.assertIsNone(supplement["judgmentBindings"][0]["targetId"])
        with self.assertRaises(lab.LabValidationError):
            lab.build_model_input(case)

    def test_d04_only_frozen_threats_not_future_response_are_visible(self):
        case = self.case("r1-dev-d04-05")
        value = case["input"]
        self.assertEqual({member["memberId"] for member in value["confirmedGroup"]["members"]}, {"a", "c"})
        self.assertEqual({row["value"] for row in value["judgments"]}, {13, 8, 14})
        self.assertEqual(lab.guard_case(case)["reason"], "ready")
        # Add the not-yet-generated responder's outgoing judgment: exact lab
        # guard must reject this future source, even though IDs are registered.
        value["judgments"].append(inputs.judgment(case["caseId"], "b", "c", 15))
        with self.assertRaisesRegex(lab.LabValidationError, "source has no frozen action"):
            lab.build_model_input(case)

    def test_frozen_sources_are_in_the_actual_acted_roster(self):
        for case in self.materials[1]:
            if case['task'] in ('D03', 'D04'):
                value = case['input']
                frozen = {m['memberId'] for m in value['confirmedGroup']['members']}
                self.assertLessEqual(frozen, set(value['alreadyActedIds']))

    def test_skip_does_not_make_a_responder_already_acted(self):
        case = self.case("r1-sealed-d04-04")
        self.assertEqual(case["input"]["previouslySkippedIds"], ["b"])
        self.assertEqual(lab.guard_case(case)["reason"], "ready")
        case["input"]["alreadyActedIds"] = ["b"]
        self.assertEqual(lab.guard_case(case)["reason"], "already_acted_reuse")

    def test_multiple_threat_prefix_is_past_and_reachable_before_b_response(self):
        for split in ('dev', 'sealed'):
            case = self.case(f'r1-{split}-d04-05')
            rows = case['input']['judgments']
            self.assertEqual([(r['sourceId'], r['targetId']) for r in rows],
                             [('c', 'b'), ('c', 'a'), ('a', 'b')])
            self.assertFalse(rows[0]['admitted'])
            self.assertTrue(rows[1]['admitted'])
            self.assertTrue(rows[2]['admitted'])
            self.assertNotIn('b', {m['memberId'] for m in case['input']['confirmedGroup']['members']})

    def test_same_target_source_was_admitted_without_current_source_future_roll(self):
        for split in ('dev', 'sealed'):
            case = self.case(f'r1-{split}-d03-10')
            rows = case['input']['knownPriorJudgments']
            self.assertEqual([(r['sourceId'], r['targetId']) for r in rows], [('a', 'b'), ('a', 'c')])
            self.assertFalse(rows[0]['admitted'])
            self.assertTrue(rows[1]['admitted'])
            self.assertEqual(case['input']['source']['memberId'], 'c')
            lab.build_model_input(case)

    def test_chain_acted_prefix_must_precede_the_current_slot(self):
        chain = copy.deepcopy(next(c for c in self.materials[3] if c['caseId'] == 'r1-sealed-chain-02'))
        self.assertEqual(chain['initialControl']['frozenOrder'], ['b', 'a'])
        self.assertEqual(chain['initialControl']['cursor'], 1)
        inputs.verify_chain_initial(chain)
        chain['initialControl'].update(frozenOrder=['a', 'b'], cursor=0)
        with self.assertRaisesRegex(ValueError, 'visited slots'):
            inputs.verify_chain_initial(chain)

    def test_four_member_path_replays_the_corrected_dfs_and_reuses_c(self):
        case = self.case("r1-sealed-d05-02")
        group = case["input"]["group"]
        supplement = self.supplement(case["caseId"])
        self.assertEqual(supplement["fixtureInitiatorId"], "d")
        self.assertEqual([(r["sourceId"], r["targetId"], r["value"]) for r in group["judgments"]],
                         [("d", "a", 16), ("a", "c", 12), ("d", "b", 17), ("b", "c", 14)])
        self.assertFalse(group["judgments"][-1]["eligible"])
        self.assertFalse(group["judgments"][-1]["admitted"])
        inputs.verify_closed_path(case, supplement)
        self.assertEqual(sum(e["kind"] == "freeze_action" and e.get("memberId") == "c" for e in supplement["fixtureEvents"]), 1)
        # The existing lab structural guard cannot establish reachability.
        # This counterexample keeps member coverage but invalidates the only
        # way to admit a; our fixture-path check must detect the old defect.
        first = group["judgments"][0]
        first.update(value=6, passed=False, admitted=False)
        self.assertTrue(lab.guard_case(case)["shouldCall"])
        with self.assertRaisesRegex(ValueError, "no frozen/admitted path"):
            inputs.verify_closed_path(case, supplement)

    def test_d05_damaged_payloads_remain_blocked_and_never_fill_missing_text(self):
        missing = self.case("r1-dev-d05-08")
        self.assertNotIn("actionText", next(m for m in missing["input"]["group"]["members"] if m["memberId"] == "c"))
        self.assertEqual(lab.guard_case(missing)["reason"], "missing_member_action")
        missing_roll = self.case("r1-dev-d05-09")
        self.assertEqual(len(missing_roll["input"]["group"]["judgments"]), 1)
        self.assertEqual(lab.guard_case(missing_roll)["reason"], "missing_or_duplicate_relation_judgment")
        events = self.supplement(missing_roll["caseId"])["fixtureEvents"]
        lost = next(e for e in events if e["kind"] == "missing_judgment")
        self.assertNotIn("value", lost)  # Never invent the lost actual value.
        duplicate = self.case("r1-sealed-d05-09")
        self.assertEqual([r["value"] for r in duplicate["input"]["group"]["judgments"]], [12, 18])
        self.assertEqual(lab.guard_case(duplicate)["reason"], "missing_or_duplicate_relation_judgment")
        open_group = self.case("r1-sealed-d05-10")
        self.assertFalse(open_group["input"]["group"]["closed"])
        self.assertFalse(any(t["sourceId"] == "b" for t in open_group["input"]["group"]["confirmedTargets"]))
        self.assertEqual(lab.guard_case(open_group)["reason"], "group_not_closed")

    def test_dice_derivatives_keep_group_split_world_and_frozen_actions(self):
        cases = {case["caseId"]: case for case in self.materials[1]}
        derived = [case for case in cases.values() if not case["anchorCase"]]
        self.assertEqual(len(derived), 4)
        for variant in derived:
            anchor = cases[variant["derivedFrom"]]
            self.assertEqual((variant["sourceGroup"], variant["split"]), (anchor["sourceGroup"], anchor["split"]))
            self.assertEqual(variant["input"]["world"], anchor["input"]["world"])
            field = "group" if variant["task"] == "D05" else "confirmedGroup"
            self.assertEqual(variant["input"][field]["members"], anchor["input"][field]["members"])
            self.assertNotEqual(inputs.fixture_identity(variant["caseId"]), inputs.fixture_identity(anchor["caseId"]))
        materials = self.materials_copy()
        materials[1][-1]["split"] = "development"
        with self.assertRaisesRegex(ValueError, "original source group/split/task"):
            inputs.validate_materials(*materials)

    def test_chain_has_only_known_initial_prefix_and_no_actual_predictions(self):
        chains = self.materials[3]
        self.assertEqual(len(chains), 10)
        for chain in chains:
            visible = lab.build_model_input(chain["initialCase"])
            self.assertEqual(visible, chain["initialCase"]["input"])
            self.assertEqual(chain["initialControl"]["confirmedTargetSets"], [])
            self.assertEqual(chain["initialControl"]["judgments"], [])
            self.assertEqual(chain["dynamicPlan"]["runnerStatus"], "not_implemented")
            self.assertIsNone(chain["dynamicPlan"]["actualPredictions"])
            self.assertIsNone(chain["dynamicPlan"]["dicePolicy"]["values"])
            self.assertFalse(chain["modelExecutionAuthorized"])
        self.assertEqual(chains[5]["initialCase"]["input"]["confirmedPrefix"], [{"memberId": "b", "actionText": "乙稳住登记图板。"}])
        self.assertEqual(chains[6]["initialControl"]["visitedIds"], ["b"])
        self.assertEqual(chains[6]["initialControl"]["actedIds"], [])
        self.assertEqual(chains[9]["dynamicPlan"]["contractStatus"], "blocked_contract_g03")
        self.assertEqual(chains[9]["initialControl"]["frozenOrder"], ["b", "a"])
        broken = self.materials_copy()
        broken[3][0]["dynamicPlan"]["actualPredictions"] = {"targets": []}
        with self.assertRaisesRegex(ValueError, "fabricated actual predictions"):
            inputs.validate_materials(*broken)

    def test_auxiliary_missing_and_cancelled_are_outside_ninety_and_do_not_infer(self):
        probes = self.materials[4]
        self.assertEqual(len(probes), 2)
        self.assertEqual([inputs.preflight_probe(p)["reason"] for p in probes], ["missing_input_text", "cancelled_before_inference"])
        self.assertTrue(all(p["outside90GroupQuota"] and not p["modelExecutionAuthorized"] for p in probes))
        # Cancellation is controller state, never a fabricated negative model
        # answer or an extra field smuggled through the closed model input.
        self.assertNotIn("cancelled", lab.build_model_input(probes[1]["case"]))

    def test_supplement_identity_cannot_be_swapped_between_cards(self):
        broken = self.materials_copy()
        broken[2][0]["contextFacts"] = broken[2][1]["contextFacts"]
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            inputs.validate_materials(*broken)

    def test_registered_positions_and_task_identity_cannot_hide_a_cycle(self):
        world = self.case("r1-dev-d02-01")["input"]["world"]
        # lab accepts the registered position type, but the full graph would
        # still be invalid if an item and its holder contained one another.
        world["items"][0]["position"] = "a"
        world["characters"][0]["position"] = "i0"
        with self.assertRaisesRegex(ValueError, "cyclic world position graph"):
            inputs.check_registered_world(world)
        world = self.case("r1-dev-d02-01")["input"]["world"]
        world["characters"][1]["tasks"][0]["id"] = world["characters"][0]["tasks"][0]["id"]
        with self.assertRaisesRegex(ValueError, "globally unique"):
            inputs.check_registered_world(world)

    def test_manifest_has_per_item_and_projection_hashes_and_no_authorization(self):
        files, summary = inputs.build_files()
        manifest = json.loads(files[inputs.DATA / "input-manifest.json"])
        self.assertEqual(manifest["sourceCards"]["files"], inputs.SOURCE_FILE_SHA256)
        self.assertEqual(manifest["summary"], summary)
        for name, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256(files[inputs.DATA / name]).hexdigest(), digest)
        for case, supplement, row in zip(self.materials[1], self.materials[2], manifest["cases"]):
            self.assertEqual(row["caseSha256"], inputs.sha(case))
            self.assertEqual(row["inputSha256"], inputs.sha(case["input"]))
            self.assertEqual(row["supplementSha256"], inputs.sha(supplement))
        self.assertIsNone(manifest["sourceReceipts"]["B"])
        self.assertIsNone(manifest["sourceReceipts"]["C"])
        self.assertEqual(manifest["candidateModelCalls"], 0)
        self.assertEqual(manifest["trainingUses"], [])

    def test_write_new_preflights_all_files_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "absent", Path(directory) / "existing"
            b.write_bytes(b"old")
            with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
                inputs.write_or_check({a: b"new", b: b"different"}, write_new=True)
            self.assertFalse(a.exists())
            self.assertEqual(b.read_bytes(), b"old")
            inputs.write_or_check({a: b"new", b: b"old"}, write_new=True)
            inputs.write_or_check({a: b"new", b: b"old"}, write_new=False)
            with self.assertRaisesRegex(ValueError, "缺少交付文件"):
                inputs.write_or_check({Path(directory) / "missing": b"x"}, write_new=False)


if __name__ == "__main__":
    unittest.main()
