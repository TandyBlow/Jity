"""v2 per-operation request models, data payloads and success envelopes.

Request models are independent union members registered under the shared
/worlds/{worldId}/checkpoint, /round-conclusion and narration endpoints; the
registry entry names the exact model. Success responses are concrete
OperationResult[T] aliases so the exported schema and the TS Record keyset stay
exhaustive and human-readable. `data` payloads carry identity, status and
binding digests only — input text never re-enters any response.
"""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field, model_validator

from app.schemas.world.contracts import (
    Contract, Count, Id, IdSet, Ids, Positive, SafeInt, Sanity, Text, TimeAdvance,
    ContinueConclusion, DescriptionChange, PendingTask, Position, TimelinePoint,
    WorldInitialState, WorldState,
)

from .base import EpochMilli, Hex64, ProtocolVersion
from .contexts import (
    SuccessorSummary, WorkingProgress, NarrationStatus,
)
from .envelopes import OperationResult, ReadResult

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
# Settlement groups (v2 replacement for v1 stageCandidates scope)
# ---------------------------------------------------------------------------


class SettlementGroup(Contract):
    """One ordered settlement unit.

    groupId=None marks the pure time-scan unit of an action-less point: it may
    not invent movement, appearance or actors. A named group is an action unit
    and requires actors. Outer order in commit requests is significant; member
    ordering inside sets is not.
    """

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"groupId": {"type": "null"}}},
         "then": {"properties": {"actorIds": {"maxItems": 0},
                                 "positions": {"maxProperties": 0},
                                 "appearances": {"maxProperties": 0}}}},
        {"if": {"properties": {"groupId": {"type": "string"}}},
         "then": {"properties": {"actorIds": {"minItems": 1}}}},
    ]})

    groupId: Id | None
    actorIds: Ids
    positions: dict[Id, Position]
    appearances: dict[Id, Annotated[list[DescriptionChange], Field(min_length=1)]]
    tasksAchieved: dict[Id, Annotated[IdSet, Field(min_length=1)]]
    subtasksAdded: dict[Id, Annotated[list[PendingTask], Field(min_length=1)]]
    personalities: dict[Id, Annotated[list[DescriptionChange], Field(min_length=1)]]
    sanities: dict[Id, Sanity]
    taskCoverageIds: IdSet
    personalityCoverageIds: IdSet

    @model_validator(mode="after")
    def stages(self):
        if self.groupId is None:
            if self.actorIds or self.positions or self.appearances:
                raise ValueError("time-scan unit cannot invent actors, movement or appearance")
        elif not self.actorIds:
            raise ValueError("action group requires actors")
        if set(self.sanities) != set(self.personalities):
            raise ValueError("personality changes and sanity recalculation must pair")
        if self.personalities and not any(self.tasksAchieved.values()):
            raise ValueError("personality stage requires newly achieved tasks")
        for owner, tasks in self.subtasksAdded.items():
            if any(task.ownerId != owner or task.parentTaskId is None for task in tasks):
                raise ValueError("subtasks require matching owner and parent")
        return self


# ---------------------------------------------------------------------------
# World creation and context
# ---------------------------------------------------------------------------


class CreateWorldRequest(CreationRequest):
    initial: WorldInitialState


# ---------------------------------------------------------------------------
# Checkpoint narrow operations
# ---------------------------------------------------------------------------


class BeginPointRequest(PointCheckpointRequest):
    kind: Literal["normal", "instant", "linked"]
    timeAdvance: TimeAdvance


class SetPointTimeRequest(PointCheckpointRequest):
    timeAdvance: TimeAdvance


class DiscoverGroupRequest(PointCheckpointRequest):
    groupId: Id
    initiatorId: Id
    actionText: Text
    # Complete target set when the same model call returned it; an empty set is
    # a complete, confirmed "no targets" result.
    targetIds: IdSet


class TargetSpec(Contract):
    targetId: Id
    triggerKey: Id


class RollRef(Contract):
    sourceId: Id
    targetId: Id
    triggerKey: Id
    rollId: Id


class MemberAdmission(Contract):
    memberId: Id
    actionText: Text
    rollRefs: list[RollRef] = Field(min_length=1)


class ExtendGroupRequest(PointCheckpointRequest):
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
    groupId: Id


class StageUnitRequest(PointCheckpointRequest):
    groupId: Id
    candidates: SettlementGroup

    @model_validator(mode="after")
    def named_group(self):
        if self.candidates.groupId != self.groupId:
            raise ValueError("staged candidates must name the closed group")
        return self


class RecordSkipRequest(PointCheckpointRequest):
    slotActorId: Id


class StageTimeScanRequest(PointCheckpointRequest):
    candidates: SettlementGroup

    @model_validator(mode="after")
    def time_scan_unit(self):
        if self.candidates.groupId is not None or self.candidates.actorIds:
            raise ValueError("time-scan candidates must be the groupId-less pure-time unit")
        return self


class SealPointRequest(PointCheckpointRequest):
    pass


class PrepareSuccessorRequest(PointCheckpointRequest):
    successorPointId: Id
    timeAdvance: TimeAdvance


class WorkManifestItem(Contract):
    memberId: Id
    actionContentHash: Hex64
    resultContentHash: Hex64


class RestoreGroupWorkRequest(PointCheckpointRequest):
    groupId: Id
    attempt: Positive
    sourceEpoch: Positive
    sourceAttempt: Positive
    manifest: list[WorkManifestItem] = Field(min_length=1)


class PauseRequest(CheckpointRequest):
    pass


class ResumeRequest(CheckpointRequest):
    pass


# ---------------------------------------------------------------------------
# Round conclusion
# ---------------------------------------------------------------------------


class ConcludeRoundRequest(WriteRequest):
    advanceId: Id
    roundId: Id
    expectedPointId: Id
    expectedVersion: Count
    expectedCheckpointRevision: Count
    leaseToken: Id
    fenceEpoch: Positive
    conclusion: ContinueConclusion


class CancelRoundRequest(WriteRequest):
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


class NarrationClaimRequest(WriteRequest):
    pointId: Id
    mode: Literal["head", "history"]
    # The claim currently held by the caller, when any; the server decides
    # whether it is still valid or a new generation must be issued.
    currentClaim: CurrentClaim | None = None


class NarrationClaimRenewRequest(WriteRequest):
    pointId: Id
    mode: Literal["head", "history"]
    claimToken: Id
    generation: Positive
    issuedAtEpochMilli: EpochMilli


class NarrationSubmitRequest(WriteRequest):
    pointId: Id
    mode: Literal["head", "history"]
    claimToken: Id
    generation: Positive
    issuedAtEpochMilli: EpochMilli
    outcome: Literal["ready", "failed"]
    text: Text | None
    failureReason: Text | None

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
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


class NarrationDeleteRequest(Contract):
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
    targetIds: IdSet


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
    groupId: Id
    sourceEpoch: Positive
    sourceAttempt: Positive
    restoredMemberIds: IdSet


class PauseData(Contract):
    paused: Literal[True]


class ResumeData(Contract):
    paused: Literal[False]


class ConcludeRoundData(Contract):
    roundId: Id
    nextRoundId: Id | None


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
    pointId: Id
    workingStateDigest: Hex64
    pointProjectionDigest: Hex64
    workingState: WorldState


class RollOutcome(Contract):
    rollId: Id
    groupId: Id
    sourceId: Id
    targetId: Id
    triggerKey: Id
    ruleVersion: Literal["reaction-fixture-v1", "reaction-d20-v1"]
    target: Annotated[SafeInt, Field(ge=1, le=20)]
    result: SafeInt


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


class NarrationClaimData(Contract):
    pointId: Id
    mode: Literal["head", "history"]
    generation: Positive
    claimToken: Id
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


class NarrationSubmitData(Contract):
    pointId: Id
    narrationStatus: NarrationStatus
    generation: Positive


class NarrationGetData(Contract):
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


class PreviewPointSuccess(OperationResult[PreviewData]):
    pass


class CreateRollsSuccess(OperationResult[CreateRollsData]):
    pass


class CommitPointSuccess(OperationResult[CommitPointData]):
    pass


class ListPointsSuccess(ReadResult[ListPointsData]):
    pass


class GetStateSuccess(ReadResult[GetStateData]):
    pass


class NarrationClaimSuccess(OperationResult[NarrationClaimData]):
    pass


class NarrationClaimRenewSuccess(OperationResult[NarrationClaimData]):
    pass


class NarrationSubmitSuccess(OperationResult[NarrationSubmitData]):
    pass


class NarrationGetSuccess(ReadResult[NarrationGetData]):
    pass


class NarrationDeleteSuccess(OperationResult[NarrationDeleteData]):
    pass
