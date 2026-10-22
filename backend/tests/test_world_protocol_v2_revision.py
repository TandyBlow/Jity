"""S1 review regressions F01-F10; runtime ownership/transactions remain A2/A3."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.schemas.world.v2 import SCHEMA_MODELS
from app.schemas.world.v2.registry import OPERATION_BY_NAME, OPERATIONS
from app.schemas.world.v2.errors import ERROR_CODES

ROOT = Path(__file__).resolve().parents[2] / "design/world-protocol/v2"
MODELS = {model.__name__: model for model in SCHEMA_MODELS}
SCHEMA = json.loads((ROOT / "world-protocol.schema.json").read_text(encoding="utf-8"))


def load(path):
    return json.loads((ROOT / "fixtures" / path).read_text(encoding="utf-8"))


def check(name, value, accepted=True):
    validator = Draft202012Validator({**SCHEMA, "$ref": f"#/$defs/{name}"})
    if accepted:
        validator.validate(value)
        return MODELS[name].model_validate(value)
    assert list(validator.iter_errors(value)), (name, value)
    with pytest.raises(ValidationError):
        MODELS[name].model_validate(value)


def test_required_workflow_operations_are_independent_of_registry_coverage():
    # Authored from workflow §9.2, deliberately not derived from the registry.
    required = {
        "create_world", "get_context", "checkpoint_start_advance",
        "checkpoint_begin_point", "checkpoint_set_point_time", "checkpoint_discover_group",
        "checkpoint_extend_group", "checkpoint_close_group", "checkpoint_stage_unit",
        "checkpoint_record_skip", "checkpoint_stage_time_scan", "checkpoint_seal_point",
        "checkpoint_prepare_successor", "checkpoint_restore_group_work", "checkpoint_pause",
        "checkpoint_resume", "round_conclusion_conclude", "round_conclusion_cancel",
        "lease_acquire", "lease_renew", "lease_release", "allocate_ids", "preview_point",
        "create_rolls", "commit_point", "list_points", "get_state", "narration_claim",
        "narration_claim_renew", "narration_submit", "narration_get", "narration_delete",
    }
    assert required == set(OPERATION_BY_NAME)
    start = OPERATION_BY_NAME["checkpoint_start_advance"]
    assert {p.kind: p.value for p in start.preconditions} == {
        "activeAdvance": "absent", "pointWork": "absent", "lease": "valid",
        "paused": False, "headNarration": "ready", "gate": "cleared"}
    assert "inputText" not in json.dumps(load("api/checkpoint_start_advance/success.json")["data"])


@pytest.mark.parametrize("spec", [s for s in OPERATIONS if s.path.endswith("/checkpoint")],
                         ids=lambda s: s.operation)
def test_checkpoint_dispatch_selects_exactly_one_operation(spec):
    value = load(f"api/{spec.operation}/request.json")
    check("CheckpointDispatch", value)
    matches = [s.operation for s in OPERATIONS if s.path == spec.path and
               not list(Draft202012Validator({**SCHEMA, "$ref": f"#/$defs/{s.requestSchema}"}).iter_errors(value))]
    assert matches == [spec.operation]
    for operation in (None, "unknown"):
        broken = {**value, "operation": operation}
        check("CheckpointDispatch", broken, False)


def test_normal_handback_has_no_successor_and_cannot_be_manual_cancel():
    request = load("branches/handback.request.json")
    check("ConcludeRoundRequest", request)
    check("RoundConclusionDispatch", request)
    check("ConcludeRoundSuccess", load("branches/handback.success.json"))
    check("ErrorResponse", load("branches/handback.error.json"))
    request["conclusion"]["closedBy"] = "cancel"
    check("ConcludeRoundRequest", request, False)
    data = load("branches/handback.success.json")["data"]
    check("ConcludeRoundData", {**data, "nextRoundId": "round_2"}, False)
    assert OPERATION_BY_NAME["round_conclusion_conclude"].conditionalSideEffects == {
        "conclusion.kind=continue": ["creates_successor_round"],
        "conclusion.kind=handback": ["expires_input_intent", "clears_input_text"]}


@pytest.mark.parametrize("name,operation", [
    ("NarrationClaimRequest", "narration_claim"),
    ("NarrationClaimRenewRequest", "narration_claim_renew"),
    ("NarrationSubmitRequest", "narration_submit"),
    ("NarrationDeleteRequest", "narration_delete"),
])
def test_head_narration_credentials_and_history_isolation(name, operation):
    value = load(f"api/{operation}/request.json")
    check(name, value)
    for field in ("leaseToken", "fenceEpoch"):
        broken = copy.deepcopy(value)
        broken.pop(field)
        check(name, broken, False)
    check(name, {**value, "fenceEpoch": 0}, False)
    history = {**value, "mode": "history", "leaseToken": None, "fenceEpoch": None}
    check(name, history)
    check(name, {**history, "leaseToken": "lease_a", "fenceEpoch": 7}, False)
    assert {"leaseToken", "fenceEpoch"} <= set(OPERATION_BY_NAME[operation].bindings)
    assert "stale_epoch" in {e.code for e in OPERATION_BY_NAME[operation].errorCodes}


def test_claim_replay_and_renewal_never_return_token():
    replay = load("branches/claim-replay.success.json")
    check("NarrationClaimSuccess", replay)
    leaked = copy.deepcopy(replay)
    leaked["data"]["claimToken"] = "claim_root"
    check("NarrationClaimSuccess", leaked, False)
    check("NarrationClaimSuccess", {**replay, "replayed": False}, False)
    check("NarrationClaimRenewSuccess", load("api/narration_claim_renew/success.json"))
    assert OPERATION_BY_NAME["narration_claim"].idempotency.replay == "claim_summary"


def test_preview_provides_a_commit_candidate_without_request_id_or_client_apply():
    preview = load("api/preview_point/success.json")
    check("PreviewPointSuccess", preview)
    assert not {"requestId", "requestHash", "replayed"} & preview.keys()
    commit = load("api/commit_point/request.json")
    commit["point"] = preview["data"]["pointProjection"]
    check("CommitPointRequest", commit)
    assert commit["point"]["entityDeltas"] == preview["data"]["mergedEntityDeltas"]
    check("PreviewPointSuccess", {**preview, "requestId": "request_missing"}, False)


@pytest.mark.parametrize("code", [code for code, spec in ERROR_CODES.items()
    if spec["controlRequired"]])
def test_required_error_control_must_be_nonnull(code):
    value = load(f"errors/{code}.json")
    value["control"] = None
    check("ErrorResponse", value, False)


@pytest.mark.parametrize("field,value", [("httpStatus", 499), ("retryable", True), ("clientAction", "retry")])
def test_error_metadata_cannot_disagree_with_code(field, value):
    error = load("errors/request_malformed.json")["error"]
    error[field] = value
    check("ErrorBody", error, False)


@pytest.mark.parametrize("generation", [0, -1, 9007199254740992])
def test_schema_enforces_positive_safe_claim_generation(generation):
    gate = {"status": "pending", "generation": generation,
            "issuedAtEpochMilli": 1792617600000, "expiresAtEpochMilli": 1792617900000}
    check("GateView", gate, False)


def test_none_gate_rejects_partially_present_claim_fields():
    check("GateView", {"status": "none", "generation": 1}, False)
    group = load("api/checkpoint_close_group/success.json")["work"]["pendingGroup"]
    check("PendingGroupView", {**group, "closed": True, "frontierIds": ["person_c"]}, False)


def test_commit_cannot_name_two_point_ids():
    value = load("api/commit_point/request.json")
    value["pointId"] = "p_different"
    # Cross-field identity equality is intentionally Python-only.
    with pytest.raises(ValidationError):
        MODELS["CommitPointRequest"].model_validate(value)


def test_internally_valid_stale_commit_has_a_refresh_error_fixture():
    request = load("api/commit_point/request.json")
    error = load("errors/version_mismatch.json")
    check("CommitPointRequest", request)
    check("ErrorResponse", error)
    assert request["expectedVersion"] != error["world"]["head"]["version"]
    assert error["error"]["clientAction"] == "refresh_context"
    # This pair documents the service expectation; it does not execute a server.


def test_protected_context_restores_confirmed_work_with_explicit_empty_targets():
    check("GetContextRequest", load("branches/recovery.request.json"))
    check("GetContextRequest", {"includeRecovery": True}, False)
    value = load("branches/recovery.success.json")
    check("ContextResponse", value)
    recovery = value["recovery"]["current"]
    assert recovery["groups"][0]["members"][1]["targets"] == []
    assert recovery["groups"][0]["candidates"] == load("api/checkpoint_stage_unit/request.json")["candidates"]
    assert "leaseToken" not in json.dumps(value) and "claimToken" not in json.dumps(value)
    assert {"order", "cursor", "actedIds", "visitedIds"} <= value["world"]["round"].keys()
    for spec in OPERATIONS:
        success = load(f"api/{spec.operation}/success.json")
        if "data" in success:
            assert "actionText" not in json.dumps(success["data"])
    context_spec = OPERATION_BY_NAME["get_context"]
    assert any(p.kind == "lease" and p.when.field == "includeRecovery" for p in context_spec.preconditions)


def test_every_write_uses_request_id_before_business_deduplication():
    for spec in OPERATIONS:
        if spec.idempotency.scope != "none":
            assert spec.idempotency.key == "requestId"
    for operation in ("allocate_ids", "create_rolls", "checkpoint_restore_group_work"):
        assert OPERATION_BY_NAME[operation].idempotency.businessKey


def test_creation_template_and_read_query_boundaries():
    request = load("api/create_world/request.json")
    check("CreateWorldRequest", request)
    request["initial"]["worldId"] = "client_world"
    check("CreateWorldRequest", request, False)
    check("ListPointsRequest", {})
    for value in ({"after": -1}, {"limit": 0}, {"limit": 101}):
        check("ListPointsRequest", value, False)
    check("GetStateRequest", {"point": "p1"})
    check("GetStateRequest", {"point": 1}, False)


def test_roll_outcome_exposes_final_admission_and_eligibility_binding():
    value = load("api/create_rolls/success.json")["data"]["rolls"][0]
    check("RollOutcome", value)
    assert value["eligibilityBaselineDigest"]
    with pytest.raises(ValidationError):
        MODELS["RollOutcome"].model_validate({**value, "admitted": not value["admitted"]})


@pytest.mark.parametrize("fixture", ["recovery-successor", "recovery-unconfirmed"])
def test_recovery_represents_reserved_and_unconfirmed_work(fixture):
    value = load(f"branches/{fixture}.success.json")
    check("ContextResponse", value)
    if fixture == "recovery-unconfirmed":
        assert value["recovery"]["current"]["groups"][0]["members"][0]["targets"] is None
        check("DiscoverGroupRequest", {
            **load("api/checkpoint_discover_group/request.json"), "targetIds": None})
    else:
        successor = value["recovery"]["successor"]["work"]
        assert successor["pointId"] == "p2" and successor["predecessorWorkDigest"]
    value["recovery"]["fenceEpoch"] = 6
    with pytest.raises(ValidationError):
        MODELS["ContextResponse"].model_validate(value)


@pytest.mark.parametrize("status,text", [("ready", None), ("failed", "stale"), ("pending", "stale")])
def test_narration_reads_pair_status_with_text_in_both_validators(status, text):
    check("NarrationGetData", {"pointId": "p1", "narrationStatus": status,
                              "generation": 1, "text": text}, False)


def test_sealed_work_requires_its_prefix_digest():
    work = load("api/checkpoint_seal_point/success.json")["work"]
    check("PointWorkView", {**work, "prefixDigest": None}, False)


def test_time_scan_completion_requires_saved_pure_time_candidates():
    value = load("branches/recovery.success.json")["recovery"]["current"]
    value["work"]["timeScanComplete"] = True
    check("PointRecoveryView", value, False)


@pytest.mark.parametrize("missing", [
    ["generation"], ["issuedAtEpochMilli"], ["expiresAtEpochMilli"],
    ["generation", "issuedAtEpochMilli", "expiresAtEpochMilli"],
    ["issuedAtEpochMilli", "expiresAtEpochMilli"],
])
def test_pending_gate_requires_every_claim_field_to_be_present(missing):
    gate = {"status": "pending", "generation": 1,
            "issuedAtEpochMilli": 1792617600000, "expiresAtEpochMilli": 1792617900000}
    check("GateView", gate)
    for field in missing:
        gate.pop(field)
    check("GateView", gate, False)


def test_cleared_gate_may_omit_all_claim_fields():
    check("GateView", {"status": "none"})


def test_takeover_wire_sequence_can_obtain_restore_inputs_before_copying_payload():
    trace = load("branches/takeover.json")
    for step in trace["steps"]:
        check(step["requestSchema"], step["request"])
        check(step["successSchema"], step["success"])
    grant, read_before, restore_current, restore_successor, read_after = trace["steps"]
    before, after = read_before["success"], read_after["success"]
    assert grant["success"]["data"]["fenceEpoch"] == before["recovery"]["fenceEpoch"] == 8
    assert read_before["request"]["leaseToken"] == grant["success"]["data"]["leaseToken"]
    for key, step in (("current", restore_current), ("successor", restore_successor)):
        hidden = before["recovery"][key]
        assert hidden["payloadStatus"] == "restore_required"
        assert hidden["groups"] == [] and hidden["timeScanCandidates"] is None
        # No need to see any old raw bytes to construct the exact accepted request.
        source = hidden["restoreSources"][0]
        request = step["request"]
        for field, value in source.items():
            assert request[field] == value
        assert request["sourceEpoch"] == 7 and request["fenceEpoch"] == 8
        assert request["leaseToken"] == read_before["request"]["leaseToken"]
        assert request["expectedCheckpointRevision"] == before["control"]["revision"]
        visible = after["recovery"][key]
        assert visible["payloadStatus"] == "available" and visible["groups"]
        assert hidden["work"] == visible["work"]
        assert hidden["restoreSources"] == visible["restoreSources"]
        assert step["success"]["control"] == before["control"] == after["control"]
    assert before["recovery"]["current"]["work"]["sealed"] is True
    assert after["recovery"]["successor"]["work"]["predecessorWorkDigest"] == before["work"]["prefixDigest"]


@pytest.mark.parametrize("field", ["groups", "timeScanCandidates"])
def test_uncopied_payload_cannot_be_included_with_restore_sources(field):
    trace = load("branches/takeover.json")
    hidden = copy.deepcopy(trace["steps"][1]["success"]["recovery"]["current"])
    if field == "groups":
        hidden[field] = trace["steps"][-1]["success"]["recovery"]["current"]["groups"]
    else:
        hidden["work"]["timeScanComplete"] = True
        hidden[field] = load("api/checkpoint_stage_time_scan/request.json")["candidates"]
    check("PointRecoveryView", hidden, False)


def test_restore_required_metadata_cannot_omit_the_restore_sources():
    point = load("branches/takeover.json")["steps"][1]["success"]["recovery"]["current"]
    check("PointRecoveryView", {**point, "restoreSources": []}, False)
    # Copy-wait is different from an unconfirmed scan: keep the saved completion
    # marker while hiding its bytes, instead of pretending the work needs rerunning.
    point["work"]["timeScanComplete"] = True
    check("PointRecoveryView", point)


def test_restore_metadata_is_a_separate_type_that_cannot_carry_old_payload():
    source = load("branches/takeover.json")["steps"][1]["success"]["recovery"]["current"]["restoreSources"][0]
    check("GroupWorkSource", source)
    check("GroupWorkSource", {**source, "actionText": "old raw text"}, False)
    point = load("branches/takeover.json")["steps"][1]["success"]["recovery"]["current"]
    point["restoreSources"][0]["pointId"] = "p_wrong"
    with pytest.raises(ValidationError):
        MODELS["PointRecoveryView"].model_validate(point)


def test_restore_sources_must_still_be_referenced_by_work():
    point = load("branches/takeover.json")["steps"][1]["success"]["recovery"]["current"]
    point["work"]["settledUnits"] = []
    point["work"]["working"]["settledUnitIds"] = []
    with pytest.raises(ValidationError, match="no active work reference"):
        MODELS["PointRecoveryView"].model_validate(point)


def test_restore_permissions_allow_active_sealed_prefix_and_reserved_work():
    spec = OPERATION_BY_NAME["checkpoint_restore_group_work"]
    preconditions = {p.kind: p.value for p in spec.preconditions}
    assert preconditions == {"lease": "valid", "pointWork": ["open", "sealed"],
                             "frozenSource": "active_reference"}
    assert spec.mutatesRevision is False
    assert spec.sideEffects == ["copies_frozen_work"]
    assert not {"gate", "paused", "phase"} & preconditions.keys()


def test_takeover_expected_predecessor_payload_preserves_accepted_originals():
    before = load("branches/recovery-successor.success.json")["recovery"]["current"]["groups"]
    after = load("branches/takeover.json")["steps"][-1]["success"]["recovery"]["current"]["groups"]
    assert after == before
    for group in after:
        for member, source in zip(group["members"], group["acceptedSources"]):
            for text_key, hash_key in (("actionText", "actionContentHash"), ("resultText", "resultContentHash")):
                raw = member[text_key].encode("utf-8")
                assert hashlib.sha256(raw).hexdigest() == source[hash_key]


@pytest.mark.parametrize("failure", load("branches/takeover.json")["failures"], ids=lambda f: f["name"])
def test_takeover_failure_examples_preserve_work_and_explicitly_block_restore(failure):
    # These are declared server expectations, not executed service transactions.
    check(failure["requestSchema"], failure["request"])
    check(failure["errorSchema"], failure["error"])
    before = load("branches/takeover.json")["steps"][1]["success"]
    assert failure["error"]["work"] == before["work"]
    assert failure["error"]["control"] == before["control"]
    assert "actionText" not in json.dumps(failure["error"])
    scope = failure["scope"]
    source = before["recovery"][scope]["restoreSources"][0]
    assert failure["request"]["pointId"] == source["pointId"]
    if failure["case"] in ("consumed", "abandoned"):
        assert failure["error"]["error"]["code"] == "frozen_work_missing"
        assert failure["error"]["error"]["details"]["reason"] == "source_not_active"


@pytest.mark.parametrize("role,index", [("current", 2), ("successor", 3)])
def test_restore_is_constructible_without_predicting_the_destination_attempt(role, index):
    trace = load("branches/takeover.json")
    grant, context = trace["steps"][0]["success"], trace["steps"][1]["success"]
    source = context["recovery"][role]["restoreSources"][0]
    request = {**source, "protocolVersion": 2, "operation": "restore_group_work",
               "requestId": "client_restore_" + role, "worldId": context["world"]["worldId"],
               "leaseToken": grant["data"]["leaseToken"], "fenceEpoch": grant["data"]["fenceEpoch"],
               "expectedPointId": context["world"]["head"]["pointId"],
               "expectedVersion": context["world"]["head"]["version"],
               "expectedCheckpointRevision": context["control"]["revision"]}
    assert "attempt" not in request
    check("RestoreGroupWorkRequest", request)
    result = trace["steps"][index]["success"]
    check("RestoreGroupWorkSuccess", result)
    data = result["data"]
    assert (data["pointId"], data["groupId"], data["fenceEpoch"]) == (
        request["pointId"], request["groupId"], request["fenceEpoch"])
    assert data["attempt"] > data["sourceAttempt"]


@pytest.mark.parametrize("attempt", [0, 1, 3])
def test_restore_rejects_caller_allocated_attempts(attempt):
    request = load("api/checkpoint_restore_group_work/request.json")
    check("RestoreGroupWorkRequest", {**request, "attempt": attempt}, False)


@pytest.mark.parametrize("missing", ["pointId", "fenceEpoch", "attempt"])
def test_restore_success_must_return_the_complete_copy_identity(missing):
    success = load("api/checkpoint_restore_group_work/success.json")
    success["data"].pop(missing)
    check("RestoreGroupWorkSuccess", success, False)


@pytest.mark.parametrize("attempt", [0, True, 9007199254740992])
def test_restore_returned_attempt_is_a_positive_safe_integer(attempt):
    success = load("api/checkpoint_restore_group_work/success.json")
    success["data"]["attempt"] = attempt
    check("RestoreGroupWorkSuccess", success, False)


def test_restore_business_deduplication_uses_readable_source_and_destination_epoch():
    spec = OPERATION_BY_NAME["checkpoint_restore_group_work"]
    assert spec.idempotency.key == "requestId"
    assert spec.idempotency.businessKey == [
        "pointId", "groupId", "fenceEpoch", "sourceEpoch", "sourceAttempt", "manifest"]
    assert spec.idempotency.businessReplay == "accepted_copy"
