"""Engineering invariants only: these fixtures are not semantic evaluation data."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("d_logic_lab", Path(__file__).resolve().parents[1] / "lab.py")
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


def world():
    return {
        "time": "2026-10-29T12:00:00+08:00",
        "places": [{"id": "room", "name": "测试房", "parentId": None}],
        "items": [{"id": "box", "name": "测试箱", "position": {"containerId": "room"}}],
        "characters": [{
            "id": person, "name": person, "position": {"containerId": "room"},
            "appearance": "工程夹具人物", "tasks": [{"id": person + "_task", "text": "保管箱子",
                "status": "pending", "parentId": None}], "personality": ["谨慎"], "sanity": 70,
        } for person in ("a", "b")],
    }


def judgment(**changes):
    value = {"sourceId": "a", "targetId": "b", "rollId": "r1", "ruleVersion": "reaction-d20-v1",
             "value": 12, "threshold": 11, "passed": True, "eligible": True, "admitted": True}
    value.update(changes)
    return value


def case(task="D02", case_id=None):
    inputs = {
        "D02": {"world": world(), "actorId": "a", "protagonistId": "a",
                "advance": {"inputText": "检查箱锁", "intentStatus": "pending"}, "confirmedPrefix": []},
        "D03": {"world": world(), "source": {"memberId": "a", "actionText": "伸手检查箱锁"},
                "candidateIds": ["a", "b"], "alreadyActedIds": [],
                "confirmedGroup": {"members": [{"memberId": "a", "actionText": "伸手检查箱锁"}]},
                "knownPriorJudgments": []},
        "D04": {"world": world(), "memberId": "b", "source": {"memberId": "a", "actionText": "伸手检查箱锁"},
                "admission": {"eligible": True, "admitted": True}, "alreadyActedIds": [],
                "previouslySkippedIds": [], "confirmedGroup": {"members": [{"memberId": "a", "actionText": "伸手检查箱锁"}]},
                "judgments": [judgment()]},
        "D05": {"world": world(), "group": {"closed": True, "memberIds": ["a", "b"],
                "members": [{"memberId": "a", "actionText": "伸手检查箱锁"}, {"memberId": "b", "actionText": "按住箱盖"}],
                "confirmedTargets": [{"sourceId": "a", "targetIds": ["b"]}, {"sourceId": "b", "targetIds": []}],
                "judgments": [judgment()]}},
    }
    return {"caseId": case_id or task + "-one", "sourceGroup": task + "-origin", "anchorCase": True,
            "derivedFrom": None, "split": "development", "purpose": "engineering_test_fixture",
            "task": task, "stageCut": task + "-current", "input": inputs[task]}


def review(item):
    return {"caseId": item["caseId"], "coverageTags": ["engineering_only"],
            "draftExpected": {"annotation": "NEVER EXPOSE THIS TO THE MODEL"}, "humanReview": "pending"}


def attempt(**changes):
    value = {"caseId": "unit", "sourceGroup": "source", "status": "complete", "elapsedMs": 10.0,
             "measurementScope": "component", "workloadId": "fixed-device-and-size", "budgetMs": 50.0}
    value.update(changes)
    return value


class IsolationTests(unittest.TestCase):
    def test_review_and_metadata_never_enter_model_input(self):
        item = case()
        validation = lab.validate_dataset([item], [review(item)])
        self.assertTrue(validation["valid"])
        visible = lab.build_model_input(item)
        self.assertEqual(visible, item["input"])
        self.assertNotIn("NEVER EXPOSE", json.dumps(visible))
        self.assertNotIn("sourceGroup", visible)
        self.assertEqual(validation["summary"]["reviewStatus"], "pending_human_review")
        self.assertEqual(validation["summary"]["formalVerdict"], "not_evaluated")

    def test_entire_world_and_nested_texts_are_preserved_without_aliases(self):
        item = case("D03")
        item["input"]["world"]["characters"][1]["tasks"][0]["text"] = "场外人物仍有完整长任务；不能因不相关而裁去"
        visible = lab.build_model_input(item)
        self.assertEqual(visible, item["input"])
        visible["world"]["characters"][1]["tasks"][0]["text"] = "changed"
        self.assertNotEqual(visible, item["input"])

    def test_unknown_input_is_rejected_instead_of_silently_dropped(self):
        item = case()
        item["input"]["requiredNewSemanticField"] = "preserve or stop"
        with self.assertRaisesRegex(lab.LabValidationError, "unexpected fields"):
            lab.build_model_input(item)

    def test_d03_current_source_future_judgments_are_rejected(self):
        item = case("D03")
        item["input"]["knownPriorJudgments"] = [judgment()]
        with self.assertRaisesRegex(lab.LabValidationError, "future judgment leakage"):
            lab.build_model_input(item)
        self.assertFalse(lab.guard_case(item)["shouldCall"])

    def test_d03_targets_and_nested_gold_cannot_be_smuggled_in(self):
        for mutate in (lambda item: item["input"].update(targets=["b"]),
                       lambda item: item["input"]["world"]["items"][0]["position"].update(expectedTargetIds=["b"])):
            item = case("D03")
            mutate(item)
            with self.assertRaises(lab.LabValidationError):
                lab.build_model_input(item)

    def test_d03_requires_the_whole_candidate_roster(self):
        item = case("D03")
        item["input"]["candidateIds"] = ["a"]
        with self.assertRaisesRegex(lab.LabValidationError, "incomplete candidate roster"):
            lab.build_model_input(item)

    def test_completed_other_source_judgment_is_preserved(self):
        item = case("D03")
        item["input"]["confirmedGroup"]["members"].append({"memberId": "b", "actionText": "已经确认的另一人物行动"})
        item["input"]["knownPriorJudgments"] = [judgment(sourceId="b", targetId="a")]
        self.assertEqual(lab.build_model_input(item), item["input"])

    def test_prior_source_must_have_a_nonempty_frozen_action(self):
        for frozen_member in (None, {"memberId": "b", "actionText": ""}):
            item = case("D03")
            if frozen_member is not None:
                item["input"]["confirmedGroup"]["members"].append(frozen_member)
            item["input"]["knownPriorJudgments"] = [judgment(sourceId="b", targetId="a")]
            with self.assertRaisesRegex(lab.LabValidationError, "source has no frozen action"):
                lab.build_model_input(item)
            self.assertFalse(lab.guard_case(item)["shouldCall"])

    def test_prior_judgment_must_be_complete_and_rule_consistent(self):
        mutations = [
            lambda value: value.pop("rollId"),
            lambda value: value.pop("value"),
            lambda value: value.update(passed=False),
            lambda value: value.update(admitted=False),
            lambda value: value.update(eligible=False),
            lambda value: value.update(value=0),
            lambda value: value.update(value=21),
            lambda value: value.update(threshold=12),
            lambda value: value.update(ruleVersion="unregistered-rule"),
        ]
        for mutate in mutations:
            item = case("D03")
            item["input"]["confirmedGroup"]["members"].append({"memberId": "b", "actionText": "已冻结的先前行动"})
            prior = judgment(sourceId="b", targetId="a")
            mutate(prior)
            item["input"]["knownPriorJudgments"] = [prior]
            with self.assertRaisesRegex(lab.LabValidationError, "incomplete or inconsistent"):
                lab.build_model_input(item)
            self.assertEqual(lab.guard_case(item)["reason"], "invalid_input")

    def test_prior_roll_and_relation_identities_must_be_unique(self):
        for second in (judgment(sourceId="b", targetId="b"),
                       judgment(sourceId="b", targetId="a", rollId="another-roll")):
            item = case("D03")
            item["input"]["confirmedGroup"]["members"].append({"memberId": "b", "actionText": "已冻结的先前行动"})
            item["input"]["knownPriorJudgments"] = [judgment(sourceId="b", targetId="a"), second]
            with self.assertRaisesRegex(lab.LabValidationError, "duplicate roll or relation"):
                lab.build_model_input(item)

    def test_prior_cannot_reference_an_unregistered_person(self):
        item = case("D03")
        item["input"]["knownPriorJudgments"] = [judgment(sourceId="unregistered", targetId="a")]
        with self.assertRaisesRegex(lab.LabValidationError, "unknown ID"):
            lab.build_model_input(item)

    def test_prior_input_does_not_certify_relation_confirmation(self):
        item = case("D03")
        result = lab.validate_dataset([item], [review(item)])
        self.assertEqual(result["summary"]["priorRelationConfirmation"],
                         "unverified_without_target_ledger_or_service_receipt")


class GuardTests(unittest.TestCase):
    def test_all_complete_fixtures_may_call_without_deciding_semantics(self):
        for task in lab.TASKS:
            self.assertEqual(lab.guard_case(case(task)), {"shouldCall": True, "reason": "ready"})

    def test_unadmitted_reaction_stops_and_does_not_mutate_the_roll(self):
        item = case("D04")
        item["input"]["admission"]["admitted"] = False
        item["input"]["judgments"] = [judgment(value=2, passed=False, admitted=False)]
        before = copy.deepcopy(item)
        self.assertEqual(lab.guard_case(item)["reason"], "not_admitted")
        self.assertEqual(item, before)

    def test_already_acted_reuses_and_skip_is_not_an_action(self):
        item = case("D04")
        item["input"]["previouslySkippedIds"] = ["b"]
        self.assertTrue(lab.guard_case(item)["shouldCall"])
        item["input"]["alreadyActedIds"] = ["b"]
        self.assertEqual(lab.guard_case(item)["reason"], "already_acted_reuse")
        self.assertEqual(item["input"]["judgments"][0]["value"], 12)

    def test_frozen_action_and_complete_current_judgment_are_required(self):
        item = case("D04")
        item["input"]["source"]["actionText"] = ""
        self.assertEqual(lab.guard_case(item)["reason"], "missing_frozen_source_text")
        item = case("D04")
        item["input"]["confirmedGroup"]["members"][0]["actionText"] = "rewritten"
        self.assertEqual(lab.guard_case(item)["reason"], "source_not_frozen_or_mismatch")
        item = case("D04")
        item["input"]["judgments"] = []
        self.assertEqual(lab.guard_case(item)["reason"], "missing_or_invalid_judgment")

    def test_roll_metadata_mismatch_does_not_become_a_model_decision(self):
        item = case("D04")
        item["input"]["judgments"][0]["passed"] = False
        self.assertEqual(lab.guard_case(item)["reason"], "missing_or_invalid_judgment")
        item["input"]["judgments"][0]["passed"] = True
        del item["input"]["judgments"][0]["threshold"]
        self.assertEqual(lab.guard_case(item)["reason"], "missing_or_invalid_judgment")

    def test_missing_another_frozen_group_action_stops_reaction(self):
        item = case("D04")
        item["input"]["confirmedGroup"]["members"].append({"memberId": "b", "actionText": ""})
        self.assertEqual(lab.guard_case(item)["reason"], "missing_frozen_group_text")

    def test_duplicate_roll_id_cannot_bind_two_relations(self):
        item = case("D05")
        group = item["input"]["group"]
        group["confirmedTargets"][1]["targetIds"] = ["a"]
        group["judgments"].append(judgment(sourceId="b", targetId="a"))
        self.assertEqual(lab.guard_case(item)["reason"], "duplicate_judgment_identity")

    def test_already_acted_target_does_not_get_eligible_again(self):
        item = case("D05")
        item["input"]["group"]["alreadyActedIds"] = ["b"]
        self.assertEqual(lab.guard_case(item)["reason"], "already_acted_eligibility_mismatch")

    def test_admitted_target_must_be_in_the_closed_group(self):
        item = case("D05")
        group = item["input"]["group"]
        group["memberIds"] = ["a"]
        group["members"] = group["members"][:1]
        group["confirmedTargets"] = group["confirmedTargets"][:1]
        self.assertEqual(lab.guard_case(item)["reason"], "admitted_target_missing_from_group")

    def test_unclosed_group_missing_member_or_judgment_stops(self):
        mutations = [
            (lambda g: g.update(closed=False), "group_not_closed"),
            (lambda g: g["members"].pop(), "missing_member_action"),
            (lambda g: g["judgments"].clear(), "missing_or_duplicate_relation_judgment"),
            (lambda g: g["confirmedTargets"].pop(), "missing_or_duplicate_confirmed_targets"),
        ]
        for mutate, reason in mutations:
            item = case("D05")
            mutate(item["input"]["group"])
            self.assertEqual(lab.guard_case(item)["reason"], reason)

    def test_damaged_guard_probe_is_valid_data_but_cannot_receive_output(self):
        item = case("D04")
        item["input"]["judgments"].clear()
        self.assertTrue(lab.validate_dataset([item], [review(item)])["valid"])
        with self.assertRaisesRegex(lab.LabValidationError, "guarded case"):
            lab.decode_output("D04", "任意回答", item)

    def test_missing_pending_input_is_not_a_legal_skip(self):
        item = case()
        item["input"]["advance"]["inputText"] = None
        self.assertEqual(lab.guard_case(item)["reason"], "missing_input_text")
        with self.assertRaises(lab.LabValidationError):
            lab.decode_output("D02", '{"kind":"skip"}', item)


class DatasetTests(unittest.TestCase):
    def test_derivatives_do_not_add_source_groups_or_anchors(self):
        anchor = case()
        child = copy.deepcopy(anchor)
        child.update(caseId="variant", derivedFrom=anchor["caseId"], anchorCase=False)
        result = lab.validate_dataset([anchor, child], [review(anchor), review(child)])
        self.assertTrue(result["valid"])
        self.assertEqual(result["summary"]["caseCount"], 2)
        self.assertEqual(result["summary"]["sourceGroupCount"], 1)
        self.assertEqual(result["summary"]["anchorCount"], 1)

    def test_renamed_group_and_split_of_derivative_are_rejected(self):
        anchor = case()
        child = copy.deepcopy(anchor)
        child.update(caseId="variant", derivedFrom=anchor["caseId"], anchorCase=False,
                     sourceGroup="falsely-new", split="screening")
        result = lab.validate_dataset([anchor, child], [review(anchor), review(child)])
        codes = {p["code"] for p in result["problems"]}
        self.assertIn("cross_group_derivation", codes)
        self.assertIn("cross_split_derivation", codes)
        self.assertFalse(result["valid"])

    def test_same_group_cannot_cross_split_even_without_parent_link(self):
        one = case()
        two = case(case_id="same-world-other-case")
        two["split"] = "screening"
        result = lab.validate_dataset([one, two], [review(one), review(two)])
        self.assertIn("cross_split_group", {p["code"] for p in result["problems"]})

    def test_missing_review_and_duplicate_case_cannot_pass_validation(self):
        one = case()
        result = lab.validate_dataset([one, copy.deepcopy(one)], [])
        codes = {p["code"] for p in result["problems"]}
        self.assertIn("duplicate_case", codes)
        self.assertIn("missing_review_draft", codes)

    def test_unchanged_input_cannot_create_an_independent_group(self):
        one = case()
        two = copy.deepcopy(one)
        two.update(caseId="fake-new-origin", sourceGroup="fake-new-group")
        result = lab.validate_dataset([one, two], [review(one), review(two)])
        self.assertIn("duplicate_input_across_groups", {p["code"] for p in result["problems"]})


class OutputTests(unittest.TestCase):
    def test_valid_closed_outputs_are_structural_only(self):
        self.assertEqual(lab.decode_output("D02", '{"kind":"skip"}', case()), {"kind": "skip"})
        self.assertEqual(lab.decode_output("D03", '{"targets":[]}', case("D03")), {"targets": []})
        raw = "  我护住箱子。\n"
        self.assertEqual(lab.decode_output("D04", raw, case("D04")), raw)
        self.assertEqual(lab.decode_output("D05", '{"results":{"a":"停下","b":"松手"}}', case("D05"))["results"]["a"], "停下")

    def test_invalid_action_is_not_repaired_into_skip(self):
        for raw in ('{"kind":"act","text":""}', '{"kind":"skip","text":"invented"}',
                    '{"kind":"unknown"}', '```json\n{"kind":"skip"}\n```'):
            with self.assertRaises(lab.LabValidationError):
                lab.decode_output("D02", raw, case())

    def test_unknown_duplicate_target_and_future_fields_are_rejected(self):
        for raw in ('{"targets":[{"targetId":"ghost"}]}',
                    '{"targets":[{"targetId":"b"},{"targetId":"b"}]}',
                    '{"targets":[{"targetId":"b","rollId":"future"}]}'):
            with self.assertRaises(lab.LabValidationError):
                lab.decode_output("D03", raw, case("D03"))

    def test_results_require_exact_nonempty_member_texts(self):
        for raw in ('{"results":{"a":"alone"}}', '{"results":{"a":"x","b":"y","ghost":"z"}}',
                    '{"results":{"a":"x","b":""}}'):
            with self.assertRaises(lab.LabValidationError):
                lab.decode_output("D05", raw, case("D05"))

    def test_duplicate_json_keys_nonfinite_and_wrong_task_are_rejected(self):
        for raw in ('{"kind":"act","kind":"skip"}', '{"kind":"act","text":NaN}'):
            with self.assertRaises(lab.LabValidationError):
                lab.decode_output("D02", raw, case())
        with self.assertRaises(lab.LabValidationError):
            lab.decode_output("D03", '{"targets":[]}', case())


class TimingTests(unittest.TestCase):
    def test_twenty_successes_do_not_hide_one_timeout(self):
        records = [attempt() for _ in range(20)] + [attempt(status="timeout", elapsedMs=900)]
        result = lab.summarize_attempts(records)
        self.assertEqual(result["attemptCount"], 21)
        self.assertEqual(result["completeCount"], 20)
        self.assertEqual(result["timeoutCount"], 1)
        self.assertEqual(result["timing"]["n"], 21)
        self.assertEqual(result["timing"]["maxMs"], 900)
        self.assertEqual(result["latencyStatus"], "latency_fail")
        self.assertEqual(result["overBudgetAttemptIndices"], [20])

    def test_cancelled_late_settle_keeps_real_cost_and_cannot_pass(self):
        records = [attempt() for _ in range(20)] + [attempt(status="cancelled", elapsedMs=5, settledElapsedMs=80)]
        result = lab.summarize_attempts(records)
        self.assertEqual(result["cancelledCount"], 1)
        self.assertEqual(result["timing"]["maxMs"], 80)
        self.assertEqual(result["latencyStatus"], "latency_fail")

    def test_fast_failure_cannot_be_counted_as_completed(self):
        result = lab.summarize_attempts([attempt() for _ in range(20)] + [attempt(status="failed")])
        self.assertEqual(result["completeCount"], 20)
        self.assertEqual(result["failedCount"], 1)
        self.assertEqual(result["latencyStatus"], "latency_unverified")

    def test_micro_success_never_proves_full_request_or_human_semantics(self):
        result = lab.summarize_attempts([attempt() for _ in range(20)])
        self.assertEqual(result["scopeSummaries"]["component"]["latencyStatus"], "within_observed_budget")
        self.assertEqual(result["fullRequestLatencyStatus"], "latency_unverified")
        self.assertEqual(result["semanticStatus"], "pending_human_review")
        self.assertEqual(result["formalVerdict"], "not_evaluated")

    def test_partial_range_chain_does_not_prove_complete_calculation(self):
        result = lab.summarize_attempts([attempt(measurementScope="range_chain", budgetMs=500, elapsedMs=100) for _ in range(20)])
        self.assertEqual(result["scopeSummaries"]["range_chain"]["latencyStatus"], "within_observed_budget")
        self.assertEqual(result["fullRequestLatencyStatus"], "latency_unverified")

    def test_full_request_budget_and_minimum_measurements_are_independent_of_quality(self):
        records = [attempt(measurementScope="full_request", budgetMs=500, elapsedMs=400) for _ in range(20)]
        report = lab.summarize_attempts(records)
        self.assertEqual(report["fullRequestLatencyStatus"], "within_observed_budget")
        self.assertEqual(report["semanticStatus"], "pending_human_review")
        self.assertEqual(report["formalVerdict"], "not_evaluated")
        records.append(attempt(measurementScope="full_request", budgetMs=500, status="timeout", elapsedMs=501))
        self.assertEqual(lab.summarize_attempts(records)["fullRequestLatencyStatus"], "latency_fail")

    def test_twenty_across_different_workloads_are_not_twenty_per_specification(self):
        records = [attempt(workloadId="short") for _ in range(10)] + [attempt(workloadId="long") for _ in range(10)]
        self.assertEqual(lab.summarize_attempts(records)["latencyStatus"], "latency_unverified")

    def test_missing_or_unknown_measurement_cannot_be_zero(self):
        result = lab.summarize_attempts([attempt(elapsedMs=None)])
        self.assertIsNone(result["timing"]["maxMs"])
        self.assertEqual(result["missingTimingAttemptIndices"], [0])
        self.assertEqual(result["latencyStatus"], "latency_unverified")
        with self.assertRaises(lab.LabValidationError):
            lab.summarize_attempts([attempt(elapsedMs=float("nan"))])
        with self.assertRaises(lab.LabValidationError):
            lab.summarize_attempts([attempt(budgetMs=1000)])


class JsonTests(unittest.TestCase):
    def test_hash_and_jsonl_are_deterministic_and_strict(self):
        value = {"z": "中文", "a": [1, True, None]}
        self.assertEqual(lab.canonical_bytes(value), lab.canonical_bytes({"a": [1, True, None], "z": "中文"}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.jsonl"
            path.write_bytes(lab.canonical_bytes(value) + b"\n")
            self.assertEqual(lab.load_jsonl(path), [value])
            self.assertEqual(len(lab.sha256_file(path)), 64)
            path.write_text('{"x":1,"x":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(lab.LabValidationError, ":1:"):
                lab.load_jsonl(path)
        for value in ({"a": float("inf")}, {1: "not a JSON key"}):
            with self.assertRaises(lab.LabValidationError):
                lab.canonical_bytes(value)


if __name__ == "__main__":
    unittest.main()
