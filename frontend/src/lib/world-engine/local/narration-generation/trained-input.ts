/** Text form of a settled point, in the shape the narration checkpoints were
 * actually trained on.
 *
 * Why this exists: the earlier real-model probes fed `legacyNarrationInput`
 * (a flattened one-line state dump ending in `【正文】`). The browser
 * checkpoints were trained on a different shape — a JSON `x` object with
 * 视角 / 上回合状态 / 本回合变化 / 本回合状态, continued after `【叙事】`, or as a
 * ChatML instruct turn. A 0/3 result on a prompt the weights never saw is not
 * evidence about the weights. This renderer reproduces the trained shape from
 * the same read-only world state + committed delta the page already has.
 *
 * It is a *view*, not a second authority: every value comes from the caller's
 * before/after state and the sealed `EntityDelta` of this point. It never
 * decides what changed.
 */
import type { EntityDelta, Id, Position, Task, TimeAdvance, WorldState } from '../../types';

interface SceneCharacter {
  位置: string;
  精神值: number;
  外貌: string[];
  个性: string[];
  任务: { 大任务: { 目标: string; 状态: string } | null; 小任务: { 目标: string; 状态: string }[] };
}

interface SceneItem {
  位于: string | null;
  外貌: string[];
}

interface SceneLocation {
  位于: string | null;
  外貌: string[];
}

export interface TrainedSceneView {
  视角: string;
  上回合状态: { 地点: Record<string, SceneLocation>; 人物: Record<string, SceneCharacter>; 物品: Record<string, SceneItem> };
  本回合变化: { 时间推进?: string; 变化: Record<string, Record<string, unknown>> };
  本回合状态: Record<string, Record<string, unknown>>;
}

/** Strip the trailing full stop so lines read like the training rows. */
const clean = (text: string): string => text.trim().replace(/[。.]+$/u, '');

const UNIT_CN: Record<TimeAdvance['duration']['unit'], string> = {
  second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年',
};
const STATUS_CN: Record<Task['status'], string> = { pending: '未完成', achieved: '已完成' };

function nameOf(state: WorldState, id: Id): string {
  return state.initial.locations[id]?.name
    ?? state.initial.items[id]?.name
    ?? state.initial.characters[id]?.name
    ?? id;
}

function containerName(state: WorldState, position: Position | null | undefined): string | null {
  if (!position) return null;
  return nameOf(state, position.containerId);
}

/** Active appearance / personality lines: the initial line plus every stored
 * change that is still live. */
function activeLines(
  initial: string | undefined,
  changes: readonly { id: Id; text: string | null; supersedes: Id[]; active?: boolean }[],
): string[] {
  const superseded = new Set(changes.flatMap((change) => change.supersedes));
  const lines: string[] = [];
  if (initial && clean(initial)) lines.push(clean(initial));
  for (const change of changes) {
    if (!change.text) continue;
    if (change.active === false) continue;
    if (superseded.has(change.id)) continue;
    lines.push(clean(change.text));
  }
  return lines;
}

/** Locations in the same connected component as the viewpoint's container
 * (its root ancestor and everything under it). This is the training rows'
 * scene scope: a corridor whose sibling is the hall belongs to the same
 * scene, a different building does not. The cap keeps a pathological tree
 * from swallowing the context window. */
function scopedLocations(state: WorldState, viewpointContainerId: Id, limit = 12): Set<Id> {
  let root: Id = viewpointContainerId;
  while (state.initial.locations[root]?.parentLocationId) {
    root = state.initial.locations[root].parentLocationId as Id;
  }
  const scope = new Set<Id>();
  const walk = (id: Id): void => {
    if (scope.has(id) || scope.size >= limit) return;
    scope.add(id);
    for (const location of Object.values(state.initial.locations)) {
      if (location.parentLocationId === id) walk(location.id);
    }
  };
  walk(root);
  if (!scope.has(viewpointContainerId)) scope.add(viewpointContainerId);
  // A location whose description names another place («明亮的走廊，通往门
  // 厅») is adjacent to it: the viewpoint can see into that place. Adding it
  // is the only way a destination across a top-level boundary appears in the
  // scene at all.
  const describe = (id: Id): string => [
    state.initial.locations[id]?.initialAppearance ?? '',
    ...(state.locations[id]?.appearanceChanges ?? []).map((change) => change.text ?? ''),
  ].join('');
  for (const id of [...scope]) {
    const text = describe(id);
    for (const other of Object.values(state.initial.locations)) {
      if (scope.has(other.id)) continue;
      if (other.name.length >= 2 && text.includes(other.name)) walk(other.id);
    }
  }
  return scope;
}

function locationView(state: WorldState, id: Id): SceneLocation {
  const initial = state.initial.locations[id];
  return {
    位于: initial?.parentLocationId ? nameOf(state, initial.parentLocationId) : null,
    外貌: activeLines(initial?.initialAppearance, state.locations[id]?.appearanceChanges ?? []),
  };
}

function characterView(state: WorldState, id: Id): SceneCharacter {
  const initial = state.initial.characters[id];
  const live = state.characters[id];
  const tasks = live?.tasks ?? {};
  const big = Object.values(tasks).find((task) => task.parentTaskId === null) ?? null;
  const small = Object.values(tasks).filter((task) => task.parentTaskId !== null);
  return {
    位置: containerName(state, live?.position) ?? nameOf(state, live?.position?.containerId ?? id),
    精神值: live?.sanity ?? initial?.initialSanity ?? 0,
    外貌: activeLines(initial?.initialAppearance, live?.appearanceChanges ?? []),
    个性: activeLines(initial?.initialPersonality, live?.personalityChanges ?? []),
    任务: {
      大任务: big ? { 目标: big.goal, 状态: STATUS_CN[big.status] } : null,
      小任务: small.map((task) => ({ 目标: task.goal, 状态: STATUS_CN[task.status] })),
    },
  };
}

function itemView(state: WorldState, id: Id): SceneItem {
  const initial = state.initial.items[id];
  return {
    位于: containerName(state, state.items[id]?.position ?? initial?.initialPosition),
    外貌: activeLines(initial?.initialAppearance, state.items[id]?.appearanceChanges ?? []),
  };
}

/** 本回合变化: the protocol's change vocabulary for this point. Only fields
 * present in the sealed delta appear. */
function changeView(
  before: WorldState | null,
  after: WorldState,
  delta: Record<Id, EntityDelta>,
  timeAdvance: TimeAdvance | null,
): TrainedSceneView['本回合变化'] {
  const changes: Record<string, Record<string, unknown>> = {};
  for (const [entityId, entityDelta] of Object.entries(delta)) {
    const entry: Record<string, unknown> = {};
    if (entityDelta.positionSet) entry.位置 = containerName(after, entityDelta.positionSet);
    if (entityDelta.sanitySet != null) entry.精神值 = entityDelta.sanitySet;
    const addedAppearance: string[] = [];
    const removedAppearance: string[] = [];
    const addedPersonality: string[] = [];
    const removedPersonality: string[] = [];
    const resolveSuperseded = (
      ids: readonly Id[],
      pool: readonly { id: Id; text: string | null }[],
    ): void => {
      for (const id of ids) {
        const found = pool.find((candidate) => candidate.id === id);
        if (found?.text) removedAppearance.push(clean(found.text));
      }
    };
    for (const change of entityDelta.appearanceChanges ?? []) {
      if (change.text) addedAppearance.push(clean(change.text));
      resolveSuperseded(change.supersedes, before?.items[entityId]?.appearanceChanges
        ?? before?.characters[entityId]?.appearanceChanges ?? []);
    }
    for (const change of entityDelta.personalityChanges ?? []) {
      if (change.text) addedPersonality.push(clean(change.text));
      for (const id of change.supersedes) {
        const found = before?.characters[entityId]?.personalityChanges.find((candidate) => candidate.id === id);
        if (found?.text) removedPersonality.push(clean(found.text));
      }
    }
    if (addedAppearance.length) entry.新增外貌 = addedAppearance;
    if (removedAppearance.length) entry.解除外貌 = removedAppearance;
    if (addedPersonality.length) entry.新增个性 = addedPersonality;
    if (removedPersonality.length) entry.解除个性 = removedPersonality;
    if (entityDelta.tasksAchieved?.length) {
      const tasks = after.characters[entityId]?.tasks ?? {};
      entry.完成任务 = entityDelta.tasksAchieved
        .map((taskId) => tasks[taskId]?.goal)
        .filter((goal): goal is string => Boolean(goal));
    }
    if (entityDelta.subtasksAdded?.length) {
      entry.新增小任务 = entityDelta.subtasksAdded.map((task) => {
        const parent = task.parentTaskId ? after.characters[entityId]?.tasks[task.parentTaskId] : null;
        return {
          目标: task.goal,
          属于大任务: parent?.goal ?? null,
          状态: STATUS_CN[task.status],
        };
      });
    }
    if (Object.keys(entry).length) changes[nameOf(after, entityId)] = entry;
  }
  const view: TrainedSceneView['本回合变化'] = { 变化: changes };
  if (timeAdvance) {
    const { amount, unit } = timeAdvance.duration;
    view.时间推进 = `${amount} ${UNIT_CN[unit]}`;
  }
  return view;
}

/** 本回合状态: only the entities and fields this point changed, carrying their
 * settled values. Nothing unchanged is repeated. */
function resultView(
  after: WorldState,
  delta: Record<Id, EntityDelta>,
): Record<string, Record<string, unknown>> {
  const result: Record<string, Record<string, unknown>> = {};
  for (const [entityId, entityDelta] of Object.entries(delta)) {
    const entry: Record<string, unknown> = {};
    const character = after.characters[entityId];
    const item = after.items[entityId];
    if (entityDelta.positionSet) {
      entry.位置 = containerName(after, entityDelta.positionSet);
    }
    if (entityDelta.sanitySet != null && character) entry.精神值 = character.sanity;
    if (entityDelta.appearanceChanges?.length) {
      const initial = after.initial.items[entityId]?.initialAppearance
        ?? after.initial.characters[entityId]?.initialAppearance;
      const pool = item?.appearanceChanges ?? character?.appearanceChanges ?? [];
      entry.外貌 = activeLines(initial, pool);
    }
    if (entityDelta.personalityChanges?.length && character) {
      entry.个性 = activeLines(after.initial.characters[entityId]?.initialPersonality ?? '', character.personalityChanges);
    }
    if (entityDelta.tasksAchieved?.length || entityDelta.subtasksAdded?.length) {
      const tasks = character?.tasks ?? {};
      const taskView: { 大任务?: { 目标: string; 状态: string }; 小任务?: { 目标: string; 状态: string }[] } = {};
      for (const taskId of entityDelta.tasksAchieved ?? []) {
        const task = tasks[taskId];
        if (!task) continue;
        if (task.parentTaskId === null) taskView.大任务 = { 目标: task.goal, 状态: STATUS_CN[task.status] };
        else (taskView.小任务 ??= []).push({ 目标: task.goal, 状态: STATUS_CN[task.status] });
      }
      for (const added of entityDelta.subtasksAdded ?? []) {
        const task = tasks[added.id];
        if (!task) continue;
        (taskView.小任务 ??= []).push({ 目标: task.goal, 状态: STATUS_CN[task.status] });
      }
      if (Object.keys(taskView).length) entry.任务 = taskView;
    }
    if (Object.keys(entry).length) result[nameOf(after, entityId)] = entry;
  }
  return result;
}

export interface TrainedSceneInput {
  /** State before the point; null at the root point. */
  before: WorldState | null;
  /** State after the point. */
  after: WorldState;
  /** Sealed delta of this point; null/empty at the root point. */
  delta?: Record<Id, EntityDelta> | null;
  /** Time advance of this point; null at the root point. */
  timeAdvance?: TimeAdvance | null;
  /** Viewpoint character id; defaults to `after.protagonistId`. */
  viewpointId?: Id;
}

/** The JSON `x` object exactly as the narration rows store it. */
export function trainedSceneView(input: TrainedSceneInput): TrainedSceneView {
  const { after } = input;
  const viewpointId = input.viewpointId ?? after.protagonistId;
  const viewpointName = after.initial.characters[viewpointId]?.name ?? viewpointId;
  const viewpointContainer = after.characters[viewpointId]?.position.containerId
    ?? after.initial.characters[viewpointId]?.initialPosition.containerId;
  const scope = viewpointContainer ? scopedLocations(after, viewpointContainer) : new Set<Id>();
  const before = input.before;
  const beforeViewpointContainer = before?.characters[viewpointId]?.position.containerId;

  const characters: Record<string, SceneCharacter> = {};
  for (const id of Object.keys(after.initial.characters)) {
    const container = after.characters[id]?.position.containerId;
    if (!scope.has(container) && id !== viewpointId) continue;
    characters[after.initial.characters[id].name] = characterView(after, id);
  }
  const items: Record<string, SceneItem> = {};
  for (const id of Object.keys(after.initial.items)) {
    if (!scope.has(after.items[id]?.position.containerId)) continue;
    items[after.initial.items[id].name] = itemView(after, id);
  }
  const locations: Record<string, SceneLocation> = {};
  for (const id of scope) locations[after.initial.locations[id].name] = locationView(after, id);
  void beforeViewpointContainer;

  return {
    视角: `主角视角（${viewpointName}）；只表达已结算的世界事实`,
    上回合状态: { 地点: locations, 人物: characters, 物品: items },
    本回合变化: changeView(before, after, input.delta ?? {}, input.timeAdvance ?? null),
    本回合状态: resultView(after, input.delta ?? {}),
  };
}

/** Raw-completion prompt of the no-instruction training arm:
 * `【状态】<json>\n【视角】<视角>\n【叙事】`. */
export function renderTrainedRawPrompt(view: TrainedSceneView): string {
  return `【状态】${JSON.stringify(view)}\n【视角】${view.视角}\n【叙事】`;
}

/** User turn of the instruct training arm: three label blocks plus 视角. */
export function renderTrainedInstructUser(view: TrainedSceneView): string {
  return [
    '【上回合状态】',
    JSON.stringify(view.上回合状态),
    '【本回合变化】',
    JSON.stringify(view.本回合变化),
    '【本回合状态】',
    JSON.stringify(view.本回合状态),
    '【视角】',
    view.视角,
  ].join('\n');
}

/** Qwen2 ChatML with the instruct arm's system prompt. wllama's
 * createChatCompletion applies the model's own template to a single user
 * message, so the scene prompt must be wrapped when the weights were trained
 * through `apply_chat_template`. */
export function wrapChatml(system: string, user: string): string {
  return `<|im_start|>system\n${system}<|im_end|>\n<|im_start|>user\n${user}<|im_end|>\n<|im_start|>assistant\n`;
}
