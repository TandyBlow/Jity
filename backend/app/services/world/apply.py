"""Commit application: advance time and fold merged deltas into the state."""
from app.schemas.world.contracts import (
    CharacterState, EntityDelta, ItemState, LocationState, StoredDescriptionChange,
    TimelinePoint, WorldState,
)

from .timing import advance_time
from .violations import KernelViolation, ViolationKind


def apply_point(state: WorldState, point: TimelinePoint) -> WorldState:
    locations = dict(state.locations)
    items = dict(state.items)
    characters = dict(state.characters)
    new_positions: dict = {}
    for entity_id, delta in point.entityDeltas.items():
        _apply_delta(state, entity_id, delta, point, locations, items,
                     characters, new_positions)
    return WorldState(
        engineVersion=state.engineVersion, schemaVersion=state.schemaVersion,
        worldId=state.worldId, protagonistId=state.protagonistId,
        time=advance_time(state.time, point.timeAdvance), initial=state.initial,
        locations=locations, items=items, characters=characters)


def _apply_delta(state, entity_id, delta, point, locations, items, characters,
                 new_positions):
    if entity_id in locations:
        if (delta.positionSet is not None or delta.personalityChanges
                or delta.sanitySet is not None or delta.tasksAchieved
                or delta.subtasksAdded):
            raise KernelViolation(
                ViolationKind.SEMANTIC_INVALID,
                f'location {entity_id} only accepts appearance changes')
        entity: LocationState | ItemState | CharacterState = locations[entity_id]
        locations[entity_id] = entity.model_copy(update={
            'appearanceChanges': _extend_changes(
                entity.appearanceChanges, delta.appearanceChanges, point, entity_id)})
        return
    entity = items.get(entity_id) or characters.get(entity_id)
    if entity is None:
        raise KernelViolation(ViolationKind.ID_UNRESOLVED, f'unknown entity {entity_id}')
    updates = {'appearanceChanges': _extend_changes(
        entity.appearanceChanges, delta.appearanceChanges, point, entity_id)}
    if delta.positionSet is not None:
        _check_position(state, entity_id, delta.positionSet, new_positions)
        new_positions[entity_id] = delta.positionSet
        updates['position'] = delta.positionSet
    if entity_id in characters:
        updates['personalityChanges'] = _extend_changes(
            entity.personalityChanges, delta.personalityChanges, point, entity_id)
        if delta.sanitySet is not None:
            updates['sanity'] = delta.sanitySet
        updates['tasks'] = _apply_tasks(entity.tasks, delta, entity_id)
    elif (delta.personalityChanges or delta.sanitySet is not None
            or delta.tasksAchieved or delta.subtasksAdded):
        raise KernelViolation(
            ViolationKind.SEMANTIC_INVALID,
            f'item {entity_id} only accepts position and appearance changes')
    if isinstance(entity, CharacterState):
        characters[entity_id] = entity.model_copy(update=updates)
    else:
        items[entity_id] = entity.model_copy(update=updates)


def _check_position(state, entity_id, position, new_positions):
    """Runtime companions of the initial-world reference checks: the container
    exists, the slot belongs to it, and a relative reference stays inside the
    same room (v1 initial rule carried over; cross-room relatives are
    semantically impossible, not malformed bytes)."""
    container_id = position.containerId
    if container_id in state.initial.locations:
        slots = state.initial.locations[container_id].slots
    elif container_id in state.initial.items or container_id in state.initial.characters:
        container = state.initial.items.get(container_id) \
            or state.initial.characters[container_id]
        slots = container.slots
    else:
        raise KernelViolation(
            ViolationKind.ID_UNRESOLVED, f'unknown container {container_id}')
    if position.slotId is not None and position.slotId not in {slot.id for slot in slots}:
        raise KernelViolation(
            ViolationKind.ID_UNRESOLVED,
            f'slot {position.slotId} does not belong to container {container_id}')
    if position.relativeTo is not None:
        target = position.relativeTo.entityId
        if target not in state.initial.locations and target not in state.items \
                and target not in state.characters:
            raise KernelViolation(
                ViolationKind.ID_UNRESOLVED, f'unknown relative reference {target}')
        if _room(state, new_positions, entity_id, position.containerId) != \
                _room(state, new_positions, target, None):
            raise KernelViolation(
                ViolationKind.SEMANTIC_INVALID,
                f'relative reference {target} is in a different location')


def _room(state, new_positions, entity_id, moved_container):
    node = entity_id
    seen = set()
    while node not in state.initial.locations:
        if node in seen:
            raise KernelViolation(
                ViolationKind.SEMANTIC_INVALID, f'position cycle at {node}')
        seen.add(node)
        override = new_positions.get(node)
        if node == entity_id and moved_container is not None:
            node = moved_container
        elif override is not None:
            node = override.containerId
        elif node in state.items:
            node = state.items[node].position.containerId
        elif node in state.characters:
            node = state.characters[node].position.containerId
        elif node in state.initial.items:
            node = state.initial.items[node].initialPosition.containerId
        elif node in state.initial.characters:
            node = state.initial.characters[node].initialPosition.containerId
        else:
            raise KernelViolation(
                ViolationKind.ID_UNRESOLVED, f'unknown container {node}')
    return node


def _extend_changes(existing, changes, point, entity_id):
    stored = [*existing]
    active = {change.id: index for index, change in enumerate(stored) if change.active}
    for change in changes:
        for target in change.supersedes:
            index = active.get(target)
            if index is None:
                raise KernelViolation(
                    ViolationKind.ID_UNRESOLVED,
                    f'{entity_id} has no active change {target} to supersede')
            stored[index] = stored[index].model_copy(update={'active': False})
        stored.append(StoredDescriptionChange(
            id=change.id, text=change.text, supersedes=change.supersedes,
            sourcePointId=point.id, sourceSequence=point.sequence, active=True))
        active[change.id] = len(stored) - 1
    return stored


def _apply_tasks(tasks, delta: EntityDelta, entity_id):
    merged = dict(tasks)
    for task_id in delta.tasksAchieved:
        task = merged.get(task_id)
        if task is None:
            raise KernelViolation(
                ViolationKind.ID_UNRESOLVED, f'{entity_id} has no task {task_id}')
        if task.status != 'pending':
            raise KernelViolation(
                ViolationKind.SEMANTIC_INVALID, f'task {task_id} is already achieved')
        merged[task_id] = task.model_copy(update={'status': 'achieved'})
    added_ids = {task.id for task in delta.subtasksAdded}
    for task in delta.subtasksAdded:
        if task.parentTaskId not in merged and task.parentTaskId not in added_ids:
            raise KernelViolation(
                ViolationKind.ID_UNRESOLVED,
                f'new task {task.id} has unknown parent {task.parentTaskId}')
        merged[task.id] = task
    return merged
