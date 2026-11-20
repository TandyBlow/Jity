/** Real projections for the shared browser candidate driver.
 *
 * Two sources only:
 *  1. the public short sample already used by the narration probes
 *     (`runtime/b3-short-samples.ts`), for comparability with earlier runs;
 *  2. the actual 龙族·自由一日 world asset, applied through the browser state
 *     kernel (`local/state.ts` + `applyPoint`), so before/after are a real
 *     applied pair with real canonical digests.
 *
 * The adapter packet is NOT a second world authority: every fact is computed
 * from the settled before/after states plus the point's own entity deltas. It
 * differs from `runtime/committed-narration.ts` in one documented way — it
 * accepts slot/relative positions (the free-day world places characters in
 * slots), which the baseline projector rejects.
 */
import type { NarrationFact, CommittedNarration } from '../../../runtime/committed-narration';
import type { EntityDelta, Id, TimelinePoint, TimeAdvance, WorldState } from '../../../types';
import { roomOf, legacyNarrationInput } from '../../prompt';
import { applyPoint, buildTimelinePoint, stateDigest } from '../../state';
import { SHORT_STATE } from '../../../runtime/b3-short-samples';
import type { CandidateScenario, SceneGrounding } from './types';

const position = (containerId: Id) => ({ containerId, slotId: null, relativeTo: null });

function nameOf(state: WorldState, id: Id): string {
  return state.initial.locations[id]?.name
    ?? state.initial.items[id]?.name
    ?? state.initial.characters[id]?.name
    ?? id;
}

function activeTexts(state: WorldState, id: Id): string[] {
  const entity = state.locations[id] ?? state.items[id] ?? state.characters[id];
  return (entity?.appearanceChanges ?? []).filter((change) => change.active && change.text).map((change) => change.text as string);
}

/** Scene grounding copied from the settled state. Notes only describe what is
 * already recorded: initial appearance plus active appearance changes. */
export function sceneFromState(state: WorldState, viewpointId: Id): SceneGrounding {
  const here = roomOf(state, viewpointId);
  const inRoom = (id: Id) => roomOf(state, id) === here;
  const present = Object.keys(state.characters)
    .filter((id) => inRoom(id))
    .map((id) => ({
      id,
      name: nameOf(state, id),
      note: [state.initial.characters[id]?.initialAppearance ?? '', ...activeTexts(state, id)].filter(Boolean).join('；'),
    }));
  const objects = Object.keys(state.items)
    .filter((id) => inRoom(id) && state.items[id].position.containerId === here)
    .map((id) => ({
      id,
      name: nameOf(state, id),
      note: [state.initial.items[id]?.initialAppearance ?? '', ...activeTexts(state, id)].filter(Boolean).join('；'),
    }));
  const inventory = Object.keys(state.items)
    .filter((id) => state.items[id].position.containerId === viewpointId)
    .map((id) => ({
      id,
      name: nameOf(state, id),
      note: [state.initial.items[id]?.initialAppearance ?? '', ...activeTexts(state, id)].filter(Boolean).join('；'),
    }));
  const exits = Object.keys(state.initial.locations)
    .filter((id) => state.initial.locations[id].parentLocationId === here)
    .map((id) => nameOf(state, id));
  return {
    location: nameOf(state, here),
    placeNotes: [state.initial.locations[here]?.initialAppearance ?? '', ...activeTexts(state, here)].filter(Boolean),
    present,
    objects,
    inventory,
    exits,
  };
}

/** Fact packet in the committed-narration shape, computed from settled state.
 * Mandatory change facts come from the point's deltas; `at`/sanity facts are
 * the backdrop. Non-character deltas are skipped, not invented. */
export function projectWorldFacts(before: WorldState | null, after: WorldState,
  delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }): CommittedNarration {
  if (!after.worldId) throw new Error('projection_world_missing');
  const facts: NarrationFact[] = [];
  const names = new Set<string>();
  for (const actorId of Object.keys(after.characters).sort()) {
    const name = after.initial.characters[actorId]?.name;
    if (!name) continue;
    if (names.has(name)) throw new Error(`projection_actor_name_ambiguous:${name}`);
    names.add(name);
    const actor = after.characters[actorId];
    const previous = before?.characters[actorId];
    const entityDelta = delta.entityDeltas?.[actorId];
    const here = roomOf(after, actorId);
    const base = { actorId, name };
    if (entityDelta?.positionSet && previous) {
      const from = roomOf(before as WorldState, actorId);
      if (from !== here) {
        facts.push({ ...base, id: `${actorId}:position`, kind: 'moved', fromId: from, from: nameOf(before as WorldState, from), toId: here, to: nameOf(after, here) });
      }
    }
    facts.push({ ...base, id: `${actorId}:at`, kind: 'at', locationId: here, location: nameOf(after, here) });
    for (const taskId of [...(entityDelta?.tasksAchieved ?? [])].sort()) {
      const task = actor.tasks[taskId];
      if (!task || task.status !== 'achieved') continue;
      facts.push({ ...base, id: `${actorId}:task:${taskId}`, kind: 'task_achieved', taskId, goal: task.goal });
    }
    for (const change of entityDelta?.personalityChanges ?? []) {
      if (!change.text) continue;
      facts.push({ ...base, id: `${actorId}:personality:${change.id}`, kind: 'personality_changed', changeId: change.id, text: change.text });
    }
    if (entityDelta?.sanitySet != null) {
      facts.push({ ...base, id: `${actorId}:sanity`, kind: 'sanity_changed', from: previous?.sanity ?? actor.sanity, to: entityDelta.sanitySet });
    } else {
      facts.push({ ...base, id: `${actorId}:sanity`, kind: 'sanity', value: actor.sanity });
    }
  }
  return {
    anchor: {
      worldId: after.worldId,
      pointId: 'unbound',
      version: before ? 1 : 0,
      stateDigest: '',
      previousPointId: before ? 'previous' : null,
    },
    facts,
  };
}

export interface ProjectedPoint {
  before: WorldState;
  after: WorldState;
  point: TimelinePoint;
  digest: string;
}

/** Apply an authored settlement through the real kernel. The delta is the
 * caller's authored change; the resulting state, positions and digest are the
 * kernel's, not a hand-copied snapshot. */
export async function applyProjectedPoint(state: WorldState, args: {
  id: string;
  sequence: number;
  timeAdvance: TimeAdvance;
  entityDeltas: Record<Id, EntityDelta>;
}): Promise<ProjectedPoint> {
  const point = buildTimelinePoint({
    worldId: state.worldId, id: args.id, sequence: args.sequence, kind: 'normal',
    previousPointId: `point_before_${args.sequence}`, roundId: 'round_projection',
    advanceId: 'advance_projection', trigger: 'player', linkedFromPointId: null,
    timeAdvance: args.timeAdvance, entityDeltas: args.entityDeltas,
  });
  const after = applyPoint(state, point);
  const digest = await stateDigest(after);
  return { before: state, after, point, digest };
}

function changeKinds(delta: Record<Id, EntityDelta>): string[] {
  const kinds = new Set<string>();
  for (const entity of Object.values(delta)) {
    if (entity.positionSet) kinds.add('position');
    if (entity.appearanceChanges?.length) kinds.add('appearance');
    if (entity.tasksAchieved?.length) kinds.add('task_achieved');
    if (entity.subtasksAdded?.length) kinds.add('subtask_added');
    if (entity.personalityChanges?.length) kinds.add('personality');
    if (entity.sanitySet != null) kinds.add('sanity');
  }
  return [...kinds].sort();
}

/** Optional product input serializer. The default is the legacy prompt the
 * early candidates were trained on; lane 01's `result-v2` renderer is what the
 * shipped page sends, so the queue must be able to use it verbatim. */
export type InputBuilder = (args: {
  before: WorldState | null;
  after: WorldState;
  delta: { timeAdvance: TimeAdvance | null; entityDeltas: Record<Id, EntityDelta> };
  viewpointId: Id;
}) => string;

/** Build a scenario from a settled projection. `inputText` is the product's
 * serialized fact input, never a candidate-specific template. */
export async function scenarioFromProjection(args: {
  id: string;
  label: string;
  note: string;
  before: WorldState | null;
  after: WorldState;
  delta: { timeAdvance: TimeAdvance | null; entityDeltas: Record<Id, EntityDelta> };
  continuesFrom?: string | null;
  pointId: string;
  version: number;
  previousPointId?: Id | null;
  stateDigest?: string;
  inputBuilder?: InputBuilder | null;
}): Promise<CandidateScenario> {
  const viewpoint = args.after.protagonistId;
  const scene = sceneFromState(args.after, viewpoint);
  const inputText = args.inputBuilder
    ? args.inputBuilder({ before: args.before, after: args.after, delta: args.delta, viewpointId: viewpoint })
    : legacyNarrationInput(args.before, args.delta, args.after, viewpoint);
  const committed = projectWorldFacts(args.before, args.after, args.delta);
  committed.anchor.pointId = args.pointId;
  committed.anchor.version = args.version;
  committed.anchor.stateDigest = args.stateDigest ?? await stateDigest(args.after);
  committed.anchor.previousPointId = args.previousPointId ?? null;
  const knownPositions = Object.keys(args.after.characters)
    .filter((id) => id !== viewpoint)
    .map((id) => ({ id, name: nameOf(args.after, id), location: nameOf(args.after, roomOf(args.after, id)) }));
  return {
    id: args.id,
    label: args.label,
    note: args.note,
    identity: {
      worldId: args.after.worldId,
      pointId: args.pointId,
      version: args.version,
      stateDigest: committed.anchor.stateDigest,
      previousPointId: committed.anchor.previousPointId,
      viewpointId: viewpoint,
      viewpointName: nameOf(args.after, viewpoint),
      changeKinds: changeKinds(args.delta.entityDeltas),
      timeAdvance: args.delta.timeAdvance,
    },
    before: args.before,
    after: args.after,
    delta: args.delta,
    committed,
    inputText,
    scene,
    policy: {
      viewpoint: { id: viewpoint, name: nameOf(args.after, viewpoint) },
      viewpointId: viewpoint,
      roster: Object.values(args.after.initial.characters).map((entity) => entity.name),
      locations: Object.keys(args.after.initial.locations).map((id) => nameOf(args.after, id)),
      knownPositions,
      knownEntities: [
        ...Object.values(args.after.initial.characters).map((entity) => entity.name),
        ...Object.values(args.after.initial.items).map((entity) => entity.name),
        ...Object.values(args.after.initial.locations).map((entity) => entity.name),
      ],
      time: args.delta.timeAdvance,
      requireTime: Boolean(args.delta.timeAdvance?.duration.amount),
      scene,
      targetChars: 240,
    },
    priorText: null,
    continuesFrom: args.continuesFrom ?? null,
  };
}

/** Public short-world scenarios, identical inputs to the earlier probes. */
export async function shortWorldScenarios(inputBuilder?: InputBuilder | null): Promise<CandidateScenario[]> {
  const root = structuredClone(SHORT_STATE) as WorldState;
  const rootScenario = await scenarioFromProjection({
    id: 'short-root', label: '公开短场景 · 起点',
    note: '无可结算变化：只能写已记录的走廊场景。新增事件/站立位置即事实错误。',
    inputBuilder: inputBuilder ?? null,
    before: null, after: root,
    delta: { timeAdvance: null, entityDeltas: {} },
    pointId: 'root_short', version: 0, previousPointId: null,
  });

  const move = await applyProjectedPoint(root, {
    id: 'point_short_move', sequence: 1,
    timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
    entityDeltas: { person_a: { entityId: 'person_a', positionSet: position('hall') } },
  });
  const moveScenario = await scenarioFromProjection({
    id: 'short-move', label: '公开短场景 · 一人移动',
    note: '必须写出林川从走廊到门厅；视角周宁仍在走廊；不得新增物品或事件。',
    inputBuilder: inputBuilder ?? null,
    before: move.before, after: move.after,
    delta: { timeAdvance: move.point.timeAdvance, entityDeltas: move.point.entityDeltas },
    stateDigest: move.digest, version: 1, pointId: move.point.id, previousPointId: 'root_short',
    continuesFrom: 'short-root',
  });

  const elapsed = await applyProjectedPoint(move.after, {
    id: 'point_short_elapsed', sequence: 2,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
    entityDeltas: {},
  });
  const elapsedScenario = await scenarioFromProjection({
    id: 'short-elapsed', label: '公开短场景 · 时间流逝',
    note: '空 delta + 2 分钟：时间必须表达，不得编造新变化。',
    inputBuilder: inputBuilder ?? null,
    before: elapsed.before, after: elapsed.after,
    delta: { timeAdvance: elapsed.point.timeAdvance, entityDeltas: {} },
    stateDigest: elapsed.digest, version: 2, pointId: elapsed.point.id, previousPointId: 'point_short_move',
    continuesFrom: 'short-move',
  });

  return [rootScenario, moveScenario, elapsedScenario];
}

/** The free-day asset is the published world file, which is already a full
 * WorldState (root time plus the current maps). */
export type FreeDayWorldAsset = WorldState;

/** The actual free-day world, projected at its opening point and after authored
 * probe settlements. The settlements are deterministic probes applied by the
 * real kernel; they are not a model's settlement output. */
export async function freeDayScenarios(asset: FreeDayWorldAsset, inputBuilder?: InputBuilder | null): Promise<CandidateScenario[]> {
  const initial = structuredClone(asset) as unknown as WorldState;
  if (initial.engineVersion !== 'world-engine-v1') throw new Error('free_day_asset_invalid');

  const root = await scenarioFromProjection({
    id: 'free-day-open', label: '自由一日 · 开局',
    note: '自由一日真实开局投影：路明非在西侧服务巷墙边，诺诺在巷口，多个物品在场。无变化。',
    inputBuilder: inputBuilder ?? null,
    before: null, after: initial,
    delta: { timeAdvance: null, entityDeltas: {} },
    pointId: 'root_free_day', version: 0, previousPointId: null,
  });

  const move = await applyProjectedPoint(initial, {
    id: 'point_free_day_move', sequence: 1,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
    entityDeltas: {
      lu: { entityId: 'lu', positionSet: position('west_arcade') },
      nono: { entityId: 'nono', positionSet: position('west_arcade') },
    },
  });
  const moveScenario = await scenarioFromProjection({
    id: 'free-day-move', label: '自由一日 · 两人转进西回廊',
    note: '路明非与诺诺同一分钟内从西侧服务巷移到西回廊；场景可写回廊与在场的人，不得新增未结算事件。',
    inputBuilder: inputBuilder ?? null,
    before: move.before, after: move.after,
    delta: { timeAdvance: move.point.timeAdvance, entityDeltas: move.point.entityDeltas },
    stateDigest: move.digest, version: 1, pointId: move.point.id, previousPointId: 'root_free_day',
    continuesFrom: 'free-day-open',
  });

  const task = await applyProjectedPoint(move.after, {
    id: 'point_free_day_task', sequence: 2,
    timeAdvance: { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } },
    entityDeltas: {
      lu: {
        entityId: 'lu',
        tasksAchieved: ['task_lu_choice'],
        personalityChanges: [{ id: 'change_lu_choice', text: '不再等别人替他决定，愿意先迈出一步。', supersedes: [] }],
        sanitySet: 48,
      },
    },
  });
  const taskScenario = await scenarioFromProjection({
    id: 'free-day-task', label: '自由一日 · 任务达成与个性变化',
    note: '任务 task_lu_choice 已达成，个性变化与精神值 43→48 是同一因果链；正文必须让读者看到这个变化，不得编造额外往事。',
    inputBuilder: inputBuilder ?? null,
    before: task.before, after: task.after,
    delta: { timeAdvance: task.point.timeAdvance, entityDeltas: task.point.entityDeltas },
    stateDigest: task.digest, version: 2, pointId: task.point.id, previousPointId: 'point_free_day_move',
    continuesFrom: 'free-day-move',
  });

  return [root, moveScenario, taskScenario];
}

export type ScenarioSet = 'short' | 'free-day' | 'all';

/** Resolve the requested scenario ids in a stable order. Unknown ids raise so
 * a typo never silently drops a run. */
export async function buildScenarios(args: {
  set: ScenarioSet;
  freeDay?: FreeDayWorldAsset | null;
  include?: string[] | null;
  exclude?: string[] | null;
  inputBuilder?: InputBuilder | null;
}): Promise<CandidateScenario[]> {
  const scenarios: CandidateScenario[] = [];
  if (args.set === 'short' || args.set === 'all') scenarios.push(...await shortWorldScenarios(args.inputBuilder));
  if (args.set === 'free-day' || args.set === 'all') {
    if (!args.freeDay) throw new Error('free_day_asset_required');
    scenarios.push(...await freeDayScenarios(args.freeDay, args.inputBuilder));
  }
  const include = args.include?.filter(Boolean) ?? null;
  const exclude = new Set(args.exclude?.filter(Boolean) ?? []);
  let selected = scenarios;
  if (include && include.length) {
    const byId = new Map(scenarios.map((scenario) => [scenario.id, scenario]));
    const missing = include.filter((id) => !byId.has(id));
    if (missing.length) throw new Error(`unknown_scenarios:${missing.join(',')}; available:${[...byId.keys()].join(',')}`);
    selected = include.map((id) => byId.get(id)!);
  }
  return selected.filter((scenario) => !exclude.has(scenario.id));
}
