"""R1 recovery candidate checks; these specimens are not SQL transactions."""

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError as JsonSchemaValidationError
from pydantic import ValidationError
import pytest

from app.schemas.world.canonical import canonical_digest
from app.schemas.world.v2 import FrozenGroupView, PointRecoveryView, RollOutcome
from app.schemas.world.v2.registry import OPERATION_BY_NAME


BASE = Path(__file__).resolve().parents[2] / "design/world-protocol/v2"
SCHEMA = json.loads((BASE / "world-protocol.schema.json").read_text())


def load(name):
    return json.loads((BASE / name).read_text())


def check_shape(name, value):
    Draft202012Validator({**SCHEMA, "$ref": f"#/$defs/{name}"}).validate(value)


def member(member_id, targets):
    return {"memberId": member_id, "actionText": f"{member_id} accepted action",
            "targets": targets, "resultText": None, "rollRefs": []}


def target(target_id):
    return {"targetId": target_id, "triggerKey": f"trigger_{target_id}"}


def final_roll(source, destination, *, eligible=True, result=15):
    return {"rollId": f"roll_{source}_{destination}", "groupId": "group",
            "sourceId": source, "targetId": destination, "triggerKey": f"trigger_{destination}",
            "ruleVersion": "reaction-d20-v1", "target": 11, "result": result,
            "eligibilityBaselineDigest": "a" * 64, "eligible": eligible,
            "admitted": eligible and result >= 11}


def threat(source, destination, status, *, disposition=None):
    value = {"sourceId": source, "targetId": destination,
             "triggerKey": f"trigger_{destination}", "status": status,
             "rollId": None if status == "pending_roll" else f"roll_{source}_{destination}",
             "reactionMemberId": destination if disposition in ("created", "reused") else None}
    if status == "handled":
        value["actionDisposition"] = disposition
    return value


def group(members, rolls, threats, stack):
    members = copy.deepcopy(members)
    for item in members:
        item["rollRefs"] = [{key: roll[key] for key in ("sourceId", "targetId", "triggerKey", "rollId")}
                            for roll in rolls if roll["sourceId"] == item["memberId"]]
    return {"groupId": "group", "pointId": "point", "inputProjectionHash": "b" * 64,
            "members": members, "acceptedSources": [
                {"memberId": item["memberId"], "sourceEpoch": 7, "sourceAttempt": 1,
                 "actionContentHash": hashlib.sha256(item["actionText"].encode()).hexdigest(),
                 "targetsContentHash": None if item["targets"] is None else canonical_digest(item["targets"]),
                 "resultContentHash": None, "candidatesContentHash": None}
                for item in members], "candidates": None,
            "rolls": sorted(copy.deepcopy(rolls), key=lambda r: (r["sourceId"], r["targetId"], r["triggerKey"])),
            "progress": {"sourceStack": stack, "threats": sorted(
                copy.deepcopy(threats), key=lambda t: (t["sourceId"], t["targetId"], t["triggerKey"]))}}


def batch_reuse_group():
    # C pre-rolled both D/E as eligible. D's subtree accepts E first, so C->E
    # explicitly reuses that action. E->C was issued later and was ineligible.
    return group([member("c", [target("d"), target("e")]),
                  member("d", [target("e")]), member("e", [target("c")])],
                 [final_roll("c", "d"), final_roll("c", "e"), final_roll("d", "e"),
                  final_roll("e", "c", eligible=False)],
                 [threat("c", "d", "handled", disposition="created"),
                  threat("c", "e", "handled", disposition="reused"),
                  threat("d", "e", "handled", disposition="created"),
                  threat("e", "c", "handled", disposition="none")], [])


@pytest.mark.parametrize("value,stack,frontier", [
    (group([member("c", None)], [], [], ["c"]), ["c"], ["c"]),
    (group([member("c", [])], [], [], []), [], []),
    (group([member("c", [target("d")])], [], [threat("c", "d", "pending_roll")], ["c"]), ["c"], ["c"]),
    (group([member("c", [target("d")])], [final_roll("c", "d")],
           [threat("c", "d", "reaction_pending")], ["c"]), ["c"], ["c"]),
    (group([member("c", [target("d")]), member("d", None)], [final_roll("c", "d")],
           [threat("c", "d", "handled", disposition="created")], ["d", "c"]), ["d", "c"], ["d"]),
    (group([member("c", [target("d"), target("e")]), member("d", None)], [final_roll("c", "d")],
           [threat("c", "d", "handled", disposition="created"), threat("c", "e", "pending_roll")],
           ["d", "c"]), ["d", "c"], ["c", "d"]),
    (group([member("c", [target("d"), target("e")]), member("d", [])], [final_roll("c", "d")],
           [threat("c", "d", "handled", disposition="created"), threat("c", "e", "pending_roll")],
           ["c"]), ["c"], ["c"]),
    (group([member("c", [target("d")])], [final_roll("c", "d", result=3)],
           [threat("c", "d", "handled", disposition="none")], []), [], []),
    (batch_reuse_group(), [], []),
])
def test_recovery_checkpoint_represents_exact_next_action(value, stack, frontier):
    check_shape("FrozenGroupView", value)
    parsed = FrozenGroupView.model_validate(value)
    assert parsed.progress.sourceStack == stack
    assert parsed.frontier_ids() == frontier
    assert parsed.initiator_id() == "c"


def test_batch_reuse_keeps_original_admission_and_distinct_acceptance_edges():
    parsed = FrozenGroupView.model_validate(batch_reuse_group())
    old_ce = next(roll for roll in parsed.rolls if roll.sourceId == "c" and roll.targetId == "e")
    assert old_ce.eligible and old_ce.admitted
    assert [(item.sourceId, item.targetId, item.actionDisposition) for item in parsed.progress.threats] == [
        ("c", "d", "created"), ("c", "e", "reused"), ("d", "e", "created"), ("e", "c", "none")]
    assert parsed.members[-1].rollRefs[0].sourceId == "e"
    assert not parsed.rolls[-1].eligible and not parsed.rolls[-1].admitted


def test_nullable_member_placeholder_retains_a_pending_admitted_causal_relation():
    value = group([member("c", [target("d")])], [final_roll("c", "d")],
                  [threat("c", "d", "reaction_pending")], ["c"])
    value["members"].append({"memberId": "d", "actionText": None, "targets": None,
                             "resultText": None, "rollRefs": []})
    check_shape("FrozenGroupView", value)
    parsed = FrozenGroupView.model_validate(value)
    assert parsed.members[-1].actionText is None
    assert [source.memberId for source in parsed.acceptedSources] == ["c"]
    assert parsed.progress.threats[0].status == "reaction_pending"
    assert parsed.rolls[0].admitted


@pytest.mark.parametrize("causal_state", ["no_target", "pending_roll", "not_admitted"])
def test_nullable_member_placeholder_cannot_be_invented_without_pending_admission(causal_state):
    if causal_state == "no_target":
        value = group([member("c", None)], [], [], ["c"])
    elif causal_state == "pending_roll":
        value = group([member("c", [target("d")])], [],
                      [threat("c", "d", "pending_roll")], ["c"])
    else:
        value = group([member("c", [target("d")])], [final_roll("c", "d", eligible=False)],
                      [threat("c", "d", "handled", disposition="none")], [])
    value["members"].append({"memberId": "d", "actionText": None, "targets": None,
                             "resultText": None, "rollRefs": []})
    # Cross-array causal identity cannot be expressed by this JSON Schema;
    # the Python model must enforce it alongside the repository validator.
    check_shape("FrozenGroupView", value)
    with pytest.raises(ValidationError, match="placeholder has no pending admitted causal relation"):
        FrozenGroupView.model_validate(value)


@pytest.mark.parametrize("field", ["rolls", "progress"])
def test_missing_recovery_arrays_are_not_defaulted(field):
    value = batch_reuse_group()
    value.pop(field)
    with pytest.raises(ValidationError):
        FrozenGroupView.model_validate(value)
    with pytest.raises(JsonSchemaValidationError):
        check_shape("FrozenGroupView", value)


@pytest.mark.parametrize("field", ["sourceStack", "threats"])
def test_progress_arrays_are_required_even_when_empty(field):
    value = group([member("c", [])], [], [], [])
    value["progress"].pop(field)
    with pytest.raises(ValidationError):
        FrozenGroupView.model_validate(value)
    with pytest.raises(JsonSchemaValidationError):
        check_shape("FrozenGroupView", value)


def test_duplicate_stack_frames_are_rejected_by_json_schema_without_sorting_stack():
    value = group([member("c", [target("d")]), member("d", None)], [final_roll("c", "d")],
                  [threat("c", "d", "handled", disposition="created")], ["d", "c"])
    check_shape("FrozenGroupView", value)
    value["progress"]["sourceStack"] = ["d", "c", "c"]
    with pytest.raises(JsonSchemaValidationError):
        check_shape("FrozenGroupView", value)


@pytest.mark.parametrize("mutation", [
    "missing_roll", "extra_roll", "duplicate_roll_id", "duplicate_roll_key", "unsorted_rolls",
    "wrong_group", "wrong_trigger", "missing_threat", "duplicate_threat", "unsorted_threats",
    "wrong_roll_binding", "missing_outgoing_ref", "wrong_outgoing_owner", "incoming_ref_misused",
    "duplicate_created", "missing_created", "created_cycle", "unaccepted_reuse", "missing_action",
    "stack_duplicate", "stack_unknown", "stack_wrong_parent", "stack_skip_unfinished", "stack_completed_top",
])
def test_recovery_rejects_incomplete_or_inconsistent_facts(mutation):
    value = batch_reuse_group()
    rolls, progress = value["rolls"], value["progress"]
    if mutation == "missing_roll": rolls.pop()
    elif mutation == "extra_roll": rolls.append(final_roll("e", "f", eligible=False))
    elif mutation == "duplicate_roll_id": rolls[1]["rollId"] = rolls[0]["rollId"]
    elif mutation == "duplicate_roll_key": rolls.append(copy.deepcopy(rolls[0]))
    elif mutation == "unsorted_rolls": rolls.reverse()
    elif mutation == "wrong_group": rolls[0]["groupId"] = "another"
    elif mutation == "wrong_trigger": rolls[0]["triggerKey"] = "wrong"
    elif mutation == "missing_threat": progress["threats"].pop()
    elif mutation == "duplicate_threat": progress["threats"].append(copy.deepcopy(progress["threats"][0]))
    elif mutation == "unsorted_threats": progress["threats"].reverse()
    elif mutation == "wrong_roll_binding": progress["threats"][0]["rollId"] = "missing"
    elif mutation == "missing_outgoing_ref": value["members"][0]["rollRefs"].pop()
    elif mutation == "wrong_outgoing_owner": value["members"][0]["rollRefs"][0]["sourceId"] = "d"
    elif mutation == "incoming_ref_misused": value["members"][1]["rollRefs"] = [copy.deepcopy(value["members"][0]["rollRefs"][0])]
    elif mutation == "duplicate_created": progress["threats"][1]["actionDisposition"] = "created"
    elif mutation == "missing_created": progress["threats"][0]["actionDisposition"] = "reused"
    elif mutation == "created_cycle":
        rolls[-1]["eligible"] = rolls[-1]["admitted"] = True
        progress["threats"][-1].update(actionDisposition="created", reactionMemberId="c")
    elif mutation == "unaccepted_reuse":
        value["acceptedSources"].pop()
        value["members"][-1]["actionText"] = None
        value["members"][-1]["targets"] = None
        value["members"][-1]["rollRefs"] = []
    elif mutation == "missing_action": value["members"][1]["actionText"] = None
    elif mutation == "stack_duplicate": progress["sourceStack"] = ["c", "c"]
    elif mutation == "stack_unknown": progress["sourceStack"] = ["missing", "c"]
    elif mutation == "stack_wrong_parent":
        value["members"][-1]["targets"] = None
        value["acceptedSources"][-1]["targetsContentHash"] = None
        value["members"][-1]["rollRefs"] = []
        rolls.pop(); progress["threats"].pop()
        progress["sourceStack"] = ["e", "c"]
    elif mutation == "stack_skip_unfinished":
        value = group([member("c", None)], [], [], [])
    elif mutation == "stack_completed_top": progress["sourceStack"] = ["c"]
    with pytest.raises(ValidationError):
        FrozenGroupView.model_validate(value)


@pytest.mark.parametrize("mutation", ["pending_with_saved_roll", "unadmitted_reaction", "accepted_reaction_pending",
                                      "admitted_without_action", "wrong_handled_target"])
def test_threat_state_requires_its_exact_final_fact(mutation):
    value = group([member("c", [target("d")])], [final_roll("c", "d")],
                  [threat("c", "d", "reaction_pending")], ["c"])
    if mutation == "pending_with_saved_roll": value["progress"]["threats"][0] = threat("c", "d", "pending_roll")
    elif mutation == "unadmitted_reaction": value["rolls"][0].update(eligible=False, admitted=False)
    elif mutation == "accepted_reaction_pending":
        value = group([member("c", [target("d")]), member("d", None)], [final_roll("c", "d")],
                      [threat("c", "d", "reaction_pending")], ["c"])
    elif mutation == "admitted_without_action": value["progress"]["threats"][0] = threat("c", "d", "handled", disposition="none")
    else:
        value = group([member("c", [target("d")]), member("d", None)], [final_roll("c", "d")],
                      [threat("c", "d", "handled", disposition="created")], ["d", "c"])
        value["progress"]["threats"][0]["reactionMemberId"] = "c"
    with pytest.raises(ValidationError):
        FrozenGroupView.model_validate(value)


@pytest.mark.parametrize("mutation", ["drop_group", "duplicate_group", "wrong_members", "wrong_frontier", "closed_unfinished"])
def test_point_recovery_cross_checks_work_and_progress(mutation):
    value = load("fixtures/branches/recovery-unconfirmed.success.json")["recovery"]["current"]
    if mutation == "drop_group": value["groups"] = []
    elif mutation == "duplicate_group": value["groups"].append(copy.deepcopy(value["groups"][0]))
    elif mutation == "wrong_members": value["work"]["pendingGroup"]["memberIds"].append("person_d")
    elif mutation == "wrong_frontier": value["work"]["pendingGroup"]["frontierIds"] = []
    else:
        value["work"]["pendingGroup"]["frontierIds"] = []
        value["work"]["pendingGroup"]["closed"] = True
        value["work"]["phase"] = "settle_group"
    with pytest.raises(ValidationError):
        PointRecoveryView.model_validate(value)


def test_d20_rule_has_one_frozen_threshold_in_python_and_json_schema():
    value = final_roll("c", "d")
    check_shape("RollOutcome", value)
    RollOutcome.model_validate(value)
    value["target"] = 10
    with pytest.raises(ValidationError):
        RollOutcome.model_validate(value)
    with pytest.raises(JsonSchemaValidationError):
        check_shape("RollOutcome", value)


@pytest.mark.parametrize("code", ["frozen_work_missing", "frozen_work_corrupt"])
def test_context_declares_frozen_read_failures_and_authored_specimens(code):
    assert code in {item.code for item in OPERATION_BY_NAME["get_context"].errorCodes}
    value = load(f"fixtures/branches/recovery-{code}.error.json")
    check_shape("ErrorResponse", value)
    assert value["operation"] == "get_context" and value["requestId"] is None
    assert value["error"]["clientAction"] == "pause"
