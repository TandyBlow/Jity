"""Saved candidates and accepted frozen work shared by reads and writes."""
from typing import Annotated, Literal
from pydantic import ConfigDict, Field, model_validator
from app.schemas.world.contracts import (
    Contract, Id, Ids, IdSet, Positive, Text, Position, DescriptionChange,
    PendingTask, Sanity,
)
from .base import Hex64
from .judgments import RollOutcome


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


class PendingRollThreat(Contract):
    sourceId: Id
    targetId: Id
    triggerKey: Id
    status: Literal["pending_roll"]
    rollId: None
    reactionMemberId: None


class ReactionPendingThreat(Contract):
    sourceId: Id
    targetId: Id
    triggerKey: Id
    status: Literal["reaction_pending"]
    rollId: Id
    reactionMemberId: None


class HandledThreat(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"actionDisposition": {"const": "none"}}},
         "then": {"properties": {"reactionMemberId": {"type": "null"}}},
         "else": {"properties": {"reactionMemberId": {"type": "string"}}}},
    ]})

    sourceId: Id
    targetId: Id
    triggerKey: Id
    status: Literal["handled"]
    rollId: Id
    actionDisposition: Literal["none", "created", "reused"]
    reactionMemberId: Id | None

    @model_validator(mode="after")
    def disposition(self):
        if (self.actionDisposition == "none") != (self.reactionMemberId is None):
            raise ValueError("reaction identity differs from handled action disposition")
        return self


ThreatProgress = Annotated[
    PendingRollThreat | ReactionPendingThreat | HandledThreat,
    Field(discriminator="status"),
]


def _threat_key(item):
    return item.sourceId, item.targetId, item.triggerKey


class GroupProgress(Contract):
    """Persisted DFS checkpoint; sourceStack order is significant."""

    sourceStack: list[Id] = Field(json_schema_extra={"uniqueItems": True})
    threats: list[ThreatProgress]

    @model_validator(mode="after")
    def ordered_unique(self):
        if len(self.sourceStack) != len(set(self.sourceStack)):
            raise ValueError("duplicate source stack frame")
        keys = [_threat_key(item) for item in self.threats]
        if keys != sorted(set(keys)):
            raise ValueError("threat progress must have unique ASCII-sorted keys")
        return self


class FrozenGroupView(Contract):
    groupId: Id
    pointId: Id
    inputProjectionHash: Hex64
    members: list[FrozenMemberView] = Field(min_length=1)
    acceptedSources: list[AcceptedWorkSource]
    candidates: SettlementGroup | None
    rolls: list[RollOutcome]
    progress: GroupProgress

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
                if member.actionText is None:
                    raise ValueError("accepted action text is missing")
                if (source.targetsContentHash is None) != (member.targets is None):
                    raise ValueError("target completion differs from accepted source")
                if (source.resultContentHash is None) != (member.resultText is None):
                    raise ValueError("result completion differs from accepted source")
                if (source.candidatesContentHash is None) != (self.candidates is None):
                    raise ValueError("candidate completion differs from accepted source")
            elif member.targets is not None or member.resultText is not None or member.rollRefs:
                raise ValueError("unconfirmed action cannot carry accepted contributions")
        self._recovery_facts(sources)
        return self

    def _recovery_facts(self, sources):
        members = {member.memberId: member for member in self.members}
        target_keys = []
        for member in self.members:
            for target in member.targets or []:
                target_keys.append((member.memberId, target.targetId, target.triggerKey))
        if len(target_keys) != len(set(target_keys)):
            raise ValueError("duplicate confirmed threat key")
        threats = {_threat_key(item): item for item in self.progress.threats}
        if set(threats) != set(target_keys):
            raise ValueError("threat progress differs from confirmed targets")
        roll_keys = [_threat_key(roll) for roll in self.rolls]
        if roll_keys != sorted(set(roll_keys)):
            raise ValueError("rolls must have unique ASCII-sorted keys")
        if len({roll.rollId for roll in self.rolls}) != len(self.rolls):
            raise ValueError("duplicate final roll identity")
        if any(roll.groupId != self.groupId for roll in self.rolls):
            raise ValueError("final roll belongs to another group")
        rolls = {_threat_key(roll): roll for roll in self.rolls}
        created = {}
        for key, threat in threats.items():
            roll = rolls.get(key)
            if threat.status == "pending_roll":
                if roll is not None:
                    raise ValueError("pending threat already has a final roll")
                continue
            if roll is None or threat.rollId != roll.rollId:
                raise ValueError("threat does not reference its final roll")
            if threat.status == "reaction_pending":
                if not roll.admitted or threat.targetId in sources:
                    raise ValueError("pending reaction must be admitted and unaccepted")
                continue
            if threat.actionDisposition == "none":
                if roll.admitted:
                    raise ValueError("admitted threat cannot be handled without an action")
                continue
            if (not roll.admitted or threat.reactionMemberId != threat.targetId
                    or threat.targetId not in sources):
                raise ValueError("handled reaction lacks an accepted target action")
            if threat.actionDisposition == "created":
                if threat.targetId in created:
                    raise ValueError("member has multiple created acceptance edges")
                created[threat.targetId] = threat.sourceId
        if set(rolls) != {key for key, item in threats.items() if item.status != "pending_roll"}:
            raise ValueError("final roll has no unique threat progress reference")
        pending_reactions = {item.targetId for item in self.progress.threats
                             if item.status == "reaction_pending"}
        if any(member.memberId not in pending_reactions for member in self.members
               if member.actionText is None):
            raise ValueError("unconfirmed member placeholder has no pending admitted causal relation")
        for member in self.members:
            refs = [(ref.sourceId, ref.targetId, ref.triggerKey, ref.rollId) for ref in member.rollRefs]
            expected = [(*_threat_key(roll), roll.rollId) for roll in self.rolls
                        if roll.sourceId == member.memberId]
            if len(refs) != len(set(refs)) or set(refs) != set(expected):
                raise ValueError("member rollRefs differ from all outgoing final rolls")
        # Every confirmed member except the initiator is accepted by exactly
        # one created edge. Reused edges may point back to ancestors.
        roots = set(sources) - set(created)
        if len(roots) != 1:
            raise ValueError("accepted actions require one created-tree initiator")
        root = next(iter(roots))
        for target in created:
            seen, current = set(), target
            while current in created:
                if current in seen:
                    raise ValueError("created acceptance edges contain a cycle")
                seen.add(current)
                current = created[current]
            if current != root:
                raise ValueError("created acceptance edge is outside the initiator tree")
        stack = self.progress.sourceStack
        if any(member_id not in sources for member_id in stack):
            raise ValueError("source stack contains an unaccepted action")
        unfinished = {
            member.memberId for member in self.members if member.memberId in sources and (
                member.targets is None or any(item.sourceId == member.memberId and item.status != "handled"
                                              for item in self.progress.threats))
        }
        if not unfinished <= set(stack):
            raise ValueError("source stack skips unfinished sources")
        if stack:
            if stack[-1] != root or stack[0] not in unfinished:
                raise ValueError("source stack must end at initiator and begin with unfinished source")
            if any(created.get(child) != parent for child, parent in zip(stack, stack[1:])):
                raise ValueError("adjacent source stack frames lack created acceptance edges")
        if self.candidates is not None and stack:
            raise ValueError("saved candidates require fully handled group progress")

    def initiator_id(self):
        created = {item.targetId for item in self.progress.threats
                   if item.status == "handled" and item.actionDisposition == "created"}
        return next(source.memberId for source in self.acceptedSources if source.memberId not in created)

    def frontier_ids(self):
        members = {member.memberId: member for member in self.members}
        return sorted(source_id for source_id in self.progress.sourceStack
                      if members[source_id].targets is None or any(
                          item.sourceId == source_id and item.status != "handled"
                          for item in self.progress.threats))
