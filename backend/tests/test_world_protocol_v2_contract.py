"""S1 field-level contract checks for the v2 protocol candidate.

Covers the IF-02 field gate: envelope and error-code closure, claimToken and
inputText leakage, all-ops fixture coverage with the machine-readable permission
matrix, legal/illegal unions, unknown fields and versions, the root claim, and
set ordering versus significant outer order. Runtime transactions and apply
semantics are A2/A3 concerns and are deliberately absent here.
"""

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from pydantic.json_schema import models_json_schema
import pytest

from app.schemas.world.contracts import CONTRACT_MODELS, TimelinePoint
from app.schemas.world.v2 import (
    SCHEMA_MODELS, CommitPointRequest, ControlState, DiscoverGroupRequest,
    ErrorResponse, ExtendGroupRequest, GateView,
    NarrationClaimData, NarrationSubmitRequest, PendingGroupView,
    PointWorkView, PreviewPointRequest, SettlementGroup, StageTimeScanRequest,
)
from app.schemas.world.v2.errors import ERROR_CODES
from app.schemas.world.v2.registry import OPERATION_BY_NAME, OPERATIONS
from app.schemas.world.v2.schema import WireSchema

ARTIFACTS = Path(__file__).resolve().parents[2] / "design" / "world-protocol" / "v2"
MODELS = {model.__name__: model for model in SCHEMA_MODELS}


def load(name):
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def json_validator(name):
    schema = load("world-protocol.schema.json")
    return Draft202012Validator({**schema, "$ref": f"#/$defs/{name}"})


def validate_both(name, value):
    json_validator(name).validate(value)
    return MODELS[name].model_validate(value)


# ---------------------------------------------------------------------------
# Exported artifacts are current, resolvable and version-pinned
# ---------------------------------------------------------------------------


def test_exported_schema_is_current_and_valid():
    schema = load("world-protocol.schema.json")
    Draft202012Validator.check_schema(schema)
    _, expected = models_json_schema([(model, "validation") for model in SCHEMA_MODELS], schema_generator=WireSchema)
    assert schema["$defs"] == expected["$defs"]
    assert schema["$id"] == "urn:jity:world-protocol:v2"
    assert all(model.__name__ in schema["$defs"] for model in SCHEMA_MODELS)


def test_v1_models_live_inside_the_v2_schema_without_version_drift():
    defs = load("world-protocol.schema.json")["$defs"]
    for model in CONTRACT_MODELS:
        assert model.__name__ in defs
    state = defs["WorldState"]
    assert state["properties"]["schemaVersion"]["const"] == 1
    assert defs["WorldInitialState"]["properties"]["engineVersion"]["const"] == "world-engine-v1"


def test_exported_api_contract_is_current():
    contract = load("api-contract.json")
    assert contract["protocolVersion"] == 2
    assert contract["clientActions"] == list(
        __import__("app.schemas.world.v2.errors", fromlist=["ClientAction"]).ClientAction.__args__)
    assert contract["errorCodes"] == ERROR_CODES
    assert contract["operations"] == [spec.model_dump(mode="json", exclude_none=True)
                                      for spec in OPERATIONS]


def test_operations_json_enumerates_exactly_the_registry():
    assert load("fixtures/api/operations.json") == {
        "protocolVersion": 2,
        "operations": [spec.operation for spec in OPERATIONS],
    }


def test_every_registry_schema_reference_resolves():
    defs = load("world-protocol.schema.json")["$defs"]
    for spec in OPERATIONS:
        if spec.requestSchema is not None:
            assert spec.requestSchema in defs, spec.operation
        assert spec.successSchema in defs, spec.operation


# ---------------------------------------------------------------------------
# Credential and input-text leakage
# ---------------------------------------------------------------------------


def test_context_and_control_never_expose_tokens():
    defs = load("world-protocol.schema.json")["$defs"]
    for name in ("WorldContext", "ControlState", "GateView", "ContextResponse", "ErrorResponse"):
        assert "claimToken" not in json.dumps(defs[name])
        assert "leaseToken" not in json.dumps(defs[name])
    create_success = load("fixtures/api/create_world/success.json")
    assert create_success["data"]["lease"]["leaseToken"] == "lease_a"
    assert "leaseToken" not in json.dumps(create_success["world"])
    claim_success = load("fixtures/api/narration_claim/success.json")
    assert claim_success["data"]["claimToken"] == "claim_root"


def test_input_text_flows_only_through_context_active_input():
    for fixture in ARTIFACTS.glob("fixtures/api/*/success.json"):
        value = json.loads(fixture.read_text(encoding="utf-8"))
        if "data" in value:
            assert "inputText" not in json.dumps(value["data"]), fixture.name
    context = load("fixtures/api/get_context/success.json")
    assert "activeInput" in context
    commit_success = load("fixtures/api/commit_point/success.json")
    assert "activeInput" not in commit_success
    defs = load("world-protocol.schema.json")["$defs"]
    leaked = [name for name in defs if name.endswith("Success")
              and "inputText" in json.dumps(defs[name])]
    assert leaked == []
    assert "text" in defs["ActiveInput"]["properties"]


def test_get_context_has_no_request_id():
    defs = load("world-protocol.schema.json")["$defs"]
    assert "requestId" not in defs["ContextResponse"]["properties"]
    read_defs = [name for name in defs if name.startswith("ReadResult")]
    assert all("requestId" not in json.dumps(defs[name]) for name in read_defs)
    assert "requestId" not in load("fixtures/api/get_context/success.json")
    spec = OPERATION_BY_NAME["get_context"]
    assert spec.requestSchema == "GetContextRequest" and spec.method == "GET"


# ---------------------------------------------------------------------------
# All-ops fixture coverage (traversed from the registry, not from directories)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", list(OPERATIONS), ids=lambda spec: spec.operation)
def test_every_operation_has_request_success_and_error_fixtures(spec):
    base = ARTIFACTS / "fixtures" / "api" / spec.operation
    request = load(f"fixtures/api/{spec.operation}/request.json")
    success = load(f"fixtures/api/{spec.operation}/success.json")
    failure = load(f"fixtures/api/{spec.operation}/error.json")

    if spec.requestSchema is not None:
        json_validator(spec.requestSchema).validate(request)
        MODELS[spec.requestSchema].model_validate(request)
    else:
        assert request == {}
    json_validator(spec.successSchema).validate(success)
    MODELS[spec.successSchema].model_validate(success)
    if success.get("replayed") is False:
        assert success["requestHash"]
    json_validator("ErrorResponse").validate(failure)
    ErrorResponse.model_validate(failure)
    code_table = ERROR_CODES[failure["error"]["code"]]
    assert failure["error"]["httpStatus"] == code_table["httpStatus"]
    assert failure["error"]["clientAction"] == code_table["clientAction"]
    assert failure["error"]["retryable"] == code_table["retryable"]


def test_error_fixtures_represent_a_deduplicated_client_action():
    for spec in OPERATIONS:
        failure = load(f"fixtures/api/{spec.operation}/error.json")
        registered = {entry.code for entry in spec.errorCodes}
        assert failure["error"]["code"] in registered, spec.operation


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_every_error_code_has_a_matching_fixture(code):
    value = load(f"fixtures/errors/{code}.json")
    assert value["error"]["code"] == code
    validate_both("ErrorResponse", value)
    if ERROR_CODES[code]["controlRequired"]:
        assert value["control"] is not None


def test_registry_error_codes_never_drift_from_the_table():
    seen = set()
    for spec in OPERATIONS:
        for entry in spec.errorCodes:
            seen.add(entry.code)
    assert seen == set(ERROR_CODES), "every runtime error code must be reachable from some operation"


# ---------------------------------------------------------------------------
# Machine-readable permission matrix distinguishes the plan's five cases
# ---------------------------------------------------------------------------


def _spec(name):
    return OPERATION_BY_NAME[name]


def test_resume_and_pause_pass_through_gate_and_pause():
    for name in ("checkpoint_pause", "checkpoint_resume"):
        kinds = {pre.kind for pre in _spec(name).preconditions}
        assert "headNarration" not in kinds and "gate" not in kinds and "paused" not in kinds
        assert _spec(name).mutatesRevision is True


def test_restore_group_work_passes_gate_but_never_moves_revision():
    spec = _spec("checkpoint_restore_group_work")
    kinds = {pre.kind for pre in spec.preconditions}
    assert kinds == {"lease", "pointWork", "frozenSource"}
    assert next(pre.value for pre in spec.preconditions if pre.kind == "pointWork") == ["open", "sealed"]
    assert spec.mutatesRevision is False
    assert spec.idempotency.key == "requestId"
    assert spec.idempotency.businessKey == [
        "pointId", "groupId", "fenceEpoch", "sourceEpoch", "sourceAttempt", "manifest"]


def test_compute_operations_require_ready_gate_and_unpaused():
    compute_ops = (
        "checkpoint_begin_point", "checkpoint_set_point_time", "checkpoint_discover_group",
        "checkpoint_extend_group", "checkpoint_close_group", "checkpoint_stage_unit",
        "checkpoint_record_skip", "checkpoint_stage_time_scan", "checkpoint_seal_point",
        "checkpoint_prepare_successor", "create_rolls", "commit_point",
        "round_conclusion_conclude",
    )
    for name in compute_ops:
        spec = _spec(name)
        kinds = {pre.kind: pre.value for pre in spec.preconditions}
        assert kinds.get("headNarration") == "ready", name
        assert kinds.get("gate") == "cleared", name
        assert kinds.get("paused") is False, name


def test_cancel_requires_ready_head_but_allows_pause():
    spec = _spec("round_conclusion_cancel")
    kinds = {pre.kind: pre.value for pre in spec.preconditions}
    assert kinds.get("headNarration") == "ready"
    assert "paused" not in kinds and "gate" not in kinds


def test_group_operations_pin_their_work_phase():
    def phases(name):
        return {pre.value for pre in _spec(name).preconditions if pre.kind == "phase"}

    def group_states(name):
        return {pre.value for pre in _spec(name).preconditions if pre.kind == "activePendingGroup"}

    assert phases("checkpoint_discover_group") == {"select_actor"}
    assert phases("checkpoint_extend_group") == {"build_group"}
    assert phases("checkpoint_stage_unit") == {"settle_group"}
    assert group_states("checkpoint_discover_group") == {"absent"}
    assert group_states("checkpoint_close_group") == {"present"}


def test_revision_and_narration_side_effects_match_the_writer_matrix():
    for name in ("narration_claim", "narration_claim_renew", "narration_submit",
                 "narration_delete", "allocate_ids", "create_rolls", "preview_point",
                 "get_context", "list_points", "get_state", "narration_get",
                 "lease_acquire", "lease_renew", "lease_release"):
        assert _spec(name).mutatesRevision is False, name
    assert "marks_point_ready" in _spec("narration_submit").sideEffects
    assert "clears_gate" in _spec("narration_submit").sideEffects
    assert "clears_gate" in _spec("checkpoint_resume").sideEffects
    assert "advances_head" in _spec("commit_point").sideEffects


def test_preview_is_stateless_and_budget_bound():
    spec = _spec("preview_point")
    assert spec.idempotency.scope == "none"
    assert "requestId" not in PreviewPointRequest.model_fields
    assert "preview_budget_exceeded" in {entry.code for entry in spec.errorCodes}
    details = load("fixtures/api/preview_point/error.json")["error"]["details"]
    assert details["limit"] in ("request", "response")


def test_idempotency_keys_follow_the_plan():
    assert _spec("create_world").idempotency.scope == "global"
    assert _spec("commit_point").idempotency.model_dump() == {
        "scope": "world", "key": "requestId", "replay": "original_data",
        "businessKey": [], "businessReplay": None}
    assert _spec("allocate_ids").idempotency.businessKey == ["allocationKey", "slots.slotKey"]
    assert _spec("create_rolls").idempotency.businessReplay == "original_roll"


# ---------------------------------------------------------------------------
# Python and JSON Schema agree on illegal combinations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutation", ["unknown_field", "old_protocol", "future_protocol"])
def test_requests_reject_unknown_fields_and_versions(mutation):
    from app.schemas.world.v2.requests import BeginPointRequest

    value = load("fixtures/api/checkpoint_begin_point/request.json")
    if mutation == "unknown_field":
        value["surprise"] = True
    elif mutation == "old_protocol":
        value["protocolVersion"] = 1
    else:
        value["protocolVersion"] = 3
    assert list(json_validator("BeginPointRequest").iter_errors(value))
    with pytest.raises(ValidationError):
        BeginPointRequest.model_validate(value)


def test_root_creation_has_roundless_context_with_issued_claim_and_gate():
    value = load("fixtures/api/create_world/success.json")
    world_ctx = validate_both("WorldContext", value["world"])
    assert world_ctx.round is None and world_ctx.activeRoundId is None
    assert world_ctx.advance.advanceId is None and not world_ctx.advance.inputAvailable
    assert world_ctx.lease.fenceEpoch > 0
    control = validate_both("ControlState", value["control"])
    assert control.gate.status == "pending" and control.gate.generation == 1
    assert control.revision == 0 and control.canCompute is False


@pytest.mark.parametrize("mutation", ["pending_without_generation", "cleared_with_generation"])
def test_gate_view_pending_and_cleared_states_are_exact(mutation):
    value = {"status": "pending", "generation": 1,
             "issuedAtEpochMilli": 1792617595000, "expiresAtEpochMilli": 1792617895000}
    if mutation == "pending_without_generation":
        value["generation"] = None
    else:
        value["status"] = "none"
    assert list(json_validator("GateView").iter_errors(value))
    with pytest.raises(ValidationError):
        GateView.model_validate(value)


@pytest.mark.parametrize("value", [
    {"blockedReasons": ["narration_pending"], "paused": False, "canCompute": True},
    {"blockedReasons": [], "paused": True, "canCompute": True},
    {"blockedReasons": ["narration_pending", "narration_pending"], "paused": False, "canCompute": False},
])
def test_control_state_can_compute_contradictions_are_schema_level(value):
    base = {"phase": "select_actor", "revision": 1,
            "gate": {"status": "none", "generation": None, "issuedAtEpochMilli": None,
                     "expiresAtEpochMilli": None}}
    value = {**base, **value}
    assert list(json_validator("ControlState").iter_errors(value))
    with pytest.raises(ValidationError):
        ControlState.model_validate(value)


def test_blocked_reasons_normalize_to_a_sorted_set():
    value = {"phase": "select_actor", "paused": False, "revision": 1,
             "gate": {"status": "none", "generation": None, "issuedAtEpochMilli": None,
                      "expiresAtEpochMilli": None},
             "blockedReasons": ["paused", "narration_pending"], "canCompute": False}
    control = ControlState.model_validate(value)
    assert control.blockedReasons == ["narration_pending", "paused"]
    with pytest.raises(ValidationError):
        ControlState.model_validate({**value, "blockedReasons": ["paused", "paused"]})


OPEN_GROUP = {"groupId": "group_cd", "sourceId": "person_c", "memberIds": ["person_c", "person_d"],
              "targetIds": ["person_d"], "frontierIds": [], "closed": False}


@pytest.mark.parametrize("mutation", ["group_in_select", "missing_group_in_build",
                                      "open_group_in_settle", "closed_group_in_build"])
def test_point_work_view_phase_and_group_rules_are_schema_level(mutation):
    value = load("fixtures/api/checkpoint_stage_unit/success.json")["work"]
    if mutation == "group_in_select":
        value["pendingGroup"] = {**OPEN_GROUP, "frontierIds": ["person_d"], "closed": False}
        value["phase"] = "select_actor"
    elif mutation == "missing_group_in_build":
        value["phase"], value["pendingGroup"] = "build_group", None
    elif mutation == "open_group_in_settle":
        value["phase"] = "settle_group"
        value["pendingGroup"] = {**OPEN_GROUP, "closed": False}
    else:
        value["phase"] = "build_group"
        value["pendingGroup"] = {**OPEN_GROUP, "closed": True}
    assert list(json_validator("PointWorkView").iter_errors(value))
    with pytest.raises(ValidationError):
        PointWorkView.model_validate(value)


def test_point_work_view_working_index_must_match_staged_units():
    value = load("fixtures/api/checkpoint_stage_unit/success.json")["work"]
    value["working"] = {**value["working"], "settledUnitIds": []}
    # Cross-referencing settledUnitIds against the staged unit list needs
    # variables; only the Python contract layer can reject the drift.
    with pytest.raises(ValidationError):
        PointWorkView.model_validate(value)


@pytest.mark.parametrize("mutation", ["source_outside", "frontier_outside", "closed_with_frontier"])
def test_pending_group_membership_rules_are_python_level(mutation):
    value = {"groupId": "group_cd", "sourceId": "person_c",
             "memberIds": ["person_c", "person_d"], "targetIds": ["person_d"],
             "frontierIds": ["person_d"], "closed": False}
    if mutation == "source_outside":
        value["sourceId"] = "person_e"
    elif mutation == "frontier_outside":
        value["frontierIds"] = ["person_e"]
    else:
        value["closed"] = True
    with pytest.raises(ValidationError):
        PendingGroupView.model_validate(value)


def test_pending_group_duplicate_members_are_schema_level():
    value = {"groupId": "group_cd", "sourceId": "person_c",
             "memberIds": ["person_c", "person_c", "person_d"], "targetIds": ["person_d"],
             "frontierIds": ["person_d"], "closed": False}
    assert list(json_validator("PendingGroupView").iter_errors(value))
    with pytest.raises(ValidationError):
        PendingGroupView.model_validate(value)


def test_member_sets_are_sorted_and_deduplicated_not_reordered_silently():
    value = {"groupId": "group_cd", "sourceId": "person_c", "memberIds": ["person_d", "person_c"],
             "targetIds": ["person_d"], "frontierIds": ["person_d"], "closed": False}
    view = PendingGroupView.model_validate(value)
    assert view.memberIds == ["person_c", "person_d"]


def test_settled_units_keep_outer_order_but_sorted_member_sets():
    work = validate_both("PointWorkView", load("fixtures/api/checkpoint_stage_unit/success.json")["work"])
    assert [unit.unitId for unit in work.settledUnits] == ["unit_1"]
    assert work.settledUnits[0].memberIds == sorted(work.settledUnits[0].memberIds)
    # The outer unit list is ordered, so reversing a longer list stays legal as
    # long as the working index (a set) still matches.
    reordered = load("fixtures/api/checkpoint_stage_unit/success.json")["work"]
    reordered["settledUnits"] = [
        {**reordered["settledUnits"][0], "unitId": "unit_2"},
        {**reordered["settledUnits"][0], "unitId": "unit_1"},
    ]
    reordered["working"] = {**reordered["working"], "settledUnitIds": ["unit_1", "unit_2"]}
    view = PointWorkView.model_validate(reordered)
    assert [unit.unitId for unit in view.settledUnits] == ["unit_2", "unit_1"]


@pytest.mark.parametrize("mutation,schema_level", [
    ("actors_in_scan", True), ("named_group_without_actors", True),
    ("sanity_without_personality", False),
])
def test_settlement_group_stage_rules(mutation, schema_level):
    value = copy.deepcopy(load("fixtures/api/checkpoint_stage_time_scan/request.json"))["candidates"]
    if mutation == "actors_in_scan":
        value["actorIds"] = ["person_c"]
    elif mutation == "named_group_without_actors":
        value["groupId"] = "group_cd"
    else:
        value["sanities"] = {}
    if schema_level:
        assert list(json_validator("SettlementGroup").iter_errors(value))
        with pytest.raises(ValidationError):
            SettlementGroup.model_validate(value)
    else:
        # 2026-10-26 adoption-rule migration: the personality/sanity pairing
        # is an ADOPTION rule, not a wire shape — between-stage previews
        # project partial stage states through this wire model, and the
        # complete candidate is held to the rule by validate_unit (the
        # kernel units-ladder suite owns that refusal).
        assert SettlementGroup.model_validate(value)


def test_action_group_requires_actors():
    value = copy.deepcopy(load("fixtures/api/checkpoint_stage_unit/request.json"))["candidates"]
    value["actorIds"] = []
    assert list(json_validator("SettlementGroup").iter_errors(value))
    with pytest.raises(ValidationError):
        SettlementGroup.model_validate(value)


def test_extend_group_accepts_exactly_one_contribution_kind():
    base = load("fixtures/api/checkpoint_extend_group/request.json")
    both = {**base, "admittedMember": {"memberId": "person_e",
                                       "actionText": "E 从另一侧拉住门。",
                                       "rollRefs": [{"sourceId": "person_e", "targetId": "person_c",
                                                     "triggerKey": "trigger_ec", "rollId": "roll_ec"}]}}
    neither = {**base, "targets": None}
    for value in (both, neither):
        assert list(json_validator("ExtendGroupRequest").iter_errors(value))
        with pytest.raises(ValidationError):
            ExtendGroupRequest.model_validate(value)
    ExtendGroupRequest.model_validate(base)


def test_stage_time_scan_must_be_the_groupless_pure_time_unit():
    value = load("fixtures/api/checkpoint_stage_time_scan/request.json")
    StageTimeScanRequest.model_validate(value)
    named = {**value, "candidates": {**value["candidates"], "groupId": "group_x"}}
    assert list(json_validator("StageTimeScanRequest").iter_errors(named))
    with pytest.raises(ValidationError):
        StageTimeScanRequest.model_validate(named)


def test_narration_submit_text_and_failure_reason_pair():
    base = load("fixtures/api/narration_submit/request.json")
    NarrationSubmitRequest.model_validate(base)
    failed = {**base, "outcome": "failed", "text": None, "failureReason": "模型推理超时"}
    NarrationSubmitRequest.model_validate(failed)
    for broken in (
        {**base, "text": None},
        {**base, "failureReason": "both"},
        {**failed, "text": "偷偷带正文"},
        {**failed, "failureReason": None},
    ):
        assert list(json_validator("NarrationSubmitRequest").iter_errors(broken))
        with pytest.raises(ValidationError):
            NarrationSubmitRequest.model_validate(broken)


@pytest.mark.parametrize("mode,fence", [("head", 7), ("history", None)])
def test_narration_claim_fence_follows_mode(mode, fence):
    value = {"pointId": "root_0", "mode": mode, "generation": 1, "claimToken": "claim_root",
             "fenceEpoch": fence, "issuedAtEpochMilli": 1792617600000,
             "expiresAtEpochMilli": 1792617900000}
    validate_both("NarrationClaimData", value)
    crossed = {**value, "fenceEpoch": None if fence else 7}
    assert list(json_validator("NarrationClaimData").iter_errors(crossed))
    with pytest.raises(ValidationError):
        NarrationClaimData.model_validate(crossed)


# ---------------------------------------------------------------------------
# Request self-binding
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mutation,schema_level", [
    ("wrong_previous", False), ("wrong_round", False), ("wrong_advance", False),
    ("unnamed_group", True), ("duplicate_group", False),
])
def test_commit_request_binds_its_own_point_and_groups(mutation, schema_level):
    value = load("fixtures/api/commit_point/request.json")
    if mutation == "wrong_previous":
        value["point"]["previousPointId"] = "p_stale"
    elif mutation == "wrong_round":
        value["point"]["roundId"] = "round_9"
    elif mutation == "wrong_advance":
        value["point"]["advanceId"] = "advance_9"
    elif mutation == "unnamed_group":
        value["settlementGroups"][0]["groupId"] = None
    else:
        value["settlementGroups"] = [value["settlementGroups"][0], value["settlementGroups"][0]]
    if schema_level:
        assert list(json_validator("CommitPointRequest").iter_errors(value))
    with pytest.raises(ValidationError):
        CommitPointRequest.model_validate(value)


def test_commit_point_fixture_point_is_a_legal_timeline_point():
    value = load("fixtures/api/commit_point/request.json")
    validate_both("TimelinePoint", value["point"])


def test_discover_group_freezes_time_with_complete_target_set():
    value = load("fixtures/api/checkpoint_discover_group/request.json")
    DiscoverGroupRequest.model_validate(value)
    empty = {**value, "targetIds": []}
    DiscoverGroupRequest.model_validate(empty)
    duplicates = {**value, "targetIds": ["person_d", "person_d"]}
    with pytest.raises(ValidationError):
        DiscoverGroupRequest.model_validate(duplicates)


# ---------------------------------------------------------------------------
# Preview budget details
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("limit", ["request", "response"])
def test_preview_budget_details_limit_is_typed(limit):
    value = {
        "protocolVersion": 2, "engineVersion": "world-engine-v1", "schemaVersion": 1,
        "canonicalVersion": "world-canonical-v1", "serverTimeEpochMilli": 1792617600000,
        "replayed": False, "operation": "preview_point", "requestId": None, "worldId": "world_school",
        "error": {"code": "preview_budget_exceeded", "httpStatus": 413, "retryable": False,
                  "clientAction": "fix_request", "details": {"limit": limit}}}
    validate_both("ErrorResponse", value)


def test_preview_budget_without_limit_is_rejected():
    value = load("fixtures/api/preview_point/error.json")
    value["error"]["details"] = {}
    assert list(json_validator("ErrorResponse").iter_errors(value))
    with pytest.raises(ValidationError):
        ErrorResponse.model_validate(value)
