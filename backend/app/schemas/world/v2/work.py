"""Saved candidates and accepted frozen work shared by reads and writes."""
from typing import Annotated
from pydantic import ConfigDict, Field, model_validator
from app.schemas.world.contracts import (
    Contract, Id, Ids, IdSet, Positive, Text, Position, DescriptionChange,
    PendingTask, Sanity,
)
from .base import Hex64


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


class TargetSpec(Contract):
    targetId: Id
    triggerKey: Id


class RollRef(Contract):
    sourceId: Id
    targetId: Id
    triggerKey: Id
    rollId: Id



class WorkManifestItem(Contract):
    memberId: Id
    actionContentHash: Hex64
    targetsContentHash: Hex64 | None
    resultContentHash: Hex64 | None
    candidatesContentHash: Hex64 | None


class GroupWorkSource(Contract):
    """Active accepted reference readable before copying any old-epoch payload.

    This is authority metadata, not a visibility grant for the referenced bytes.
    Missing/corrupt rows retain their reference and must fail restore explicitly.
    """

    pointId: Id
    groupId: Id
    sourceEpoch: Positive
    sourceAttempt: Positive
    manifest: list[WorkManifestItem] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_members(self):
        members = [item.memberId for item in self.manifest]
        if len(members) != len(set(members)):
            raise ValueError("duplicate member in accepted source manifest")
        return self



class AcceptedWorkSource(Contract):
    memberId: Id
    sourceEpoch: Positive
    sourceAttempt: Positive
    actionContentHash: Hex64
    targetsContentHash: Hex64 | None
    resultContentHash: Hex64 | None
    candidatesContentHash: Hex64 | None


class FrozenMemberView(Contract):
    memberId: Id
    actionText: Text | None
    targets: list[TargetSpec] | None
    resultText: Text | None
    rollRefs: list[RollRef]


class FrozenGroupView(Contract):
    groupId: Id
    pointId: Id
    inputProjectionHash: Hex64
    members: list[FrozenMemberView] = Field(min_length=1)
    acceptedSources: list[AcceptedWorkSource]
    candidates: SettlementGroup | None

    @model_validator(mode="after")
    def identities(self):
        ids = [member.memberId for member in self.members]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate frozen member")
        if any(source.memberId not in ids for source in self.acceptedSources):
            raise ValueError("accepted source outside frozen group")
        if self.candidates is not None and self.candidates.groupId != self.groupId:
            raise ValueError("frozen candidates name another group")
        source_ids = [source.memberId for source in self.acceptedSources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate accepted member source")
        sources = {source.memberId: source for source in self.acceptedSources}
        for member in self.members:
            source = sources.get(member.memberId)
            if member.actionText is not None and source is None:
                raise ValueError("confirmed action has no accepted source")
            if source is not None:
                if (source.targetsContentHash is None) != (member.targets is None):
                    raise ValueError("target completion differs from accepted source")
                if (source.resultContentHash is None) != (member.resultText is None):
                    raise ValueError("result completion differs from accepted source")
                if (source.candidatesContentHash is None) != (self.candidates is None):
                    raise ValueError("candidate completion differs from accepted source")
        return self
