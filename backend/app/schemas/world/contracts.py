"""Stage-0 contracts; contextual transition checks belong to the later engine.

The exported JSON Schema describes shape and local field combinations. Python
validators additionally check collection identity and initial-world references.
No apply, scheduler, lease executor, or API implementation lives here.
"""

from datetime import datetime
from decimal import Decimal
import math
from typing import Annotated, Literal, Union

from pydantic import (
    AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field,
    model_serializer, model_validator,
)

MAX_SAFE = 2**53 - 1


def _integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("expected a safe JSON integer")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("expected a finite integer")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError("expected a finite integer")
    if not -MAX_SAFE <= value <= MAX_SAFE or int(value) != value:
        raise ValueError("expected a safe JSON integer")
    return int(value)


def _unique(values):
    if len(values) != len(set(values)):
        raise ValueError("duplicate identity")
    return values


def _sorted_unique(values):
    return sorted(_unique(values))


def _nonblank(value):
    if not value.strip():
        raise ValueError("text must contain a non-whitespace character")
    return value


Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")]
Text = Annotated[str, Field(min_length=1, pattern=r"\S"), AfterValidator(_nonblank)]
SafeInt = Annotated[int, BeforeValidator(_integer), Field(ge=-MAX_SAFE, le=MAX_SAFE)]
Count = Annotated[SafeInt, Field(ge=0)]
Positive = Annotated[SafeInt, Field(ge=1)]
Sanity = Annotated[SafeInt, Field(ge=0, le=100)]
Ids = Annotated[list[Id], AfterValidator(_unique), Field(json_schema_extra={"uniqueItems": True})]
IdSet = Annotated[list[Id], AfterValidator(_sorted_unique), Field(json_schema_extra={"uniqueItems": True})]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WorldTime(Contract):
    calendar: Literal["gregorian"]
    dateTime: Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}$")]
    instantOrdinal: Count

    @model_validator(mode="after")
    def valid_date(self):
        datetime.fromisoformat(self.dateTime)
        return self


class Duration(Contract):
    amount: Count
    unit: Literal["second", "minute", "hour", "day", "month", "year"]


class TimeAdvance(Contract):
    boundary: Literal["elapsed", "instant"]
    duration: Duration


class RelativePosition(Contract):
    entityId: Id
    relation: Literal["under", "above", "beside", "in_front_of", "behind"]


class Position(Contract):
    containerId: Id
    slotId: Id | None = None
    relativeTo: RelativePosition | None = None


class SpatialSlot(Contract):
    id: Id
    label: Text


class Task(Contract):
    id: Id
    ownerId: Id
    parentTaskId: Id | None
    goal: Text
    status: Literal["pending", "achieved"]


class InitialLocation(Contract):
    id: Id
    name: Text
    parentLocationId: Id | None
    initialAppearance: Text
    slots: list[SpatialSlot] = Field(default_factory=list)


class InitialItem(Contract):
    id: Id
    name: Text
    initialPosition: Position
    initialAppearance: Text
    slots: list[SpatialSlot] = Field(default_factory=list)


class InitialCharacter(InitialItem):
    initialPersonality: Text
    initialSanity: Sanity
    tasks: dict[Id, Task]


def _acyclic(edges):
    active, done = set(), set()

    def visit(node):
        if node in active:
            raise ValueError("cyclic dependency")
        if node in done:
            return
        active.add(node)
        for target in edges.get(node, ()):
            visit(target)
        active.remove(node)
        done.add(node)

    for node in edges:
        visit(node)


class WorldInitialState(Contract):
    engineVersion: Literal["world-engine-v1"]
    schemaVersion: Annotated[Literal[1], BeforeValidator(_integer)]
    worldId: Id
    protagonistId: Id
    initialTime: WorldTime
    locations: dict[Id, InitialLocation]
    items: dict[Id, InitialItem]
    characters: dict[Id, InitialCharacter]

    @model_validator(mode="after")
    def references(self):
        records = [*self.locations.items(), *self.items.items(), *self.characters.items()]
        if len(records) != len({key for key, _ in records}):
            raise ValueError("entity IDs must be globally unique")
        entities = dict(records)
        if not self.locations or self.protagonistId not in self.characters:
            raise ValueError("world requires locations and a registered protagonist")
        edges, parents = {}, {}
        for key, entity in records:
            if key != entity.id:
                raise ValueError("map key differs from entity ID")
            _unique([slot.id for slot in entity.slots])
            edges[key] = []
            if isinstance(entity, InitialLocation):
                parent = entity.parentLocationId
                if parent is not None and parent not in self.locations:
                    raise ValueError("unknown parent location")
            else:
                position = entity.initialPosition
                parent = position.containerId
                if parent not in entities:
                    raise ValueError("unknown container")
                if position.slotId is not None and position.slotId not in {
                    slot.id for slot in entities[parent].slots
                }:
                    raise ValueError("slot does not belong to container")
                if position.relativeTo is not None:
                    target = position.relativeTo.entityId
                    if target not in entities:
                        raise ValueError("unknown relative reference")
                    edges[key].append(target)
            parents[key] = parent
            if parent is not None:
                edges[key].append(parent)
        _acyclic(edges)

        def room(node):
            while node not in self.locations:
                node = parents[node]
            return node

        task_ids = set()
        for key, entity in records:
            if isinstance(entity, InitialItem) and entity.initialPosition.relativeTo:
                if room(key) != room(entity.initialPosition.relativeTo.entityId):
                    raise ValueError("relative reference is in a different location")
        for owner, character in self.characters.items():
            task_edges = {}
            for key, task in character.tasks.items():
                if key != task.id or task.ownerId != owner or key in task_ids:
                    raise ValueError("invalid task identity or owner")
                task_ids.add(key)
                parent = task.parentTaskId
                if parent is not None and parent not in character.tasks:
                    raise ValueError("unknown parent task")
                task_edges[key] = [] if parent is None else [parent]
            _acyclic(task_edges)
        return self


class DescriptionChange(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={
        "if": {"properties": {"text": {"type": "null"}}},
        "then": {"properties": {"supersedes": {"minItems": 1}}},
    })
    id: Id
    text: Text | None
    supersedes: IdSet

    @model_validator(mode="after")
    def meaningful(self):
        if self.text is None and not self.supersedes:
            raise ValueError("pure removal requires supersedes")
        if self.id in self.supersedes:
            raise ValueError("cannot supersede self")
        return self


class EntityDelta(Contract):
    entityId: Id
    positionSet: Position | None = None
    appearanceChanges: list[DescriptionChange] = Field(default_factory=list)
    personalityChanges: list[DescriptionChange] = Field(default_factory=list)
    sanitySet: Sanity | None = None
    tasksAchieved: IdSet = Field(default_factory=list)
    subtasksAdded: list[Task] = Field(default_factory=list)

    @model_validator(mode="after")
    def identities(self):
        changes = [*self.appearanceChanges, *self.personalityChanges]
        _unique([change.id for change in changes])
        for field in (self.appearanceChanges, self.personalityChanges):
            targets = [target for change in field for target in change.supersedes]
            _unique(targets)
            if set(targets) & {change.id for change in changes}:
                raise ValueError("same-point supersedes is forbidden")
        added = {task.id: task for task in self.subtasksAdded}
        if len(added) != len(self.subtasksAdded) or set(added) & set(self.tasksAchieved):
            raise ValueError("duplicate or overlapping task delta")
        if any(task.ownerId != self.entityId or task.parentTaskId is None for task in added.values()):
            raise ValueError("new subtask needs same owner and a parent")
        levels = {}

        def level(key, trail):
            if key in trail:
                raise ValueError("cyclic new task tree")
            if key not in levels:
                parent = added[key].parentTaskId
                levels[key] = level(parent, trail | {key}) + 1 if parent in added else 0
            return levels[key]

        for key in added:
            level(key, set())
        self.subtasksAdded = sorted(added.values(), key=lambda task: (levels[task.id], task.id))
        return self

    @model_serializer(mode="wrap")
    def omit_empty_operations(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None and value != []}


class AdvanceContext(Contract):
    advanceId: Id
    inputId: Id
    inputText: Text | None
    intentStatus: Literal["pending", "consumed", "expired"]


class StoredDescriptionChange(DescriptionChange):
    sourcePointId: Id
    sourceSequence: Positive
    active: bool


class LocationState(Contract):
    id: Id
    appearanceChanges: list[StoredDescriptionChange] = Field(default_factory=list)


class ItemState(LocationState):
    position: Position


class CharacterState(ItemState):
    personalityChanges: list[StoredDescriptionChange] = Field(default_factory=list)
    sanity: Sanity
    tasks: dict[Id, Task]


class WorldState(Contract):
    """The exact hash projection; contains no execution or narration metadata."""

    engineVersion: Literal["world-engine-v1"]
    schemaVersion: Annotated[Literal[1], BeforeValidator(_integer)]
    worldId: Id
    protagonistId: Id
    time: WorldTime
    initial: WorldInitialState
    locations: dict[Id, LocationState]
    items: dict[Id, ItemState]
    characters: dict[Id, CharacterState]

    @model_validator(mode="after")
    def fixed_registry(self):
        if self.worldId != self.initial.worldId or self.protagonistId != self.initial.protagonistId:
            raise ValueError("initial world binding changed")
        for field in ("locations", "items", "characters"):
            current = getattr(self, field)
            initial = getattr(self.initial, field)
            if set(current) != set(initial):
                raise ValueError("fixed entity registry changed")
            if any(key != value.id for key, value in current.items()):
                raise ValueError("state key differs from entity ID")
        return self


class ContinueConclusion(Contract):
    kind: Literal["continue"]
    closedBy: Literal["model"]
    cancelReason: None
    candidateCharacterIds: Annotated[IdSet, Field(min_length=1)]
    nextRoundId: Id


class ModelHandback(Contract):
    kind: Literal["handback"]
    closedBy: Literal["model"]
    cancelReason: None


class CancelHandback(Contract):
    kind: Literal["handback"]
    closedBy: Literal["cancel"]
    cancelReason: Text


RoundConclusion = Union[ContinueConclusion, ModelHandback, CancelHandback]


class Reaction(Contract):
    sourceId: Id
    targetId: Id
    triggerKey: Id
    rollId: Id
    admitted: bool


class PendingGroup(Contract):
    groupId: Id
    initiatorId: Id
    memberIds: Ids
    frontierIds: Ids
    reactions: list[Reaction]
    closed: bool

    @model_validator(mode="after")
    def membership(self):
        if self.initiatorId not in self.memberIds or not set(self.frontierIds) <= set(self.memberIds):
            raise ValueError("invalid group membership")
        if self.closed and self.frontierIds:
            raise ValueError("closed group has unfinished frontier")
        _unique([edge.triggerKey for edge in self.reactions])
        for edge in self.reactions:
            if edge.sourceId not in self.memberIds:
                raise ValueError("reaction source outside group")
            if edge.admitted and edge.targetId not in self.memberIds:
                raise ValueError("admitted target outside group")
        return self


ResumePhase = Literal["select_actor", "build_group", "settle_group", "continue_round", "assess_continuation", "complete"]
DurablePhase = Literal["select_actor", "build_group", "settle_group", "await_narration", "continue_round", "assess_continuation", "paused", "complete"]

CHECKPOINT_SCHEMA_RULES = {"allOf": [
    {"if": {"properties": {"phase": {"enum": ["await_narration", "paused"]}}},
     "then": {"properties": {"resumePhase": {"type": "string"}}},
     "else": {"properties": {"resumePhase": {"type": "null"}}}},
    {"if": {"properties": {"phase": {"const": "complete"}}},
     "then": {"properties": {"conclusion": {"type": "object"}, "pendingGroup": {"type": "null"}}},
     "else": {"properties": {"conclusion": {"type": "null"}}}},
    {"if": {"properties": {"trigger": {"const": "automatic"}}},
     "then": {"properties": {"advance": {"properties": {"intentStatus": {"const": "consumed"}}}}}},
    {"if": {"properties": {"phase": {"enum": ["build_group", "settle_group"]}}},
     "then": {"properties": {"pendingGroup": {"type": "object"}}}},
]}


class RoundCheckpoint(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra=CHECKPOINT_SCHEMA_RULES)
    roundId: Id
    advance: AdvanceContext
    trigger: Literal["player", "automatic"]
    order: Ids
    cursor: Count
    actedIds: IdSet
    visitedIds: IdSet
    phase: DurablePhase
    resumePhase: ResumePhase | None
    pendingGroup: PendingGroup | None
    conclusion: RoundConclusion | None

    @model_validator(mode="after")
    def combinations(self):
        waiting = self.phase in ("await_narration", "paused")
        if waiting != (self.resumePhase is not None):
            raise ValueError("invalid resume phase")
        if self.cursor > len(self.order) or set(self.visitedIds) != set(self.order[:self.cursor]):
            raise ValueError("visited slots must match cursor prefix")
        if not set(self.actedIds) <= set(self.order):
            raise ValueError("actor outside frozen order")
        if self.trigger == "automatic" and self.advance.intentStatus != "consumed":
            raise ValueError("automatic round cannot consume input again")
        if (self.phase == "complete") != (self.conclusion is not None):
            raise ValueError("complete needs exactly one conclusion")
        effective = self.resumePhase if waiting else self.phase
        if effective in ("build_group", "settle_group") and self.pendingGroup is None:
            raise ValueError("group phase needs pending group")
        if effective == "settle_group" and not self.pendingGroup.closed:
            raise ValueError("settlement requires closed group")
        if self.pendingGroup and not set(self.pendingGroup.memberIds) <= set(self.order):
            raise ValueError("group member outside frozen order")
        if effective in ("assess_continuation", "complete") and self.pendingGroup:
            raise ValueError("terminal phase still has a group")
        cancelled = isinstance(self.conclusion, CancelHandback)
        if effective == "assess_continuation" or (self.phase == "complete" and not cancelled):
            if self.cursor != len(self.order):
                raise ValueError("round still has unvisited slots")
        if isinstance(self.conclusion, ContinueConclusion) and self.conclusion.nextRoundId == self.roundId:
            raise ValueError("cannot continue to the same round")
        return self


class RootPoint(Contract):
    worldId: Id
    id: Id
    sequence: Annotated[Literal[0], BeforeValidator(_integer)]
    kind: Literal["root"]
    previousPointId: None
    roundId: None
    advanceId: None
    trigger: None
    linkedFromPointId: None
    timeAdvance: None
    entityDeltas: None


class TimelinePoint(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"kind": {"const": "normal"}}},
         "then": {"properties": {"linkedFromPointId": {"type": "null"},
                                    "timeAdvance": {"properties": {"boundary": {"const": "elapsed"}}}}},
         "else": {"properties": {"linkedFromPointId": {"type": "string"},
                                    "timeAdvance": {"properties": {"boundary": {"const": "instant"}}}}}},
        {"if": {"properties": {"kind": {"const": "instant"}}},
         "then": {"properties": {"timeAdvance": {"properties": {"duration": {"properties": {"amount": {"const": 0}}}}}}}},
    ]})
    worldId: Id
    id: Id
    sequence: Positive
    kind: Literal["normal", "instant", "linked"]
    previousPointId: Id
    roundId: Id
    advanceId: Id
    trigger: Literal["player", "automatic"]
    linkedFromPointId: Id | None
    timeAdvance: TimeAdvance
    entityDeltas: dict[Id, EntityDelta]

    @model_validator(mode="after")
    def shape(self):
        if self.id == self.previousPointId:
            raise ValueError("point cannot precede itself")
        if self.kind == "normal":
            if self.linkedFromPointId is not None or self.timeAdvance.boundary != "elapsed":
                raise ValueError("normal point must start a round")
        elif self.linkedFromPointId != self.previousPointId or self.timeAdvance.boundary != "instant":
            raise ValueError("associated point needs instant predecessor boundary")
        if self.kind == "instant" and self.timeAdvance.duration.amount != 0:
            raise ValueError("instant settlement duration must be zero")
        for key, delta in self.entityDeltas.items():
            if key != delta.entityId:
                raise ValueError("delta key differs from entity ID")
        return self


class ClaimBase(Contract):
    worldId: Id
    pointId: Id
    advanceId: Id | None
    generation: Positive
    claimToken: Id
    expiresAt: Positive


class HeadNarrationClaim(ClaimBase):
    mode: Literal["head"]
    fenceEpoch: Positive


class HistoryNarrationClaim(ClaimBase):
    mode: Literal["history"]
    fenceEpoch: None


class RoundConclusionRequest(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={
        "if": {"properties": {"operation": {"const": "cancel"}}},
        "then": {"properties": {"conclusion": {"properties": {"closedBy": {"const": "cancel"}}}}},
        "else": {"properties": {"conclusion": {"properties": {"closedBy": {"const": "model"}}}}},
    })
    worldId: Id
    advanceId: Id
    roundId: Id
    expectedPointId: Id
    expectedVersion: Count
    requestId: Id
    expectedCheckpointRevision: Count
    leaseToken: Id
    fenceEpoch: Positive
    operation: Literal["conclude", "cancel"]
    conclusion: RoundConclusion

    @model_validator(mode="after")
    def source(self):
        if (self.operation == "cancel") != isinstance(self.conclusion, CancelHandback):
            raise ValueError("conclusion source does not match operation")
        return self


class PendingTask(Task):
    status: Literal["pending"]


class SettlementCandidates(Contract):
    """Six ordered state stages; no natural-language action history."""

    scopeId: Id
    actorIds: Ids
    pureTime: bool
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
        if self.pureTime:
            if self.actorIds or self.positions or self.appearances:
                raise ValueError("pure-time unit cannot invent movement or appearance")
        elif not self.actorIds:
            raise ValueError("action unit requires actors")
        if set(self.sanities) != set(self.personalities):
            raise ValueError("personality changes and sanity recalculation must pair")
        if self.personalities and not any(self.tasksAchieved.values()):
            raise ValueError("personality stage requires newly achieved tasks")
        for owner, tasks in self.subtasksAdded.items():
            if any(task.ownerId != owner or task.parentTaskId is None for task in tasks):
                raise ValueError("subtasks require matching owner and parent")
        return self


class PointCommitRequest(Contract):
    worldId: Id
    advanceId: Id
    expectedPointId: Id
    expectedVersion: Count
    requestId: Id
    roundId: Id
    expectedCheckpointRevision: Count
    leaseToken: Id
    fenceEpoch: Positive
    point: TimelinePoint
    checkpoint: RoundCheckpoint
    stageCandidates: Annotated[list[SettlementCandidates], Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def bindings(self):
        if (self.point.worldId, self.point.roundId, self.point.advanceId, self.point.previousPointId) != (
            self.worldId, self.roundId, self.advanceId, self.expectedPointId
        ):
            raise ValueError("point binding differs from request")
        if self.checkpoint.roundId != self.roundId or self.checkpoint.advance.advanceId != self.advanceId:
            raise ValueError("checkpoint binding differs from request")
        if self.checkpoint.trigger != self.point.trigger:
            raise ValueError("round trigger differs from point trigger")
        if self.checkpoint.phase != "await_narration":
            raise ValueError("point must enter narration gate")
        _unique([unit.scopeId for unit in self.stageCandidates])
        _unique([actor for unit in self.stageCandidates for actor in unit.actorIds])
        roster = set(self.checkpoint.order)
        for unit in self.stageCandidates:
            if not set(unit.actorIds) <= roster or set(unit.taskCoverageIds) != roster:
                raise ValueError("unit must cover the complete frozen roster")
            expected = roster if any(unit.tasksAchieved.values()) else set()
            if set(unit.personalityCoverageIds) != expected:
                raise ValueError("personality scan must cover all characters after achievement")
        return self


class PreviewRequest(Contract):
    worldId: Id
    advanceId: Id
    roundId: Id
    pointId: Id
    expectedPointId: Id
    expectedVersion: Count
    expectedCheckpointRevision: Count
    timeAdvance: TimeAdvance
    stageCandidates: Annotated[list[SettlementCandidates], Field(min_length=1, max_length=32)]


class RollRequest(Contract):
    worldId: Id
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


CONTRACT_MODELS = (
    WorldInitialState, WorldState, WorldTime, Position, Task, DescriptionChange, EntityDelta,
    AdvanceContext, PendingGroup, ContinueConclusion, ModelHandback, CancelHandback,
    RoundCheckpoint, RootPoint, TimelinePoint, HeadNarrationClaim,
    HistoryNarrationClaim, RoundConclusionRequest, SettlementCandidates,
    PointCommitRequest, PreviewRequest, RollRequest,
)
