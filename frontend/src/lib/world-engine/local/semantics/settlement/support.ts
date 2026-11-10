/** Read-only state projections and local id allocation for settlement.
 *
 * Nothing in this file is a second state authority: projectStage() is used
 * only to compose the next stage's prompt and to reject candidates before the
 * controller's own preview_point calls applyPoint on the authoritative copy.
 */
import type { Change, EntityDelta, Id, Json, Position, StoredChange, Task, WorldState } from '../../../types';
import { applyPoint, buildTimelinePoint, clone } from '../../state';
import { activeText, locationName } from '../../prompt';

export const SETTLEMENT_STAGES = ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'] as const;
export type SettlementStage = typeof SETTLEMENT_STAGES[number];

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

export function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

export function asIdList(value: unknown): Id[] {
  return Array.isArray(value) ? value.filter((item): item is Id => typeof item === 'string' && item.trim().length > 0) : [];
}

export function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function asInteger(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) ? value : null;
}

export function toJson(value: unknown): Json {
  return JSON.parse(JSON.stringify(value)) as Json;
}

export function errorText(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error);
}

export function stripCodeFence(raw: string): string {
  return raw.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/i, '').trim();
}

/** Parse the first complete JSON object/array in a free-form answer. Small
 * models often add a short lead-in even when constrained; the controller's
 * JSON decoder stays the final gate for its own tasks, but this lane needs to
 * inspect semantic coverage before returning a candidate. */
export function parseJsonValue(raw: string): unknown {
  const text = stripCodeFence(raw);
  const objectStart = text.indexOf('{');
  const arrayStart = text.indexOf('[');
  let start = -1;
  let close = '';
  if (objectStart >= 0 && (arrayStart < 0 || objectStart < arrayStart)) {
    start = objectStart;
    close = '}';
  } else if (arrayStart >= 0) {
    start = arrayStart;
    close = ']';
  }
  if (start < 0) throw new Error('model output is not JSON');
  const end = text.lastIndexOf(close);
  if (end <= start) throw new Error('model output is incomplete JSON');
  return JSON.parse(text.slice(start, end + 1)) as unknown;
}

export function roster(state: WorldState): Id[] {
  return Object.keys(state.characters).sort();
}

export function movableIds(state: WorldState): Id[] {
  return [...Object.keys(state.items), ...Object.keys(state.characters)].sort();
}

export function allEntityIds(state: WorldState): Id[] {
  return [...Object.keys(state.locations), ...Object.keys(state.items), ...Object.keys(state.characters)].sort();
}

export function allTasks(state: WorldState): { ownerId: Id; task: Task }[] {
  const rows: { ownerId: Id; task: Task }[] = [];
  for (const ownerId of Object.keys(state.characters).sort()) {
    for (const task of Object.values(state.characters[ownerId].tasks).sort((a, b) => a.id.localeCompare(b.id))) {
      rows.push({ ownerId, task });
    }
  }
  return rows;
}

export function taskIndex(state: WorldState): Map<Id, { ownerId: Id; task: Task }> {
  const index = new Map<Id, { ownerId: Id; task: Task }>();
  for (const row of allTasks(state)) index.set(row.task.id, row);
  return index;
}

export function currentAchieved(state: WorldState): Set<Id> {
  const achieved = new Set<Id>();
  for (const { task } of allTasks(state)) if (task.status === 'achieved') achieved.add(task.id);
  return achieved;
}

export function activeRecords(state: WorldState, kind: 'appearance' | 'personality', entityId: Id): StoredChange[] {
  if (kind === 'appearance') {
    return state.locations[entityId]?.appearanceChanges
      ?? state.items[entityId]?.appearanceChanges
      ?? state.characters[entityId]?.appearanceChanges
      ?? [];
  }
  return state.characters[entityId]?.personalityChanges ?? [];
}

export function activeRecordText(records: StoredChange[]): string[] {
  return activeText(records);
}

export function containerLabel(state: WorldState, entityId: Id): string {
  const position = state.items[entityId]?.position ?? state.characters[entityId]?.position;
  if (!position) return '（无位置）';
  const base = `${locationName(state, position.containerId)}${position.slotId ? `/${position.slotId}` : ''}`;
  return position.relativeTo ? `${base}（${position.relativeTo.relation} ${locationName(state, position.relativeTo.entityId)}）` : base;
}

export function positionLine(state: WorldState, entityId: Id): string {
  const kind = state.characters[entityId] ? '人物' : '物品';
  const name = state.initial.characters[entityId]?.name ?? state.initial.items[entityId]?.name ?? entityId;
  return `- ${name}（id=${entityId}，${kind}）当前位置=${containerLabel(state, entityId)}`;
}

export function appearanceLine(state: WorldState, entityId: Id): string {
  const initial = state.initial.locations[entityId]?.initialAppearance
    ?? state.initial.items[entityId]?.initialAppearance
    ?? state.initial.characters[entityId]?.initialAppearance
    ?? '';
  const kind = state.locations[entityId] ? '地点' : state.items[entityId] ? '物品' : '人物';
  const name = state.initial.locations[entityId]?.name
    ?? state.initial.items[entityId]?.name
    ?? state.initial.characters[entityId]?.name
    ?? entityId;
  const records = activeRecords(state, 'appearance', entityId).filter((record) => record.active)
    .map((record) => `${record.id}=${record.text ?? '（已解除）'}`);
  const position = kind === '地点' ? '' : `；当前位置=${containerLabel(state, entityId)}`;
  return `- ${name}（id=${entityId}，${kind}）初始外貌=${initial}；有效变化=[${records.join('；')}]${position}`;
}

export function taskLine(state: WorldState, ownerId: Id): string {
  const name = state.initial.characters[ownerId]?.name ?? ownerId;
  const position = containerLabel(state, ownerId);
  const initial = state.initial.characters[ownerId];
  const appearance = [initial?.initialAppearance ?? '', ...activeRecordText(activeRecords(state, 'appearance', ownerId))]
    .filter(Boolean).join('；');
  const personality = [initial?.initialPersonality ?? '', ...activeRecordText(activeRecords(state, 'personality', ownerId))]
    .filter(Boolean).join('；');
  const tasks = Object.values(state.characters[ownerId]?.tasks ?? {});
  const prefix = `- ${name}（id=${ownerId}）位置=${position}；外貌=${appearance}；个性=${personality}`;
  if (!tasks.length) return `${prefix}：无任务`;
  const rows = tasks.map((task) => `${task.id}：${task.goal}（${task.status === 'achieved' ? '已完成' : '待办'}）`);
  return `${prefix}：${rows.join('；')}`;
}

export function personalityLine(state: WorldState, characterId: Id): string {
  const initial = state.initial.characters[characterId];
  const name = initial?.name ?? characterId;
  const records = activeRecords(state, 'personality', characterId).filter((record) => record.active)
    .map((record) => `${record.id}=${record.text ?? '（已解除）'}`);
  return `- ${name}（id=${characterId}）初始个性=${initial?.initialPersonality ?? ''}；有效个性变化=[${records.join('；')}]；当前理智=${state.characters[characterId]?.sanity ?? '?'}`;
}

export function taskDecisionsText(rows: { ownerId: Id; task: Task }[]): string {
  return rows.map(({ ownerId, task }) => `${ownerId}:${task.id}`).join(',');
}

export function taskParentIds(state: WorldState): Id[] {
  return allTasks(state).map(({ task }) => task.id);
}

export function maxChangeSequence(state: WorldState): number {
  let latest = -1;
  for (const entityId of Object.keys(state.items)) for (const record of state.items[entityId].appearanceChanges) latest = Math.max(latest, record.sourceSequence);
  for (const entityId of Object.keys(state.locations)) for (const record of state.locations[entityId].appearanceChanges) latest = Math.max(latest, record.sourceSequence);
  for (const entityId of Object.keys(state.characters)) {
    for (const record of state.characters[entityId].appearanceChanges) latest = Math.max(latest, record.sourceSequence);
    for (const record of state.characters[entityId].personalityChanges) latest = Math.max(latest, record.sourceSequence);
  }
  return latest;
}

export function personalityOwnersAbove(state: WorldState, sequence: number): Set<Id> {
  const owners = new Set<Id>();
  for (const id of Object.keys(state.characters)) {
    if (state.characters[id].personalityChanges.some((record) => record.active && record.sourceSequence > sequence)) owners.add(id);
  }
  return owners;
}

export function activeChangeIds(state: WorldState): Set<Id> {
  const ids = new Set<Id>();
  for (const entityId of Object.keys(state.items)) {
    for (const record of state.items[entityId].appearanceChanges) { ids.add(record.id); for (const old of record.supersedes) ids.add(old); }
  }
  for (const entityId of Object.keys(state.locations)) {
    for (const record of state.locations[entityId].appearanceChanges) { ids.add(record.id); for (const old of record.supersedes) ids.add(old); }
  }
  for (const entityId of Object.keys(state.characters)) {
    for (const record of state.characters[entityId].appearanceChanges) { ids.add(record.id); for (const old of record.supersedes) ids.add(old); }
    for (const record of state.characters[entityId].personalityChanges) { ids.add(record.id); for (const old of record.supersedes) ids.add(old); }
  }
  return ids;
}

export function allKnownTaskIds(state: WorldState): Set<Id> {
  return new Set(allTasks(state).map(({ task }) => task.id));
}

export function hasDeltaContent(delta: Partial<EntityDelta> | undefined): boolean {
  if (!delta) return false;
  return delta.positionSet != null
    || (delta.appearanceChanges?.length ?? 0) > 0
    || (delta.personalityChanges?.length ?? 0) > 0
    || delta.sanitySet != null
    || (delta.tasksAchieved?.length ?? 0) > 0
    || (delta.subtasksAdded?.length ?? 0) > 0;
}

export function hasRoundProgress(roundChanges: { entityDeltas?: Record<Id, EntityDelta> }[]): boolean {
  return roundChanges.some((point) => Object.values(point.entityDeltas ?? {}).some((delta) => hasDeltaContent(delta)));
}

/** Local projection only: uses the same browser state kernel so an illegal
 * candidate is caught here instead of failing the controller's preview. The
 * caller keeps the returned value for prompt composition; it is never stored. */
let localPointSequence = 0;

export function projectStage(state: WorldState, stage: SettlementStage, changes: Record<Id, Partial<EntityDelta>>): WorldState {
  const deltas: Record<Id, EntityDelta> = {};
  for (const [entityId, partial] of Object.entries(changes)) {
    if (!partial) continue;
    const delta: EntityDelta = { entityId };
    if (partial.positionSet !== undefined) delta.positionSet = partial.positionSet;
    if (partial.appearanceChanges !== undefined) delta.appearanceChanges = partial.appearanceChanges;
    if (partial.personalityChanges !== undefined) delta.personalityChanges = partial.personalityChanges;
    if (partial.sanitySet !== undefined) delta.sanitySet = partial.sanitySet;
    if (partial.tasksAchieved !== undefined) delta.tasksAchieved = partial.tasksAchieved;
    if (partial.subtasksAdded !== undefined) delta.subtasksAdded = partial.subtasksAdded;
    if (!hasDeltaContent(delta)) continue;
    deltas[entityId] = delta;
  }
  if (!Object.keys(deltas).length) return clone(state);
  const point = buildTimelinePoint({
    worldId: state.worldId,
    id: `local_${stage}_${++localPointSequence}`,
    sequence: 0,
    kind: 'normal',
    previousPointId: 'local',
    roundId: 'local',
    advanceId: 'local',
    trigger: 'automatic',
    linkedFromPointId: null,
    timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
    entityDeltas: deltas,
  });
  const next = applyPoint(state, point);
  next.time = clone(state.time);
  return next;
}

export function normalizeChangeText(text: string): string {
  return text.replace(/\s+/gu, '').replace(/[。！？!?；;，,、]+$/u, '').trim();
}

export function sameChangeText(a: string | null | undefined, b: string | null | undefined): boolean {
  return normalizeChangeText(a ?? '') === normalizeChangeText(b ?? '');
}

export class LocalIdAllocator {
  private sequence = 0;

  changeId(prefix: 'appearance' | 'personality', entityId: Id, used: ReadonlySet<Id>): Id {
    let id = '';
    do {
      this.sequence += 1;
      id = `${prefix}_${safeId(entityId)}_${this.sequence}`;
    } while (used.has(id));
    return id;
  }

  taskId(parentTaskId: Id | null, used: ReadonlySet<Id>): Id {
    let id = '';
    do {
      this.sequence += 1;
      id = `task_${safeId(parentTaskId ?? 'root')}_${this.sequence}`;
    } while (used.has(id));
    return id;
  }

  roundId(seed?: Id): Id {
    this.sequence += 1;
    const base = seed ? safeId(seed).slice(0, 24) : Date.now().toString(36);
    return `round_auto_${base}_${this.sequence}`;
  }
}

function safeId(value: Id): Id {
  return value.replace(/[^A-Za-z0-9_-]/gu, '_').slice(0, 40) || 'x';
}

export function taskGoalById(state: WorldState, taskId: Id): string {
  return taskIndex(state).get(taskId)?.task.goal ?? taskId;
}

type RelativeRelation = 'under' | 'above' | 'beside' | 'in_front_of' | 'behind';
const RELATIVE_RELATIONS: readonly RelativeRelation[] = ['under', 'above', 'beside', 'in_front_of', 'behind'];

export function positionFromRow(row: Record<string, unknown>): Position | null {
  const containerId = asString(row.containerId);
  if (!containerId) return null;
  const slotId = row.slotId == null ? null : asString(row.slotId) || null;
  const relative = asRecord(row.relativeTo);
  const relativeId = asString(relative.entityId);
  const relation = asString(relative.relation);
  if (relativeId && !RELATIVE_RELATIONS.includes(relation as RelativeRelation)) return null;
  return {
    containerId,
    slotId,
    relativeTo: relativeId ? { entityId: relativeId, relation: relation as RelativeRelation } : null,
  };
}

export function changeFromRow(id: Id, row: Record<string, unknown>): Change | null {
  const text = row.text == null ? null : asString(row.text) || null;
  const supersedes = asIdList(row.supersedes);
  if (text == null && supersedes.length === 0) return null;
  return { id, text, supersedes };
}
