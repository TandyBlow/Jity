/** Conservative affected-dependency projection for one settled point.
 *
 * The LLM no longer has to read the whole world and declare "unchanged" for
 * every task/entity. This module uses the settled facts (whose memberIds are
 * the actors), the facts' named entities, the scene (the actors' locations and
 * their contents), the position/appearance changes already applied, the time
 * advance and a global-event flag to over-approximate what may be affected.
 * Every other task/entity is left untouched with a recorded basis. The audit
 * still counts every row, so coverage is a program obligation, not a request
 * for the model to repeat the world.
 */
import type { EntityDelta, Id, WorldState } from '../../../types';
import type { SettlementStage } from './support';
import { activeRecords, allTasks, resultFacts } from './support';

export interface UnaffectedRow {
  id: Id;
  basis: string;
}

export interface PointProjection {
  actors: Id[];
  sceneLocations: Id[];
  sceneCharacters: Id[];
  sceneItems: Id[];
  factEntities: Id[];
  changedEntities: Id[];
  timeChanged: boolean;
  timeAffected: boolean;
  global: boolean;
  affectedTasks: Id[];
  unaffectedTasks: UnaffectedRow[];
  affectedTaskOwners: Id[];
  affectedAppearance: Id[];
  affectedMovable: Id[];
  unaffectedMovable: UnaffectedRow[];
  unaffectedAppearance: UnaffectedRow[];
  basis: { kind: string; refs: string[] }[];
}

const TIME_WORDS = [
  '结束前', '时间', '分钟', '小时', '截止', '之前', '以后', '期间', '当天', '天亮',
  '日落', '演习结束', '自由一日', '撤离', '此前', '最后', '守到', '等到', '到期',
];
const GLOBAL_WORDS = ['全城', '世界', '广播', '宣布', '所有人', '全场', '演习区', '演习结束', '整个'];

function namesOf(state: WorldState): Map<Id, string> {
  const out = new Map<Id, string>();
  for (const [id, value] of Object.entries(state.initial.characters)) out.set(id, value.name);
  for (const [id, value] of Object.entries(state.initial.items)) out.set(id, value.name);
  for (const [id, value] of Object.entries(state.initial.locations)) out.set(id, value.name);
  return out;
}

function mentions(text: string, id: Id, names: Map<Id, string>): boolean {
  const name = names.get(id) ?? '';
  if (name.length >= 2 && text.includes(name)) return true;
  return text.includes(id);
}

function locationOf(state: WorldState, id: Id): Id | null {
  let cursor: Id | null = state.characters[id]?.position.containerId
    ?? state.items[id]?.position.containerId
    ?? null;
  const seen = new Set<Id>();
  while (cursor) {
    if (seen.has(cursor)) return null;
    seen.add(cursor);
    if (state.locations[cursor]) return cursor;
    const item = state.items[cursor] as { position: { containerId: Id } } | undefined;
    if (!item) return null;
    cursor = item.position.containerId;
  }
  return null;
}

function appearanceSignature(state: WorldState, id: Id): string {
  const initial = state.initial.characters[id]?.initialAppearance
    ?? state.initial.items[id]?.initialAppearance
    ?? state.initial.locations[id]?.initialAppearance
    ?? '';
  const active = activeRecords(state, 'appearance', id)
    .filter((record) => record.active)
    .map((record) => `${record.id}:${record.text ?? ''}`)
    .sort();
  return [initial, ...active].join('|');
}

function samePosition(left: unknown, right: unknown): boolean {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

/** Map one point to the tasks/entities that need a semantic decision.
 * `priorChanges` are the stages already applied in this batch; the baseline is
 * the state before the batch, so a direct position/appearance diff is also
 * covered for split-stage callers. */
export function projectPoint(
  state: WorldState,
  baseline: WorldState,
  results: Record<Id, string>,
  priorChanges: Partial<Record<SettlementStage, Record<Id, Partial<EntityDelta>>>> = {},
  mode: 'group' | 'time_scan' = 'group',
): PointProjection {
  const names = namesOf(state);
  const facts = resultFacts(results);
  const actors = new Set<Id>();
  for (const fact of facts) actors.add(fact.memberId);

  const factEntities = new Set<Id>();
  let global = false;
  for (const fact of facts) {
    if (GLOBAL_WORDS.some((word) => fact.text.includes(word))) global = true;
    for (const id of names.keys()) {
      if (mentions(fact.text, id, names)) factEntities.add(id);
    }
  }
  for (const id of factEntities) {
    if (state.characters[id]) actors.add(id);
  }

  const sceneLocations = new Set<Id>();
  for (const actor of actors) {
    const location = locationOf(state, actor);
    if (location) sceneLocations.add(location);
  }
  const sceneCharacters = new Set<Id>();
  const sceneItems = new Set<Id>();
  for (const id of Object.keys(state.characters)) if (sceneLocations.has(locationOf(state, id) ?? '')) sceneCharacters.add(id);
  for (const id of Object.keys(state.items)) if (sceneLocations.has(locationOf(state, id) ?? '')) sceneItems.add(id);

  const changedEntities = new Set<Id>();
  const timeChanged = baseline.time.dateTime !== state.time.dateTime;
  // A two-minute action does not by itself re-open every deadline task; a time
  // scan does, and so does a fact that explicitly talks about elapsed time.
  const timeAffected = mode === 'time_scan' || facts.some((fact) => TIME_WORDS.some((word) => fact.text.includes(word)));
  for (const id of [...Object.keys(state.characters), ...Object.keys(state.items)]) {
    if (!samePosition(state.characters[id]?.position, baseline.characters[id]?.position)
      || !samePosition(state.items[id]?.position, baseline.items[id]?.position)) changedEntities.add(id);
  }
  for (const id of [...Object.keys(state.locations), ...Object.keys(state.characters), ...Object.keys(state.items)]) {
    if (appearanceSignature(state, id) !== appearanceSignature(baseline, id)) changedEntities.add(id);
  }
  for (const stage of ['position', 'appearance'] as SettlementStage[]) {
    for (const id of Object.keys(priorChanges[stage] ?? {})) changedEntities.add(id);
  }

  const allRows = allTasks(state);
  const affectedTasks = new Set<Id>();
  const reasons = new Map<Id, string[]>();
  for (const { ownerId, task } of allRows) {
    const why: string[] = [];
    if (actors.has(ownerId)) why.push('owner_is_actor');
    if (sceneCharacters.has(ownerId)) why.push('owner_in_scene');
    if (factEntities.has(ownerId)) why.push('owner_named_in_fact');
    if (global) why.push('global_fact');
    if (timeAffected && TIME_WORDS.some((word) => task.goal.includes(word))) why.push('time_condition');
    for (const id of new Set([...factEntities, ...changedEntities])) {
      if (mentions(task.goal, id, names)) why.push(`goal_mentions_${id}`);
    }
    if (why.length) {
      affectedTasks.add(task.id);
      reasons.set(task.id, why);
    }
  }
  // A subtask or parent of an affected task shares the condition; include the
  // family closure so a result cannot silently orphan a related row.
  let grew = true;
  while (grew) {
    grew = false;
    for (const { task } of allRows) {
      const parent = task.parentTaskId;
      if (affectedTasks.has(task.id)) {
        if (parent && !affectedTasks.has(parent)) { affectedTasks.add(parent); grew = true; }
      } else if (parent && affectedTasks.has(parent)) {
        affectedTasks.add(task.id);
        reasons.set(task.id, ['family_of_affected_parent']);
        grew = true;
      }
    }
  }

  const affectedTaskOwners = [...new Set(allRows.filter(({ task }) => affectedTasks.has(task.id)).map(({ ownerId }) => ownerId))].sort();
  // A decision is per character, so one affected task means the whole owner
  // row is presented; never imply the model judged the owner's other tasks.
  const ownerSet = new Set(affectedTaskOwners);
  const affectedTaskSet = new Set(allRows.filter((row) => ownerSet.has(row.ownerId)).map((row) => row.task.id));
  const unaffectedTasks: UnaffectedRow[] = allRows
    .filter(({ task }) => !affectedTaskSet.has(task.id))
    .map(({ task }) => ({ id: task.id, basis: 'owner_not_actor_or_scene; goal_has_no_point_entity_or_time' }));
  const affectedAppearance = new Set<Id>(actors);
  for (const id of [...factEntities, ...changedEntities, ...sceneLocations, ...sceneCharacters, ...sceneItems]) affectedAppearance.add(id);
  if (global) for (const id of [...Object.keys(state.locations), ...Object.keys(state.items), ...Object.keys(state.characters)]) affectedAppearance.add(id);

  const affectedMovable = new Set<Id>(actors);
  for (const id of [...factEntities, ...changedEntities, ...sceneItems, ...sceneCharacters]) {
    if (state.characters[id] || state.items[id]) affectedMovable.add(id);
  }
  if (global) for (const id of [...Object.keys(state.items), ...Object.keys(state.characters)]) affectedMovable.add(id);

  const allAppearance = [...Object.keys(state.locations), ...Object.keys(state.items), ...Object.keys(state.characters)].sort();
  const allMovable = [...Object.keys(state.items), ...Object.keys(state.characters)].sort();
  return {
    actors: [...actors].sort(),
    sceneLocations: [...sceneLocations].sort(),
    sceneCharacters: [...sceneCharacters].sort(),
    sceneItems: [...sceneItems].sort(),
    factEntities: [...factEntities].sort(),
    changedEntities: [...changedEntities].sort(),
    timeChanged,
    timeAffected,
    global,
    affectedTasks: [...affectedTaskSet].sort(),
    unaffectedTasks,
    affectedTaskOwners,
    affectedAppearance: allAppearance.filter((id) => affectedAppearance.has(id)),
    unaffectedAppearance: allAppearance.filter((id) => !affectedAppearance.has(id))
      .map((id) => ({ id, basis: 'not_actor_scene_fact_or_changed' })),
      affectedMovable: allMovable.filter((id) => affectedMovable.has(id)),
    unaffectedMovable: allMovable.filter((id) => !affectedMovable.has(id))
      .map((id) => ({ id, basis: 'not_actor_scene_fact_or_changed' })),
    basis: [
      { kind: 'actors', refs: [...actors].sort() },
      { kind: 'fact_entities', refs: [...factEntities].sort() },
      { kind: 'scene_locations', refs: [...sceneLocations].sort() },
      { kind: 'changed_entities', refs: [...changedEntities].sort() },
      { kind: 'time_changed', refs: timeChanged ? [state.time.dateTime] : [] },
      { kind: 'global', refs: global ? ['global_fact'] : [] },
    ],
  };
}
