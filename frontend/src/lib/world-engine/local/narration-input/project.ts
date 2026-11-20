/** WorldState -> the four-field narration projection.
 *
 * Collection rules follow the source rows, not the old browser prototype:
 *   - every changed entity enters (even outside the viewpoint's scene);
 *   - characters enter when they share the viewpoint's innermost location
 *     after the round;
 *   - locations are dependencies of those characters/items plus their
 *     immediate parent; slots never split a scene;
 *   - only changed items enter, never every item in the room;
 *   - the state block is the BEFORE state; the AFTER state appears only as
 *     the partial result of the changed fields.
 *
 * The result block is built from the settled AFTER state and then validated
 * by `buildResult` against the delta, so a mismatch is refused instead of
 * silently rewritten.
 */
import type {
  Change, EntityDelta, Id, Position, StoredChange, Task, TimeAdvance, WorldState,
} from '../../types';
import { compareCodePoints } from './code-points';
import {
  ancestorLocationIds, entityKind, entityName, innermostLocationId, parentLocationName,
  positionText,
} from './position';
import {
  NarrationInputError,
  type DeltaOps, type NarrationEntitySets, type NarrationProjection,
  type OmittedField, type ProjectionResult, type ProjectionState, type ResultPerson,
  type ResultState, type RowPerson, type RowTask, type RowTasks, type TaskHierarchyEntry,
  type TextCarryLimit,
} from './types';
import { narrationVersions } from './versions';

export interface ProjectNarrationInputArgs {
  before: WorldState;
  after: WorldState;
  delta: Record<Id, EntityDelta>;
  timeAdvance: TimeAdvance;
  viewpointId: Id;
}

const TIME_UNITS: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};

const SOURCE_LOCATION_PARENT_DEPTH = 1;

function activeTexts(changes: StoredChange[]): string[] {
  return changes.filter((change) => change.active && typeof change.text === 'string' && change.text.length > 0)
    .map((change) => change.text as string);
}

function joinedTexts(initial: string, changes: StoredChange[]): string[] {
  const texts = activeTexts(changes);
  return initial.length > 0 ? [initial, ...texts] : texts;
}

function hasEffectiveOps(delta: EntityDelta): boolean {
  return delta.positionSet != null
    || delta.sanitySet != null
    || (delta.appearanceChanges?.length ?? 0) > 0
    || (delta.personalityChanges?.length ?? 0) > 0
    || (delta.tasksAchieved?.length ?? 0) > 0
    || (delta.subtasksAdded?.length ?? 0) > 0;
}

function sortedIdsByName(state: WorldState, ids: Iterable<Id>): Id[] {
  return [...new Set(ids)].sort((left, right) => compareCodePoints(
    entityName(state.initial, left), entityName(state.initial, right),
  ));
}

function sameStrings(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function samePosition(left: Position | undefined, right: Position | undefined): boolean {
  if (!left || !right) return left === right;
  const leftRelative = left.relativeTo ?? null;
  const rightRelative = right.relativeTo ?? null;
  const sameRelative = leftRelative === null
    ? rightRelative === null
    : rightRelative !== null
      && leftRelative.entityId === rightRelative.entityId
      && leftRelative.relation === rightRelative.relation;
  return left.containerId === right.containerId
    && (left.slotId ?? null) === (right.slotId ?? null)
    && sameRelative;
}

function taskRows(state: WorldState, entityId: Id): RowTasks | null {
  const tasks = Object.values(state.characters[entityId]?.tasks ?? {});
  if (tasks.length === 0) return null;
  const roots = tasks.filter((task) => task.parentTaskId == null);
  if (roots.length !== 1) {
    throw new NarrationInputError('multiple_task_roots', `character ${entityId} has ${roots.length} task roots`, {
      entityId, rootTaskIds: roots.map((task) => task.id),
    });
  }
  return {
    大任务: { 目标: roots[0].goal, 状态: roots[0].status === 'achieved' ? '已完成' : '未完成' },
    小任务: tasks.filter((task) => task.parentTaskId != null).map((task) => ({
      目标: task.goal, 状态: task.status === 'achieved' ? '已完成' : '未完成',
    })),
  };
}

function taskHierarchy(state: WorldState, entityIds: Iterable<Id>): TaskHierarchyEntry[] {
  const entries: TaskHierarchyEntry[] = [];
  for (const entityId of entityIds) {
    const tasks = state.characters[entityId]?.tasks ?? {};
    const depthOf = (task: Task): number => {
      let depth = 0;
      let parentId = task.parentTaskId;
      const seen = new Set<Id>([task.id]);
      while (parentId) {
        if (seen.has(parentId)) {
          throw new NarrationInputError('position_cycle', `task parent cycle at ${parentId}`, { entityId, taskId: task.id });
        }
        seen.add(parentId);
        const parent = tasks[parentId];
        if (!parent) {
          throw new NarrationInputError('invalid_projection', `task ${task.id} has unknown parent ${parentId}`, { entityId, taskId: task.id });
        }
        depth += 1;
        parentId = parent.parentTaskId;
      }
      return depth;
    };
    for (const task of Object.values(tasks)) {
      entries.push({
        entityId,
        entityName: entityName(state.initial, entityId),
        taskId: task.id,
        goal: task.goal,
        status: task.status,
        parentTaskId: task.parentTaskId,
        parentGoal: task.parentTaskId ? tasks[task.parentTaskId]?.goal ?? null : null,
        depth: depthOf(task),
      });
    }
  }
  return entries;
}

function computeTextCarryLimits(hierarchy: TaskHierarchyEntry[], inText: Set<string>): TextCarryLimit[] {
  const limits: TextCarryLimit[] = [];
  for (const entry of hierarchy) {
    if (!inText.has(`${entry.entityId}\u0000${entry.taskId}`)) continue;
    if (entry.depth >= 1) limits.push({
      entityId: entry.entityId,
      entityName: entry.entityName,
      taskId: entry.taskId,
      goal: entry.goal,
      parentTaskId: entry.parentTaskId,
      parentGoal: entry.parentGoal,
      reason: 'task_parent_relation_not_in_v2_text',
    });
    if (entry.depth >= 2) limits.push({
      entityId: entry.entityId,
      entityName: entry.entityName,
      taskId: entry.taskId,
      goal: entry.goal,
      parentTaskId: entry.parentTaskId,
      parentGoal: entry.parentGoal,
      reason: 'task_depth_not_in_v2_text',
    });
  }
  return limits;
}

function rowPlace(state: WorldState, entityId: Id): ProjectionState['地点'][string] {
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

function rowPerson(state: WorldState, entityId: Id): RowPerson {
  const initial = state.initial.characters[entityId];
  const live = state.characters[entityId];
  if (!initial || !live) {
    throw new NarrationInputError('invalid_projection', `character ${entityId} is missing from the state`, { entityId });
  }
  const tasks = taskRows(state, entityId);
  if (!tasks?.大任务) {
    throw new NarrationInputError('empty_tasks', `character ${entityId} has no task tree to serialize`, {
      entityId, entityName: initial.name,
    });
  }
  return {
    位置: positionText(state, entityId),
    精神值: live.sanity,
    外貌: joinedTexts(initial.initialAppearance, live.appearanceChanges),
    个性: joinedTexts(initial.initialPersonality, live.personalityChanges),
    任务: tasks,
  };
}

function rowItem(state: WorldState, entityId: Id): ProjectionState['物品'][string] {
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

function collectIncludedLocations(
  before: WorldState, after: WorldState, changed: Set<Id>, characters: Iterable<Id>,
  items: Iterable<Id>, viewRoom: Id,
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
    let node: Id | null = seed;
    for (let depth = 0; depth < SOURCE_LOCATION_PARENT_DEPTH && node; depth += 1) {
      const parent: Id | null = before.initial.locations[node]?.parentLocationId
        ?? after.initial.locations[node]?.parentLocationId
        ?? null;
      if (parent) included.add(parent);
      node = parent;
    }
  }
  return included;
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
}

function storedChanges(state: WorldState, entityId: Id, field: 'appearanceChanges' | 'personalityChanges'): StoredChange[] {
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
  const stored = storedChanges(after, entityId, field).find((entry) => entry.id === change.id);
  if (!stored || !stored.active || stored.text !== change.text || !sameStrings(stored.supersedes, change.supersedes ?? [])) {
    throw new NarrationInputError('after_mismatch', `${entityId} ${field} change ${change.id} is not the settled value`, {
      entityId, field, changeId: change.id,
    });
  }
  for (const target of change.supersedes ?? []) {
    if (!storedChanges(before, entityId, field).some((entry) => entry.id === target && entry.active)) {
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
        if (!samePosition(settled, ops.positionSet)) {
          throw new NarrationInputError('after_mismatch', `item ${entityId} position does not reflect the delta`, { entityId });
        }
      }
    }
    if (kind === 'character') {
      const settled = after.characters[entityId];
      if (!settled) {
        throw new NarrationInputError('invalid_projection', `character ${entityId} is missing from the after state`, { entityId });
      }
      if (ops.positionSet != null && !samePosition(settled.position, ops.positionSet)) {
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
      if (!settled || settled.goal !== task.goal || settled.parentTaskId !== task.parentTaskId) {
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
    byName.set(name, [...(byName.get(name) ?? []), id]);
  }
  for (const [name, list] of byName) {
    if (list.length > 1) {
      throw new NarrationInputError('ambiguous_entity', `entities share the name ${name}`, { name, entityIds: list });
    }
  }
}

function resolveRemovedTexts(
  state: WorldState, entityId: Id, field: 'appearanceChanges' | 'personalityChanges',
  changes: Change[],
): string[] {
  const stored = storedChanges(state, entityId, field);
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

function buildDelta(
  before: WorldState, after: WorldState, delta: Record<Id, EntityDelta>, timeAdvance: TimeAdvance,
): NarrationProjection['本回合变化'] {
  const unit = TIME_UNITS[timeAdvance.duration.unit];
  if (!unit || !Number.isFinite(timeAdvance.duration.amount)) {
    throw new NarrationInputError('invalid_time', 'time advance is invalid', { timeAdvance });
  }
  const changes: Record<string, DeltaOps> = {};
  for (const entityId of sortedIdsByName(before, Object.keys(delta))) {
    const ops = delta[entityId];
    if (!hasEffectiveOps(ops)) continue;
    const rendered: DeltaOps = {};
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
    const addedTaskIds = new Set((ops.subtasksAdded ?? []).map((task) => task.id));
    const achieved = (ops.tasksAchieved ?? []).filter((taskId) => !addedTaskIds.has(taskId));
    if (achieved.length) {
      rendered.完成任务 = achieved.map((taskId) => {
        const task = after.characters[entityId]?.tasks[taskId];
        if (!task) {
          throw new NarrationInputError('after_mismatch', `task ${taskId} is missing from the after state`, { entityId, taskId });
        }
        return task.goal;
      });
    }
    if (ops.subtasksAdded?.length) {
      rendered.新增小任务 = ops.subtasksAdded.map((task) => {
        const settled = after.characters[entityId]?.tasks[task.id];
        if (!settled) {
          throw new NarrationInputError('after_mismatch', `new task ${task.id} is missing from the after state`, { entityId, taskId: task.id });
        }
        const parent = settled.parentTaskId
          ? after.characters[entityId].tasks[settled.parentTaskId]
          : undefined;
        if (!parent) {
          throw new NarrationInputError('after_mismatch', `new task ${task.id} has no parent task`, { entityId, taskId: task.id });
        }
        return {
          目标: settled.goal,
          属于大任务: parent.goal,
          状态: settled.status === 'achieved' ? '已完成' : '未完成',
        };
      });
    }
    if (Object.keys(rendered).length > 0) {
      changes[entityName(before.initial, entityId)] = rendered;
    }
  }
  return { 时间推进: `${timeAdvance.duration.amount} ${unit}`, 变化: changes };
}

function buildResult(
  before: WorldState, after: WorldState, delta: Record<Id, EntityDelta>,
): ResultState {
  const result: ResultState = {};
  for (const entityId of sortedIdsByName(before, Object.keys(delta))) {
    const ops = delta[entityId];
    if (!hasEffectiveOps(ops)) continue;
    const kind = entityKind(before.initial, entityId);
    const name = entityName(before.initial, entityId);
    if (kind === 'character') {
      const view: ResultPerson = {};
      if (ops.positionSet != null) view.位置 = positionText(after, entityId);
      if (ops.sanitySet != null) {
        const sanity = after.characters[entityId]?.sanity;
        if (sanity == null) {
          throw new NarrationInputError('after_mismatch', `character ${entityId} has no settled sanity`, { entityId });
        }
        view.精神值 = sanity;
      }
      if ((ops.appearanceChanges?.length ?? 0) > 0) {
        view.外貌 = joinedTexts(after.initial.characters[entityId].initialAppearance, after.characters[entityId].appearanceChanges);
      }
      if ((ops.personalityChanges?.length ?? 0) > 0) {
        view.个性 = joinedTexts(after.initial.characters[entityId].initialPersonality, after.characters[entityId].personalityChanges);
      }
      if ((ops.tasksAchieved?.length ?? 0) > 0 || (ops.subtasksAdded?.length ?? 0) > 0) {
        const tasks = after.characters[entityId].tasks;
        const changed = new Set<Id>([...(ops.tasksAchieved ?? []), ...(ops.subtasksAdded ?? []).map((task) => task.id)]);
        let big: RowTask | undefined;
        const small: RowTask[] = [];
        for (const taskId of changed) {
          const task = tasks[taskId];
          if (!task) {
            throw new NarrationInputError('after_mismatch', `task ${taskId} is missing from the after state`, { entityId, taskId });
          }
          const row: RowTask = { 目标: task.goal, 状态: task.status === 'achieved' ? '已完成' : '未完成' };
          if (task.parentTaskId == null) {
            if (big) {
              throw new NarrationInputError('multiple_task_roots', `result for ${entityId} changes more than one root task`, { entityId });
            }
            big = row;
          } else {
            small.push(row);
          }
        }
        view.任务 = {};
        if (big) view.任务.大任务 = big;
        if (small.length > 0) view.任务.小任务 = small;
      }
      if (Object.keys(view).length > 0) result[name] = view;
    } else if (kind === 'item') {
      const view: { 位置?: string; 外貌?: string[] } = {};
      if (ops.positionSet != null) view.位置 = positionText(after, entityId);
      if ((ops.appearanceChanges?.length ?? 0) > 0) {
        view.外貌 = joinedTexts(after.initial.items[entityId].initialAppearance, after.items[entityId].appearanceChanges);
      }
      if (Object.keys(view).length > 0) result[name] = view;
    } else {
      const view: { 外貌?: string[] } = {};
      if ((ops.appearanceChanges?.length ?? 0) > 0) {
        view.外貌 = joinedTexts(after.initial.locations[entityId].initialAppearance, after.locations[entityId].appearanceChanges);
      }
      if (Object.keys(view).length > 0) result[name] = view;
    }
  }
  return result;
}

function entitySetsFrom(characters: Iterable<Id>, locations: Iterable<Id>, items: Iterable<Id>): NarrationEntitySets {
  return { characters: [...characters], locations: [...locations], items: [...items] };
}

export function projectNarrationInput(args: ProjectNarrationInputArgs): ProjectionResult {
  const { before, after, delta, timeAdvance, viewpointId } = args;
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
  const visibleCharacters = sortedIdsByName(after, Object.keys(after.characters)
    .filter((id) => innermostLocationId(after, id) === viewRoom));
  const visibleItems = sortedIdsByName(after, Object.keys(after.items)
    .filter((id) => innermostLocationId(after, id) === viewRoom));
  const visibleLocations = sortedIdsByName(after, [viewRoom, ...ancestorLocationIds(after, viewRoom)]);

  const includedCharacters = new Set<Id>(visibleCharacters);
  includedCharacters.add(viewpointId);
  for (const id of effectiveChanged) if (after.initial.characters[id]) includedCharacters.add(id);
  const includedItems = new Set<Id>();
  for (const id of effectiveChanged) if (after.initial.items[id]) includedItems.add(id);
  const includedLocations = collectIncludedLocations(
    before, after, effectiveChanged, includedCharacters, includedItems, viewRoom,
  );

  assertUniqueNames(before, [...includedCharacters, ...includedItems, ...includedLocations, ...effectiveChanged]);

  const beforeState: ProjectionState = { 地点: {}, 人物: {}, 物品: {} };
  for (const id of sortedIdsByName(before, includedLocations)) beforeState.地点[entityName(before.initial, id)] = rowPlace(before, id);
  for (const id of sortedIdsByName(before, includedCharacters)) beforeState.人物[entityName(before.initial, id)] = rowPerson(before, id);
  for (const id of sortedIdsByName(before, includedItems)) beforeState.物品[entityName(before.initial, id)] = rowItem(before, id);

  const deltaProjection = buildDelta(before, after, delta, timeAdvance);
  const resultState = buildResult(before, after, delta);

  const tasks = taskHierarchy(after, includedCharacters);
  // Every task of an included character is printed in the before-state line
  // (the big task plus the flat small-task list), so every one of them is a
  // candidate for a text-carry limit.
  const inText = new Set<string>(tasks.map((entry) => `${entry.entityId}\u0000${entry.taskId}`));
  const textCarryLimits = computeTextCarryLimits(tasks, inText);

  const omittedFields: OmittedField[] = [];
  for (const id of Object.keys(before.initial.characters)) {
    if (includedCharacters.has(id)) continue;
    omittedFields.push({ entityId: id, entityName: entityName(before.initial, id), entityType: 'character', field: 'entity', reason: 'character_outside_scene' });
  }
  for (const id of Object.keys(before.initial.items)) {
    if (includedItems.has(id)) continue;
    omittedFields.push({ entityId: id, entityName: entityName(before.initial, id), entityType: 'item', field: 'entity', reason: 'item_not_changed' });
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
    });
  }
  for (const [entityId, ops] of Object.entries(delta)) {
    if (!hasEffectiveOps(ops)) {
      omittedFields.push({ entityId, entityName: entityName(before.initial, entityId), entityType: 'unknown', field: '*', reason: 'unknown_or_unchanged_delta_entity' });
      continue;
    }
    const name = entityName(before.initial, entityId);
    const kind = entityKind(before.initial, entityId);
    const result = resultState[name] as Record<string, unknown> | undefined;
    const fields = kind === 'character' ? ['位置', '精神值', '外貌', '个性', '任务']
      : kind === 'item' ? ['位置', '外貌'] : ['外貌'];
    for (const field of fields) {
      if (!result || !(field in result)) {
        omittedFields.push({ entityId, entityName: name, entityType: kind, field, reason: 'field_not_changed' });
      }
    }
  }

  const projection: NarrationProjection = {
    视角: `主角视角（${entityName(before.initial, viewpointId)}）；只表达已结算的世界事实`,
    上回合状态: beforeState,
    本回合变化: deltaProjection,
    本回合状态: resultState,
  };

  return {
    projection,
    includedEntities: entitySetsFrom(
      sortedIdsByName(before, includedCharacters),
      sortedIdsByName(before, includedLocations),
      sortedIdsByName(before, includedItems),
    ),
    visibleEntities: entitySetsFrom(visibleCharacters, visibleLocations, visibleItems),
    omittedFields,
    tasks,
    textCarryLimits,
    version: narrationVersions(),
  };
}

