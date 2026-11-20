"""Stage-0 contract checks, not claims of a working scheduler or state reducer."""

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from pydantic.json_schema import models_json_schema
import pytest

from app.schemas.world.canonical import canonical_bytes, canonical_digest, parse_json
from app.schemas.world.contracts import (
    CONTRACT_MODELS, CancelHandback, DescriptionChange, EntityDelta,
    HeadNarrationClaim, HistoryNarrationClaim, ModelHandback, RootPoint,
    RoundCheckpoint, RoundConclusionRequest, TimelinePoint, WorldInitialState,
)

ARTIFACTS = Path(__file__).resolve().parents[2] / "design" / "world-protocol" / "v1"
MODELS = {model.__name__: model for model in CONTRACT_MODELS}


def load(name):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def json_validator(name):
    schema = load("world-protocol.schema.json")
    return Draft202012Validator({**schema, "$ref": f"#/$defs/{name}"})


def validate_both(name, value):
    json_validator(name).validate(value)
    return MODELS[name].model_validate(value)


def fixture_cases():
    yield "WorldInitialState", load("fixtures/school.initial.json")
    yield "WorldState", load("fixtures/school.initial-state.json")
    associated = load("fixtures/associated-points.json")
    yield "RootPoint", associated["root"]
    for point in associated["points"]:
        yield "TimelinePoint", point
    for checkpoint in associated["checkpoints"]:
        yield "RoundCheckpoint", checkpoint
    for checkpoint in load("fixtures/advance-chain.json").values():
        yield "RoundCheckpoint", checkpoint
    times = load("fixtures/time-only.json")
    for key in ("standalone", "chainMiddle"):
        yield "TimelinePoint", times[key]
    yield "RoundCheckpoint", times["checkpoint"]
    yield "WorldState", times["expectedStandaloneState"]
    yield "EntityDelta", load("fixtures/task-normalization.json")["finalDelta"]
    for key in ("replacement", "pureRemoval", "expectedCollapsed"):
        yield "DescriptionChange", load("fixtures/description-changes.json")[key]
    claims = load("fixtures/claims.json")
    yield "HeadNarrationClaim", claims["rootHead"]
    yield "HistoryNarrationClaim", claims["historyRoot"]
    requests = load("fixtures/requests.json")
    yield "PointCommitRequest", requests["normalCommit"]
    yield "PointCommitRequest", requests["timeCommit"]
    yield "RoundConclusionRequest", requests["conclusion"]
    yield "PreviewRequest", requests["preview"]


@pytest.mark.parametrize("name,value", list(fixture_cases()))
def test_authored_fixtures_match_schema_and_python(name, value):
    validate_both(name, value)


def test_exported_schema_is_current_and_valid():
    schema = load("world-protocol.schema.json")
    Draft202012Validator.check_schema(schema)
    _, expected = models_json_schema([(model, "validation") for model in CONTRACT_MODELS])
    assert schema["$defs"] == expected["$defs"]
    assert all(model.__name__ in schema["$defs"] for model in CONTRACT_MODELS)


@pytest.mark.parametrize("vector", load("canonical-vectors.json")["vectors"], ids=lambda v: v["id"])
def test_independently_authored_canonical_bytes_and_hashes(vector):
    value = parse_json(vector["inputJson"])
    if vector["schema"]:
        value = MODELS[vector["schema"]].model_validate(value).model_dump(mode="json")
    assert canonical_bytes(value).decode("utf-8") == vector["expectedCanonical"]
    assert canonical_bytes(value).hex() == vector["expectedUtf8Hex"]
    assert canonical_digest(value) == vector["expectedSha256"]


@pytest.mark.parametrize("raw", load("canonical-vectors.json")["rejectedJson"])
def test_invalid_raw_json_or_projection_rejected(raw):
    with pytest.raises(ValueError):
        parse_json(raw)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 1.25, 2**53])
def test_invalid_numeric_values_rejected(value):
    with pytest.raises(ValueError):
        canonical_bytes(value)


@pytest.mark.parametrize("field", ["schemaVersion", "initialSanity"])
def test_booleans_are_not_integer_fields(field):
    world = load("fixtures/school.initial.json")
    if field == "schemaVersion":
        world[field] = True
    else:
        world["characters"]["person_c"][field] = True
    with pytest.raises(ValidationError):
        WorldInitialState.model_validate(world)


def test_decimal_input_is_not_rounded_to_a_safe_integer():
    with pytest.raises(ValueError):
        parse_json('{"sanity":9007199254740991.1}')


def test_union_position_cycle_is_not_just_a_containment_cycle():
    world = load("fixtures/school.initial.json")
    world["items"]["key"]["initialPosition"] = {
        "containerId": "classroom1", "slotId": None,
        "relativeTo": {"entityId": "blackboard", "relation": "under"},
    }
    # Initially legal. Adding blackboard -> key creates a cross-kind cycle.
    WorldInitialState.model_validate(world)
    world["items"]["blackboard"]["initialPosition"]["containerId"] = "key"
    with pytest.raises(ValidationError, match="cyclic dependency"):
        WorldInitialState.model_validate(world)


@pytest.mark.parametrize("mutation", ["unknown_container", "wrong_slot", "unknown_task_parent", "duplicate_entity"])
def test_initial_registry_rejects_invalid_references(mutation):
    world = load("fixtures/school.initial.json")
    if mutation == "unknown_container":
        world["items"]["key"]["initialPosition"]["containerId"] = "new_entity"
    elif mutation == "wrong_slot":
        world["items"]["key"]["initialPosition"]["slotId"] = "unknown_pocket"
    elif mutation == "unknown_task_parent":
        world["characters"]["person_c"]["tasks"]["task_wait_noon"]["parentTaskId"] = "new_task"
    else:
        world["items"]["person_a"] = copy.deepcopy(world["items"]["key"])
    with pytest.raises(ValidationError):
        WorldInitialState.model_validate(world)


@pytest.mark.parametrize("change", [
    {"id": "change_x", "text": None, "supersedes": []},
    {"id": "change_x", "text": "", "supersedes": ["old"]},
    {"id": "change_x", "text": "  \t", "supersedes": ["old"]},
    {"id": "change_x", "text": "恢复。", "supersedes": ["change_x"]},
    {"id": "change_x", "text": "恢复。", "supersedes": ["old", "old"]},
])
def test_invalid_description_operation_rejected(change):
    with pytest.raises(ValidationError):
        DescriptionChange.model_validate(change)


def test_new_achieved_task_uses_one_encoding_and_stable_topology():
    value = load("fixtures/task-normalization.json")["finalDelta"]
    value["subtasksAdded"].reverse()
    result = EntityDelta.model_validate(value).model_dump(mode="json")
    assert [task["id"] for task in result["subtasksAdded"]] == ["task_new_parent", "task_new_child"]
    assert result["subtasksAdded"][1]["status"] == "achieved"
    assert "tasksAchieved" not in result
    value["tasksAchieved"] = ["task_new_child"]
    with pytest.raises(ValidationError, match="overlapping"):
        EntityDelta.model_validate(value)


def test_task_cycle_is_not_fixed_by_sorting():
    value = load("fixtures/task-normalization.json")["finalDelta"]
    value["subtasksAdded"][0]["parentTaskId"] = "task_new_child"
    with pytest.raises(ValidationError, match="cyclic"):
        EntityDelta.model_validate(value)


@pytest.mark.parametrize("conclusion", [
    {"kind": "handback", "closedBy": "cancel", "cancelReason": None},
    {"kind": "handback", "closedBy": "cancel", "cancelReason": " \n"},
    {"kind": "handback", "closedBy": "model", "cancelReason": "pretend_cancel"},
    {"kind": "handback"},
])
def test_cancellation_cannot_be_misrepresented_as_model_handback(conclusion):
    value = load("fixtures/advance-chain.json")["handback"]
    value["conclusion"] = conclusion
    assert list(json_validator("RoundCheckpoint").iter_errors(value))
    with pytest.raises(ValidationError):
        RoundCheckpoint.model_validate(value)


def test_cancel_and_model_handback_remain_distinguishable_in_history():
    rows = load("fixtures/advance-chain.json")
    cancel = validate_both("RoundCheckpoint", rows["cancel"])
    handback = validate_both("RoundCheckpoint", rows["handback"])
    assert isinstance(cancel.conclusion, CancelHandback)
    assert isinstance(handback.conclusion, ModelHandback)
    assert cancel.conclusion.cancelReason and handback.conclusion.cancelReason is None


@pytest.mark.parametrize("mutation", ["waiting_no_resume", "complete_no_conclusion", "automatic_pending", "internal_apply_phase", "settle_no_group"])
def test_checkpoint_combination_rejections(mutation):
    value = load("fixtures/advance-chain.json")["automatic"]
    if mutation == "waiting_no_resume":
        value["phase"] = "await_narration"
    elif mutation == "complete_no_conclusion":
        value["phase"] = "complete"
    elif mutation == "automatic_pending":
        value["advance"]["intentStatus"] = "pending"
    elif mutation == "internal_apply_phase":
        value["phase"] = "apply_updates"
    else:
        value["phase"] = "settle_group"
    assert list(json_validator("RoundCheckpoint").iter_errors(value))
    with pytest.raises(ValidationError):
        RoundCheckpoint.model_validate(value)


def test_linked_boundary_cannot_be_elapsed_even_with_nonzero_duration():
    value = load("fixtures/associated-points.json")["points"][2]
    value["timeAdvance"]["boundary"] = "elapsed"
    assert list(json_validator("TimelinePoint").iter_errors(value))
    with pytest.raises(ValidationError):
        TimelinePoint.model_validate(value)


def test_root_claim_needs_epoch_but_not_advance():
    value = load("fixtures/claims.json")["rootHead"]
    claim = validate_both("HeadNarrationClaim", value)
    assert claim.advanceId is None and claim.fenceEpoch == 7
    value["fenceEpoch"] = None
    assert list(json_validator("HeadNarrationClaim").iter_errors(value))
    with pytest.raises(ValidationError):
        HeadNarrationClaim.model_validate(value)


def test_history_claim_cannot_borrow_head_lease_epoch():
    value = load("fixtures/claims.json")["historyRoot"]
    value["fenceEpoch"] = 7
    with pytest.raises(ValidationError):
        HistoryNarrationClaim.model_validate(value)


def test_cancel_operation_and_conclusion_source_must_agree():
    value = {"worldId": "world_school", "advanceId": "advance_1", "roundId": "round_1",
             "expectedPointId": "p3", "expectedVersion": 3, "requestId": "request_conclusion",
             "expectedCheckpointRevision": 5, "leaseToken": "lease_a", "fenceEpoch": 7,
             "operation": "conclude", "conclusion": load("fixtures/advance-chain.json")["cancel"]["conclusion"]}
    assert list(json_validator("RoundConclusionRequest").iter_errors(value))
    with pytest.raises(ValidationError):
        RoundConclusionRequest.model_validate(value)


def test_cross_round_chain_fixture_keeps_identity_and_consumption():
    rows = load("fixtures/advance-chain.json")
    first = RoundCheckpoint.model_validate(rows["afterConclusion"])
    second = RoundCheckpoint.model_validate(rows["automatic"])
    assert first.conclusion.nextRoundId == second.roundId
    assert first.advance == second.advance
    middle = load("fixtures/time-only.json")
    point = TimelinePoint.model_validate(middle["chainMiddle"])
    checkpoint = RoundCheckpoint.model_validate(middle["checkpoint"])
    assert point.advanceId == checkpoint.advance.advanceId == second.advance.advanceId
    assert point.roundId == checkpoint.roundId == second.roundId
    assert checkpoint.phase == "await_narration"
    assert point.entityDeltas["person_c"].tasksAchieved == ["task_wait_noon"]


@pytest.mark.parametrize("mutation", ["wrong_parent", "wrong_advance", "skip_narration", "missing_task_coverage", "missing_personality_coverage", "repeat_actor"])
def test_commit_request_rejects_inconsistent_bindings_and_coverage(mutation):
    from app.schemas.world.contracts import PointCommitRequest

    requests = load("fixtures/requests.json")
    value = requests["timeCommit"] if mutation == "missing_personality_coverage" else requests["normalCommit"]
    if mutation == "wrong_parent":
        value["point"]["previousPointId"] = "stale_head"
    elif mutation == "wrong_advance":
        value["checkpoint"]["advance"]["advanceId"] = "another_advance"
    elif mutation == "skip_narration":
        value["checkpoint"]["phase"] = "settle_group"
        value["checkpoint"]["resumePhase"] = None
    elif mutation == "missing_task_coverage":
        value["stageCandidates"][0]["taskCoverageIds"].pop()
    elif mutation == "missing_personality_coverage":
        value["stageCandidates"][0]["personalityCoverageIds"].pop()
    else:
        value["stageCandidates"][1]["actorIds"] = ["person_a"]
    with pytest.raises(ValidationError):
        PointCommitRequest.model_validate(value)


def test_stage_candidate_cannot_claim_a_new_task_was_born_achieved():
    from app.schemas.world.contracts import PointCommitRequest

    value = load("fixtures/requests.json")["normalCommit"]
    task = load("fixtures/task-normalization.json")["finalDelta"]["subtasksAdded"][1]
    value["stageCandidates"][0]["subtasksAdded"] = {"person_c": [task]}
    assert list(json_validator("PointCommitRequest").iter_errors(value))
    with pytest.raises(ValidationError):
        PointCommitRequest.model_validate(value)


def test_pure_time_unit_cannot_invent_movement_or_direct_sanity_loss():
    from app.schemas.world.contracts import PointCommitRequest

    value = load("fixtures/requests.json")["timeCommit"]
    value["stageCandidates"][0]["positions"] = {"person_c": {"containerId": "corridor"}}
    with pytest.raises(ValidationError):
        PointCommitRequest.model_validate(value)
    value["stageCandidates"][0]["positions"] = {}
    value["stageCandidates"][0]["personalities"] = {}
    with pytest.raises(ValidationError):
        PointCommitRequest.model_validate(value)
