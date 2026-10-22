"""Unit-level candidate validation and unit content hashes.

Coverage rules (2026-10-22 ruling per the workflow design §6.3): task
coverage always lists the world's full character set; personality coverage
stays empty unless the unit achieves tasks, and then lists the whole cast —
named groups exactly like the time-scan unit, never only the members.
Cross-unit actor uniqueness is the A-side ruling of 2026-10-22: one actor
acts in at most one unit per point, which makes cross-unit position
conflicts unreachable.
"""
from app.schemas.world.canonical import canonical_digest
from app.schemas.world.contracts import Id
from app.schemas.world.v2.contexts import WorkingProgress
from app.schemas.world.v2.work import SettlementGroup

from .violations import Violation


def validate_unit(unit: SettlementGroup, world_roster: frozenset[Id]) -> tuple[Violation, ...]:
    violations = []
    if not set(unit.actorIds) <= world_roster:
        violations.append(Violation(
            'roster', f'actors {sorted(set(unit.actorIds) - world_roster)} are not world characters'))
    character_only = (set(unit.tasksAchieved) | set(unit.personalities)
                      | set(unit.sanities) | set(unit.subtasksAdded))
    if not character_only <= world_roster:
        violations.append(Violation(
            'roster', f'character keys {sorted(character_only - world_roster)} are not world characters'))
    if set(unit.taskCoverageIds) != world_roster:
        violations.append(Violation(
            'coverage', 'task coverage must list the world\'s full character set'))
    if unit.tasksAchieved:
        # Ruling of 2026-10-22, per the workflow design §6.3: an achieved task
        # may affect any character, so the personality/sanity scan covers the
        # whole cast for named groups exactly as it does for the time-scan
        # unit. The T03-collapse fixture (coverage=actors) is a known-deviant
        # artifact; validation refuses it and the replay tests do not run
        # validation, so only real traffic sees the refusal.
        expected = world_roster
    else:
        expected = set()
    if set(unit.personalityCoverageIds) != expected:
        violations.append(Violation(
            'coverage', 'personality coverage must stay empty without achieved tasks, '
                        'else list the world\'s full character set'))
    if not set(unit.personalities) <= set(unit.personalityCoverageIds):
        violations.append(Violation(
            'coverage', f'personality changes {sorted(set(unit.personalities) - set(unit.personalityCoverageIds))} '
                        'fall outside the declared scan coverage'))
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


def begin_working(committed: tuple[int, list[Id], list[Id]],
                  intent_status: str) -> WorkingProgress:
    """A new point starts from the round's committed progress (cursor,
    actedIds, visitedIds live in the head): only settledUnitIds are
    point-scoped and start empty. intentStatus projects the advance's
    current value."""
    cursor, acted, visited = committed
    return WorkingProgress(cursor=cursor, actedIds=acted, visitedIds=visited,
                           settledUnitIds=[], intentStatus=intent_status)


def stage_working(working: WorkingProgress, unit_id: Id,
                  actors: list[Id]) -> WorkingProgress:
    """One staged settlement: every actor fills its slot, the unit id joins
    the staged set and the input intent is consumed."""
    return WorkingProgress(
        cursor=working.cursor + len(actors),
        actedIds=working.actedIds + list(actors),
        visitedIds=working.visitedIds + list(actors),
        settledUnitIds=working.settledUnitIds + [unit_id],
        intentStatus='consumed')


def skip_working(working: WorkingProgress, slot_actor: Id) -> WorkingProgress:
    """A recorded skip advances the cursor and the visited set, never actedIds."""
    return WorkingProgress(
        cursor=working.cursor + 1,
        actedIds=working.actedIds,
        visitedIds=working.visitedIds + [slot_actor],
        settledUnitIds=working.settledUnitIds,
        intentStatus=working.intentStatus)


def scan_working(working: WorkingProgress, order: list[Id]) -> WorkingProgress:
    """The time-scan unit settles without actors: it closes every remaining
    slot at once and never consumes the input intent (T03 keeps pending)."""
    return WorkingProgress(
        cursor=len(order),
        actedIds=working.actedIds,
        visitedIds=list(order),
        settledUnitIds=working.settledUnitIds,
        intentStatus=working.intentStatus)
