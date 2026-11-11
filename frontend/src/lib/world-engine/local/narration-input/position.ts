/** Entity lookup and position resolution shared by the projection and the
 * serializers. Visibility ends at the innermost location; slots are only
 * details inside a container and never split a visible scene. */
import type { Id, InitialState, Position, WorldState } from '../../types';
import { NarrationInputError } from './types';

export type EntityKind = 'character' | 'location' | 'item';

export function entityKind(initial: InitialState, entityId: Id): EntityKind {
  const isCharacter = Boolean(initial.characters[entityId]);
  const isLocation = Boolean(initial.locations[entityId]);
  const isItem = Boolean(initial.items[entityId]);
  const count = Number(isCharacter) + Number(isLocation) + Number(isItem);
  if (count === 0) throw new NarrationInputError('unknown_entity', `unknown entity ${entityId}`, { entityId });
  if (count > 1) throw new NarrationInputError('ambiguous_entity', `entity ${entityId} exists in more than one registry`, { entityId });
  if (isCharacter) return 'character';
  if (isLocation) return 'location';
  return 'item';
}

export function entityName(initial: InitialState, entityId: Id): string {
  const kind = entityKind(initial, entityId);
  if (kind === 'character') return initial.characters[entityId].name;
  if (kind === 'location') return initial.locations[entityId].name;
  return initial.items[entityId].name;
}

export function knownEntityIds(initial: InitialState): Id[] {
  return [
    ...Object.keys(initial.characters),
    ...Object.keys(initial.locations),
    ...Object.keys(initial.items),
  ];
}

function positionOf(state: WorldState, entityId: Id): Position | null {
  return state.characters[entityId]?.position ?? state.items[entityId]?.position ?? null;
}

export function containerIdOf(state: WorldState, entityId: Id): Id {
  const position = positionOf(state, entityId);
  if (!position) {
    throw new NarrationInputError('unknown_container', `entity ${entityId} has no position`, { entityId });
  }
  return position.containerId;
}

/** Follow the container chain until a location. A location is its own room.
 * Throws on missing containers and on cycles instead of returning a partial
 * answer; a partial room would silently change the visible set. */
export function innermostLocationId(state: WorldState, entityId: Id): Id {
  if (state.initial.locations[entityId]) return entityId;
  const seen = new Set<Id>([entityId]);
  let node = entityId;
  for (;;) {
    const next = containerIdOf(state, node);
    if (seen.has(next)) {
      throw new NarrationInputError('position_cycle', `position cycle at ${next}`, { entityId, cycleAt: next });
    }
    seen.add(next);
    if (state.initial.locations[next]) return next;
    node = next;
  }
}

function slotLabel(initial: InitialState, containerId: Id, slotId: Id): string {
  const slots = initial.locations[containerId]?.slots
    ?? initial.items[containerId]?.slots
    ?? initial.characters[containerId]?.slots
    ?? [];
  const slot = slots.find((entry) => entry.id === slotId);
  if (!slot) {
    throw new NarrationInputError('unknown_container', `slot ${slotId} does not belong to ${containerId}`, {
      containerId,
      slotId,
    });
  }
  return slot.label;
}

/** A model-facing position string. The innermost location is always present,
 * so a reader can place the entity. A slot is written as its label, never as
 * a raw slot id. A container that is not a location keeps its own name and
 * the enclosing location, e.g. 路明非的身上（在西侧服务巷里）. */
export function positionText(state: WorldState, entityId: Id): string {
  const kind = entityKind(state.initial, entityId);
  if (kind === 'location') {
    throw new NarrationInputError('field_not_allowed', `location ${entityId} has no position text`, { entityId });
  }
  const position = positionOf(state, entityId);
  if (!position) {
    throw new NarrationInputError('unknown_container', `entity ${entityId} has no position`, { entityId });
  }
  const container = position.containerId;
  const containerKind = entityKind(state.initial, container);
  const label = position.slotId ? slotLabel(state.initial, container, position.slotId) : null;
  if (containerKind === 'location') {
    const name = state.initial.locations[container].name;
    return label ? `${name}（${label}）` : name;
  }
  const room = innermostLocationId(state, entityId);
  const roomName = state.initial.locations[room].name;
  const containerName = entityName(state.initial, container);
  const head = label ? `${containerName}的${label}` : containerName;
  return `${head}（在${roomName}里）`;
}

/** Locations use `位于` in the data format: the parent location, or null at
 * the root. */
export function parentLocationName(state: WorldState, locationId: Id): string | null {
  const parent = state.initial.locations[locationId]?.parentLocationId ?? null;
  return parent ? state.initial.locations[parent]?.name ?? parent : null;
}

export function ancestorLocationIds(state: WorldState, locationId: Id): Id[] {
  const ancestors: Id[] = [];
  const seen = new Set<Id>([locationId]);
  let node = state.initial.locations[locationId]?.parentLocationId ?? null;
  while (node) {
    if (seen.has(node)) {
      throw new NarrationInputError('position_cycle', `location parent cycle at ${node}`, { locationId, cycleAt: node });
    }
    seen.add(node);
    ancestors.push(node);
    node = state.initial.locations[node]?.parentLocationId ?? null;
  }
  return ancestors;
}
