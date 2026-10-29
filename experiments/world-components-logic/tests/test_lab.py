"""Engineering invariants only: these fixtures are not semantic evaluation data."""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("d_logic_lab", Path(__file__).resolve().parents[1] / "lab.py")
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)

SMOKE_PATH = Path(__file__).resolve().parents[1] / "runtime_smoke.py"
sys.path.insert(0, str(SMOKE_PATH.parent))
SMOKE_SPEC = importlib.util.spec_from_file_location("d_runtime_smoke", SMOKE_PATH)
smoke = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(smoke)


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


FULL_IDENTITY = {"arm": "A0", "task": "D02", "stage": "current", "component": "action",
                 "modelId": "M02", "deviceId": "dev1", "configHash": "cfg0"}


def bound_attempt(**changes):
    """Attempt whose record explicitly carries every comparability dimension."""
    return attempt(**{**FULL_IDENTITY, **changes})


def unbound_attempt(**changes):
    """Attempt with the workloadId field genuinely removed, not re-labeled."""
    value = attempt(**changes)
    del value["workloadId"]
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

    def test_d04_judgment_source_must_have_a_frozen_action(self):
        item = case("D04")
        item["input"]["judgments"].append(judgment(sourceId="b", targetId="a", rollId="future-b-a"))
        with self.assertRaisesRegex(lab.LabValidationError, "source has no frozen action"):
            lab.build_model_input(item)
        self.assertEqual(lab.guard_case(item)["reason"], "invalid_input")
        self.assertFalse(lab.validate_dataset([item], [review(item)])["valid"])

    def test_d04_prior_from_another_frozen_source_is_still_preserved(self):
        item = case("D04")
        item["input"]["confirmedGroup"]["members"].append({"memberId": "b", "actionText": "已冻结的先前行动"})
        item["input"]["judgments"].append(judgment(sourceId="b", targetId="a", rollId="prior-b-a"))
        self.assertEqual(lab.build_model_input(item), item["input"])

    def test_d04_round_source_judgment_stays_valid_probe_data_when_ledger_contradicts(self):
        item = case("D04")
        item["input"]["confirmedGroup"]["members"][0]["actionText"] = ""
        self.assertTrue(lab.validate_dataset([item], [review(item)])["valid"])
        self.assertEqual(lab.guard_case(item)["reason"], "source_not_frozen_or_mismatch")

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
        result = lab.summarize_attempts([bound_attempt() for _ in range(20)])
        self.assertEqual(result["scopeSummaries"]["component"]["latencyStatus"], "within_observed_budget")
        self.assertEqual(result["fullRequestLatencyStatus"], "latency_unverified")
        self.assertEqual(result["semanticStatus"], "pending_human_review")
        self.assertEqual(result["formalVerdict"], "not_evaluated")

    def test_partial_range_chain_does_not_prove_complete_calculation(self):
        records = [bound_attempt(measurementScope="range_chain", budgetMs=500, elapsedMs=100) for _ in range(20)]
        result = lab.summarize_attempts(records)
        self.assertEqual(result["scopeSummaries"]["range_chain"]["latencyStatus"], "within_observed_budget")
        self.assertEqual(result["fullRequestLatencyStatus"], "latency_unverified")

    def test_full_request_budget_and_minimum_measurements_are_independent_of_quality(self):
        records = [bound_attempt(measurementScope="full_request", budgetMs=500, elapsedMs=400) for _ in range(20)]
        report = lab.summarize_attempts(records)
        self.assertEqual(report["fullRequestLatencyStatus"], "within_observed_budget")
        self.assertEqual(report["semanticStatus"], "pending_human_review")
        self.assertEqual(report["formalVerdict"], "not_evaluated")
        records.append(attempt(measurementScope="full_request", budgetMs=500, status="timeout", elapsedMs=501))
        self.assertEqual(lab.summarize_attempts(records)["fullRequestLatencyStatus"], "latency_fail")

    def test_twenty_across_different_workloads_are_not_twenty_per_specification(self):
        records = [attempt(workloadId="short") for _ in range(10)] + [attempt(workloadId="long") for _ in range(10)]
        self.assertEqual(lab.summarize_attempts(records)["latencyStatus"], "latency_unverified")

    def test_mixed_arms_or_tasks_under_one_workload_split_and_cannot_pool_to_twenty(self):
        records = [attempt(arm=arm, task="D02", caseId=f"{arm}-D02-{i}")
                   for arm in ("A0", "A1") for i in range(10)]
        report = lab.summarize_attempts(records)
        nodes = report["scopeSummaries"]["component"]["workloads"]
        self.assertEqual(len(nodes), 2)
        self.assertEqual(sorted(node["identity"]["arm"] for node in nodes.values()), ["A0", "A1"])
        self.assertTrue(all(node["latencyStatus"] == "latency_unverified" for node in nodes.values()))
        self.assertEqual(report["latencyStatus"], "latency_unverified")
        task_records = [attempt(arm="A0", task=task, caseId=f"A0-{task}-{i}")
                        for task in ("D02", "D03") for i in range(10)]
        self.assertEqual(lab.summarize_attempts(task_records)["latencyStatus"], "latency_unverified")

    def test_partial_or_missing_identity_never_reaches_the_sample_floor(self):
        for records in ([attempt() for _ in range(20)],
                        [attempt(arm="A0", task="D02") for _ in range(20)]):
            report = lab.summarize_attempts(records)
            nodes = report["scopeSummaries"]["component"]["workloads"]
            self.assertEqual(len(nodes), 1)
            self.assertEqual(list(nodes.values())[0]["latencyStatus"], "latency_unverified")
            self.assertEqual(report["latencyStatus"], "latency_unverified")

    def test_full_identity_and_twenty_complete_attempts_pass_component_scope(self):
        report = lab.summarize_attempts([bound_attempt() for _ in range(20)])
        nodes = report["scopeSummaries"]["component"]["workloads"]
        self.assertEqual(len(nodes), 1)
        node = list(nodes.values())[0]
        self.assertEqual(node["latencyStatus"], "within_observed_budget")
        self.assertEqual(node["identity"], FULL_IDENTITY)
        self.assertEqual(node["completeCount"], 20)

    def test_structural_keys_keep_lookalike_identities_and_workloads_separate(self):
        records = [attempt(workloadId="job|arm=A0", caseId=f"one-{i}") for i in range(10)] + [
            attempt(workloadId="job", arm="A0", caseId=f"two-{i}") for i in range(10)]
        report = lab.summarize_attempts(records)
        nodes = report["scopeSummaries"]["component"]["workloads"]
        self.assertEqual(len(nodes), 2)
        self.assertTrue(all(node["attemptCount"] == 10 for node in nodes.values()))
        self.assertEqual(report["latencyStatus"], "latency_unverified")
        base = {"arm": "A0", "task": "D02", "stage": "current", "deviceId": "cpu", "configHash": "config"}
        records = [attempt(**base, component="action,modelId=qwen", modelId="t5", caseId=f"full-one-{i}")
                   for i in range(10)] + [
            attempt(**base, component="action", modelId="qwen,modelId=t5", caseId=f"full-two-{i}")
            for i in range(10)]
        report = lab.summarize_attempts(records)
        nodes = report["scopeSummaries"]["component"]["workloads"]
        self.assertEqual(len(nodes), 2)
        self.assertTrue(all(node["latencyStatus"] == "latency_unverified" for node in nodes.values()))
        self.assertTrue(all(len(node["identity"]) == len(lab.TIMING_IDENTITY_FIELDS) for node in nodes.values()))

    def test_missing_workload_id_never_shares_a_node_with_the_literal_id(self):
        records = [attempt(workloadId="unregistered", **FULL_IDENTITY, caseId=f"lit-{i}") for i in range(19)]
        records.append(unbound_attempt(**FULL_IDENTITY, caseId="absent"))
        report = lab.summarize_attempts(records)
        nodes = report["scopeSummaries"]["component"]["workloads"]
        self.assertEqual(len(nodes), 2)
        self.assertEqual(sorted(node["attemptCount"] for node in nodes.values()), [1, 19])
        self.assertTrue(all(node["latencyStatus"] == "latency_unverified" for node in nodes.values()))
        self.assertEqual(lab.summarize_attempts(list(reversed(records)))["scopeSummaries"]["component"]["workloads"],
                         nodes)
        records = [attempt(workloadId="unregistered", **FULL_IDENTITY, caseId=f"lit-{i}") for i in range(10)] + [
            unbound_attempt(**FULL_IDENTITY, caseId=f"absent-{i}") for i in range(10)]
        report = lab.summarize_attempts(records)
        self.assertEqual(len(report["scopeSummaries"]["component"]["workloads"]), 2)
        self.assertEqual(report["latencyStatus"], "latency_unverified")

    def test_blank_workload_id_is_absent_and_a_literal_id_binds_with_full_identity(self):
        report = lab.summarize_attempts([attempt(workloadId="  ", **FULL_IDENTITY) for _ in range(20)])
        nodes = report["scopeSummaries"]["component"]["workloads"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(list(nodes.values())[0]["latencyStatus"], "latency_unverified")
        nodes = lab.summarize_attempts(
            [attempt(workloadId="unregistered", **FULL_IDENTITY) for _ in range(20)]
        )["scopeSummaries"]["component"]["workloads"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(list(nodes.values())[0]["latencyStatus"], "within_observed_budget")

    def test_missing_or_unknown_measurement_cannot_be_zero(self):
        result = lab.summarize_attempts([attempt(elapsedMs=None)])
        self.assertIsNone(result["timing"]["maxMs"])
        self.assertEqual(result["missingTimingAttemptIndices"], [0])
        self.assertEqual(result["latencyStatus"], "latency_unverified")
        with self.assertRaises(lab.LabValidationError):
            lab.summarize_attempts([attempt(elapsedMs=float("nan"))])
        with self.assertRaises(lab.LabValidationError):
            lab.summarize_attempts([attempt(budgetMs=1000)])


class RuntimeSmokeTests(unittest.TestCase):
    """Regression coverage for the smoke journaling and no-overwrite rules."""

    def test_missing_dependency_import_writes_failure_record_and_preserves_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan, record = root / "plan.json", root / "record.json"
            plan.write_bytes(b'{"earlier": "evidence"}\n')

            def broken_import():
                raise ImportError("torch is not installed")

            report = smoke_report()
            with self.assertRaisesRegex(RuntimeError, "dependency_import"):
                smoke.run_with_journal(report, root, record, import_stack=broken_import,
                                       load_tokenizer=_not_called, load_model=_not_called,
                                       generation_attempt=_not_called)
            written = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(written["status"], "failed")
            self.assertEqual(written["failedStage"], "dependency_import")
            self.assertEqual(written["stages"][0]["stage"], "dependency_import")
            self.assertEqual(written["stages"][0]["error"],
                             {"type": "ImportError", "message": "torch is not installed"})
            self.assertIsInstance(written["stages"][0]["elapsedMs"], float)
            self.assertEqual(written["attempts"][0]["status"], "failed")
            self.assertEqual(written["attempts"][0]["stage"], "dependency_import")
            self.assertEqual(written["formalVerdict"], "not_evaluated")
            self.assertEqual(plan.read_bytes(), b'{"earlier": "evidence"}\n')

    def test_tokenizer_and_model_load_failures_are_journaled_with_stage(self):
        for stage in ("tokenizer_load", "model_load"):
            with tempfile.TemporaryDirectory() as directory:
                record = Path(directory) / "record.json"

                def failing(*_args, _stage=stage):
                    raise ValueError(f"broken {_stage}")

                steps = {"import_stack": lambda: {"importWallMs": 1.0},
                         "load_tokenizer": lambda ns, d: _FakeTokenizer(),
                         "load_model": lambda ns, d: _FakeModel(),
                         "generation_attempt": _not_called}
                steps["load_tokenizer" if stage == "tokenizer_load" else "load_model"] = failing
                report = smoke_report()
                with self.assertRaisesRegex(RuntimeError, stage):
                    smoke.run_with_journal(report, Path(directory), record, **steps)
                written = json.loads(record.read_text(encoding="utf-8"))
                self.assertEqual(written["failedStage"], stage)
                self.assertEqual([s["stage"] for s in written["stages"] if s["status"] == "failed"], [stage])
                self.assertEqual(written["attempts"][0]["stage"], stage)

    def test_generation_failure_keeps_partial_attempt_and_fails_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "record.json"

            def broken_generation(ns, tokenizer, model):
                return {"status": "failed", "stage": "generate", "raw": "", "inputTokens": 4,
                        "error": {"type": "RuntimeError", "message": "device vanished"}, "elapsedMs": 7.0}

            report = smoke_report()
            with self.assertRaisesRegex(RuntimeError, "generate"):
                smoke.run_with_journal(report, Path(directory), record,
                                       import_stack=lambda: {"importWallMs": 1.0},
                                       load_tokenizer=lambda ns, d: _FakeTokenizer(),
                                       load_model=lambda ns, d: _FakeModel(),
                                       generation_attempt=broken_generation)
            written = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(written["failedStage"], "generate")
            self.assertEqual(written["attempts"][0]["inputTokens"], 4)
            self.assertEqual((written["stages"][-1]["stage"], written["stages"][-1]["status"]),
                             ("generation_attempt", "failed"))

    def test_complete_run_records_every_stage_and_load_wall_ms(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "record.json"
            report = smoke_report()
            result = smoke.run_with_journal(report, Path(directory), record,
                                            import_stack=lambda: {"importWallMs": 1.0},
                                            load_tokenizer=lambda ns, d: _FakeTokenizer(),
                                            load_model=lambda ns, d: _FakeModel(),
                                            generation_attempt=ok_generation())
            self.assertIs(result, report)
            written = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(written["status"], "complete")
            self.assertIsNone(written["failedStage"])
            self.assertEqual([s["stage"] for s in written["stages"]],
                             ["dependency_import", "tokenizer_load", "model_load", "generation_attempt"])
            self.assertEqual([s["status"] for s in written["stages"]],
                             ["ok", "ok", "ok", "complete"])
            self.assertEqual(written["parameterCount"], 5)
            self.assertEqual(written["tokenizerLength"], 9)
            self.assertEqual(written["embeddingRows"], 7)
            self.assertIsInstance(written["loadWallMs"], float)
            self.assertEqual(written["attempts"][0]["status"], "complete")

    def test_plan_is_never_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "runtime-smoke-plan.json"
            self.assertEqual(smoke.write_plan(plan, {"identity": "A"}), "written")
            first = plan.read_bytes()
            with self.assertRaises(FileExistsError):
                smoke.write_plan(plan, {"identity": "B"})
            self.assertEqual(plan.read_bytes(), first)
            self.assertEqual(smoke.write_plan(plan, {"identity": "A"}), "reused")
            self.assertEqual(plan.read_bytes(), first)

    def test_run_ids_register_distinct_plan_and_record_names(self):
        plan, record = smoke.resolve_run_paths(None)
        self.assertEqual(plan.name, "runtime-smoke-plan.json")
        self.assertEqual(record.name, "l3-1-runtime-smoke.json")
        plan, record = smoke.resolve_run_paths("cpu-retry-1")
        self.assertEqual(plan.name, "runtime-smoke-plan-cpu-retry-1.json")
        self.assertEqual(record.name, "l3-1-runtime-smoke-cpu-retry-1.json")
        for bad in ("", "../escape", "a/b", "-lead", "x" * 65):
            with self.assertRaises(ValueError):
                smoke.resolve_run_paths(bad)

    def test_prepare_only_freezes_the_plan_without_loading_any_model(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory)
            payload_files = {}
            selected = ("README.md", "config.json", "tokenizer_config.json",
                        "special_tokens_map.json", "spiece.model", "model.safetensors")
            for name in selected:
                payload_files[name] = hashlib.sha256(f"payload-{name}".encode()).hexdigest()
            model_dir = local / "models" / "M02" / "r1"
            model_dir.mkdir(parents=True)
            (model_dir / "payload-manifest.json").write_text(json.dumps({
                "modelId": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese", "revision": "r1",
                "files": [{"path": name, "sha256": digest} for name, digest in payload_files.items()],
            }), encoding="utf-8")
            for name, digest in payload_files.items():
                (model_dir / name).write_text(f"payload-{name}", encoding="utf-8")
            registry_path = local / "registry.json"
            registry_path.write_text(json.dumps({"models": [{
                "id": "IDEA-CCNL/Randeng-T5-77M-MultiTask-Chinese", "revision": "r1",
                "files": [{"path": name, "sha256_of_fetched_bytes": digest}
                          for name, digest in payload_files.items()],
            }]}), encoding="utf-8")
            saved = (smoke.LOCAL, smoke.REGISTRY, smoke._dependency_versions, sys.argv,
                     {k: os.environ.get(k) for k in ("HF_HOME", "HF_HUB_OFFLINE")})
            smoke.LOCAL, smoke.REGISTRY = local, registry_path
            smoke._dependency_versions = lambda: {"torch": "stub"}
            sys.argv = ["runtime_smoke.py", "--prepare-only"]
            try:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    smoke.main()
                summary = json.loads(output.getvalue())
                plan_path = local / "runtime-smoke-plan.json"
                self.assertEqual(summary["modelLoaded"], False)
                self.assertEqual(summary["planState"], "written")
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
                self.assertEqual(plan["formalVerdict"], "not_evaluated")
                self.assertEqual(plan["model"]["revision"], "r1")
                plan_bytes_after_first = plan_path.read_bytes()
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    smoke.main()
                self.assertEqual(json.loads(output.getvalue())["planState"], "reused")
                self.assertEqual(plan_path.read_bytes(), plan_bytes_after_first)
            finally:
                smoke.LOCAL, smoke.REGISTRY = saved[0], saved[1]
                smoke._dependency_versions = saved[2]
                sys.argv = saved[3]
                for key, value in saved[4].items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


def _not_called(*_args, **_kwargs):
    raise AssertionError("this step must not be reached")


def _FakeTokenizer():
    class _Tokenizer:
        def __len__(self):
            return 9
    return _Tokenizer()


def _FakeModel():
    class _Param:
        def numel(self):
            return 5

    class _Embeddings:
        num_embeddings = 7

    class _Model:
        generation_config = type("GenerationConfig", (), {"eos_token_id": 1})()

        def parameters(self):
            return [_Param()]

        def get_input_embeddings(self):
            return _Embeddings()
    return _Model()


def ok_generation(record_status="complete", stage="decoded"):
    def generate(_ns, _tokenizer, _model):
        return {"status": record_status, "stage": stage, "raw": "模型已载入",
                "finishedWithEos": record_status == "complete",
                "elapsedMs": 5.0, "settledElapsedMs": 5.0}
    return generate


def smoke_report():
    return {"schema": "jity-d-nonbusiness-runtime-smoke-v1", "formalVerdict": "not_evaluated",
            "semanticStatus": "not_evaluated"}


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
