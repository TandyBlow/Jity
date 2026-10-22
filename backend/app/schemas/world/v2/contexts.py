"""The three shared v2 view types: WorldContext, PointWorkView, ControlState.

All three are server-computed read projections. None of them carries a
credential: the lease token travels only in operation `data`, the claim token
only in narration-jobs/claim `data`. Absolute times are epoch milliseconds.
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, ConfigDict, Field, model_validator

from app.schemas.world.contracts import (
    Contract, Count, Id, IdSet, Ids, Positive, Text, TimeAdvance, WorldTime,
    _integer, _sorted_unique, ContinueConclusion, ModelHandback, CancelHandback,
)

from .base import EpochMilli, Hex64
from .work import FrozenGroupView, GroupWorkSource, SettlementGroup

NarrationStatus = Literal["pending", "ready", "failed", "missing"]
IntentStatus = Literal["pending", "consumed", "expired"]


class HeadSummary(Contract):
    """Latest committed point; the state its digest projects."""

    pointId: Id
    version: Count
    stateDigest: Hex64
    narrationStatus: NarrationStatus


class AdvanceSummary(Contract):
    """Active input chain; input text itself is only readable via GET context."""

    advanceId: Id | None
    inputId: Id | None
    intentStatus: IntentStatus
    inputAvailable: bool

    @model_validator(mode="after")
    def chain_identity(self):
        if (self.advanceId is None) != (self.inputId is None):
            raise ValueError("advance and input identity must be present together")
        if self.advanceId is None and self.inputAvailable:
            raise ValueError("no active input can be available")
        return self


class RoundSummary(Contract):
    """Active round; conclusion is set once the round reaches complete."""

    roundId: Id
    trigger: Literal["player", "automatic"]
    order: Ids
    cursor: Count
    actedIds: IdSet
    visitedIds: IdSet
    conclusion: ContinueConclusion | ModelHandback | CancelHandback | None

    @model_validator(mode="after")
    def committed_progress(self):
        if len(self.order) != len(set(self.order)) or self.cursor > len(self.order):
            raise ValueError("invalid frozen round order or cursor")
        return self


class LeaseSummary(Contract):
    """Active advance lease without its token; fenceEpoch is always positive."""

    fenceEpoch: Positive
    expiresAtEpochMilli: EpochMilli


class SuccessorSummary(Contract):
    """Sealed-prefix successor reservation (prepare_successor)."""

    pointId: Id
    predecessorPointId: Id
    timeAdvance: TimeAdvance
    expectedPredecessorVersion: Count
    prefixDigest: Hex64
    expectedPredecessorStateDigest: Hex64
    baseline: "BaselineView"


class WorldContext(Contract):
    """Where the world stands: head, input chain, round, time, lease, pointers."""

    worldId: Id
    head: HeadSummary
    advance: AdvanceSummary
    round: RoundSummary | None
    time: WorldTime
    lease: LeaseSummary | None
    successor: SuccessorSummary | None
    activePointId: Id | None
    activeRoundId: Id | None

    @model_validator(mode="after")
    def pointers(self):
        if self.activeRoundId is not None:
            if self.round is None or self.round.roundId != self.activeRoundId:
                raise ValueError("round summary and active round pointer must agree")
        elif self.round is not None and self.round.conclusion is None:
            raise ValueError("an unconcluded round must stay the active round")
        return self


class BaselineView(Contract):
    """Frozen baseline the point work applies time and candidates onto."""

    headPointId: Id
    version: Count
    stateDigest: Hex64


class WorkingProgress(Contract):
    """Uncommitted working cursor and sets; committed progress lives in the head."""

    cursor: Count
    actedIds: IdSet
    visitedIds: IdSet
    settledUnitIds: IdSet
    intentStatus: IntentStatus


class SettledUnitView(Contract):
    """One staged settlement unit; outer order is significant and never sorted."""

    unitId: Id
    groupId: Id
    memberIds: IdSet
    contentHash: Hex64


class PendingGroupView(Contract):
    """Model goals only; admission is recomputed from rolls and eligibility."""

    groupId: Id
    sourceId: Id
    memberIds: IdSet
    targetIds: IdSet
    frontierIds: IdSet
    closed: bool

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"closed": {"const": True}}},
         "then": {"properties": {"frontierIds": {"maxItems": 0}}}},
    ]})

    @model_validator(mode="after")
    def membership(self):
        if self.sourceId not in self.memberIds:
            raise ValueError("group source outside member set")
        if not set(self.frontierIds) <= set(self.memberIds):
            raise ValueError("frontier outside member set")
        if self.closed and self.frontierIds:
            raise ValueError("closed group has unfinished frontier")
        return self


class PointWorkView(Contract):
    """Read-only projection of one point's uncommitted work.

    phase is the point-scoped work position (select_actor/build_group/
    settle_group); round-scoped positions live on ControlState. The browser
    must never send this view back as authoritative state.
    """

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"sealed": {"const": True}}},
         "then": {"properties": {"prefixDigest": {"type": "string"}}},
         "else": {"properties": {"prefixDigest": {"type": "null"}}}},
        {"if": {"properties": {"phase": {"const": "select_actor"}}},
         "then": {"properties": {"pendingGroup": {"type": "null"}}}},
        {"if": {"properties": {"phase": {"enum": ["build_group", "settle_group"]}}},
         "then": {"properties": {"pendingGroup": {"type": "object"}}}},
        {"if": {"properties": {"phase": {"const": "settle_group"}}},
         "then": {"properties": {"pendingGroup": {"type": "object",
                                                  "properties": {"closed": {"const": True}}}}}},
        {"if": {"properties": {"phase": {"const": "build_group"}}},
         "then": {"properties": {"pendingGroup": {"type": "object",
                                                  "properties": {"closed": {"const": False}}}}}},
    ]})

    pointId: Id
    kind: Literal["normal", "instant", "linked"]
    timeAdvance: TimeAdvance
    timeLocked: bool
    sealed: bool
    prefixDigest: Hex64 | None
    predecessorWorkDigest: Hex64 | None
    timeScanComplete: bool
    baseline: BaselineView
    phase: Literal["select_actor", "build_group", "settle_group"]
    working: WorkingProgress
    settledUnits: list[SettledUnitView]
    pendingGroup: PendingGroupView | None
    successor: SuccessorSummary | None

    @model_validator(mode="after")
    def combinations(self):
        if self.sealed != (self.prefixDigest is not None):
            raise ValueError("sealed work must carry its prefix digest")
        if (self.phase == "select_actor") != (self.pendingGroup is None):
            raise ValueError("pending group must match the work phase")
        if self.phase == "settle_group" and not self.pendingGroup.closed:
            raise ValueError("settlement requires a closed group")
        if self.phase == "build_group" and self.pendingGroup.closed:
            raise ValueError("build phase cannot hold a closed group")
        if set(self.working.settledUnitIds) != {unit.unitId for unit in self.settledUnits}:
            raise ValueError("settled unit ids must match the staged units")
        return self


class PointRecoveryView(Contract):
    """Lease-protected source metadata and current-epoch payload.

    targets=None means not confirmed; [] means a confirmed empty target set.
    A null action/result similarly denotes work that has not been accepted yet.
    restore_required instead withholds the entire payload while independently
    exposing active source references, including their old epoch and hashes.
    Sealed/time-scan completion markers remain unchanged while bytes are hidden.
    """

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"payloadStatus": {"const": "restore_required"}}},
         "then": {"properties": {"restoreSources": {"minItems": 1}, "groups": {"maxItems": 0},
                                  "timeScanCandidates": {"type": "null"}}}},
        {"if": {"properties": {"payloadStatus": {"const": "available"},
                                 "work": {"properties": {"timeScanComplete": {"const": True}}}}},
         "then": {"properties": {"timeScanCandidates": {"type": "object", "properties": {"groupId": {"type": "null"}}}}},
         "else": {"properties": {"timeScanCandidates": {"type": "null"}}}},
    ]})

    work: PointWorkView
    payloadStatus: Literal["available", "restore_required"]
    restoreSources: list[GroupWorkSource]
    groups: list[FrozenGroupView]
    timeScanCandidates: SettlementGroup | None

    @model_validator(mode="after")
    def point_scope(self):
        if any(source.pointId != self.work.pointId for source in self.restoreSources):
            raise ValueError("restore source belongs to another point")
        active_groups = {unit.groupId: set(unit.memberIds) for unit in self.work.settledUnits}
        if self.work.pendingGroup is not None:
            group = self.work.pendingGroup
            active_groups[group.groupId] = set(group.memberIds)
        for source in self.restoreSources:
            if source.groupId not in active_groups:
                raise ValueError("restore source has no active work reference")
            if not {item.memberId for item in source.manifest} <= active_groups[source.groupId]:
                raise ValueError("restore source member is outside the active group")
        if any(group.pointId != self.work.pointId for group in self.groups):
            raise ValueError("recovery group belongs to another point")
        if self.payloadStatus == "restore_required":
            if not self.restoreSources:
                raise ValueError("restore-required work needs readable source references")
            if self.groups or self.timeScanCandidates is not None:
                raise ValueError("old-epoch payload must stay hidden until restored")
            return self
        if self.work.timeScanComplete != (self.timeScanCandidates is not None):
            raise ValueError("time scan marker differs from saved candidates")
        if self.timeScanCandidates is not None and self.timeScanCandidates.groupId is not None:
            raise ValueError("time scan cannot name an action group")
        return self


class RecoveryView(Contract):
    fenceEpoch: Positive
    current: PointRecoveryView | None
    successor: PointRecoveryView | None


BlockedReason = Literal[
    "narration_pending",
    "narration_failed",
    "cache_missing",
    "claim_expired",
    "claim_fenced",
    "paused",
    "phase_not_computable",
    "lease_invalid",
]

ControlPhase = Literal[
    "select_actor", "build_group", "settle_group",
    "continue_round", "assess_continuation", "complete",
]


class GateView(Contract):
    """Narration gate without its claim token.

    status=pending carries the current claim generation and issue/expiry instants;
    status=none carries nulls. Generation 0 never exists: the creation and commit
    transactions issue generation=1 directly.
    """

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"status": {"const": "pending"}}},
         "then": {"required": ["generation", "issuedAtEpochMilli", "expiresAtEpochMilli"],
                  "properties": {"generation": {"type": "integer"},
                                 "issuedAtEpochMilli": {"type": "integer"},
                                 "expiresAtEpochMilli": {"type": "integer"}}}},
        {"if": {"properties": {"status": {"const": "none"}}},
         "then": {"properties": {"generation": {"type": "null"},
                                 "issuedAtEpochMilli": {"type": "null"},
                                 "expiresAtEpochMilli": {"type": "null"}}}},
    ]})

    status: Literal["none", "pending"]
    generation: Positive | None = None
    issuedAtEpochMilli: EpochMilli | None = None
    expiresAtEpochMilli: EpochMilli | None = None

    @model_validator(mode="after")
    def pending_is_fully_issued(self):
        fields = (self.generation, self.issuedAtEpochMilli, self.expiresAtEpochMilli)
        if ((self.status == "pending" and any(value is None for value in fields))
                or (self.status == "none" and any(value is not None for value in fields))):
            raise ValueError("pending gate needs generation and instants; cleared gate has none")
        return self


class ControlState(Contract):
    """Controller position, pause and narration gate.

    phase is the next computation position; there is no await_narration or
    paused phase anymore — waiting is the gate, pausing is the flag. canCompute
    is a transaction-time server snapshot, never a client-side invariant: the
    next write can still fail on lease or gate grounds.
    """

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"canCompute": {"const": True}}},
         "then": {"properties": {"blockedReasons": {"maxItems": 0}, "paused": {"const": False}}}},
    ]})

    phase: ControlPhase
    paused: bool
    revision: Count
    gate: GateView
    blockedReasons: Annotated[
        list[BlockedReason], AfterValidator(_sorted_unique),
        Field(json_schema_extra={"uniqueItems": True}),
    ]
    canCompute: bool

    @model_validator(mode="after")
    def computability_matches_blockers(self):
        if self.canCompute and (self.paused or self.blockedReasons):
            raise ValueError("canCompute contradicts pause or blocked reasons")
        return self
