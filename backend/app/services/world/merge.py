"""The three merge paths of a committed point: action groups in outer order,
the saved time-scan unit, and same-point collapse.

Invariant over every successful commit:
``point.entityDeltas == collapse(merge(groups ∪ timeScan))`` — the saved
``stage_time_scan`` candidates must join the merge even though the commit
request carries named action groups only.
"""
from app.schemas.world.contracts import EntityDelta, Id, Task
from app.schemas.world.v2.work import SettlementGroup

from .violations import KernelViolation, ViolationKind


def collapse_tasks(added: list[Task], achieved: set[Id]) -> tuple[list[Task], list[Id]]:
    """Both steps together: drop newly-added-and-achieved ids from ``achieved``
    and mark those records achieved; either step alone breaks T03-collapse."""
    collapsed = sorted(achieved - {task.id for task in added})
    merged = [task.model_copy(update={'status': 'achieved'})
              if task.id in achieved else task for task in added]
    return merged, collapsed


def point_entity_deltas(groups: list[SettlementGroup],
                        time_scan: SettlementGroup | None) -> dict[Id, EntityDelta]:
    units = [*groups] + ([time_scan] if time_scan is not None else [])
    entity_ids: list[Id] = []
    for unit in units:
        for field in (unit.positions, unit.appearances, unit.tasksAchieved,
                      unit.subtasksAdded, unit.personalities, unit.sanities):
            entity_ids.extend(key for key in field if key not in entity_ids)
    deltas: dict[Id, EntityDelta] = {}
    for entity_id in entity_ids:
        position = None
        sanity = None
        appearances: list = []
        personalities: list = []
        achieved: set[Id] = set()
        added: list[Task] = []
        for unit in units:
            if entity_id in unit.positions:
                if position is not None and position != unit.positions[entity_id]:
                    raise KernelViolation(
                        ViolationKind.POSITION_INVALID,
                        f'{entity_id} receives conflicting positions in one point')
                position = unit.positions[entity_id]
            appearances.extend(unit.appearances.get(entity_id, ()))
            personalities.extend(unit.personalities.get(entity_id, ()))
            if entity_id in unit.sanities:
                if sanity is not None and sanity != unit.sanities[entity_id]:
                    raise KernelViolation(
                        ViolationKind.SEMANTIC_INVALID,
                        f'{entity_id} receives conflicting sanity values in one point')
                sanity = unit.sanities[entity_id]
            achieved.update(unit.tasksAchieved.get(entity_id, ()))
            added.extend(unit.subtasksAdded.get(entity_id, ()))
        merged_tasks, merged_achieved = collapse_tasks(added, achieved)
        deltas[entity_id] = EntityDelta(
            entityId=entity_id, positionSet=position,
            appearanceChanges=appearances, personalityChanges=personalities,
            sanitySet=sanity, tasksAchieved=merged_achieved, subtasksAdded=merged_tasks)
    return deltas
