/** WorldState -> structured narration projection.
 *
 * This is the runtime adapter the data-side conversion never had. It follows
 * the source rows' collection rules, not the old browser prototype:
 *   - changed entities all enter;
 *   - characters enter when they share the viewpoint's innermost location
 *     after the round;
 *   - locations are dependencies of those characters and changed entities,
 *     plus their immediate parents;
 *   - only changed items enter (never every item in the same room);
 *   - the state block is the BEFORE state; the after state appears only in
 *     the result block, changed entities and changed fields only.
 *
 * The projection contains no reference narrative and no evaluation label.
 */
import type {
  Change, EntityDelta, Id, StoredChange, Task, TimeAdvance, WorldState,
} from '../../types';
import { compareCodePoints } from './code-points';
import {
  ancestorLocationIds, entityKind, entityName, innermostLocationId, parentLocationName,
  positionText,
} from './position';
import {
  DEFAULT_NARRATION_PROJECTION_POLICY,
  NarrationInputError,
  type NarrationEntitySets,
  type NarrationLengthPolicy,
  type NarrationProjection,
  type NarrationProjectionPolicy,
  type OmittedField,
  type ProjectNarrationInputResult,
  type RowDelta,
  type RowDeltaOps,
  type RowItem,
  type RowLocation,
  type RowPerson,
  type RowResultItem,
  type RowResultLocation,
  type RowResultPerson,
  type RowResultState,
  type RowState,
  type RowTask,
  type RowTasks,
} from './types';

export interface ProjectNarrationInputArgs {
  before: WorldState;
  after: WorldState;
  delta: Record<Id, EntityDelta>;
  timeAdvance: TimeAdvance;
  viewpointId: Id;
  policy?: Partial<NarrationProjectionPolicy> & { length?: Partial<NarrationLengthPolicy> };
}

const TIME_UNITS: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

function mergePolicy(policy: ProjectNarrationInputArgs['policy']): NarrationProjectionPolicy {
  const base = DEFAULT_NARRATION_PROJECTION_POLICY;
  const locationParentDepth = policy?.locationParentDepth ?? base.locationParentDepth;
  if (!Number.isInteger(locationParentDepth) || locationParentDepth < 0) {
    throw new NarrationInputError('invalid_projection', 'locationParentDepth must be a non-negative integer', {
      locationParentDepth,
    });
  }
  const maxChars = policy?.length?.maxChars ?? base.length.maxChars;
  const maxUtf8Bytes = policy?.length?.maxUtf8Bytes ?? base.length.maxUtf8Bytes;
  for (const [name, value] of [['maxChars', maxChars], ['maxUtf8Bytes', maxUtf8Bytes]] as const) {
    if (value !== null && (!Number.isInteger(value) || value <= 0)) {
      throw new NarrationInputError('invalid_projection', `${name} must be a positive integer or null`, { [name]: value });
    }
  }
  return {
    locationParentDepth,
    length: { maxChars, maxUtf8Bytes },
  };
}

function activeTexts(changes: StoredChange[]): string[] {
  return changes.filter((change) => change.active && typeof change.text === 'string' && change.text.length > 0)
    .map((change) => change.text as string);
}

function joinedTexts(initial: string, changes: StoredChange[]): string[] {
  const texts = activeTexts(changes);
  return initial.length > 0 ? [initial, ...texts] : texts;
}

function rowTask(task: Task): RowTask {
  return { 目标: task.goal, 状态: task.status === 'achieved' ? '已完成' : '未完成' };
}

function rowTasks(state: WorldState, entityId: Id): RowTasks | null {
  const tasks = Object.values(state.characters[entityId]?.tasks ?? {});
  if (tasks.length === 0) return null;
  const roots = tasks.filter((task) => task.parentTaskId == null);
  if (roots.length !== 1) {
    throw new NarrationInputError('multiple_task_roots', `character ${entityId} has ${roots.length} task roots`, {
      entityId,
      rootTaskIds: roots.map((task) => task.id),
    });
  }
  return {
    大任务: rowTask(roots[0]),
    小任务: tasks.filter((task) => task.parentTaskId != null).map(rowTask),
  };
}

function rowPerson(state: WorldState, entityId: Id): RowPerson {
  const initial = state.initial.characters[entityId];
  const live = state.characters[entityId];
  if (!initial || !live) {
    throw new NarrationInputError('invalid_projection', `character ${entityId} is missing from the state`, { entityId });
  }
  return {
    位置: positionText(state, entityId),
    精神值: live.sanity,
    外貌: joinedTexts(initial.initialAppearance, live.appearanceChanges),
    个性: joinedTexts(initial.initialPersonality, live.personalityChanges),
    任务: rowTasks(state, entityId),
  };
}

function rowLocation(state: WorldState, entityId: Id): RowLocation {
  const initial = state.initial.locations[entityId];
  const live = state.locations[entityId];
  if (!initial || !live) {
    throw new NarrationInputError('invalid_projection', `location ${entityId} is missing from the state`, { entityId });
  }
  return {
    位于: parentLocationName(state, entityId),
    外貌: joinedTexts(initial.initialAppearance, live.appearanceChanges),
  };
}

function rowItem(state: WorldState, entityId: Id): RowItem {
  const initial = state.initial.items[entityId];
  const live = state.items[entityId];
  if (!initial || !live) {
    throw new NarrationInputError('invalid_projection', `item ${entityId} is missing from the state`, { entityId });
  }
  return {
    位置: positionText(state, entityId),
    外貌: joinedTexts(initial.initialAppearance, live.appearanceChanges),
  };
}

function sortIdsByName(state: WorldState, ids: Iterable<Id>): Id[] {
  return [...new Set(ids)].sort((left, right) => compareCodePoints(
    entityName(state.initial, left),
    entityName(state.initial, right),
  ));
}

function hasEffectiveOps(delta: EntityDelta): boolean {
  return delta.positionSet != null
    || delta.sanitySet != null
    || (delta.appearanceChanges?.length ?? 0) > 0
    || (delta.personalityChanges?.length ?? 0) > 0
    || (delta.tasksAchieved?.length ?? 0) > 0
    || (delta.subtasksAdded?.length ?? 0) > 0;
}

function sameStrings(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function assertChangeShape(change: Change, entityId: Id, field: 'appearanceChanges' | 'personalityChanges'): void {
  if (!change || typeof change.id !== 'string' || change.id.length === 0) {
    throw new NarrationInputError('invalid_projection', `${entityId} has a change without an id`, { entityId, field });
  }
  if (change.text !== null && typeof change.text !== 'string') {
    throw new NarrationInputError('invalid_projection', `${entityId} change ${change.id} has a non-string text`, { entityId, field, changeId: change.id });
  }
  if (change.text === null && (!change.supersedes || change.supersedes.length === 0)) {
    throw new NarrationInputError('pure_removal_without_supersedes', `${entityId} change ${change.id} removes nothing`, {
      entityId, field, changeId: change.id,
    });
  }
  if (new Set(change.supersedes ?? []).size !== (change.supersedes ?? []).length) {
    throw new NarrationInputError('invalid_projection', `${entityId} change ${change.id} repeats a supersede target`, {
      entityId, field, changeId: change.id,
    });
  }
}

function storedChangeField(
  state: WorldState,
  entityId: Id,
  field: 'appearanceChanges' | 'personalityChanges',
): StoredChange[] {
  const entity = state.characters[entityId] ?? state.items[entityId] ?? state.locations[entityId];
  if (!entity) {
    throw new NarrationInputError('invalid_projection', `entity ${entityId} is missing from the state`, { entityId });
  }
  const changes = (entity as { appearanceChanges?: StoredChange[]; personalityChanges?: StoredChange[] })[field];
  return changes ?? [];
}

function assertSettledChange(
  before: WorldState, after: WorldState, entityId: Id,
  field: 'appearanceChanges' | 'personalityChanges', change: Change,
): void {
  const stored = storedChangeField(after, entityId, field).find((entry) => entry.id === change.id);
  if (!stored || !stored.active || stored.text !== change.text || !sameStrings(stored.supersedes, change.supersedes ?? [])) {
    throw new NarrationInputError('after_mismatch', `${entityId} ${field} change ${change.id} is not the settled value`, {
      entityId, field, changeId: change.id,
    });
  }
  for (const target of change.supersedes ?? []) {
    const previous = storedChangeField(before, entityId, field).find((entry) => entry.id === target && entry.active);
    if (!previous) {
      throw new NarrationInputError('unresolved_supersedes', `${entityId} ${field} change ${change.id} supersedes unknown ${target}`, {
        entityId, field, changeId: change.id, supersededId: target,
      });
    }
  }
}

function assertSettled(before: WorldState, after: WorldState, delta: Record<Id, EntityDelta>): void {
  for (const [entityId, ops] of Object.entries(delta)) {
    const kind = entityKind(before.initial, entityId);
    if (!after.initial.characters[entityId] && !after.initial.items[entityId] && !after.initial.locations[entityId]) {
      throw new NarrationInputError('invalid_projection', `after state lost entity ${entityId}`, { entityId });
    }
    if (kind === 'location') {
      if (ops.positionSet != null || ops.sanitySet != null || (ops.personalityChanges?.length ?? 0)
        || (ops.tasksAchieved?.length ?? 0) || (ops.subtasksAdded?.length ?? 0)) {
        throw new NarrationInputError('field_not_allowed', `location ${entityId} only accepts appearance changes`, { entityId });
      }
    }
    if (kind === 'item') {
      if (ops.sanitySet != null || (ops.personalityChanges?.length ?? 0)
        || (ops.tasksAchieved?.length ?? 0) || (ops.subtasksAdded?.length ?? 0)) {
        throw new NarrationInputError('field_not_allowed', `item ${entityId} only accepts position and appearance changes`, { entityId });
      }
      if (ops.positionSet != null) {
        const settled = after.items[entityId]?.position;
        if (!settled || JSON.stringify(settled) !== JSON.stringify(ops.positionSet)) {
          throw new NarrationInputError('after_mismatch', `item ${entityId} position does not reflect the delta`, { entityId });
        }
      }
    }
    if (kind === 'character') {
      const settled = after.characters[entityId];
      if (!settled) {
        throw new NarrationInputError('invalid_projection', `character ${entityId} is missing from the after state`, { entityId });
      }
      if (ops.positionSet != null && JSON.stringify(settled.position) !== JSON.stringify(ops.positionSet)) {
        throw new NarrationInputError('after_mismatch', `character ${entityId} position does not reflect the delta`, { entityId });
      }
      if (ops.sanitySet != null && settled.sanity !== ops.sanitySet) {
        throw new NarrationInputError('after_mismatch', `character ${entityId} sanity does not reflect the delta`, { entityId });
      }
    }
    for (const change of ops.appearanceChanges ?? []) {
      assertChangeShape(change, entityId, 'appearanceChanges');
      assertSettledChange(before, after, entityId, 'appearanceChanges', change);
    }
    for (const change of ops.personalityChanges ?? []) {
      assertChangeShape(change, entityId, 'personalityChanges');
      assertSettledChange(before, after, entityId, 'personalityChanges', change);
    }
    for (const taskId of ops.tasksAchieved ?? []) {
      const task = after.characters[entityId]?.tasks[taskId];
      if (!task || task.status !== 'achieved') {
        throw new NarrationInputError('after_mismatch', `task ${taskId} is not achieved in the after state`, { entityId, taskId });
      }
    }
    for (const task of ops.subtasksAdded ?? []) {
      const settled = after.characters[entityId]?.tasks[task.id];
      if (!settled || settled.goal !== task.goal || settled.parentTaskId !== task.parentTaskId
        || settled.status !== task.status) {
        throw new NarrationInputError('after_mismatch', `new task ${task.id} is missing or different in the after state`, {
          entityId, taskId: task.id,
        });
      }
    }
  }
}

function assertUniqueNames(state: WorldState, ids: Iterable<Id>): void {
  const byName = new Map<string, Id[]>();
  for (const id of new Set(ids)) {
    const name = entityName(state.initial, id);
    const list = byName.get(name) ?? [];
    list.push(id);
    byName.set(name, list);
  }
  for (const [name, list] of byName) {
    if (list.length > 1) {
      throw new NarrationInputError('duplicate_name', `entities share the name ${name}`, { name, entityIds: list });
    }
  }
}

function collectIncludedLocations(
  before: WorldState, after: WorldState, policy: NarrationProjectionPolicy,
  changed: Set<Id>, characters: Iterable<Id>, items: Iterable<Id>, viewRoom: Id,
): Set<Id> {
  const seeds = new Set<Id>([viewRoom]);
  for (const id of characters) {
    seeds.add(innermostLocationId(before, id));
    seeds.add(innermostLocationId(after, id));
  }
  for (const id of items) {
    if (before.items[id]) seeds.add(innermostLocationId(before, id));
    if (after.items[id]) seeds.add(innermostLocationId(after, id));
  }
  for (const id of changed) if (before.initial.locations[id]) seeds.add(id);
  const included = new Set<Id>(seeds);
  for (const seed of seeds) {
    let frontier = [seed];
    for (let depth = 0; depth < policy.locationParentDepth; depth += 1) {
      const next: Id[] = [];
      for (const locationId of frontier) {
        const parent = before.initial.locations[locationId]?.parentLocationId
          ?? after.initial.locations[locationId]?.parentLocationId
          ?? null;
        if (parent && !included.has(parent)) {
          included.add(parent);
          next.push(parent);
        } else if (parent) {
          next.push(parent);
        }
      }
      frontier = next;
    }
  }
  return included;
}

function resolveRemovedTexts(
  state: WorldState, entityId: Id, field: 'appearanceChanges' | 'personalityChanges',
  changes: Change[],
): string[] {
  const stored = storedChangeField(state, entityId, field);
  const texts: string[] = [];
  for (const change of changes) {
    for (const target of change.supersedes ?? []) {
      const previous = stored.find((entry) => entry.id === target && entry.active);
      if (!previous) {
        throw new NarrationInputError('unresolved_supersedes', `${entityId} ${field} cannot resolve ${target}`, {
          entityId, field, supersededId: target,
        });
      }
      if (typeof previous.text === 'string' && previous.text.length > 0) texts.push(previous.text);
    }
  }
  return texts;
}

function buildRowDelta(
  before: WorldState, after: WorldState, delta: Record<Id, EntityDelta>, timeAdvance: TimeAdvance,
): RowDelta {
  if (!Number.isFinite(timeAdvance.duration.amount)) {
    throw new NarrationInputError('invalid_time', 'time advance amount is not finite', { timeAdvance });
  }
  const unit = TIME_UNITS[timeAdvance.duration.unit];
  if (!unit) {
    throw new NarrationInputError('invalid_time', `unknown time unit ${String(timeAdvance.duration.unit)}`, { timeAdvance });
  }
  const changes: Record<string, RowDeltaOps> = {};
  const ordered = Object.keys(delta).sort((left, right) => compareCodePoints(
    entityName(before.initial, left),
    entityName(before.initial, right),
  ));
  for (const entityId of ordered) {
    const ops = delta[entityId];
    if (!hasEffectiveOps(ops)) continue;
    if (!before.characters[entityId] && !before.items[entityId] && !before.locations[entityId]) {
      throw new NarrationInputError('invalid_projection', `delta entity ${entityId} is missing from the before state`, { entityId });
    }
    const rendered: RowDeltaOps = {};
    if (ops.positionSet != null) rendered.位置 = positionText(after, entityId);
    if (ops.sanitySet != null) {
      const sanity = after.characters[entityId]?.sanity;
      if (sanity == null) {
        throw new NarrationInputError('after_mismatch', `character ${entityId} has no settled sanity`, { entityId });
      }
      rendered.精神值 = sanity;
    }
    const removedAppearance = resolveRemovedTexts(before, entityId, 'appearanceChanges', ops.appearanceChanges ?? []);
    const addedAppearance = (ops.appearanceChanges ?? []).filter((change) => change.text != null)
      .map((change) => change.text as string);
    if (removedAppearance.length) rendered.解除外貌 = removedAppearance;
    if (addedAppearance.length) rendered.新增外貌 = addedAppearance;
    const removedPersonality = resolveRemovedTexts(before, entityId, 'personalityChanges', ops.personalityChanges ?? []);
    const addedPersonality = (ops.personalityChanges ?? []).filter((change) => change.text != null)
      .map((change) => change.text as string);
    if (removedPersonality.length) rendered.解除个性 = removedPersonality;
    if (addedPersonality.length) rendered.新增个性 = addedPersonality;
    if (ops.tasksAchieved?.length) {
      rendered.完成任务 = ops.tasksAchieved.map((taskId) => {
        const task = after.characters[entityId]?.tasks[taskId];
        if (!task) {
          throw new NarrationInputError('after_mismatch', `task ${taskId} is missing from the after state`, { entityId, taskId });
        }
        return task.goal;
      });
    }
    if (ops.subtasksAdded?.length) rendered.新增小任务 = ops.subtasksAdded.map((task) => ({ 目标: task.goal }));
    changes[entityName(before.initial, entityId)] = rendered;
  }
  return { 时间推进: `${timeAdvance.duration.amount} ${unit}`, 变化: changes };
}

function buildRowResult(
  before: WorldState, after: WorldState, delta: Record<Id, EntityDelta>,
  beforeState: RowState,
): RowResultState {
  const result: RowResultState = {};
  for (const [entityId, ops] of Object.entries(delta)) {
    if (!hasEffectiveOps(ops)) continue;
    const kind = entityKind(before.initial, entityId);
    const name = entityName(before.initial, entityId);
    const inBefore = Boolean(beforeState.人物[name] ?? beforeState.地点[name] ?? beforeState.物品[name]);
    if (!inBefore) {
      throw new NarrationInputError('invalid_projection', `result entity ${name} is not in the before projection`, { entityId });
    }
    if (kind === 'character') {
      const view: RowResultPerson = {};
      if (ops.positionSet != null) view.位置 = positionText(after, entityId);
      if (ops.sanitySet != null) {
        const sanity = after.characters[entityId]?.sanity;
        if (sanity == null) {
          throw new NarrationInputError('after_mismatch', `character ${entityId} has no settled sanity`, { entityId });
        }
        view.精神值 = sanity;
      }
      if ((ops.appearanceChanges?.length ?? 0) > 0) {
        const initial = after.initial.characters[entityId].initialAppearance;
        view.外貌 = joinedTexts(initial, after.characters[entityId].appearanceChanges);
      }
      if ((ops.personalityChanges?.length ?? 0) > 0) {
        const initial = after.initial.characters[entityId].initialPersonality;
        view.个性 = joinedTexts(initial, after.characters[entityId].personalityChanges);
      }
      if ((ops.tasksAchieved?.length ?? 0) > 0 || (ops.subtasksAdded?.length ?? 0) > 0) {
        const taskIds = [...new Set([...(ops.tasksAchieved ?? []), ...(ops.subtasksAdded ?? []).map((task) => task.id)])];
        const tasks = after.characters[entityId].tasks;
        let root: RowTask | undefined;
        const small: NonNullable<NonNullable<RowResultPerson['任务']>['小任务']> = [];
        for (const taskId of taskIds) {
          const task = tasks[taskId];
          if (!task) {
            throw new NarrationInputError('after_mismatch', `task ${taskId} is missing from the after state`, { entityId, taskId });
          }
          if (task.parentTaskId == null) {
            if (root) {
              throw new NarrationInputError('multiple_task_roots', `result for ${entityId} changes more than one root task`, {
                entityId, taskIds,
              });
            }
            root = rowTask(task);
          } else {
            const parent = tasks[task.parentTaskId];
            if (!parent) {
              throw new NarrationInputError('after_mismatch', `task ${task.id} has unknown parent ${task.parentTaskId}`, {
                entityId, taskId: task.id, parentTaskId: task.parentTaskId,
              });
            }
            small.push({ ...rowTask(task), 属于大任务: parent.goal });
          }
        }
        view.任务 = {};
        if (root) view.任务.大任务 = root;
        if (small.length) view.任务.小任务 = small;
      }
      if (Object.keys(view).length > 0) result[name] = view;
    } else if (kind === 'item') {
      const view: RowResultItem = {};
      if (ops.positionSet != null) view.位置 = positionText(after, entityId);
      if ((ops.appearanceChanges?.length ?? 0) > 0) {
        view.外貌 = joinedTexts(after.initial.items[entityId].initialAppearance, after.items[entityId].appearanceChanges);
      }
      if (Object.keys(view).length > 0) result[name] = view;
    } else {
      const view: RowResultLocation = {};
      if ((ops.appearanceChanges?.length ?? 0) > 0) {
        view.外貌 = joinedTexts(after.initial.locations[entityId].initialAppearance, after.locations[entityId].appearanceChanges);
      }
      if (Object.keys(view).length > 0) result[name] = view;
    }
  }
  return result;
}

function entitySetsFrom(
  characters: Iterable<Id>, locations: Iterable<Id>, items: Iterable<Id>,
): NarrationEntitySets {
  return { characters: [...characters], locations: [...locations], items: [...items] };
}

export function projectNarrationInput(args: ProjectNarrationInputArgs): ProjectNarrationInputResult {
  const { before, after, delta, timeAdvance, viewpointId } = args;
  const policy = mergePolicy(args.policy);
  entityKind(before.initial, viewpointId);
  if (!before.initial.characters[viewpointId]) {
    throw new NarrationInputError('invalid_projection', `viewpoint ${viewpointId} is not a character`, { viewpointId });
  }
  if (!before.characters[viewpointId] || !after.characters[viewpointId]) {
    throw new NarrationInputError('invalid_projection', `viewpoint ${viewpointId} is missing from a state`, { viewpointId });
  }
  assertSettled(before, after, delta);

  const effectiveChanged = new Set<Id>(Object.keys(delta).filter((id) => hasEffectiveOps(delta[id])));
  const viewRoom = innermostLocationId(after, viewpointId);
  const visibleCharacters = sortIdsByName(after, Object.keys(after.characters)
    .filter((id) => innermostLocationId(after, id) === viewRoom));
  const visibleItems = sortIdsByName(after, Object.keys(after.items)
    .filter((id) => innermostLocationId(after, id) === viewRoom));
  const visibleLocations = sortIdsByName(after, [viewRoom, ...ancestorLocationIds(after, viewRoom)]);

  const includedCharacters = new Set<Id>(visibleCharacters);
  includedCharacters.add(viewpointId);
  for (const id of effectiveChanged) if (after.initial.characters[id]) includedCharacters.add(id);
  const includedItems = new Set<Id>();
  for (const id of effectiveChanged) if (after.initial.items[id]) includedItems.add(id);
  const includedLocations = collectIncludedLocations(
    before, after, policy, effectiveChanged, includedCharacters, includedItems, viewRoom,
  );

  assertUniqueNames(before, [
    ...includedCharacters, ...includedItems, ...includedLocations, ...effectiveChanged,
  ]);

  const beforeState: RowState = { 地点: {}, 人物: {}, 物品: {} };
  for (const id of sortIdsByName(before, includedLocations)) {
    beforeState.地点[entityName(before.initial, id)] = rowLocation(before, id);
  }
  for (const id of sortIdsByName(before, includedCharacters)) {
    beforeState.人物[entityName(before.initial, id)] = rowPerson(before, id);
  }
  for (const id of sortIdsByName(before, includedItems)) {
    beforeState.物品[entityName(before.initial, id)] = rowItem(before, id);
  }
  const rowDelta = buildRowDelta(before, after, delta, timeAdvance);
  const resultState = buildRowResult(before, after, delta, beforeState);

  const omittedFields: OmittedField[] = [];
  for (const id of Object.keys(before.initial.characters)) {
    if (includedCharacters.has(id)) continue;
    omittedFields.push({
      entityId: id,
      entityName: entityName(before.initial, id),
      entityType: 'character',
      field: 'entity',
      reason: 'character_outside_scene',
      originalValue: null,
    });
  }
  for (const id of Object.keys(before.initial.items)) {
    if (includedItems.has(id)) continue;
    omittedFields.push({
      entityId: id,
      entityName: entityName(before.initial, id),
      entityType: 'item',
      field: 'entity',
      reason: 'item_not_changed',
      originalValue: null,
    });
  }
  const visibleLocationSet = new Set(visibleLocations);
  for (const id of Object.keys(before.initial.locations)) {
    if (includedLocations.has(id)) continue;
    omittedFields.push({
      entityId: id,
      entityName: entityName(before.initial, id),
      entityType: 'location',
      field: 'entity',
      reason: visibleLocationSet.has(id) ? 'location_visible_but_not_a_state_dependency' : 'location_not_referenced',
      originalValue: null,
    });
  }
  for (const [entityId, ops] of Object.entries(delta)) {
    if (!hasEffectiveOps(ops)) {
      omittedFields.push({
        entityId,
        entityName: entityName(before.initial, entityId),
        entityType: 'unknown',
        field: '*',
        reason: 'unknown_or_null_delta_field',
        originalValue: null,
      });
      continue;
    }
    const name = entityName(before.initial, entityId);
    const kind = entityKind(before.initial, entityId);
    const result = resultState[name] as Record<string, unknown> | undefined;
    const fields = kind === 'character'
      ? ['位置', '精神值', '外貌', '个性', '任务']
      : kind === 'item' ? ['位置', '外貌'] : ['外貌'];
    for (const field of fields) {
      if (!result || !(field in result)) {
        omittedFields.push({
          entityId,
          entityName: name,
          entityType: kind,
          field,
          reason: 'field_not_changed',
          originalValue: null,
        });
      }
    }
  }

  const projection: NarrationProjection = {
    projectionVersion: 'narration-projection-v1',
    viewpoint: {
      id: viewpointId,
      name: entityName(before.initial, viewpointId),
      text: `主角视角（${entityName(before.initial, viewpointId)}）；只表达已结算的世界事实`,
    },
    beforeState,
    delta: rowDelta,
    resultState,
    policy,
  };

  return {
    projection,
    includedEntities: entitySetsFrom(
      sortIdsByName(before, includedCharacters),
      sortIdsByName(before, includedLocations),
      sortIdsByName(before, includedItems),
    ),
    visibleEntities: entitySetsFrom(visibleCharacters, visibleLocations, visibleItems),
    omittedFields,
    version: {
      projectionVersion: 'narration-projection-v1',
      legacySerializerVersion: 'yuyan-prose-legacy-v1',
      resultSerializerVersion: 'yuyan-prose-result-v2',
    },
  };
}

export { DEFAULT_NARRATION_PROJECTION_POLICY };
