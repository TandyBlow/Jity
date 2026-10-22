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
    # Workflow design §6.1: all position changes of one settlement are
    # validated together on the candidate's final position graph, so the
    # result never depends on the delta iteration order.
    new_positions = {entity_id: delta.positionSet
                     for entity_id, delta in point.entityDeltas.items()
                     if delta.positionSet is not None}
    if new_positions:
        _check_positions(state, new_positions)
    for entity_id, delta in point.entityDeltas.items():
        _apply_delta(state, entity_id, delta, point, locations, items, characters)
    return WorldState(
        engineVersion=state.engineVersion, schemaVersion=state.schemaVersion,
        worldId=state.worldId, protagonistId=state.protagonistId,
        time=advance_time(state.time, point.timeAdvance), initial=state.initial,
        locations=locations, items=items, characters=characters)


def _check_positions(state, new_positions):
    """Unified checks over the final position graph: references and slots
    exist, the union of the three edge kinds (location tree, containment,
    relative) stays acyclic, and every relative — including untouched ones
    whose reference moved in this settlement — still shares a room with its
    target. Dangling relations must be updated or cleared in the same
    candidate, never silently kept."""
    known = (set(state.initial.locations) | set(state.initial.items)
             | set(state.initial.characters))

    def final_pos(node):
        if node in new_positions:
            return new_positions[node]
        entity = state.items.get(node) or state.characters.get(node)
        return entity.position if entity else None

    for entity_id, position in new_positions.items():
        if entity_id not in known:
            raise KernelViolation(
                ViolationKind.ID_UNRESOLVED, f'unknown entity {entity_id}')
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
        if position.relativeTo is not None and position.relativeTo.entityId not in known:
            raise KernelViolation(
                ViolationKind.ID_UNRESOLVED,
                f'unknown relative reference {position.relativeTo.entityId}')

    def edges(node):
        out = []
        location = state.initial.locations.get(node)
        if location is not None and location.parentLocationId:
            out.append(location.parentLocationId)
        position = final_pos(node)
        if position is not None:
            out.append(position.containerId)
            if position.relativeTo is not None:
                out.append(position.relativeTo.entityId)
        return out

    def cyclic(start):
        on_path = {start}

        def walk(node):
            for nxt in edges(node):
                if nxt in on_path:
                    return True
                if nxt not in known:
                    continue
                on_path.add(nxt)
                if walk(nxt):
                    return True
                on_path.discard(nxt)
            return False

        return walk(start)

    def room(node):
        seen = set()
        while node not in state.initial.locations:
            if node in seen:
                raise KernelViolation(
                    ViolationKind.SEMANTIC_INVALID, f'position cycle at {node}')
            seen.add(node)
            position = final_pos(node)
            if position is None:
                raise KernelViolation(
                    ViolationKind.ID_UNRESOLVED, f'unknown container {node}')
            node = position.containerId
        return node

    for start in new_positions:
        if cyclic(start):
            raise KernelViolation(
                ViolationKind.SEMANTIC_INVALID, f'position cycle at {start}')
    for node in known:
        position = final_pos(node)
        if position is not None and position.relativeTo is not None:
            if room(node) != room(position.relativeTo.entityId):
                raise KernelViolation(
                    ViolationKind.SEMANTIC_INVALID,
                    f'relative reference {position.relativeTo.entityId} of {node} '
                    'is in a different location')


def _apply_delta(state, entity_id, delta, point, locations, items, characters):
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
