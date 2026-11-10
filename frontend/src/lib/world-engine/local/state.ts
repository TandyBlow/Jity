/** Browser port of the Python state kernel: S0 construction, point application,
 * same-point merge, replay and world-canonical digests. This module is the only
 * place a browser world state is mutated; the local transport calls it inside
 * its own transaction copy and never edits committed points.
 *
 * The contract checks here are deliberately the ones that can change facts:
 * ids and text, entity/container/slot/relative references, the joint position
 * graph, change supersedes, task trees and time. The loader in `world-loader`
 * additionally validates a complete static `WorldState` before a game starts. */
import { canonicalDigest, canonicalJson } from './canonical';
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

function refuse(kind: KernelViolation['kind'], detail: string): never {
  throw new KernelViolation(kind, detail);
}

export function clone<T>(value: T): T {
  return structuredClone(value);
}

const ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const RELATIONS = new Set(['under', 'above', 'beside', 'in_front_of', 'behind']);
const UNITS = new Set(['second', 'minute', 'hour', 'day', 'month', 'year']);
const MAX_SAFE = 2 ** 53 - 1;

export function isContractId(value: unknown): value is Id {
  return typeof value === 'string' && ID_PATTERN.test(value);
}

function idOf(value: unknown, field: string): Id {
  if (!isContractId(value)) refuse('semantic_invalid', `${field} is not a contract id`);
  return value;
}

function textOf(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.length === 0 || !/\S/.test(value)) {
    refuse('semantic_invalid', `${field} must be non-blank text`);
  }
  return value;
}

function safeIntOf(value: unknown, field: string, min = -MAX_SAFE, max = MAX_SAFE): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < min || value > max) {
    refuse('semantic_invalid', `${field} must be a safe integer in [${min}, ${max}]`);
  }
  return value;
}

function idListOf(value: unknown, field: string): Id[] {
  if (!Array.isArray(value)) refuse('semantic_invalid', `${field} must be a list`);
  const ids = value.map((item, index) => idOf(item, `${field}[${index}]`));
  if (new Set(ids).size !== ids.length) refuse('semantic_invalid', `${field} has duplicate identity`);
  return ids;
}

function idSetOf(value: unknown, field: string): Id[] {
  return idListOf(value, field).sort();
}

function recordOf(value: unknown, field: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    refuse('semantic_invalid', `${field} must be an object`);
  }
  return value as Record<string, unknown>;
}

function keysOf(record: Record<string, unknown>, allowed: readonly string[], field: string): void {
  for (const key of Object.keys(record)) {
    if (!allowed.includes(key)) refuse('semantic_invalid', `${field} has unknown field ${key}`);
  }
}

export function buildInitialState(initial: InitialState): WorldState {
  // The Python model fills optional `slots` and explicit position nulls even
  // when a raw asset omits them; normalize here so S0 and every later digest
  // are built from the same contract shape.
  const fixed = normalizeInitialState(initial);
  const worldId = fixed.worldId;
  return {
    engineVersion: fixed.engineVersion,
    schemaVersion: fixed.schemaVersion,
    worldId,
    protagonistId: fixed.protagonistId,
    time: clone(fixed.initialTime),
    initial: clone(fixed),
    locations: Object.fromEntries(Object.keys(fixed.locations).map((key) => [key, { id: key, appearanceChanges: [] }])),
    items: Object.fromEntries(Object.entries(fixed.items).map(([key, entity]) => [key, { id: key, position: clone(entity.initialPosition), appearanceChanges: [] }])),
    characters: Object.fromEntries(Object.entries(fixed.characters).map(([key, entity]) => [key, {
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
const DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/;

function pad(value: number, width = 2): string {
  return String(value).padStart(width, '0');
}

interface TimeParts { year: number; month: number; day: number; hour: number; minute: number; second: number }

function daysInMonth(year: number, month: number): number {
  const date = new Date(0);
  date.setUTCFullYear(year, month, 0);
  date.setUTCHours(0, 0, 0, 0);
  return date.getUTCDate();
}

function dateFromParts(parts: TimeParts): Date {
  const date = new Date(0);
  date.setUTCFullYear(parts.year, parts.month - 1, parts.day);
  date.setUTCHours(parts.hour, parts.minute, parts.second, 0);
  if (date.getUTCFullYear() !== parts.year || date.getUTCMonth() !== parts.month - 1
    || date.getUTCDate() !== parts.day || date.getUTCHours() !== parts.hour
    || date.getUTCMinutes() !== parts.minute || date.getUTCSeconds() !== parts.second) {
    refuse('semantic_invalid', `invalid dateTime ${formatParts(parts)}`);
  }
  if (parts.year < 1 || parts.year > 9999) refuse('semantic_invalid', `dateTime year is out of range`);
  return date;
}

function formatParts(parts: TimeParts): string {
  return `${pad(parts.year, 4)}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}:${pad(parts.second)}`;
}

function parseTime(value: string): { parts: TimeParts; date: Date } {
  const match = DATE_TIME.exec(value);
  if (!match) refuse('semantic_invalid', `invalid dateTime ${value}`);
  const parts = {
    year: Number(match[1]), month: Number(match[2]), day: Number(match[3]),
    hour: Number(match[4]), minute: Number(match[5]), second: Number(match[6]),
  };
  return { parts, date: dateFromParts(parts) };
}

export function advanceTime(at: WorldState['time'], advance: TimeAdvance): WorldState['time'] {
  const amount = safeIntOf(advance.duration.amount, 'timeAdvance.duration.amount', 0);
  const unit = advance.duration.unit;
  if (!UNITS.has(unit)) refuse('semantic_invalid', `unknown time unit ${unit}`);
  if (amount === 0) return { ...at, instantOrdinal: safeIntOf(at.instantOrdinal + 1, 'instantOrdinal', 0) };
  const { parts, date } = parseTime(at.dateTime);
  if (unit === 'month' || unit === 'year') {
    const months = amount * (unit === 'year' ? 12 : 1);
    if (!Number.isSafeInteger(months)) refuse('semantic_invalid', 'timeAdvance.duration.amount is too large');
    const index = parts.month - 1 + months;
    const year = parts.year + Math.floor(index / 12);
    const month = ((index % 12) + 12) % 12 + 1;
    if (year < 1 || year > 9999) refuse('semantic_invalid', 'dateTime year is out of range');
    const day = Math.min(parts.day, daysInMonth(year, month));
    return { ...at, dateTime: formatParts({ ...parts, year, month, day }), instantOrdinal: 0 };
  }
  const millis = date.getTime() + amount * (SECONDS[unit] ?? 0) * 1000;
  const next = new Date(millis);
  if (!Number.isFinite(millis)) refuse('semantic_invalid', 'dateTime is out of range');
  const nextParts: TimeParts = {
    year: next.getUTCFullYear(), month: next.getUTCMonth() + 1, day: next.getUTCDate(),
    hour: next.getUTCHours(), minute: next.getUTCMinutes(), second: next.getUTCSeconds(),
  };
  if (nextParts.year < 1 || nextParts.year > 9999) refuse('semantic_invalid', 'dateTime year is out of range');
  return { ...at, dateTime: formatParts(nextParts), instantOrdinal: 0 };
}

export function normalizePosition(value: unknown, field = 'position'): Position {
  const position = recordOf(value, field);
  keysOf(position, ['containerId', 'slotId', 'relativeTo'], field);
  const containerId = idOf(position.containerId, `${field}.containerId`);
  const slotId = position.slotId == null ? null : idOf(position.slotId, `${field}.slotId`);
  let relativeTo: Position['relativeTo'] = null;
  if (position.relativeTo != null) {
    const relative = recordOf(position.relativeTo, `${field}.relativeTo`);
    keysOf(relative, ['entityId', 'relation'], `${field}.relativeTo`);
    const relation = relative.relation;
    if (typeof relation !== 'string' || !RELATIONS.has(relation)) {
      refuse('semantic_invalid', `${field}.relativeTo.relation is not a contract relation`);
    }
    relativeTo = { entityId: idOf(relative.entityId, `${field}.relativeTo.entityId`),
      relation: relation as NonNullable<Position['relativeTo']>['relation'] };
  }
  return { containerId, slotId, relativeTo };
}

function positionsEqual(left: Position, right: Position): boolean {
  return canonicalJson(left) === canonicalJson(right);
}

function normalizeTimeOf(value: unknown, field: string): WorldState['time'] {
  const time = recordOf(value, field);
  keysOf(time, ['calendar', 'dateTime', 'instantOrdinal'], field);
  if (time.calendar !== 'gregorian') refuse('semantic_invalid', `${field}.calendar is not gregorian`);
  if (typeof time.dateTime !== 'string') refuse('semantic_invalid', `${field}.dateTime must be text`);
  parseTime(time.dateTime);
  return { calendar: 'gregorian', dateTime: time.dateTime,
    instantOrdinal: safeIntOf(time.instantOrdinal, `${field}.instantOrdinal`, 0) };
}

export function normalizeTimeAdvance(value: unknown, field: string): TimeAdvance {
  const advance = recordOf(value, field);
  keysOf(advance, ['boundary', 'duration'], field);
  if (advance.boundary !== 'elapsed' && advance.boundary !== 'instant') {
    refuse('semantic_invalid', `${field}.boundary is not a contract boundary`);
  }
  const duration = recordOf(advance.duration, `${field}.duration`);
  keysOf(duration, ['amount', 'unit'], `${field}.duration`);
  const unit = duration.unit;
  if (typeof unit !== 'string' || !UNITS.has(unit)) refuse('semantic_invalid', `${field}.duration.unit is unknown`);
  return {
    boundary: advance.boundary,
    duration: {
      amount: safeIntOf(duration.amount, `${field}.duration.amount`, 0),
      unit: unit as TimeAdvance['duration']['unit'],
    },
  };
}

function normalizeChange(value: unknown, field: string): Change {
  const change = recordOf(value, field);
  keysOf(change, ['id', 'text', 'supersedes'], field);
  const id = idOf(change.id, `${field}.id`);
  const text = change.text == null ? null : textOf(change.text, `${field}.text`);
  if (change.supersedes != null && !Array.isArray(change.supersedes)) {
    refuse('semantic_invalid', `${field}.supersedes must be a list`);
  }
  const supersedes = idSetOf(change.supersedes ?? [], `${field}.supersedes`);
  if (text === null && supersedes.length === 0) {
    refuse('semantic_invalid', `${field} is a pure removal without supersedes`);
  }
  if (supersedes.includes(id)) refuse('semantic_invalid', `${field} cannot supersede itself`);
  return { id, text, supersedes };
}

function normalizeChanges(value: unknown, field: string): Change[] {
  if (value == null) return [];
  if (!Array.isArray(value)) refuse('semantic_invalid', `${field} must be a list`);
  return value.map((entry, index) => normalizeChange(entry, `${field}[${index}]`));
}

function normalizeTask(value: unknown, field: string): Task {
  const task = recordOf(value, field);
  keysOf(task, ['id', 'ownerId', 'parentTaskId', 'goal', 'status'], field);
  const status = task.status;
  if (status !== 'pending' && status !== 'achieved') {
    refuse('semantic_invalid', `${field}.status is not a contract status`);
  }
  return {
    id: idOf(task.id, `${field}.id`),
    ownerId: idOf(task.ownerId, `${field}.ownerId`),
    parentTaskId: task.parentTaskId == null ? null : idOf(task.parentTaskId, `${field}.parentTaskId`),
    goal: textOf(task.goal, `${field}.goal`),
    status,
  };
}

function taskLevels(tasks: Task[], field: string): Map<Id, number> {
  const byId = new Map<Id, Task>();
  for (const task of tasks) {
    if (byId.has(task.id)) refuse('semantic_invalid', `${field} has duplicate task ${task.id}`);
    byId.set(task.id, task);
  }
  const levels = new Map<Id, number>();
  const level = (id: Id, trail: Set<Id>): number => {
    const cached = levels.get(id);
    if (cached != null) return cached;
    if (trail.has(id)) refuse('semantic_invalid', `${field} has a cyclic new task tree at ${id}`);
    trail.add(id);
    const task = byId.get(id)!;
    const parent = task.parentTaskId;
    const value = parent != null && byId.has(parent) ? level(parent, trail) + 1 : 0;
    trail.delete(id);
    levels.set(id, value);
    return value;
  };
  for (const task of tasks) level(task.id, new Set());
  return levels;
}

function normalizeAddedTasks(value: unknown, ownerId: Id, field: string, achieved: Set<Id>): Task[] {
  if (value == null) return [];
  if (!Array.isArray(value)) refuse('semantic_invalid', `${field} must be a list`);
  const tasks = value.map((entry, index) => normalizeTask(entry, `${field}[${index}]`));
  const levels = taskLevels(tasks, field);
  const ids = new Set<Id>();
  for (const task of tasks) {
    if (task.ownerId !== ownerId) refuse('semantic_invalid', `${field} task ${task.id} has another owner`);
    if (task.parentTaskId == null) refuse('semantic_invalid', `${field} task ${task.id} has no parent`);
    if (ids.has(task.id)) refuse('semantic_invalid', `${field} has duplicate task ${task.id}`);
    if (achieved.has(task.id)) refuse('semantic_invalid', `${field} task ${task.id} is both added and achieved`);
    ids.add(task.id);
  }
  return tasks.slice().sort((left, right) => {
    const byLevel = (levels.get(left.id) ?? 0) - (levels.get(right.id) ?? 0);
    if (byLevel !== 0) return byLevel;
    return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
  });
}

function normalizeSanity(value: unknown, field: string): number {
  return safeIntOf(value, field, 0, 100);
}

/** Validate one per-entity point delta and return its contract-normalized form.
 * This mirrors Python `EntityDelta`: change ids are unique across appearance
 * and personality; one point cannot supersede its own new changes; new task
 * trees are acyclic and sorted by level; sanity is an integer in 0..100. */
export function normalizeEntityDelta(value: unknown, expectedEntityId?: Id): EntityDelta {
  const delta = recordOf(value, 'entityDelta');
  keysOf(delta, ['entityId', 'positionSet', 'appearanceChanges', 'personalityChanges',
    'sanitySet', 'tasksAchieved', 'subtasksAdded'], 'entityDelta');
  const entityId = idOf(delta.entityId, 'entityDelta.entityId');
  if (expectedEntityId != null && expectedEntityId !== entityId) {
    refuse('semantic_invalid', `entity delta key ${expectedEntityId} differs from entityId ${entityId}`);
  }
  const appearanceChanges = normalizeChanges(delta.appearanceChanges, 'entityDelta.appearanceChanges');
  const personalityChanges = normalizeChanges(delta.personalityChanges, 'entityDelta.personalityChanges');
  const changeIds = new Set<Id>();
  for (const change of [...appearanceChanges, ...personalityChanges]) {
    if (changeIds.has(change.id)) refuse('semantic_invalid', `entity delta ${entityId} repeats change ${change.id}`);
    changeIds.add(change.id);
  }
  for (const change of [...appearanceChanges, ...personalityChanges]) {
    for (const target of change.supersedes) {
      if (changeIds.has(target)) {
        refuse('semantic_invalid', `entity delta ${entityId} supersedes a same-point change ${target}`);
      }
    }
  }
  const achieved = idSetOf(delta.tasksAchieved ?? [], 'entityDelta.tasksAchieved');
  const added = normalizeAddedTasks(delta.subtasksAdded, entityId, 'entityDelta.subtasksAdded', new Set(achieved));
  const normalized: EntityDelta = { entityId };
  if (delta.positionSet != null) normalized.positionSet = normalizePosition(delta.positionSet, 'entityDelta.positionSet');
  if (appearanceChanges.length) normalized.appearanceChanges = appearanceChanges;
  if (personalityChanges.length) normalized.personalityChanges = personalityChanges;
  if (delta.sanitySet != null) normalized.sanitySet = normalizeSanity(delta.sanitySet, 'entityDelta.sanitySet');
  if (achieved.length) normalized.tasksAchieved = achieved;
  if (added.length) normalized.subtasksAdded = added;
  return normalized;
}

/** Normalize one settlement group exactly as the Python contract model dumps
 * it: optional nulls become explicit, identity sets are sorted, and empty
 * candidate maps are refused because the wire requires at least one entry. */
export function normalizeSettlementGroup(value: unknown): SettlementGroup {
  const group = recordOf(value, 'settlementGroup');
  const groupFields = ['groupId', 'actorIds', 'positions', 'appearances', 'tasksAchieved',
    'subtasksAdded', 'personalities', 'sanities', 'taskCoverageIds', 'personalityCoverageIds'] as const;
  keysOf(group, groupFields, 'settlementGroup');
  for (const field of groupFields) {
    if (!(field in group)) refuse('semantic_invalid', `settlementGroup.${field} is required`);
  }
  const groupId = group.groupId == null ? null : idOf(group.groupId, 'settlementGroup.groupId');
  const actorIds = idListOf(group.actorIds ?? [], 'settlementGroup.actorIds');
  const positions = Object.fromEntries(Object.entries(recordOf(group.positions ?? {}, 'settlementGroup.positions'))
    .map(([key, position]) => [idOf(key, 'settlementGroup.positions key'), normalizePosition(position, `settlementGroup.positions.${key}`)]));
  const appearances = Object.fromEntries(Object.entries(recordOf(group.appearances ?? {}, 'settlementGroup.appearances'))
    .map(([key, changes]) => {
      if (!Array.isArray(changes) || changes.length === 0) refuse('semantic_invalid', `settlementGroup.appearances.${key} must not be empty`);
      return [idOf(key, 'settlementGroup.appearances key'), normalizeChanges(changes, `settlementGroup.appearances.${key}`)];
    }));
  const personalities = Object.fromEntries(Object.entries(recordOf(group.personalities ?? {}, 'settlementGroup.personalities'))
    .map(([key, changes]) => {
      if (!Array.isArray(changes) || changes.length === 0) refuse('semantic_invalid', `settlementGroup.personalities.${key} must not be empty`);
      return [idOf(key, 'settlementGroup.personalities key'), normalizeChanges(changes, `settlementGroup.personalities.${key}`)];
    }));
  const tasksAchieved = Object.fromEntries(Object.entries(recordOf(group.tasksAchieved ?? {}, 'settlementGroup.tasksAchieved'))
    .map(([key, ids]) => {
      if (!Array.isArray(ids) || ids.length === 0) refuse('semantic_invalid', `settlementGroup.tasksAchieved.${key} must not be empty`);
      return [idOf(key, 'settlementGroup.tasksAchieved key'), idSetOf(ids, `settlementGroup.tasksAchieved.${key}`)];
    }));
  const subtasksAdded = Object.fromEntries(Object.entries(recordOf(group.subtasksAdded ?? {}, 'settlementGroup.subtasksAdded'))
    .map(([key, tasks]) => {
      if (!Array.isArray(tasks) || tasks.length === 0) refuse('semantic_invalid', `settlementGroup.subtasksAdded.${key} must not be empty`);
      const owner = idOf(key, 'settlementGroup.subtasksAdded key');
      return [owner, (tasks as unknown[]).map((task, index) => {
        const normalized = normalizeTask(task, `settlementGroup.subtasksAdded.${key}[${index}]`);
        if (normalized.ownerId !== owner) refuse('semantic_invalid', `subtask ${normalized.id} has another owner`);
        if (normalized.parentTaskId == null) refuse('semantic_invalid', `subtask ${normalized.id} has no parent`);
        return normalized;
      })];
    }));
  const sanities = Object.fromEntries(Object.entries(recordOf(group.sanities ?? {}, 'settlementGroup.sanities'))
    .map(([key, sanity]) => [idOf(key, 'settlementGroup.sanities key'), normalizeSanity(sanity, `settlementGroup.sanities.${key}`)]));
  const taskCoverageIds = idSetOf(group.taskCoverageIds ?? [], 'settlementGroup.taskCoverageIds');
  const personalityCoverageIds = idSetOf(group.personalityCoverageIds ?? [], 'settlementGroup.personalityCoverageIds');
  if (groupId === null) {
    if (actorIds.length || Object.keys(positions).length || Object.keys(appearances).length) {
      refuse('semantic_invalid', 'time-scan unit cannot invent actors, movement or appearance');
    }
  } else if (!actorIds.length) {
    refuse('semantic_invalid', 'action group requires actors');
  }
  return { groupId, actorIds, positions, appearances, tasksAchieved, subtasksAdded,
    personalities, sanities, taskCoverageIds, personalityCoverageIds };
}

function normalizeStoredChange(value: unknown, field: string): StoredChange {
  const change = recordOf(value, field);
  keysOf(change, ['id', 'text', 'supersedes', 'sourcePointId', 'sourceSequence', 'active'], field);
  const normalized = normalizeChange(change, field);
  return {
    ...normalized,
    sourcePointId: idOf(change.sourcePointId, `${field}.sourcePointId`),
    sourceSequence: safeIntOf(change.sourceSequence, `${field}.sourceSequence`, 1),
    active: typeof change.active === 'boolean' ? change.active : refuse('semantic_invalid', `${field}.active must be boolean`),
  };
}

function normalizeStoredChanges(value: unknown, field: string): StoredChange[] {
  if (!Array.isArray(value)) refuse('semantic_invalid', `${field} must be a list`);
  const changes = value.map((entry, index) => normalizeStoredChange(entry, `${field}[${index}]`));
  if (new Set(changes.map((change) => change.id)).size !== changes.length) {
    refuse('semantic_invalid', `${field} has duplicate change id`);
  }
  return changes;
}

function normalizeTaskRecord(value: unknown, owner: Id, field: string): Record<Id, Task> {
  const tasks = recordOf(value ?? {}, field);
  return Object.fromEntries(Object.entries(tasks).map(([key, raw]) => {
    const task = normalizeTask(raw, `${field}.${key}`);
    const taskId = idOf(key, `${field} key`);
    if (task.id !== taskId) refuse('semantic_invalid', `${field} key differs from task id`);
    if (task.ownerId !== owner) refuse('semantic_invalid', `${field} task ${taskId} has another owner`);
    return [taskId, task];
  }));
}

function normalizeSlots(value: unknown, field: string): { id: Id; label: string }[] {
  const slots = value == null ? [] : value;
  if (!Array.isArray(slots)) refuse('semantic_invalid', `${field} must be a list`);
  const normalized = slots.map((raw, index) => {
    const slot = recordOf(raw, `${field}[${index}]`);
    keysOf(slot, ['id', 'label'], `${field}[${index}]`);
    return { id: idOf(slot.id, `${field}[${index}].id`), label: textOf(slot.label, `${field}[${index}].label`) };
  });
  if (new Set(normalized.map((slot) => slot.id)).size !== normalized.length) {
    refuse('semantic_invalid', `${field} has duplicate slot id`);
  }
  return normalized;
}

function acyclic(edges: Map<Id, Id[]>, field: string): void {
  const active = new Set<Id>();
  const done = new Set<Id>();
  const visit = (node: Id): void => {
    if (active.has(node)) refuse('semantic_invalid', `${field} has a cycle at ${node}`);
    if (done.has(node)) return;
    active.add(node);
    for (const target of edges.get(node) ?? []) visit(target);
    active.delete(node);
    done.add(node);
  };
  for (const node of edges.keys()) visit(node);
}

/** Validate and normalize `initial` exactly as `WorldInitialState` defines it.
 * Missing optional slots become `[]`; positions gain explicit nulls. */
export function normalizeInitialState(value: unknown): InitialState {
  const initial = recordOf(value, 'initial');
  keysOf(initial, ['engineVersion', 'schemaVersion', 'worldId', 'protagonistId',
    'initialTime', 'locations', 'items', 'characters'], 'initial');
  if (initial.engineVersion !== 'world-engine-v1') refuse('semantic_invalid', 'unsupported engineVersion');
  if (initial.schemaVersion !== 1) refuse('semantic_invalid', 'unsupported schemaVersion');
  const worldId = idOf(initial.worldId, 'initial.worldId');
  const protagonistId = idOf(initial.protagonistId, 'initial.protagonistId');
  const initialTime = normalizeTimeOf(initial.initialTime, 'initial.initialTime');
  const locations = recordOf(initial.locations, 'initial.locations');
  const items = recordOf(initial.items, 'initial.items');
  const characters = recordOf(initial.characters, 'initial.characters');
  if (!Object.keys(locations).length) refuse('semantic_invalid', 'world requires locations');

  const ids = new Set<Id>();
  const initialEntityFields = (kind: 'locations' | 'items' | 'characters'): string[] =>
    kind === 'locations' ? ['id', 'name', 'parentLocationId', 'initialAppearance', 'slots']
      : kind === 'items' ? ['id', 'name', 'initialPosition', 'initialAppearance', 'slots']
        : ['id', 'name', 'initialPosition', 'initialAppearance', 'slots',
          'initialPersonality', 'initialSanity', 'tasks'];
  for (const kind of ['locations', 'items', 'characters'] as const) {
    const table = { locations, items, characters }[kind] as Record<string, unknown>;
    for (const [key, raw] of Object.entries(table)) {
      const entity = recordOf(raw, `initial.${kind}.${key}`);
      keysOf(entity, initialEntityFields(kind), `initial.${kind}.${key}`);
      const id = idOf(key, `initial entity key`);
      if (entity.id !== id) refuse('semantic_invalid', `initial entity ${key} id differs from its key`);
      if (ids.has(id)) refuse('semantic_invalid', `entity id ${id} is not globally unique`);
      ids.add(id);
    }
  }

  const slotsByEntity = new Map<Id, { id: Id; label: string }[]>();
  for (const [key, raw] of [...Object.entries(locations), ...Object.entries(items), ...Object.entries(characters)]) {
    const entity = recordOf(raw, `initial entity ${key}`);
    slotsByEntity.set(key, normalizeSlots(entity.slots, `initial.${key}.slots`));
  }
  const slotsOfInitial = (containerId: Id): { id: Id; label: string }[] => slotsByEntity.get(containerId) ?? [];

  const normalizedLocations: InitialState['locations'] = {};
  const edges = new Map<Id, Id[]>();
  const parents = new Map<Id, Id | null>();
  for (const [key, raw] of Object.entries(locations)) {
    const entity = recordOf(raw, `initial.locations.${key}`);
    idOf(entity.id, `initial.locations.${key}.id`);
    const parentLocationId = entity.parentLocationId == null ? null : idOf(entity.parentLocationId, `initial.locations.${key}.parentLocationId`);
    if (parentLocationId != null && !locations[parentLocationId]) {
      refuse('id_unresolved', `location ${key} has unknown parent ${parentLocationId}`);
    }
    normalizedLocations[key] = {
      id: key,
      name: textOf(entity.name, `initial.locations.${key}.name`),
      parentLocationId,
      initialAppearance: textOf(entity.initialAppearance, `initial.locations.${key}.initialAppearance`),
      slots: slotsByEntity.get(key) ?? [],
    };
    parents.set(key, parentLocationId);
    edges.set(key, parentLocationId ? [parentLocationId] : []);
  }

  const normalizedItems: InitialState['items'] = {};
  const normalizedCharacters: InitialState['characters'] = {};
  const taskIds = new Set<Id>();
  const normalizeEntityPosition = (entityId: Id, raw: unknown): Position => {
    const position = normalizePosition(raw, `initial.${entityId}.initialPosition`);
    if (!ids.has(position.containerId)) {
      refuse('id_unresolved', `entity ${entityId} has unknown container ${position.containerId}`);
    }
    if (position.slotId != null && !slotsOfInitial(position.containerId).some((slot) => slot.id === position.slotId)) {
      refuse('id_unresolved', `entity ${entityId} uses slot ${position.slotId} outside ${position.containerId}`);
    }
    if (position.relativeTo != null && !ids.has(position.relativeTo.entityId)) {
      refuse('id_unresolved', `entity ${entityId} has unknown relative target ${position.relativeTo.entityId}`);
    }
    return position;
  };
  for (const [key, raw] of Object.entries(items)) {
    const entity = recordOf(raw, `initial.items.${key}`);
    const position = normalizeEntityPosition(key, entity.initialPosition);
    normalizedItems[key] = {
      id: key,
      name: textOf(entity.name, `initial.items.${key}.name`),
      initialPosition: position,
      initialAppearance: textOf(entity.initialAppearance, `initial.items.${key}.initialAppearance`),
      slots: slotsByEntity.get(key) ?? [],
    };
    parents.set(key, position.containerId);
    const outgoing = [position.containerId];
    if (position.relativeTo != null) outgoing.push(position.relativeTo.entityId);
    edges.set(key, outgoing);
  }
  for (const [key, raw] of Object.entries(characters)) {
    const entity = recordOf(raw, `initial.characters.${key}`);
    const position = normalizeEntityPosition(key, entity.initialPosition);
    const tasks = normalizeTaskRecord(entity.tasks, key, `initial.characters.${key}.tasks`);
    const taskEdges = new Map<Id, Id[]>();
    for (const [taskId, task] of Object.entries(tasks)) {
      if (taskIds.has(taskId)) refuse('semantic_invalid', `task id ${taskId} is not globally unique`);
      taskIds.add(taskId);
      if (task.parentTaskId != null && !tasks[task.parentTaskId]) {
        refuse('id_unresolved', `task ${taskId} has unknown parent ${task.parentTaskId}`);
      }
      taskEdges.set(taskId, task.parentTaskId == null ? [] : [task.parentTaskId]);
    }
    acyclic(taskEdges, `task tree of ${key}`);
    normalizedCharacters[key] = {
      id: key,
      name: textOf(entity.name, `initial.characters.${key}.name`),
      initialPosition: position,
      initialAppearance: textOf(entity.initialAppearance, `initial.characters.${key}.initialAppearance`),
      slots: slotsByEntity.get(key) ?? [],
      initialPersonality: textOf(entity.initialPersonality, `initial.characters.${key}.initialPersonality`),
      initialSanity: normalizeSanity(entity.initialSanity, `initial.characters.${key}.initialSanity`),
      tasks,
    };
    parents.set(key, position.containerId);
    const outgoing = [position.containerId];
    if (position.relativeTo != null) outgoing.push(position.relativeTo.entityId);
    edges.set(key, outgoing);
  }
  acyclic(edges, 'initial position graph');
  if (!normalizedCharacters[protagonistId]) {
    refuse('id_unresolved', `protagonist ${protagonistId} is not a registered character`);
  }
  const room = (node: Id): Id => {
    const seen = new Set<Id>();
    let current: Id | null = node;
    while (current != null && !normalizedLocations[current]) {
      if (seen.has(current)) refuse('semantic_invalid', `initial position graph has a cycle at ${current}`);
      seen.add(current);
      current = parents.get(current) ?? null;
    }
    if (current == null) refuse('id_unresolved', `entity ${node} has no location root`);
    return current;
  };
  for (const [key, entity] of [...Object.entries(normalizedItems), ...Object.entries(normalizedCharacters)]) {
    const relative = entity.initialPosition.relativeTo;
    if (relative != null && room(key) !== room(relative.entityId)) {
      refuse('semantic_invalid', `relative reference ${relative.entityId} of ${key} is in a different location`);
    }
  }
  return {
    engineVersion: 'world-engine-v1',
    schemaVersion: 1,
    worldId,
    protagonistId,
    initialTime,
    locations: normalizedLocations,
    items: normalizedItems,
    characters: normalizedCharacters,
  };
}

/** Validate the initial projection and return the same list-of-errors shape
 * the old static-world helper exposed. */
export function validateInitialTemplate(value: unknown): string[] {
  try {
    normalizeInitialState(value);
    return [];
  } catch (error) {
    return [(error as Error).message];
  }
}

/** Normalize the current tables of a full `WorldState` against an already
 * normalized initial projection. It checks registry identity and every
 * current position/task/change field; the caller decides whether the current
 * snapshot must equal S0 and compares the registered digest. */
export function normalizeWorldState(value: unknown, initial: InitialState): WorldState {
  const world = recordOf(value, 'world');
  keysOf(world, ['engineVersion', 'schemaVersion', 'worldId', 'protagonistId', 'time',
    'initial', 'locations', 'items', 'characters'], 'world');
  if (world.engineVersion !== 'world-engine-v1') refuse('semantic_invalid', 'unsupported engineVersion');
  if (world.schemaVersion !== 1) refuse('semantic_invalid', 'unsupported schemaVersion');
  const worldId = idOf(world.worldId, 'world.worldId');
  const protagonistId = idOf(world.protagonistId, 'world.protagonistId');
  if (worldId !== initial.worldId || protagonistId !== initial.protagonistId) {
    refuse('semantic_invalid', 'initial world binding changed');
  }
  const time = normalizeTimeOf(world.time, 'world.time');
  const currentLocations = recordOf(world.locations, 'world.locations');
  const currentItems = recordOf(world.items, 'world.items');
  const currentCharacters = recordOf(world.characters, 'world.characters');
  const checkRegistry = (current: Record<string, unknown>, expected: Record<string, unknown>, field: string): void => {
    const currentKeys = Object.keys(current).sort();
    const expectedKeys = Object.keys(expected).sort();
    if (canonicalJson(currentKeys) !== canonicalJson(expectedKeys)) {
      refuse('semantic_invalid', `${field} registry differs from the initial state`);
    }
  };
  checkRegistry(currentLocations, initial.locations, 'locations');
  checkRegistry(currentItems, initial.items, 'items');
  checkRegistry(currentCharacters, initial.characters, 'characters');
  const locations: WorldState['locations'] = {};
  for (const [key, raw] of Object.entries(currentLocations)) {
    const entity = recordOf(raw, `world.locations.${key}`);
    keysOf(entity, ['id', 'appearanceChanges'], `world.locations.${key}`);
    if (entity.id !== key) refuse('semantic_invalid', `state key ${key} differs from entity id`);
    locations[key] = { id: key, appearanceChanges: normalizeStoredChanges(entity.appearanceChanges ?? [], `world.locations.${key}.appearanceChanges`) };
  }
  const items: WorldState['items'] = {};
  for (const [key, raw] of Object.entries(currentItems)) {
    const entity = recordOf(raw, `world.items.${key}`);
    keysOf(entity, ['id', 'appearanceChanges', 'position'], `world.items.${key}`);
    if (entity.id !== key) refuse('semantic_invalid', `state key ${key} differs from entity id`);
    items[key] = {
      id: key,
      appearanceChanges: normalizeStoredChanges(entity.appearanceChanges ?? [], `world.items.${key}.appearanceChanges`),
      position: normalizePosition(entity.position, `world.items.${key}.position`),
    };
  }
  const characters: WorldState['characters'] = {};
  for (const [key, raw] of Object.entries(currentCharacters)) {
    const entity = recordOf(raw, `world.characters.${key}`);
    keysOf(entity, ['id', 'appearanceChanges', 'position', 'personalityChanges', 'sanity', 'tasks'],
      `world.characters.${key}`);
    if (entity.id !== key) refuse('semantic_invalid', `state key ${key} differs from entity id`);
    const tasks = normalizeTaskRecord(entity.tasks, key, `world.characters.${key}.tasks`);
    const taskEdges = new Map<Id, Id[]>();
    for (const [taskId, task] of Object.entries(tasks)) {
      if (task.parentTaskId != null && !tasks[task.parentTaskId]) {
        refuse('id_unresolved', `task ${taskId} has unknown parent ${task.parentTaskId}`);
      }
      taskEdges.set(taskId, task.parentTaskId == null ? [] : [task.parentTaskId]);
    }
    acyclic(taskEdges, `task tree of ${key}`);
    characters[key] = {
      id: key,
      appearanceChanges: normalizeStoredChanges(entity.appearanceChanges ?? [], `world.characters.${key}.appearanceChanges`),
      position: normalizePosition(entity.position, `world.characters.${key}.position`),
      personalityChanges: normalizeStoredChanges(entity.personalityChanges ?? [], `world.characters.${key}.personalityChanges`),
      sanity: normalizeSanity(entity.sanity, `world.characters.${key}.sanity`),
      tasks,
    };
  }
  return {
    engineVersion: 'world-engine-v1', schemaVersion: 1, worldId, protagonistId, time, initial,
    locations, items, characters,
  };
}

/** Validate positions in a normalized state, including untouched relative
 * references whose target may have moved. */
export function validateWorldPositions(state: WorldState): string[] {
  try {
    const positions: Record<Id, Position> = {};
    for (const [id, entity] of [...Object.entries(state.items), ...Object.entries(state.characters)]) {
      positions[id] = normalizePosition(entity.position, `world.${id}.position`);
    }
    checkPositions(state, positions);
    return [];
  } catch (error) {
    return [(error as Error).message];
  }
}

function validatePointShape(point: TimelinePoint): void {
  const world = recordOf(point, 'point');
  keysOf(world, ['worldId', 'id', 'sequence', 'kind', 'previousPointId', 'roundId',
    'advanceId', 'trigger', 'linkedFromPointId', 'timeAdvance', 'entityDeltas'], 'point');
  idOf(world.worldId, 'point.worldId');
  const id = idOf(world.id, 'point.id');
  const sequence = safeIntOf(world.sequence, 'point.sequence', 1);
  if (sequence < 1) refuse('semantic_invalid', 'point.sequence must be positive');
  if (world.kind !== 'normal' && world.kind !== 'instant' && world.kind !== 'linked') {
    refuse('semantic_invalid', 'point.kind is not a contract kind');
  }
  const previousPointId = idOf(world.previousPointId, 'point.previousPointId');
  if (id === previousPointId) refuse('semantic_invalid', 'point cannot precede itself');
  idOf(world.roundId, 'point.roundId');
  idOf(world.advanceId, 'point.advanceId');
  if (world.trigger !== 'player' && world.trigger !== 'automatic') {
    refuse('semantic_invalid', 'point.trigger is not a contract trigger');
  }
  const timeAdvance = normalizeTimeAdvance(world.timeAdvance, 'point.timeAdvance');
  const linkedFromPointId = world.linkedFromPointId == null ? null : idOf(world.linkedFromPointId, 'point.linkedFromPointId');
  if (world.kind === 'normal') {
    if (linkedFromPointId !== null || timeAdvance.boundary !== 'elapsed') {
      refuse('semantic_invalid', 'normal point must start a round');
    }
  } else if (linkedFromPointId !== previousPointId || timeAdvance.boundary !== 'instant') {
    refuse('semantic_invalid', 'associated point needs an instant predecessor boundary');
  }
  if (world.kind === 'instant' && timeAdvance.duration.amount !== 0) {
    refuse('semantic_invalid', 'instant settlement duration must be zero');
  }
  if (world.entityDeltas == null || typeof world.entityDeltas !== 'object' || Array.isArray(world.entityDeltas)) {
    refuse('semantic_invalid', 'point.entityDeltas must be an object');
  }
}

/** Validate one committed point and return the contract-normalized value:
 * explicit time fields, normalized entity deltas and the same entity order. */
export function normalizeTimelinePoint(value: unknown): TimelinePoint {
  const point = recordOf(value, 'point') as unknown as TimelinePoint;
  validatePointShape(point);
  const entityDeltas: Record<Id, EntityDelta> = {};
  for (const [entityId, delta] of Object.entries(point.entityDeltas)) {
    entityDeltas[entityId] = normalizeEntityDelta(delta, entityId);
  }
  return {
    worldId: point.worldId,
    id: point.id,
    sequence: point.sequence,
    kind: point.kind,
    previousPointId: point.previousPointId,
    roundId: point.roundId,
    advanceId: point.advanceId,
    trigger: point.trigger,
    linkedFromPointId: point.linkedFromPointId ?? null,
    timeAdvance: normalizeTimeAdvance(point.timeAdvance, 'point.timeAdvance'),
    entityDeltas,
  };
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
    if (task.parentTaskId == null || (!merged[task.parentTaskId] && !added.has(task.parentTaskId))) {
      throw new KernelViolation('id_unresolved', `new task ${task.id} has unknown parent ${task.parentTaskId}`);
    }
    merged[task.id] = clone(task);
  }
  return merged;
}

export function applyPoint(state: WorldState, point: TimelinePoint): WorldState {
  const normalizedPoint = normalizeTimelinePoint(point);
  const locations = Object.fromEntries(Object.entries(state.locations).map(([key, value]) => [key, clone(value)]));
  const items = Object.fromEntries(Object.entries(state.items).map(([key, value]) => [key, clone(value)]));
  const characters = Object.fromEntries(Object.entries(state.characters).map(([key, value]) => [key, clone(value)]));
  const deltas = normalizedPoint.entityDeltas;
  const newPositions: Record<Id, Position> = {};
  for (const [entityId, delta] of Object.entries(deltas)) {
    if (delta.positionSet != null) newPositions[entityId] = delta.positionSet;
  }
  if (Object.keys(newPositions).length) checkPositions(state, newPositions);
  for (const [entityId, delta] of Object.entries(deltas)) {
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
    time: advanceTime(state.time, normalizedPoint.timeAdvance),
    locations,
    items,
    characters,
  };
}

/** Replay committed points over a start state, exactly like Python
 * `replay_world`: each point is validated by `applyPoint`; the start state is
 * never mutated. */
export function replayWorld(start: WorldState, points: TimelinePoint[]): WorldState {
  let state = start;
  for (const point of points) state = applyPoint(state, point);
  return state;
}

/** Merge one point's settlement units (named groups plus the optional
 * time-scan unit) exactly as the Python `point_entity_deltas`: collapse
 * added-and-achieved task ids, reject conflicting positions/sanity and emit
 * the normalized `EntityDelta` projection used by the point digest. */
export function pointEntityDeltas(groups: SettlementGroup[], timeScan: SettlementGroup | null): Record<Id, EntityDelta> {
  const units = (timeScan ? [...groups, timeScan] : [...groups]).map(normalizeSettlementGroup);
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
        if (position && !positionsEqual(position, unitPosition)) {
          throw new KernelViolation('position_invalid', `${entityId} receives conflicting positions in one point`);
        }
        position = unitPosition;
      }
      appearances.push(...(unit.appearances[entityId] ?? []));
      personalities.push(...(unit.personalities[entityId] ?? []));
      if (unit.sanities[entityId] !== undefined) {
        if (sanity !== null && sanity !== unit.sanities[entityId]) {
          throw new KernelViolation('semantic_invalid', `${entityId} receives conflicting sanity values in one point`);
        }
        sanity = unit.sanities[entityId];
      }
      for (const taskId of unit.tasksAchieved[entityId] ?? []) achieved.add(taskId);
      added.push(...(unit.subtasksAdded[entityId] ?? []));
    }
    const addedIds = new Set(added.map((task) => task.id));
    const collapsedAchieved = [...achieved].filter((taskId) => !addedIds.has(taskId));
    const mergedAdded = added.map((task) => achieved.has(task.id) ? { ...task, status: 'achieved' as const } : task);
    deltas[entityId] = normalizeEntityDelta({
      entityId,
      positionSet: position,
      appearanceChanges: appearances,
      personalityChanges: personalities,
      sanitySet: sanity,
      tasksAchieved: collapsedAchieved,
      subtasksAdded: mergedAdded,
    }, entityId);
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

/** Initial-state helper kept for callers that only have the opening
 * projection. Full static files go through `world-loader`. */
export function validateStaticWorld(value: unknown): string[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ['world is not an object'];
  const world = value as Record<string, unknown>;
  if (world.engineVersion !== 'world-engine-v1') return ['unsupported engineVersion'];
  if (world.schemaVersion !== 1) return ['unsupported schemaVersion'];
  if (!world.initial) return ['missing initial state'];
  const errors = validateInitialTemplate(world.initial);
  if (errors.length) return errors;
  const initial = normalizeInitialState(world.initial);
  for (const field of ['locations', 'items', 'characters'] as const) {
    const table = world[field];
    if (!table || typeof table !== 'object' || Array.isArray(table)) {
      errors.push(`missing ${field} table`);
      continue;
    }
    if (canonicalJson(Object.keys(table).sort()) !== canonicalJson(Object.keys(initial[field]).sort())) {
      errors.push(`${field} registry differs from the initial state`);
    }
  }
  return errors;
}
