"""Unit-level candidate validation and unit content hashes.

Coverage rules, pinned against every staged group in the traces: task
coverage always lists the world's full character set; personality coverage
stays empty unless the unit achieves tasks, and then lists the whole cast
for the time-scan unit or exactly the group's actors for a named group.
Cross-unit actor uniqueness is the A-side ruling of 2026-10-22: one actor
acts in at most one unit per point, which makes cross-unit position
conflicts unreachable.
"""
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import Id
from app.schemas.world.v2.work import SettlementGroup

from .violations import Violation


def validate_unit(unit: SettlementGroup, world_roster: frozenset[Id]) -> tuple[Violation, ...]:
    violations = []
    if not set(unit.actorIds) <= world_roster:
        violations.append(Violation(
            'roster', f'actors {sorted(set(unit.actorIds) - world_roster)} are not world characters'))
    if set(unit.taskCoverageIds) != world_roster:
        violations.append(Violation(
            'coverage', 'task coverage must list the world\'s full character set'))
    if unit.tasksAchieved:
        expected = (world_roster if unit.groupId is None else set(unit.actorIds))
    else:
        expected = set()
    if set(unit.personalityCoverageIds) != expected:
        violations.append(Violation(
            'coverage', 'personality coverage must stay empty without achieved tasks, '
                        'else list the whole cast for a time-scan unit or the actors of a group'))
    return tuple(violations)


def validate_commit_groups(groups: list[SettlementGroup],
                           world_roster: frozenset[Id]) -> tuple[Violation, ...]:
    violations = []
    seen_groups: set[Id] = set()
    seen_actors: set[Id] = set()
    for unit in groups:
        if unit.groupId is not None:
            if unit.groupId in seen_groups:
                violations.append(Violation('identity', f'duplicate group {unit.groupId}'))
            seen_groups.add(unit.groupId)
        for actor in unit.actorIds:
            if actor in seen_actors:
                violations.append(Violation(
                    'semantic_invalid', f'actor {actor} acts in two units of one point'))
            seen_actors.add(actor)
        violations.extend(validate_unit(unit, world_roster))
    return tuple(violations)


def unit_content_hash(unit: SettlementGroup) -> str:
    """Pinned by 18 staged groups across the traces: the wire contentHash of a
    settled unit is exactly the canonical digest of its candidate set."""
    return canonical_digest(unit.model_dump(mode='json'))
