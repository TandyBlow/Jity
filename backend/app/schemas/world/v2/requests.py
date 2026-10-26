"""v2 per-operation request models, data payloads and success envelopes.

Request models are independent union members registered under the shared
/worlds/{worldId}/checkpoint, /round-conclusion and narration endpoints; the
registry entry names the exact model. Success responses are concrete
OperationResult[T] aliases so the exported schema and the TS Record keyset stay
exhaustive and human-readable. `data` payloads carry identity, status and
binding digests only — input text never re-enters any response.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, RootModel, model_validator

from app.schemas.world.contracts import (
    Contract, Count, Id, IdSet, Ids, Positive, SafeInt, Text, TimeAdvance,
    ContinueConclusion, ModelHandback, TimelinePoint, WorldInitialState, WorldState,
    EntityDelta, WorldTime, InitialLocation, InitialItem, InitialCharacter,
)

from .base import EpochMilli, Hex64, ProtocolVersion, SchemaVersion
from .judgments import RollOutcome
from .work import SettlementGroup, TargetSpec, RollRef, WorkManifestItem, GroupWorkSource
from .contexts import (
    SuccessorSummary, WorkingProgress, NarrationStatus,
)
from .envelopes import OperationResult, ReadResult, ComputeResult

# ---------------------------------------------------------------------------
# Shared request bases
# ---------------------------------------------------------------------------


class CreationRequest(Contract):
    """POST /worlds: the worldId does not exist yet and is server-assigned."""

    protocolVersion: ProtocolVersion
    requestId: Id


class WriteRequest(Contract):
    protocolVersion: ProtocolVersion
    requestId: Id
    worldId: Id


class LeaseBoundRequest(WriteRequest):
    leaseToken: Id
    fenceEpoch: Positive


class CheckpointRequest(LeaseBoundRequest):
    """Every checkpoint write binds the world head, version and revision."""

    expectedPointId: Id
    expectedVersion: Count
    expectedCheckpointRevision: Count


class PointCheckpointRequest(CheckpointRequest):
    """Checkpoint writes that operate on one point's work."""

    pointId: Id


class CurrentClaim(Contract):
    claimToken: Id
    generation: Positive
    issuedAtEpochMilli: EpochMilli


# ---------------------------------------------------------------------------
# World creation and context
# ---------------------------------------------------------------------------


class WorldInitialTemplate(Contract):
    """Creation template has no worldId; the server binds it once assigned.

    Domain reference validation is identical to the frozen initial-world type.
    """

    engineVersion: Literal["world-engine-v1"]
    schemaVersion: SchemaVersion
    protagonistId: Id
    initialTime: WorldTime
    locations: dict[Id, InitialLocation]
    items: dict[Id, InitialItem]
    characters: dict[Id, InitialCharacter]

    @model_validator(mode="after")
    def references(self):
        WorldInitialState.model_validate({"worldId": "creation_template", **self.model_dump()})
        return self


class CreateWorldRequest(CreationRequest):
    initial: WorldInitialTemplate


class StartAdvanceRequest(CheckpointRequest):
    operation: Literal["start_advance"]
    advanceId: Id
    inputId: Id
    roundId: Id
    inputText: Text
    order: Ids = Field(min_length=1)

    @model_validator(mode="after")
    def unique_order(self):
        if len(self.order) != len(set(self.order)):
            raise ValueError("round order contains duplicate characters")
        return self


class StartAdvanceData(Contract):
    advanceId: Id
    inputId: Id
    roundId: Id


# ---------------------------------------------------------------------------
# Checkpoint narrow operations
# ---------------------------------------------------------------------------


class BeginPointRequest(PointCheckpointRequest):
    operation: Literal["begin_point"]
    kind: Literal["normal", "instant", "linked"]
    timeAdvance: TimeAdvance


class SetPointTimeRequest(PointCheckpointRequest):
    operation: Literal["set_point_time"]
    timeAdvance: TimeAdvance


class DiscoverGroupRequest(PointCheckpointRequest):
    operation: Literal["discover_group"]
    groupId: Id
    initiatorId: Id
    actionText: Text
    # Null is unconfirmed; [] is a complete, confirmed "no targets" result.
    targetIds: IdSet | None = None


class MemberAdmission(Contract):
    memberId: Id
    actionText: Text | None = None
    rollRefs: list[RollRef] = Field(min_length=1)


class ExtendGroupRequest(PointCheckpointRequest):
    operation: Literal["extend_group"]
    groupId: Id
    sourceId: Id
    # Exactly one per call: the source's complete target set, or one admitted
    # member with its action and judgment references.
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"oneOf": [
        {"properties": {"targets": {"type": "array"}, "admittedMember": {"type": "null"}}},
        {"properties": {"targets": {"type": "null"}, "admittedMember": {"type": "object"}}},
    ]})
    targets: list[TargetSpec] | None = None
    admittedMember: MemberAdmission | None = None

    @model_validator(mode="after")
    def one_contribution_kind(self):
        if (self.targets is None) == (self.admittedMember is None):
            raise ValueError("extend_group needs exactly one of targets or admittedMember")
        return self


class CloseGroupRequest(PointCheckpointRequest):
    operation: Literal["close_group"]
    groupId: Id


class StageUnitRequest(PointCheckpointRequest):
    operation: Literal["stage_unit"]
    groupId: Id
    candidates: SettlementGroup
    results: dict[Id, Text]

    @model_validator(mode="after")
    def named_group(self):
        if self.candidates.groupId != self.groupId:
            raise ValueError("staged candidates must name the closed group")
        if set(self.results) != set(self.candidates.actorIds):
            raise ValueError("staging requires each member's confirmed result")
        return self


class RecordSkipRequest(PointCheckpointRequest):
    operation: Literal["record_skip"]
    slotActorId: Id


class StageTimeScanRequest(PointCheckpointRequest):
    operation: Literal["stage_time_scan"]
    candidates: SettlementGroup

    @model_validator(mode="after")
    def time_scan_unit(self):
        if self.candidates.groupId is not None or self.candidates.actorIds:
            raise ValueError("time-scan candidates must be the groupId-less pure-time unit")
        return self


class SealPointRequest(PointCheckpointRequest):
    operation: Literal["seal_point"]


class PrepareSuccessorRequest(PointCheckpointRequest):
    operation: Literal["prepare_successor"]
    successorPointId: Id
    timeAdvance: TimeAdvance


class RestoreGroupWorkRequest(PointCheckpointRequest, GroupWorkSource):
    """The service allocates the destination attempt, never the caller."""

    operation: Literal["restore_group_work"]


class PauseRequest(CheckpointRequest):
    operation: Literal["pause"]


class ResumeRequest(CheckpointRequest):
    operation: Literal["resume"]


# ---------------------------------------------------------------------------
# Round conclusion
# ---------------------------------------------------------------------------


class ConcludeRoundRequest(WriteRequest):
    operation: Literal["conclude"]
    advanceId: Id
    roundId: Id
    expectedPointId: Id
    expectedVersion: Count
    expectedCheckpointRevision: Count
    leaseToken: Id
    fenceEpoch: Positive
    conclusion: Annotated[ContinueConclusion | ModelHandback, Field(discriminator="kind")]


class CancelRoundRequest(WriteRequest):
    operation: Literal["cancel"]
    advanceId: Id
    roundId: Id
    expectedPointId: Id
    expectedVersion: Count
    expectedCheckpointRevision: Count
    leaseToken: Id
    fenceEpoch: Positive
    cancelReason: Text


# ---------------------------------------------------------------------------
# Lease, ids, preview, rolls
# ---------------------------------------------------------------------------


class AcquireLeaseRequest(WriteRequest):
    holderId: Id


class RenewLeaseRequest(WriteRequest):
    leaseToken: Id
    fenceEpoch: Positive


class ReleaseLeaseRequest(Contract):
    """Query-string model for DELETE /worlds/{worldId}/lease."""

    protocolVersion: ProtocolVersion
    requestId: Id
    leaseToken: Id
    fenceEpoch: Positive


IdKind = Literal["advance", "input", "round", "group", "task", "change", "point", "trigger"]


class AllocationSlot(Contract):
    slotKey: Id
    kind: IdKind
    scope: Id | None = None


class AllocateIdsRequest(LeaseBoundRequest):
    allocationKey: Id
    slots: list[AllocationSlot] = Field(min_length=1)


class PreviewPointRequest(Contract):
    """Stateless recompute; no requestId, never enters the idempotency table."""

    protocolVersion: ProtocolVersion
    worldId: Id
    advanceId: Id
    roundId: Id
    pointId: Id
    expectedPointId: Id
    expectedVersion: Count
    expectedCheckpointRevision: Count
    timeAdvance: TimeAdvance
    settlementGroups: list[SettlementGroup] = Field(max_length=32)


class RollSpec(Contract):
    advanceId: Id
    roundId: Id
    groupId: Id
    sourceId: Id
    targetId: Id
    triggerKey: Id
    ruleVersion: Literal["reaction-fixture-v1", "reaction-d20-v1"]
    target: Annotated[SafeInt, Field(ge=1, le=20)]

    @model_validator(mode="after")
    def rule(self):
        if self.ruleVersion == "reaction-d20-v1" and self.target != 11:
            raise ValueError("reaction-d20-v1 has fixed target 11")
        return self


class CreateRollsRequest(CheckpointRequest):
    rolls: list[RollSpec] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Point commit
# ---------------------------------------------------------------------------


class CommitPointRequest(WriteRequest):
    advanceId: Id
    roundId: Id
    expectedPointId: Id
    expectedVersion: Count
    expectedCheckpointRevision: Count
    leaseToken: Id
    fenceEpoch: Positive
    pointId: Id
    point: TimelinePoint
    settlementGroups: list[SettlementGroup] = Field(max_length=32)

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"properties": {"settlementGroups": {"items": {"properties": {
            "groupId": {"type": "string"}}}}}},
    ]})

    @model_validator(mode="after")
    def bindings(self):
        if self.pointId != self.point.id:
            raise ValueError("pointId differs from point.id")
        if (self.point.worldId, self.point.roundId, self.point.advanceId, self.point.previousPointId) != (
            self.worldId, self.roundId, self.advanceId, self.expectedPointId
        ):
            raise ValueError("point binding differs from request")
        group_ids = [unit.groupId for unit in self.settlementGroups]
        if any(group is None for group in group_ids):
            raise ValueError("committed settlement groups must be named action groups")
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("duplicate settlement group identity")
        return self


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------


class NarrationLeaseBinding(Contract):
    mode: Literal["head", "history"]
    leaseToken: Id | None = None
    fenceEpoch: Positive | None = None

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"mode": {"const": "head"}}},
         "then": {"required": ["leaseToken", "fenceEpoch"], "properties": {
             "leaseToken": {"type": "string"}, "fenceEpoch": {"type": "integer", "minimum": 1}}}},
        {"if": {"properties": {"mode": {"const": "history"}}},
         "then": {"properties": {"leaseToken": {"type": "null"}, "fenceEpoch": {"type": "null"}}}},
    ]})

    @model_validator(mode="after")
    def lease_matches_mode(self):
        if self.mode == "head":
            if self.leaseToken is None or self.fenceEpoch is None:
                raise ValueError("head narration requires lease token and epoch")
        elif self.leaseToken is not None or self.fenceEpoch is not None:
            raise ValueError("history narration cannot borrow the advance lease")
        return self


class _NarrationClaimRequestFields(NarrationLeaseBinding, WriteRequest):
    pointId: Id
    mode: Literal["head", "history"]
    # The claim currently held by the caller, when any; the server decides
    # whether it is still valid or a new generation must be issued.
    currentClaim: CurrentClaim | None = None


class _NarrationClaimRenewRequestFields(NarrationLeaseBinding, WriteRequest):
    pointId: Id
    mode: Literal["head", "history"]
    claimToken: Id
    generation: Positive
    issuedAtEpochMilli: EpochMilli


class _NarrationSubmitRequestFields(NarrationLeaseBinding, WriteRequest):
    pointId: Id
    mode: Literal["head", "history"]
    claimToken: Id
    generation: Positive
    issuedAtEpochMilli: EpochMilli
    outcome: Literal["ready", "failed"]
    text: Text | None
    failureReason: Text | None

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        *NarrationLeaseBinding.model_config["json_schema_extra"]["allOf"],
        {"if": {"properties": {"outcome": {"const": "ready"}}},
         "then": {"properties": {"text": {"type": "string"}, "failureReason": {"type": "null"}}}},
        {"if": {"properties": {"outcome": {"const": "failed"}}},
         "then": {"properties": {"text": {"type": "null"}, "failureReason": {"type": "string"}}}},
    ]})

    @model_validator(mode="after")
    def outcome_pairing(self):
        if self.outcome == "ready":
            if self.text is None or self.failureReason is not None:
                raise ValueError("ready narration carries text and no failure reason")
        elif self.failureReason is None or self.text is not None:
            raise ValueError("failed narration carries a failure reason and no text")
        return self


class _NarrationDeleteRequestFields(NarrationLeaseBinding):
    """Query-string model for DELETE .../narration."""

    protocolVersion: ProtocolVersion
    requestId: Id
    mode: Literal["head", "history"]
    claimToken: Id
    generation: Positive
    issuedAtEpochMilli: EpochMilli


# ---------------------------------------------------------------------------
# Data payloads: identity, status and binding digests only
# ---------------------------------------------------------------------------


class LeaseGrant(Contract):
    leaseToken: Id
    fenceEpoch: Positive
    expiresAtEpochMilli: EpochMilli


class CreateWorldData(Contract):
    worldId: Id
    rootPointId: Id
    lease: LeaseGrant


class BeginPointData(Contract):
    pointId: Id


class SetPointTimeData(Contract):
    pointId: Id
    timeAdvance: TimeAdvance


class DiscoverGroupData(Contract):
    groupId: Id
    targetIds: IdSet | None


class ExtendGroupData(Contract):
    groupId: Id
    memberIds: IdSet
    frontierIds: IdSet


class CloseGroupData(Contract):
    groupId: Id
    closed: Literal[True]


class StageUnitData(Contract):
    groupId: Id
    unitId: Id
    working: WorkingProgress


class WorkProgressData(Contract):
    pointId: Id
    working: WorkingProgress


class SealPointData(Contract):
    pointId: Id
    prefixDigest: Hex64


class PrepareSuccessorData(Contract):
    pointId: Id
    successorPointId: Id
    prefixDigest: Hex64
    successor: SuccessorSummary


class RestoreGroupWorkData(Contract):
    pointId: Id
    groupId: Id
    fenceEpoch: Positive
    attempt: Positive
    sourceEpoch: Positive
    sourceAttempt: Positive
    restoredMemberIds: IdSet


class PauseData(Contract):
    paused: Literal[True]


class ResumeData(Contract):
    paused: Literal[False]


class ConcludeRoundData(Contract):
    kind: Literal["continue", "handback"]
    roundId: Id
    nextRoundId: Id | None

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"kind": {"const": "continue"}}},
         "then": {"properties": {"nextRoundId": {"type": "string"}}}},
        {"if": {"properties": {"kind": {"const": "handback"}}},
         "then": {"properties": {"nextRoundId": {"type": "null"}}}},
    ]})

    @model_validator(mode="after")
    def successor_matches_conclusion(self):
        if (self.kind == "continue") != (self.nextRoundId is not None):
            raise ValueError("only continue creates a successor round")
        return self


class CancelRoundData(Contract):
    roundId: Id
    abandonedGroupIds: IdSet


class AcquireLeaseData(Contract):
    holderId: Id
    leaseToken: Id
    fenceEpoch: Positive
    expiresAtEpochMilli: EpochMilli


class RenewLeaseData(LeaseGrant):
    pass


class ReleaseLeaseData(Contract):
    released: Literal[True]


class Allocation(Contract):
    slotKey: Id
    id: Id


class AllocateIdsData(Contract):
    allocations: list[Allocation] = Field(min_length=1)


class PreviewData(Contract):
    pointProjection: TimelinePoint
    mergedEntityDeltas: dict[Id, EntityDelta]
    pointId: Id
    workingStateDigest: Hex64
    pointProjectionDigest: Hex64
    workingState: WorldState

    @model_validator(mode="after")
    def projection_binding(self):
        if self.pointId != self.pointProjection.id:
            raise ValueError("preview projection names another point")
        if self.mergedEntityDeltas != (self.pointProjection.entityDeltas or {}):
            raise ValueError("merged deltas differ from point projection")
        return self


class CreateRollsData(Contract):
    rolls: list[RollOutcome] = Field(min_length=1)


class CommitPointData(Contract):
    pointId: Id
    version: Count
    stateDigest: Hex64


class PointSummary(Contract):
    pointId: Id
    sequence: Count
    kind: Literal["root", "normal", "instant", "linked"]
    roundId: Id | None
    advanceId: Id | None
    stateDigest: Hex64


class ListPointsData(Contract):
    points: list[PointSummary]


class GetStateData(Contract):
    pointId: Id
    version: Count
    state: WorldState
    stateDigest: Hex64
    # The point's own saved record, echoed for narration assembly:
    # previousPointId/timeAdvance/entityDeltas are the point's ORIGINAL
    # delta - root points carry null/null/{}. Required with no defaults: a
    # reader missing them must report incomplete read capability, never
    # assume an empty delta.
    previousPointId: Id | None
    timeAdvance: TimeAdvance | None
    entityDeltas: dict[Id, EntityDelta]


class NarrationClaimSummary(Contract):
    pointId: Id
    mode: Literal["head", "history"]
    generation: Positive
    # head claims fence through the advance lease epoch; history claims carry
    # null and must never borrow it.
    fenceEpoch: Positive | None
    issuedAtEpochMilli: EpochMilli
    expiresAtEpochMilli: EpochMilli

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"mode": {"const": "head"}}},
         "then": {"properties": {"fenceEpoch": {"type": "integer"}}}},
        {"if": {"properties": {"mode": {"const": "history"}}},
         "then": {"properties": {"fenceEpoch": {"type": "null"}}}},
    ]})

    @model_validator(mode="after")
    def fence_matches_mode(self):
        if (self.mode == "head") != (self.fenceEpoch is not None):
            raise ValueError("head claims fence via lease epoch; history claims carry null")
        return self


class NarrationClaimData(NarrationClaimSummary):
    claimToken: Id


class NarrationSubmitData(Contract):
    pointId: Id
    narrationStatus: NarrationStatus
    generation: Positive


class NarrationGetData(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"narrationStatus": {"const": "ready"}}},
         "then": {"properties": {"text": {"type": "string"}}},
         "else": {"properties": {"text": {"type": "null"}}}},
    ]})
    pointId: Id
    narrationStatus: NarrationStatus
    generation: Positive | None
    text: Text | None

    @model_validator(mode="after")
    def text_only_when_ready(self):
        if (self.narrationStatus == "ready") != (self.text is not None):
            raise ValueError("only ready narration carries text")
        return self


class NarrationDeleteData(Contract):
    pointId: Id
    narrationStatus: Literal["missing"]
    invalidatedGeneration: Positive


# ---------------------------------------------------------------------------
# Concrete success envelopes (one $defs entry per operation)
# ---------------------------------------------------------------------------


class CreateWorldSuccess(OperationResult[CreateWorldData]):
    pass


class BeginPointSuccess(OperationResult[BeginPointData]):
    pass


class SetPointTimeSuccess(OperationResult[SetPointTimeData]):
    pass


class DiscoverGroupSuccess(OperationResult[DiscoverGroupData]):
    pass


class ExtendGroupSuccess(OperationResult[ExtendGroupData]):
    pass


class CloseGroupSuccess(OperationResult[CloseGroupData]):
    pass


class StageUnitSuccess(OperationResult[StageUnitData]):
    pass


class RecordSkipSuccess(OperationResult[WorkProgressData]):
    pass


class StageTimeScanSuccess(OperationResult[WorkProgressData]):
    pass


class SealPointSuccess(OperationResult[SealPointData]):
    pass


class PrepareSuccessorSuccess(OperationResult[PrepareSuccessorData]):
    pass


class RestoreGroupWorkSuccess(OperationResult[RestoreGroupWorkData]):
    pass


class PauseSuccess(OperationResult[PauseData]):
    pass


class ResumeSuccess(OperationResult[ResumeData]):
    pass


class ConcludeRoundSuccess(OperationResult[ConcludeRoundData]):
    pass


class CancelRoundSuccess(OperationResult[CancelRoundData]):
    pass


class AcquireLeaseSuccess(OperationResult[AcquireLeaseData]):
    pass


class RenewLeaseSuccess(OperationResult[RenewLeaseData]):
    pass


class ReleaseLeaseSuccess(OperationResult[ReleaseLeaseData]):
    pass


class AllocateIdsSuccess(OperationResult[AllocateIdsData]):
    pass


class PreviewPointSuccess(ComputeResult[PreviewData]):
    pass


class CreateRollsSuccess(OperationResult[CreateRollsData]):
    pass


class CommitPointSuccess(OperationResult[CommitPointData]):
    pass


class ListPointsSuccess(ReadResult[ListPointsData]):
    pass


class GetStateSuccess(ReadResult[GetStateData]):
    pass


class NarrationClaimSuccess(OperationResult[NarrationClaimData | NarrationClaimSummary]):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"replayed": {"const": True}}},
         "then": {"properties": {"data": {"not": {"required": ["claimToken"]}}}}},
        {"if": {"properties": {"replayed": {"const": False}}},
         "then": {"properties": {"data": {"required": ["claimToken"]}}}},
    ]})

    @model_validator(mode="after")
    def token_only_on_authorized_claim(self):
        if isinstance(self.data, NarrationClaimData) == self.replayed:
            raise ValueError("only a fresh authorized claim may return a token")
        return self


class NarrationClaimRenewSuccess(OperationResult[NarrationClaimSummary]):
    pass


class NarrationSubmitSuccess(OperationResult[NarrationSubmitData]):
    pass


class NarrationGetSuccess(ReadResult[NarrationGetData]):
    pass


class NarrationDeleteSuccess(OperationResult[NarrationDeleteData]):
    pass


class StartAdvanceSuccess(OperationResult[StartAdvanceData]):
    pass


class ListPointsRequest(Contract):
    after: Count | None = None
    limit: Annotated[Positive, Field(le=100)] = 50


class GetStateRequest(Contract):
    point: Id | None = None


class GetContextRequest(Contract):
    includeRecovery: bool = False
    leaseToken: Id | None = None
    fenceEpoch: Positive | None = None

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"includeRecovery": {"const": True}}, "required": ["includeRecovery"]},
         "then": {"required": ["leaseToken", "fenceEpoch"], "properties": {
             "leaseToken": {"type": "string"}, "fenceEpoch": {"type": "integer", "minimum": 1}}}},
    ]})

    @model_validator(mode="after")
    def recovery_requires_lease(self):
        if self.includeRecovery and (self.leaseToken is None or self.fenceEpoch is None):
            raise ValueError("recovery reads require the current advance lease")
        return self


CheckpointBody = Annotated[
    StartAdvanceRequest | BeginPointRequest | SetPointTimeRequest | DiscoverGroupRequest
    | ExtendGroupRequest | CloseGroupRequest | StageUnitRequest | RecordSkipRequest
    | StageTimeScanRequest | SealPointRequest | PrepareSuccessorRequest
    | RestoreGroupWorkRequest | PauseRequest | ResumeRequest,
    Field(discriminator="operation"),
]


class CheckpointDispatch(RootModel[CheckpointBody]):
    """The HTTP request body itself, selected by operation."""


class RoundConclusionDispatch(RootModel[Annotated[
    ConcludeRoundRequest | CancelRoundRequest, Field(discriminator="operation")
]]):
    """The round-conclusion HTTP body itself."""


class HeadNarrationClaimRequest(_NarrationClaimRequestFields):
    mode: Literal["head"]
    leaseToken: Id
    fenceEpoch: Positive


class HistoryNarrationClaimRequest(_NarrationClaimRequestFields):
    mode: Literal["history"]
    leaseToken: None = None
    fenceEpoch: None = None


class NarrationClaimRequest(RootModel[Annotated[
    HeadNarrationClaimRequest | HistoryNarrationClaimRequest, Field(discriminator="mode")
]]):
    """Wire body/query union, selected by head/history mode."""


class HeadNarrationClaimRenewRequest(_NarrationClaimRenewRequestFields):
    mode: Literal["head"]
    leaseToken: Id
    fenceEpoch: Positive


class HistoryNarrationClaimRenewRequest(_NarrationClaimRenewRequestFields):
    mode: Literal["history"]
    leaseToken: None = None
    fenceEpoch: None = None


class NarrationClaimRenewRequest(RootModel[Annotated[
    HeadNarrationClaimRenewRequest | HistoryNarrationClaimRenewRequest, Field(discriminator="mode")
]]):
    """Wire body/query union, selected by head/history mode."""


class HeadNarrationSubmitRequest(_NarrationSubmitRequestFields):
    mode: Literal["head"]
    leaseToken: Id
    fenceEpoch: Positive


class HistoryNarrationSubmitRequest(_NarrationSubmitRequestFields):
    mode: Literal["history"]
    leaseToken: None = None
    fenceEpoch: None = None


class NarrationSubmitRequest(RootModel[Annotated[
    HeadNarrationSubmitRequest | HistoryNarrationSubmitRequest, Field(discriminator="mode")
]]):
    """Wire body/query union, selected by head/history mode."""


class HeadNarrationDeleteRequest(_NarrationDeleteRequestFields):
    mode: Literal["head"]
    leaseToken: Id
    fenceEpoch: Positive


class HistoryNarrationDeleteRequest(_NarrationDeleteRequestFields):
    mode: Literal["history"]
    leaseToken: None = None
    fenceEpoch: None = None


class NarrationDeleteRequest(RootModel[Annotated[
    HeadNarrationDeleteRequest | HistoryNarrationDeleteRequest, Field(discriminator="mode")
]]):
    """Wire body/query union, selected by head/history mode."""
