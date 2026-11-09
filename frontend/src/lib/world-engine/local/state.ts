/** Browser port of the Python state kernel: S0 construction, point application,
 * same-point merge and world-canonical digests. This module is the only place
 * a browser world state is mutated; the local transport calls it inside its
 * own transaction copy and never edits committed points. */
import { canonicalDigest } from './canonical';
import type {
  Change, EntityDelta, Id, InitialState, Position, SettlementGroup, StoredChange, Task,
  TimeAdvance, TimelinePoint, WorldState,
} from '../types';

export class KernelViolation extends Error {
  readonly name = 'KernelViolation';
  constructor(readonly kind: 'semantic_invalid' | 'id_unresolved' | 'prefix_binding' | 'position_invalid', detail: string) {
    super(`${kind}: ${detail}`);
  }
}

export function clone<T>(value: T): T {
  return structuredClone(value);
}

export function buildInitialState(initial: InitialState): WorldState {
  const worldId = initial.worldId;
  return {
    engineVersion: initial.engineVersion,
    schemaVersion: initial.schemaVersion,
    worldId,
    protagonistId: initial.protagonistId,
    time: clone(initial.initialTime),
    initial: clone(initial),
    locations: Object.fromEntries(Object.keys(initial.locations).map((key) => [key, { id: key, appearanceChanges: [] }])),
    items: Object.fromEntries(Object.entries(initial.items).map(([key, entity]) => [key, { id: key, position: clone(entity.initialPosition), appearanceChanges: [] }])),
    characters: Object.fromEntries(Object.entries(initial.characters).map(([key, entity]) => [key, {
      id: key,
      position: clone(entity.initialPosition),
      appearanceChanges: [],
      personalityChanges: [],
      sanity: entity.initialSanity,
      tasks: Object.fromEntries(Object.entries(entity.tasks).map(([taskId, task]) => [taskId, clone(task)])),
    }])),
  };
}

export async function stateDigest(state: WorldState): Promise<string> {
  return canonicalDigest(state);
}

const SECONDS: Record<string, number> = { second: 1, minute: 60, hour: 3600, day: 86400 };

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

function formatTime(date: Date): string {
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`;
}

function parseTime(value: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new KernelViolation('semantic_invalid', `invalid dateTime ${value}`);
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5]), Number(match[6])));
}

export function advanceTime(at: WorldState['time'], advance: TimeAdvance): WorldState['time'] {
  if (advance.duration.amount === 0) return { ...at, instantOrdinal: at.instantOrdinal + 1 };
  const moment = parseTime(at.dateTime);
  const unit = advance.duration.unit;
  if (unit === 'month' || unit === 'year') {
    const months = advance.duration.amount * (unit === 'year' ? 12 : 1);
    const index = moment.getUTCMonth() + months;
    const year = moment.getUTCFullYear() + Math.floor(index / 12);
    const month = ((index % 12) + 12) % 12;
    const day = Math.min(moment.getUTCDate(), new Date(Date.UTC(year, month + 1, 0)).getUTCDate());
    return { ...at, dateTime: formatTime(new Date(Date.UTC(year, month, day, moment.getUTCHours(), moment.getUTCMinutes(), moment.getUTCSeconds()))), instantOrdinal: 0 };
  }
  const next = new Date(moment.getTime() + advance.duration.amount * (SECONDS[unit] ?? 0) * 1000);
  return { ...at, dateTime: formatTime(next), instantOrdinal: 0 };
}

function knownEntities(state: WorldState): Set<Id> {
  return new Set([...Object.keys(state.initial.locations), ...Object.keys(state.initial.items), ...Object.keys(state.initial.characters)]);
}

function slotsOf(state: WorldState, containerId: Id): { id: Id; label: string }[] | null {
  if (state.initial.locations[containerId]) return state.initial.locations[containerId].slots ?? [];
  if (state.initial.items[containerId]) return state.initial.items[containerId].slots ?? [];
  if (state.initial.characters[containerId]) return state.initial.characters[containerId].slots ?? [];
  return null;
}

function finalPosition(state: WorldState, node: Id, newPositions: Record<Id, Position>): Position | null {
  if (newPositions[node]) return newPositions[node];
  const entity = state.items[node] ?? state.characters[node];
  return entity ? entity.position : null;
}

/** Port of `_check_positions`: final-graph references, slot ownership, joint
 * acyclicity and relative-room consistency. */
function checkPositions(state: WorldState, newPositions: Record<Id, Position>): void {
  const known = knownEntities(state);
  for (const [entityId, position] of Object.entries(newPositions)) {
    if (!known.has(entityId)) throw new KernelViolation('id_unresolved', `unknown entity ${entityId}`);
    const slots = slotsOf(state, position.containerId);
    if (!slots) throw new KernelViolation('id_unresolved', `unknown container ${position.containerId}`);
    if (position.slotId != null && !slots.some((slot) => slot.id === position.slotId)) {
      throw new KernelViolation('id_unresolved', `slot ${position.slotId} does not belong to container ${position.containerId}`);
    }
    if (position.relativeTo != null && !known.has(position.relativeTo.entityId)) {
      throw new KernelViolation('id_unresolved', `unknown relative reference ${position.relativeTo.entityId}`);
    }
  }
  const edges = (node: Id): Id[] => {
    const out: Id[] = [];
    const location = state.initial.locations[node];
    if (location?.parentLocationId) out.push(location.parentLocationId);
    const position = finalPosition(state, node, newPositions);
    if (position) {
      out.push(position.containerId);
      if (position.relativeTo) out.push(position.relativeTo.entityId);
    }
    return out;
  };
  const onPath = new Set<Id>();
  const finished = new Set<Id>();
  const walk = (node: Id): boolean => {
    onPath.add(node);
    try {
      for (const next of edges(node)) {
        if (onPath.has(next)) return true;
        if (finished.has(next) || !known.has(next)) continue;
        if (walk(next)) return true;
      }
    } finally {
      onPath.delete(node);
      finished.add(node);
    }
    return false;
  };
  for (const start of Object.keys(newPositions)) {
    if (!finished.has(start) && walk(start)) throw new KernelViolation('semantic_invalid', `position cycle at ${start}`);
  }
  const room = (node: Id): Id => {
    const seen = new Set<Id>();
    while (!state.initial.locations[node]) {
      if (seen.has(node)) throw new KernelViolation('semantic_invalid', `position cycle at ${node}`);
      seen.add(node);
      const position = finalPosition(state, node, newPositions);
      if (!position) throw new KernelViolation('id_unresolved', `unknown container ${node}`);
      node = position.containerId;
    }
    return node;
  };
  for (const node of known) {
    const position = finalPosition(state, node, newPositions);
    if (position?.relativeTo && room(node) !== room(position.relativeTo.entityId)) {
      throw new KernelViolation('semantic_invalid', `relative reference ${position.relativeTo.entityId} of ${node} is in a different location`);
    }
  }
}

function extendChanges(existing: StoredChange[], changes: Change[] | undefined, point: TimelinePoint, entityId: Id): StoredChange[] {
  const stored = clone(existing);
  const active = new Map<Id, number>();
  stored.forEach((change, index) => { if (change.active) active.set(change.id, index); });
  for (const change of changes ?? []) {
    for (const target of change.supersedes ?? []) {
      const index = active.get(target);
      if (index == null) throw new KernelViolation('id_unresolved', `${entityId} has no active change ${target} to supersede`);
      stored[index] = { ...stored[index], active: false };
    }
    stored.push({ id: change.id, text: change.text ?? null, supersedes: [...(change.supersedes ?? [])], sourcePointId: point.id, sourceSequence: point.sequence, active: true });
    active.set(change.id, stored.length - 1);
  }
  return stored;
}

function applyTasks(tasks: Record<Id, Task>, delta: EntityDelta, entityId: Id): Record<Id, Task> {
  const merged = Object.fromEntries(Object.entries(tasks).map(([key, task]) => [key, clone(task)]));
  for (const taskId of delta.tasksAchieved ?? []) {
    const task = merged[taskId];
    if (!task) throw new KernelViolation('id_unresolved', `${entityId} has no task ${taskId}`);
    if (task.status !== 'pending') throw new KernelViolation('semantic_invalid', `task ${taskId} is already achieved`);
    merged[taskId] = { ...task, status: 'achieved' };
  }
  const added = new Set((delta.subtasksAdded ?? []).map((task) => task.id));
  for (const task of delta.subtasksAdded ?? []) {
    if (!merged[task.parentTaskId ?? ''] && !added.has(task.parentTaskId ?? '')) {
      throw new KernelViolation('id_unresolved', `new task ${task.id} has unknown parent ${task.parentTaskId}`);
    }
    merged[task.id] = clone(task);
  }
  return merged;
}

export function applyPoint(state: WorldState, point: TimelinePoint): WorldState {
  const locations = Object.fromEntries(Object.entries(state.locations).map(([key, value]) => [key, clone(value)]));
  const items = Object.fromEntries(Object.entries(state.items).map(([key, value]) => [key, clone(value)]));
  const characters = Object.fromEntries(Object.entries(state.characters).map(([key, value]) => [key, clone(value)]));
  const newPositions: Record<Id, Position> = {};
  for (const [entityId, delta] of Object.entries(point.entityDeltas)) {
    if (delta.positionSet != null) newPositions[entityId] = delta.positionSet;
  }
  if (Object.keys(newPositions).length) checkPositions(state, newPositions);
  for (const [entityId, delta] of Object.entries(point.entityDeltas)) {
    if (locations[entityId]) {
      if (delta.positionSet != null || (delta.personalityChanges?.length ?? 0) || delta.sanitySet != null
        || (delta.tasksAchieved?.length ?? 0) || (delta.subtasksAdded?.length ?? 0)) {
        throw new KernelViolation('semantic_invalid', `location ${entityId} only accepts appearance changes`);
      }
      locations[entityId].appearanceChanges = extendChanges(locations[entityId].appearanceChanges, delta.appearanceChanges, point, entityId);
      continue;
    }
    const entity = items[entityId] ?? characters[entityId];
    if (!entity) throw new KernelViolation('id_unresolved', `unknown entity ${entityId}`);
    entity.appearanceChanges = extendChanges(entity.appearanceChanges, delta.appearanceChanges, point, entityId);
    if (delta.positionSet != null) entity.position = clone(delta.positionSet);
    if (characters[entityId]) {
      const character = characters[entityId];
      character.personalityChanges = extendChanges(character.personalityChanges, delta.personalityChanges, point, entityId);
      if (delta.sanitySet != null) character.sanity = delta.sanitySet;
      character.tasks = applyTasks(character.tasks, delta, entityId);
    } else if ((delta.personalityChanges?.length ?? 0) || delta.sanitySet != null
      || (delta.tasksAchieved?.length ?? 0) || (delta.subtasksAdded?.length ?? 0)) {
      throw new KernelViolation('semantic_invalid', `item ${entityId} only accepts position and appearance changes`);
    }
  }
  return {
    ...state,
    time: advanceTime(state.time, point.timeAdvance),
    locations,
    items,
    characters,
  };
}

/** Merge one point's settlement units (named groups plus the optional
 * time-scan unit) exactly as the Python `point_entity_deltas`. */
export function pointEntityDeltas(groups: SettlementGroup[], timeScan: SettlementGroup | null): Record<Id, EntityDelta> {
  const units = timeScan ? [...groups, timeScan] : [...groups];
  const entityIds: Id[] = [];
  for (const unit of units) {
    for (const field of [unit.positions, unit.appearances, unit.tasksAchieved, unit.subtasksAdded, unit.personalities, unit.sanities]) {
      for (const key of Object.keys(field)) if (!entityIds.includes(key)) entityIds.push(key);
    }
  }
  const deltas: Record<Id, EntityDelta> = {};
  for (const entityId of entityIds) {
    let position: Position | null = null;
    let sanity: number | null = null;
    const appearances: Change[] = [];
    const personalities: Change[] = [];
    const achieved = new Set<Id>();
    const added: Task[] = [];
    for (const unit of units) {
      const unitPosition = unit.positions[entityId];
      if (unitPosition) {
        if (position && JSON.stringify(position) !== JSON.stringify(unitPosition)) throw new KernelViolation('position_invalid', `${entityId} receives conflicting positions in one point`);
        position = unitPosition;
      }
      appearances.push(...(unit.appearances[entityId] ?? []));
      personalities.push(...(unit.personalities[entityId] ?? []));
      if (unit.sanities[entityId] !== undefined) {
        if (sanity !== null && sanity !== unit.sanities[entityId]) throw new KernelViolation('semantic_invalid', `${entityId} receives conflicting sanity values in one point`);
        sanity = unit.sanities[entityId];
      }
      for (const taskId of unit.tasksAchieved[entityId] ?? []) achieved.add(taskId);
      added.push(...(unit.subtasksAdded[entityId] ?? []));
    }
    const addedIds = new Set(added.map((task) => task.id));
    const collapsedAchieved = [...achieved].filter((taskId) => !addedIds.has(taskId)).sort();
    const mergedAdded = added.map((task) => achieved.has(task.id) ? { ...task, status: 'achieved' as const } : task);
    deltas[entityId] = {
      entityId,
      positionSet: position,
      appearanceChanges: appearances,
      personalityChanges: personalities,
      sanitySet: sanity,
      tasksAchieved: collapsedAchieved,
      subtasksAdded: mergedAdded,
    };
  }
  return deltas;
}

export function buildTimelinePoint(args: {
  worldId: Id; id: Id; sequence: number; kind: TimelinePoint['kind']; previousPointId: Id;
  roundId: Id; advanceId: Id; trigger: TimelinePoint['trigger']; linkedFromPointId: Id | null;
  timeAdvance: TimeAdvance; entityDeltas: Record<Id, EntityDelta>;
}): TimelinePoint {
  return {
    worldId: args.worldId, id: args.id, sequence: args.sequence, kind: args.kind,
    previousPointId: args.previousPointId, roundId: args.roundId, advanceId: args.advanceId,
    trigger: args.trigger, linkedFromPointId: args.linkedFromPointId,
    timeAdvance: args.timeAdvance, entityDeltas: args.entityDeltas,
  };
}

/** Structural validation for the user-fixed static world format. It checks the
 * same references the Python contract does (entities, slots, parents, relative
 * rooms, task trees) and rejects an unsupported version instead of letting a
 * model invent initial facts. */
export function validateStaticWorld(value: unknown): string[] {
  const errors: string[] = [];
  if (!value || typeof value !== 'object') return ['world is not an object'];
  const world = value as Record<string, unknown>;
  if (world.engineVersion !== 'world-engine-v1') errors.push('unsupported engineVersion');
  if (world.schemaVersion !== 1) errors.push('unsupported schemaVersion');
  const initial = world.initial as Record<string, unknown> | undefined;
  if (!initial || typeof initial !== 'object') { errors.push('missing initial state'); return errors; }
  const locs = initial.locations as Record<string, { parentLocationId?: string | null; slots?: { id: string }[] }> | undefined;
  const its = initial.items as Record<string, { initialPosition?: Position; slots?: { id: string }[] }> | undefined;
  const chars = initial.characters as Record<string, { initialPosition?: Position; initialSanity?: number; tasks?: Record<string, Task>; slots?: { id: string }[] }> | undefined;
  if (!locs || !its || !chars) { errors.push('initial entity tables missing'); return errors; }
  const ids = new Set([...Object.keys(locs), ...Object.keys(its), ...Object.keys(chars)]);
  if (ids.size !== Object.keys(locs).length + Object.keys(its).length + Object.keys(chars).length) errors.push('entity ids are not globally unique');
  const protagonist = initial.protagonistId as string | undefined;
  if (!protagonist || !chars[protagonist]) errors.push('protagonist is not a registered character');
  const slots = (id: string): { id: string }[] => locs[id]?.slots ?? its[id]?.slots ?? chars[id]?.slots ?? [];
  const parents: Record<string, string | null> = {};
  for (const [id, loc] of Object.entries(locs)) {
    if (loc.parentLocationId && !locs[loc.parentLocationId]) errors.push(`location ${id} has unknown parent`);
    parents[id] = loc.parentLocationId ?? null;
  }
  for (const [id, entity] of [...Object.entries(its), ...Object.entries(chars)]) {
    const pos = entity.initialPosition;
    if (!pos) { errors.push(`entity ${id} has no initial position`); continue; }
    if (!ids.has(pos.containerId)) errors.push(`entity ${id} has unknown container ${pos.containerId}`);
    if (pos.slotId && !slots(pos.containerId).some((slot) => slot.id === pos.slotId)) errors.push(`entity ${id} uses a slot outside ${pos.containerId}`);
    if (pos.relativeTo && !ids.has(pos.relativeTo.entityId)) errors.push(`entity ${id} has unknown relative target`);
    parents[id] = pos.containerId;
  }
  const state = buildInitialState(initial as unknown as InitialState);
  try { checkPositions(state, Object.fromEntries(Object.entries(its).map(([id, entity]) => [id, entity.initialPosition!]))); } catch (error) { errors.push((error as Error).message); }
  const room = (node: string): string => {
    const seen = new Set<string>();
    while (!locs[node]) {
      if (seen.has(node)) throw new KernelViolation('semantic_invalid', `cycle at ${node}`);
      seen.add(node);
      node = parents[node] ?? '';
      if (!node) throw new KernelViolation('id_unresolved', 'missing container');
    }
    return node;
  };
  for (const [id, entity] of [...Object.entries(its), ...Object.entries(chars)]) {
    if (entity.initialPosition?.relativeTo) {
      try { if (room(id) !== room(entity.initialPosition.relativeTo.entityId)) errors.push(`entity ${id} relative target is in another room`); }
      catch (error) { errors.push((error as Error).message); }
    }
  }
  for (const [owner, character] of Object.entries(chars)) {
    for (const [taskId, task] of Object.entries(character.tasks ?? {})) {
      if (task.id !== taskId || task.ownerId !== owner) errors.push(`task ${taskId} identity/owner mismatch`);
      if (task.parentTaskId && !character.tasks?.[task.parentTaskId]) errors.push(`task ${taskId} has unknown parent`);
    }
  }
  return errors;
}
