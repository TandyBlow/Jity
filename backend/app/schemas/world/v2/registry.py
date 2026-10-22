"""v2 API operation registry: the machine-readable permission matrix.

This module is the single authority behind the exported api-contract.json.
Prose (workflow §9.2) explains; this table is what tests and the TS consumer
check against. Every operation carries method/path, schema references, success
HTTP status, machine-readable preconditions, applicable error codes (with the
controlRequired flag from the error table), bindings, revision impact, success
side effects and idempotency behaviour.

Precondition kinds and their values are a closed vocabulary; JSON Schema cannot
express history or lease conditions, so anything schema-inexpressible is a
registered service-validation item (A2/A3), never claimed as schema-checked.
"""

from typing import Annotated, Literal, Union

from pydantic import Field, model_validator

from app.schemas.world.contracts import Contract

from .errors import ErrorCode, ERROR_CODES

OperationName = Literal[
    "create_world",
    "get_context",
    "checkpoint_start_advance",
    "checkpoint_begin_point",
    "checkpoint_set_point_time",
    "checkpoint_discover_group",
    "checkpoint_extend_group",
    "checkpoint_close_group",
    "checkpoint_stage_unit",
    "checkpoint_record_skip",
    "checkpoint_stage_time_scan",
    "checkpoint_seal_point",
    "checkpoint_prepare_successor",
    "checkpoint_restore_group_work",
    "checkpoint_pause",
    "checkpoint_resume",
    "round_conclusion_conclude",
    "round_conclusion_cancel",
    "lease_acquire",
    "lease_renew",
    "lease_release",
    "allocate_ids",
    "preview_point",
    "create_rolls",
    "commit_point",
    "list_points",
    "get_state",
    "narration_claim",
    "narration_claim_renew",
    "narration_submit",
    "narration_get",
    "narration_delete",
]

# Request fields the server re-checks against authoritative state before the
# business write. "inputProjection" denotes the point's saved advance/input and
# time binding selected via pointId.
BINDING_FIELDS = (
    "protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
    "expectedVersion", "expectedCheckpointRevision", "expectedPointId",
    "advanceId", "roundId", "pointId", "groupId", "claimToken", "generation",
    "issuedAtEpochMilli", "inputProjection", "allocationKey", "judgmentKey", "inputId",
)

CONTROL_PHASES = ("select_actor", "build_group", "settle_group", "continue_round", "assess_continuation", "complete")
CLAIM_MODES = ("head", "history")
POINT_WORK_STATES = ("absent", "open", "sealed")
PENDING_GROUP_STATES = ("absent", "present")

PRECONDITION_KINDS = (
    "phase", "paused", "gate", "headNarration", "lease", "timeLocked",
    "activePendingGroup", "pointWork", "confirmedWork", "settledUnits",
    "claimMode", "point", "activeAdvance", "frozenSource",
)

class PreconditionWhen(Contract):
    """Conditional precondition: applies only when the request field matches."""

    field: str
    value: str | bool


class Precondition(Contract):
    kind: Annotated[str, Field(pattern=r"^[a-zA-Z]+$")]
    value: Union[str, bool, list[str]]
    when: PreconditionWhen | None = None

    @model_validator(mode="after")
    def closed_vocabulary(self):
        if self.kind not in PRECONDITION_KINDS:
            raise ValueError(f"unknown precondition kind: {self.kind}")
        values = self.value if isinstance(self.value, list) else [self.value]
        checks = {
            "phase": lambda v: v in CONTROL_PHASES,
            "paused": lambda v: v is False,
            "gate": lambda v: v == "cleared",
            "headNarration": lambda v: v == "ready",
            "lease": lambda v: v == "valid",
            "timeLocked": lambda v: isinstance(v, bool),
            "activePendingGroup": lambda v: v in PENDING_GROUP_STATES,
            "pointWork": lambda v: v in POINT_WORK_STATES,
            "confirmedWork": lambda v: v == "absent",
            "settledUnits": lambda v: v == "empty",
            "claimMode": lambda v: v in CLAIM_MODES,
            "point": lambda v: v == "committed",
            "activeAdvance": lambda v: v == "absent",
            "frozenSource": lambda v: v == "active_reference",
        }
        if not all(checks[self.kind](value) for value in values):
            raise ValueError(f"invalid value for precondition {self.kind}: {self.value}")
        if self.kind == "paused" and self.value is not False:
            raise ValueError("paused precondition only expresses paused=false")
        return self


class ErrorCodeSpec(Contract):
    code: ErrorCode
    controlRequired: bool

    @model_validator(mode="after")
    def matches_error_table(self):
        table = ERROR_CODES[self.code]
        if self.controlRequired != table["controlRequired"]:
            raise ValueError(f"controlRequired for {self.code} must come from the error table")
        return self


class IdempotencySpec(Contract):
    scope: Literal["global", "world", "none"]
    key: Literal["requestId"] | None
    businessKey: list[str] = Field(default_factory=list)
    businessReplay: Literal["same_ids", "original_roll", "accepted_copy"] | None = None
    replay: Literal["original_data", "current_state", "same_ids", "original_roll", "recomputable", "claim_summary"]

    @model_validator(mode="after")
    def key_follows_scope(self):
        if self.scope == "none":
            if self.key is not None or self.replay != "recomputable":
                raise ValueError("scope none means no idempotency key and recomputable replay")
        elif self.key is None:
            raise ValueError("world or global scope needs a key")
        return self


class OperationSpec(Contract):
    operation: OperationName
    method: Literal["POST", "GET", "PUT", "DELETE"]
    path: str
    # $defs names inside the exported v2 schema. None means the request carries
    # no parameters beyond the path; for GET/DELETE operations with parameters,
    # requestSchema names the query-string model and queryBindings lists them.
    requestSchema: str | None
    successSchema: str
    successHttpStatus: Annotated[int, Field(ge=200, le=299)]
    bindings: list[str]
    preconditions: list[Precondition]
    errorCodes: list[ErrorCodeSpec]
    mutatesRevision: bool
    sideEffects: list[str]
    conditionalSideEffects: dict[str, list[str]] = Field(default_factory=dict)
    idempotency: IdempotencySpec
    # Bodyless requests carry protocolVersion via the X-World-Protocol-Version
    # header and their parameters via the query string; this lists the query
    # parameters in order.
    queryBindings: list[str]
    notes: str | None = None

    @model_validator(mode="after")
    def vocabulary(self):
        if not self.path.startswith("/worlds") and self.path != "/worlds":
            raise ValueError("every v2 operation lives under /worlds")
        unknown_bindings = [b for b in self.bindings if b not in BINDING_FIELDS]
        if unknown_bindings:
            raise ValueError(f"unknown binding fields: {unknown_bindings}")
        unknown_effects = [s for s in self.sideEffects if s not in SIDE_EFFECTS]
        if unknown_effects:
            raise ValueError(f"unknown side effects: {unknown_effects}")
        return self


SIDE_EFFECTS = (
    "creates_world", "creates_root_point", "issues_initial_lease", "issues_lease",
    "extends_lease_expiry", "releases_lease",
    "issues_head_claim", "issues_gate", "begins_point_work", "sets_time_advance",
    "locks_time", "creates_pending_group", "extends_group", "closes_group",
    "appends_settled_unit", "advances_working_progress", "clears_active_group",
    "advances_working_cursor", "stages_time_scan", "seals_point_prefix",
    "creates_successor_reservation", "copies_frozen_work", "sets_paused",
    "clears_paused", "bumps_revision_on_change", "concludes_round",
    "completes_round", "creates_successor_round", "abandons_uncommitted_work",
    "expires_input_intent", "clears_input_text", "advances_head", "creates_point",
    "promotes_working_progress", "consumes_point_groups",
    "clears_consumed_group_work", "issues_narration_claim",
    "rotates_narration_generation", "extends_claim_expiry",
    "writes_narration_cache", "marks_point_ready", "clears_gate",
    "starts_advance", "creates_player_round", "saves_input_text",
    "invalidates_narration_cache", "allocates_ids", "creates_roll_rows",
)


def _pre(kind, value, when=None):
    return {"kind": kind, "value": value, "when": when}


def _when(field, value):
    return {"field": field, "value": value}


def _errors(*codes):
    return [{"code": code, "controlRequired": ERROR_CODES[code]["controlRequired"]} for code in codes]


# Codes shared by every lease- and revision-bound write operation.
_WIRE_ERRORS = _errors("protocol_version_unsupported", "request_malformed",
                       "request_id_reused", "request_in_progress")
_LEASE_ERRORS = _errors("lease_invalid", "stale_epoch")
_GATE_ERRORS = _errors("narration_blocked", "paused")
_COMPUTE_ERRORS = _WIRE_ERRORS + _LEASE_ERRORS + _GATE_ERRORS + _errors(
    "revision_mismatch", "version_mismatch", "phase_invalid")

_HEAD_LEASE = _pre("lease", "valid", _when("mode", "head"))

OPERATIONS: tuple[OperationSpec, ...] = tuple(OperationSpec.model_validate(spec) for spec in [
    {
        "operation": "create_world", "method": "POST", "path": "/worlds",
        "requestSchema": "CreateWorldRequest", "successSchema": "CreateWorldSuccess",
        "successHttpStatus": 201, "bindings": ["protocolVersion", "requestId"],
        "preconditions": [], "errorCodes": _WIRE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["creates_world", "creates_root_point", "issues_initial_lease",
                        "issues_head_claim", "issues_gate"],
        "idempotency": {"scope": "global", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Same transaction creates the world, the initial advance lease and the root "
                 "point generation=1 head claim and gate; no generation=0 claim path exists. "
                 "worldId is server-assigned; the same requestId returns the same world.",
    },
    {
        "operation": "get_context", "method": "GET", "path": "/worlds/{worldId}/context",
        "requestSchema": "GetContextRequest", "successSchema": "ContextResponse",
        "successHttpStatus": 200, "bindings": ["worldId", "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("lease", "valid", _when("includeRecovery", True))],
        "errorCodes": _errors("protocol_version_unsupported", "request_malformed", "version_mismatch", "lease_invalid", "stale_epoch"),
        "mutatesRevision": False, "sideEffects": [],
        "idempotency": {"scope": "none", "key": None, "replay": "recomputable"},
        "queryBindings": ["includeRecovery", "leaseToken", "fenceEpoch"],
        "notes": "includeRecovery=true validates the live lease/epoch, then returns active accepted "
                 "restoreSources independently of payload visibility for current and reserved successor work. "
                 "Sources include the old epoch/attempt and hashes needed to build restore requests, "
                 "but no raw text or candidates. If copying is needed, payloadStatus=restore_required "
                 "with groups=[] and timeScanCandidates=null; after copying, payloadStatus=available "
                 "returns only current-epoch bytes. Missing/corrupt payload rows do not erase "
                 "accepted references or authorize resampling. Consumed/abandoned sources are excluded; ordinary reads "
                 "return recovery=null. Invalid/old lease cannot read frozen text. No requestId; the only response carrying activeInput. Context never returns "
                 "lease or claim tokens.",
    },
    {
        "operation": "checkpoint_start_advance", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "StartAdvanceRequest", "successSchema": "StartAdvanceSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "advanceId", "roundId"],
        "preconditions": [_pre("activeAdvance", "absent"), _pre("pointWork", "absent"),
                          _pre("lease", "valid"), _pre("paused", False),
                          _pre("headNarration", "ready"), _pre("gate", "cleared")],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["starts_advance", "creates_player_round", "saves_input_text"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Starts the player chain only after the ready root/last handback. IDs must be "
                 "allocated, unused and world-bound. Validate the frozen character order against "
                 "the authoritative world. Persist text only in active input storage; data and "
                 "idempotency records contain identities only. Initialize select_actor/cursor=0.",
    },
    {
        "operation": "checkpoint_begin_point", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "BeginPointRequest", "successSchema": "BeginPointSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "advanceId", "inputProjection"],
        "preconditions": [
            _pre("phase", ["select_actor", "continue_round"]), _pre("pointWork", "absent"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["begins_point_work"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Saves the preallocated pointId, kind, baseline head/version/digest and "
                 "timeAdvance; working progress initializes from committed progress.",
    },
    {
        "operation": "checkpoint_set_point_time", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "SetPointTimeRequest", "successSchema": "SetPointTimeSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId"],
        "preconditions": [
            _pre("phase", ["select_actor", "build_group", "settle_group"]),
            _pre("timeLocked", False), _pre("confirmedWork", "absent"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS + _errors("point_time_locked"), "mutatesRevision": True,
        "sideEffects": ["sets_time_advance"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "First confirmed action/target/skip/time-scan locks time in the same "
                 "transaction; afterwards an explicit cancel chain is the only way to change it.",
    },
    {
        "operation": "checkpoint_discover_group", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "DiscoverGroupRequest", "successSchema": "DiscoverGroupSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "groupId", "inputProjection"],
        "preconditions": [
            _pre("phase", "select_actor"), _pre("activePendingGroup", "absent"),
            _pre("pointWork", "open"), _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["creates_pending_group", "locks_time"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "select_actor→build_group. Stores model goals only; admission is recomputed "
                 "from rolls and the eligibility baseline. Committed cursor/order/acted/visited "
                 "and working progress stay untouched.",
    },
    {
        "operation": "checkpoint_extend_group", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "ExtendGroupRequest", "successSchema": "ExtendGroupSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "groupId"],
        "preconditions": [
            _pre("phase", "build_group"), _pre("activePendingGroup", "present"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["extends_group"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Exactly one of complete target set for a source or one admitted member with "
                 "its action and judgment references. Confirmed targets and actions are final; "
                 "members only grow; group results are not consumed here.",
    },
    {
        "operation": "checkpoint_close_group", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "CloseGroupRequest", "successSchema": "CloseGroupSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "groupId"],
        "preconditions": [
            _pre("phase", "build_group"), _pre("activePendingGroup", "present"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["closes_group"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "build_group→settle_group; server requires every target analysed and an empty "
                 "frontier. Closed groups are read-only for membership, targets and actions.",
    },
    {
        "operation": "checkpoint_stage_unit", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "StageUnitRequest", "successSchema": "StageUnitSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "groupId", "inputProjection"],
        "preconditions": [
            _pre("phase", "settle_group"), _pre("activePendingGroup", "present"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["appends_settled_unit", "advances_working_progress", "clears_active_group"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "settle_group→select_actor. Appends one complete six-stage candidate set in "
                 "order, advances working fields, clears the active pendingGroup slot without "
                 "deleting its text or results. Same requestId replays; a changed candidate for "
                 "a staged group is rejected. Never writes world deltas or committed progress.",
    },
    {
        "operation": "checkpoint_record_skip", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "RecordSkipRequest", "successSchema": "RecordSkipSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "inputProjection"],
        "preconditions": [
            _pre("phase", "select_actor"), _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["advances_working_cursor", "locks_time"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Records the skip of the current legal slot; never adds to actedIds. Characters "
                 "already in actedIds are skipped programmatically.",
    },
    {
        "operation": "checkpoint_stage_time_scan", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "StageTimeScanRequest", "successSchema": "StageTimeScanSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "inputProjection"],
        "preconditions": [
            _pre("phase", "select_actor"), _pre("activePendingGroup", "absent"),
            _pre("settledUnits", "empty"), _pre("pointWork", "open"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["stages_time_scan", "locks_time"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Saves the complete no-action time-scan stage candidates at a legal point "
                 "boundary; workingActedIds is not extended and task/personality/sanity checks "
                 "cannot be skipped.",
    },
    {
        "operation": "checkpoint_seal_point", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "SealPointRequest", "successSchema": "SealPointSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId"],
        "preconditions": [
            _pre("phase", "select_actor"), _pre("activePendingGroup", "absent"),
            _pre("pointWork", "open"), _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["seals_point_prefix"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "An empty point must have its time-scan candidates saved first. After sealing, "
                 "no candidate can be added or changed; only points consumes the prefix.",
    },
    {
        "operation": "checkpoint_prepare_successor", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "PrepareSuccessorRequest", "successSchema": "PrepareSuccessorSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId"],
        "preconditions": [
            _pre("phase", "select_actor"), _pre("activePendingGroup", "absent"),
            _pre("pointWork", "open"), _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["seals_point_prefix", "creates_successor_reservation", "locks_time"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Seals the current prefix and creates the single direct successor reservation "
                 "with fixed successor time and baseline binding; committed cursors do not move. "
                 "Until the predecessor commits, only this successor's boundary-source "
                 "discover/extend and its rolls are allowed.",
    },
    {
        "operation": "checkpoint_restore_group_work", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "RestoreGroupWorkRequest", "successSchema": "RestoreGroupWorkSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "pointId", "groupId"],
        "preconditions": [_pre("lease", "valid"), _pre("pointWork", ["open", "sealed"]),
                          _pre("frozenSource", "active_reference")],
        "errorCodes": _WIRE_ERRORS + _LEASE_ERRORS + _errors(
            "revision_mismatch", "version_mismatch", "frozen_work_missing", "frozen_work_corrupt"),
        "mutatesRevision": False,
        "sideEffects": ["copies_frozen_work"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data",
                        "businessKey": ["pointId", "groupId", "fenceEpoch", "sourceEpoch", "sourceAttempt", "manifest"],
                        "businessReplay": "accepted_copy"},
        "queryBindings": [],
        "notes": "Takeover continuation: the server byte-copies server-accepted frozen work "
                 "(action text, targets, results, stage candidates) into the current epoch after "
                 "verifying accepted-source records, scope and every hash against active references. "
                 "The input source metadata is available from context.recovery.*.restoreSources before "
                 "copying. The request has no destination attempt. After validating authority and "
                 "sources, the transaction allocates a positive, monotonically increasing attempt "
                 "within (worldId, pointId, groupId), across epochs, and returns pointId/groupId/"
                 "fenceEpoch/attempt as the accepted copy identity. RequestId replay returns the "
                 "original data; a new requestId with the same business key reuses the accepted copy "
                 "and attempt without allocating again. The business manifest projection sorts by "
                 "memberId and includes all source content hashes. Both open and sealed "
                 "current/reserved work can be copied; consumed or "
                 "abandoned sources fail frozen_work_missing with details.reason=source_not_active. "
                 "Missing/corrupt bytes fail explicitly and never authorize model resampling. "
                 "Passes through gate and pause; group, time, cursor, sealed flag, prefix digest, "
                 "candidates, phase and revision stay unchanged.",
    },
    {
        "operation": "checkpoint_pause", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "PauseRequest", "successSchema": "PauseSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedCheckpointRevision"],
        "preconditions": [_pre("lease", "valid")],
        "errorCodes": _WIRE_ERRORS + _LEASE_ERRORS + _errors("revision_mismatch", "version_mismatch"),
        "mutatesRevision": True,
        "sideEffects": ["sets_paused", "bumps_revision_on_change"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Allowed through the narration gate; idempotent when already paused. Phase, "
                 "work and gate are preserved; claim TTL is not extended.",
    },
    {
        "operation": "checkpoint_resume", "method": "PUT", "path": "/worlds/{worldId}/checkpoint",
        "requestSchema": "ResumeRequest", "successSchema": "ResumeSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedCheckpointRevision"],
        "preconditions": [_pre("lease", "valid")],
        "errorCodes": _WIRE_ERRORS + _LEASE_ERRORS + _errors("revision_mismatch", "version_mismatch"),
        "mutatesRevision": True,
        "sideEffects": ["clears_paused", "clears_gate", "bumps_revision_on_change"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "resolve_gate runs in-transaction: expired or fenced gates are cleared and "
                 "reported via blockedReasons while the resume itself succeeds with "
                 "canCompute=false. Resume is never an authorization to compute.",
    },
    {
        "operation": "round_conclusion_conclude", "method": "POST",
        "path": "/worlds/{worldId}/round-conclusion",
        "requestSchema": "ConcludeRoundRequest", "successSchema": "ConcludeRoundSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "advanceId", "roundId",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision",
                     "leaseToken", "fenceEpoch"],
        "preconditions": [
            _pre("phase", "assess_continuation"), _pre("headNarration", "ready"),
            _pre("gate", "cleared"), _pre("lease", "valid"), _pre("paused", False),
            _pre("activePendingGroup", "absent"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["concludes_round", "completes_round"],
        "conditionalSideEffects": {"conclusion.kind=continue": ["creates_successor_round"],
                                   "conclusion.kind=handback": ["expires_input_intent", "clears_input_text"]},
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "continue requires a non-empty legal candidate set and an unallocated "
                 "nextRoundId; the successor automatic round inherits the advance. handback ends "
                 "the input chain and clears its text. Neither moves the world head.",
    },
    {
        "operation": "round_conclusion_cancel", "method": "POST",
        "path": "/worlds/{worldId}/round-conclusion",
        "requestSchema": "CancelRoundRequest", "successSchema": "CancelRoundSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "advanceId", "roundId",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision",
                     "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("headNarration", "ready"), _pre("lease", "valid")],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["completes_round", "abandons_uncommitted_work", "expires_input_intent",
                        "clears_input_text"],
        "queryBindings": [],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "notes": "Explicit cancel from the last full commit point; still requires a ready head "
                 "but is allowed while paused. Abandons current and reserved work with terminal "
                 "identity records; frozen copies survive until their last active reference goes.",
    },
    {
        "operation": "lease_acquire", "method": "POST", "path": "/worlds/{worldId}/lease",
        "requestSchema": "AcquireLeaseRequest", "successSchema": "AcquireLeaseSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId"],
        "preconditions": [],
        "errorCodes": _WIRE_ERRORS + _errors("lease_invalid", "version_mismatch"),
        "mutatesRevision": False,
        "sideEffects": ["issues_lease"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Grants a free lease or takes over an expired one with a new fenceEpoch; "
                 "lease_invalid with details.reason=lease_held reports another holder's still "
                 "valid lease. The token travels only in data.",
    },
    {
        "operation": "lease_renew", "method": "PUT", "path": "/worlds/{worldId}/lease",
        "requestSchema": "RenewLeaseRequest", "successSchema": "RenewLeaseSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("lease", "valid")],
        "errorCodes": _WIRE_ERRORS + _LEASE_ERRORS,
        "mutatesRevision": False,
        "sideEffects": ["extends_lease_expiry"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Extends expiry for the matching token and epoch; token and fenceEpoch persist.",
    },
    {
        "operation": "lease_release", "method": "DELETE", "path": "/worlds/{worldId}/lease",
        "requestSchema": "ReleaseLeaseRequest", "successSchema": "ReleaseLeaseSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("lease", "valid")],
        "errorCodes": _WIRE_ERRORS + _LEASE_ERRORS,
        "mutatesRevision": False,
        "sideEffects": ["releases_lease"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": ["requestId", "leaseToken", "fenceEpoch"],
        "notes": "Releases the matching lease; parameters travel in the query string.",
    },
    {
        "operation": "allocate_ids", "method": "POST", "path": "/worlds/{worldId}/ids",
        "requestSchema": "AllocateIdsRequest", "successSchema": "AllocateIdsSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "allocationKey"],
        "preconditions": [_pre("lease", "valid")],
        "errorCodes": _WIRE_ERRORS + _LEASE_ERRORS + _errors("version_mismatch"),
        "mutatesRevision": False,
        "sideEffects": ["allocates_ids"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data",
                        "businessKey": ["allocationKey", "slots.slotKey"], "businessReplay": "same_ids"},
        "queryBindings": [],
        "notes": "Preallocates advance/input/round/group/task/change/point/trigger identities "
                 "per stable slot keys; the same slot key always returns the same ID. Committed "
                 "IDs are never reallocated. rollId is deliberately absent: rolls allocates it.",
    },
    {
        "operation": "preview_point", "method": "POST", "path": "/worlds/{worldId}/preview",
        "requestSchema": "PreviewPointRequest", "successSchema": "PreviewPointSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "advanceId", "roundId", "pointId",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision"],
        "preconditions": [
            _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
            _pre("pointWork", ["open", "sealed"]),
        ],
        "errorCodes": _errors("protocol_version_unsupported", "request_malformed") + _GATE_ERRORS + _errors(
            "revision_mismatch", "version_mismatch", "phase_invalid", "preview_budget_exceeded"),
        "mutatesRevision": False,
        "sideEffects": [],
        "idempotency": {"scope": "none", "key": None, "replay": "recomputable"},
        "queryBindings": [],
        "notes": "Recomputes candidates from the authoritative baseline (max 32 units, request "
                 "JSON up to 512 KiB, response up to 2 MiB); over budget returns "
                 "preview_budget_exceeded with details.limit=request|response. preview carries no "
                 "requestId and never enters the idempotency table.",
    },
    {
        "operation": "create_rolls", "method": "POST", "path": "/worlds/{worldId}/rolls",
        "requestSchema": "CreateRollsRequest", "successSchema": "CreateRollsSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "leaseToken", "fenceEpoch",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision", "judgmentKey"],
        "preconditions": [
            _pre("phase", "build_group"), _pre("activePendingGroup", "present"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": False,
        "sideEffects": ["creates_roll_rows"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data",
                        "businessKey": ["rolls.roundId", "rolls.groupId", "rolls.sourceId", "rolls.targetId", "rolls.triggerKey"],
                        "businessReplay": "original_roll"},
        "queryBindings": [],
        "notes": "Server-side dice keyed by (worldId, roundId, groupId, sourceId, targetId, "
                 "triggerKey); the same key returns the original row. One INSERT with the final "
                 "eligibility/admission result; no NULL-admission intermediate rows.",
    },
    {
        "operation": "commit_point", "method": "POST", "path": "/worlds/{worldId}/points",
        "requestSchema": "CommitPointRequest", "successSchema": "CommitPointSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "advanceId", "roundId",
                     "expectedPointId", "expectedVersion", "expectedCheckpointRevision",
                     "leaseToken", "fenceEpoch", "pointId", "inputProjection"],
        "preconditions": [
            _pre("pointWork", "sealed"), _pre("activePendingGroup", "absent"),
            _pre("lease", "valid"), _pre("paused", False),
            _pre("headNarration", "ready"), _pre("gate", "cleared"),
        ],
        "errorCodes": _COMPUTE_ERRORS, "mutatesRevision": True,
        "sideEffects": ["advances_head", "creates_point", "promotes_working_progress",
                        "consumes_point_groups", "clears_consumed_group_work",
                        "issues_head_claim", "issues_gate"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Same transaction applies locked time and staged candidates, verifies "
                 "settlementGroups against settledUnits (identity, members, order), promotes "
                 "working progress, saves the next control position with a generation=1 head "
                 "claim and gate, and cleans only this point's consumed groups. Pure-time points "
                 "commit with an empty settlementGroups list using the saved time-scan candidates.",
    },
    {
        "operation": "list_points", "method": "GET", "path": "/worlds/{worldId}/points",
        "requestSchema": "ListPointsRequest", "successSchema": "ListPointsSuccess",
        "successHttpStatus": 200, "bindings": ["worldId"], "preconditions": [],
        "errorCodes": _errors("protocol_version_unsupported", "version_mismatch"),
        "mutatesRevision": False, "sideEffects": [],
        "idempotency": {"scope": "none", "key": None, "replay": "recomputable"},
        "queryBindings": ["after", "limit"],
        "notes": "Committed points in timeline order.",
    },
    {
        "operation": "get_state", "method": "GET", "path": "/worlds/{worldId}/state",
        "requestSchema": "GetStateRequest", "successSchema": "GetStateSuccess",
        "successHttpStatus": 200, "bindings": ["worldId"], "preconditions": [],
        "errorCodes": _errors("protocol_version_unsupported", "version_mismatch"),
        "mutatesRevision": False, "sideEffects": [],
        "idempotency": {"scope": "none", "key": None, "replay": "recomputable"},
        "queryBindings": ["point"],
        "notes": "Rebuilds the state at a committed point from the canonical projection.",
    },
    {
        "operation": "narration_claim", "method": "POST",
        "path": "/worlds/{worldId}/points/{pointId}/narration-jobs",
        "requestSchema": "NarrationClaimRequest", "successSchema": "NarrationClaimSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "pointId", "claimToken",
                     "generation", "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("point", "committed"), _HEAD_LEASE],
        "errorCodes": _WIRE_ERRORS + _errors("lease_invalid", "stale_epoch", "version_mismatch",
                                             "cache_missing", "claim_expired", "claim_fenced"),
        "mutatesRevision": False,
        "sideEffects": ["issues_narration_claim", "rotates_narration_generation"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "claim_summary"},
        "queryBindings": [],
        "notes": "A fresh requestId with the valid head lease (or a valid currentClaim for history) "
                 "retrieves the still-valid claim. Successful requestId replay returns summary "
                 "without token; expired or fenced authority cannot retrieve it. Returns the issued claim for a valid claim; only invalidation, retry or "
                 "regeneration rotates the generation and token. This is the only response that "
                 "may carry claimToken. Head mode requires the valid advance lease; history mode "
                 "operates on the point claim only and borrows no lease.",
    },
    {
        "operation": "narration_claim_renew", "method": "PUT",
        "path": "/worlds/{worldId}/points/{pointId}/narration-claim",
        "requestSchema": "NarrationClaimRenewRequest", "successSchema": "NarrationClaimRenewSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "pointId", "claimToken",
                     "generation", "issuedAtEpochMilli", "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("point", "committed"), _HEAD_LEASE],
        "errorCodes": _WIRE_ERRORS + _errors("lease_invalid", "stale_epoch", "version_mismatch",
                                             "claim_expired", "claim_fenced"),
        "mutatesRevision": False,
        "sideEffects": ["extends_claim_expiry"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Extends the matching claim's expiry without changing generation or token; "
                 "long generations renew instead of re-claiming.",
    },
    {
        "operation": "narration_submit", "method": "PUT",
        "path": "/worlds/{worldId}/points/{pointId}/narration",
        "requestSchema": "NarrationSubmitRequest", "successSchema": "NarrationSubmitSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "pointId", "claimToken",
                     "generation", "issuedAtEpochMilli", "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("point", "committed"), _HEAD_LEASE],
        "errorCodes": _WIRE_ERRORS + _errors("lease_invalid", "stale_epoch", "version_mismatch",
                                             "claim_expired", "claim_fenced", "cache_missing"),
        "mutatesRevision": False,
        "sideEffects": ["writes_narration_cache", "marks_point_ready", "clears_gate"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": [],
        "notes": "Commits text or a failure code against generation, claimToken and issued "
                 "epoch. Cache write, point ready and matching-gate clearing share one "
                 "transaction; phase, paused and checkpoint revision never change. Same "
                 "generation and text replays the original success; a changed text is rejected.",
    },
    {
        "operation": "narration_get", "method": "GET",
        "path": "/worlds/{worldId}/points/{pointId}/narration",
        "requestSchema": None, "successSchema": "NarrationGetSuccess",
        "successHttpStatus": 200, "bindings": ["worldId", "pointId"], "preconditions": [],
        "errorCodes": _errors("protocol_version_unsupported", "version_mismatch"),
        "mutatesRevision": False, "sideEffects": [],
        "idempotency": {"scope": "none", "key": None, "replay": "recomputable"},
        "queryBindings": [],
        "notes": "Reads narration status, current generation and its text; never a lease check.",
    },
    {
        "operation": "narration_delete", "method": "DELETE",
        "path": "/worlds/{worldId}/points/{pointId}/narration",
        "requestSchema": "NarrationDeleteRequest", "successSchema": "NarrationDeleteSuccess",
        "successHttpStatus": 200,
        "bindings": ["protocolVersion", "worldId", "requestId", "pointId", "claimToken",
                     "generation", "issuedAtEpochMilli", "leaseToken", "fenceEpoch"],
        "preconditions": [_pre("point", "committed"), _HEAD_LEASE],
        "errorCodes": _WIRE_ERRORS + _errors("lease_invalid", "stale_epoch", "version_mismatch",
                                             "claim_expired", "claim_fenced"),
        "mutatesRevision": False,
        "sideEffects": ["invalidates_narration_cache"],
        "idempotency": {"scope": "world", "key": "requestId", "replay": "original_data"},
        "queryBindings": ["requestId", "mode", "claimToken", "generation", "issuedAtEpochMilli", "leaseToken", "fenceEpoch"],
        "notes": "Deletes the cache and invalidates the matching generation; world facts are "
                 "never deleted.",
    },
])

OPERATION_BY_NAME: dict[str, OperationSpec] = {spec.operation: spec for spec in OPERATIONS}
assert len(OPERATION_BY_NAME) == len(OPERATIONS), "operation names must be unique"
