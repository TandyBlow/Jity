/** Convert one settled state step (before/after world reads) into the dataset
 * row shape lane 01's narration reviewer reads. Shared by the twenty-turn gate
 * and by scripts that replay a recorded product turn on the same input.
 *
 * This is a review adapter, not a product module: it copies only settled state
 * and never decides whether the text is good.
 */
export interface Entity {
  id: string;
  name?: string;
  initialPosition?: { containerId: string | null };
  position?: { containerId: string | null };
  initialSanity?: number;
  sanity?: number;
  initialAppearance?: string;
  appearanceChanges?: Array<{ id: string; text: string }>;
  initialPersonality?: string;
  personalityChanges?: Array<{ id: string; text: string }>;
  tasks?: Record<string, { id: string; goal: string; status: string; parentTaskId: string | null }>;
}
export interface WorldState {
  initial: {
    characters: Record<string, Entity>;
    locations: Record<string, { id: string; name: string; parentLocationId: string | null; initialAppearance?: string }>;
    items: Record<string, { id: string; name: string; initialPosition?: { containerId: string | null }; initialAppearance?: string }>;
  };
  characters: Record<string, Entity>;
  locations: Record<string, { id: string; appearanceChanges?: Array<{ id: string; text: string }> }>;
  items: Record<string, { id: string; position?: { containerId: string | null }; appearanceChanges?: Array<{ id: string; text: string }> }>;
}

function placeName(state: WorldState, containerId: string | null | undefined): string | undefined {
  if (!containerId) return undefined;
  return state.initial.locations[containerId]?.name;
}

const STATUS_LABEL: Record<string, string> = {
  achieved: '已完成', pending: '未完成', done: '已完成', open: '未完成',
};

function nameOfCharacter(state: WorldState, id: string): string {
  return state.initial.characters[id]?.name ?? id;
}
/** Full before-state block, keyed by display names the way 01's corpus is. */
export function stateTables(state: WorldState) {
  const 人物: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(state.initial.characters)) {
    const live = state.characters[id] ?? initial;
    const tasks = Object.values(live.tasks ?? {});
    const big = tasks.find((task) => !task.parentTaskId);
    人物[initial.name ?? id] = {
      位置: placeName(state, live.position?.containerId ?? initial.initialPosition?.containerId),
      精神值: live.sanity ?? initial.initialSanity,
      外貌: [
        initial.initialAppearance,
        ...(live.appearanceChanges ?? []).map((change) => change.text),
      ].filter((text): text is string => Boolean(text)),
      个性: [
        initial.initialPersonality,
        ...(live.personalityChanges ?? []).map((change) => change.text),
      ].filter((text): text is string => Boolean(text)),
      任务: {
        ...(big ? { 大任务: { 目标: big.goal, 状态: STATUS_LABEL[big.status] ?? big.status } } : {}),
        小任务: tasks.filter((task) => task.parentTaskId)
          .map((task) => ({ 目标: task.goal, 状态: STATUS_LABEL[task.status] ?? task.status })),
      },
    };
  }
  const 地点: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(state.initial.locations)) {
    const live = state.locations[id];
    地点[initial.name ?? id] = {
      位于: initial.parentLocationId ? state.initial.locations[initial.parentLocationId]?.name ?? null : null,
      外貌: [initial.initialAppearance, ...(live?.appearanceChanges ?? []).map((change) => change.text)]
        .filter((text): text is string => Boolean(text)),
    };
  }
  const 物品: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(state.initial.items)) {
    const live = state.items[id];
    物品[initial.name ?? id] = {
      位置: placeName(state, live?.position?.containerId ?? initial.initialPosition?.containerId),
      外貌: [initial.initialAppearance, ...(live?.appearanceChanges ?? []).map((change) => change.text)]
        .filter((text): text is string => Boolean(text)),
    };
  }
  return { 人物, 地点, 物品 };
}

export function rowFor01(before: WorldState, after: WorldState, minutes: number) {
  const 变化: Record<string, unknown> = {};
  for (const [id, initial] of Object.entries(after.initial.characters)) {
    const b = before.characters[id] ?? initial;
    const a = after.characters[id] ?? initial;
    const delta: Record<string, unknown> = {};
    const beforePlace = placeName(before, b.position?.containerId ?? initial.initialPosition?.containerId);
    const afterPlace = placeName(after, a.position?.containerId ?? initial.initialPosition?.containerId);
    if (beforePlace !== afterPlace) delta.位置 = afterPlace;
    if (b.sanity !== a.sanity) delta.精神值 = a.sanity;
    const beforeAppearance = new Set((b.appearanceChanges ?? []).map((change) => change.text));
    const addedAppearance = (a.appearanceChanges ?? [])
      .map((change) => change.text).filter((text) => !beforeAppearance.has(text));
    const removedAppearance = (b.appearanceChanges ?? [])
      .map((change) => change.text).filter((text) => !new Set((a.appearanceChanges ?? []).map((c) => c.text)).has(text));
    if (addedAppearance.length) delta.新增外貌 = addedAppearance;
    if (removedAppearance.length) delta.解除外貌 = removedAppearance;
    const beforePersonality = new Set((b.personalityChanges ?? []).map((change) => change.text));
    const addedPersonality = (a.personalityChanges ?? [])
      .map((change) => change.text).filter((text) => !beforePersonality.has(text));
    const removedPersonality = (b.personalityChanges ?? [])
      .map((change) => change.text).filter((text) => !new Set((a.personalityChanges ?? []).map((c) => c.text)).has(text));
    if (addedPersonality.length) delta.新增个性 = addedPersonality;
    if (removedPersonality.length) delta.解除个性 = removedPersonality;
    const completed = Object.values(a.tasks ?? {})
      .filter((task) => task.status === 'achieved' && b.tasks?.[task.id]?.status !== 'achieved')
      .map((task) => task.goal);
    if (completed.length) delta.完成任务 = completed;
    const addedTasks = Object.values(a.tasks ?? {})
      .filter((task) => !b.tasks?.[task.id]).map((task) => task.goal);
    if (addedTasks.length) delta.新增任务 = addedTasks;
    if (Object.keys(delta).length) 变化[initial.name ?? id] = delta;
  }
  const 变化状态: Record<string, unknown> = {};
  for (const name of Object.keys(变化)) {
    const id = Object.keys(after.initial.characters)
      .find((key) => after.initial.characters[key].name === name);
    if (!id) continue;
    const live = after.characters[id];
    变化状态[name] = {
      位置: placeName(after, live.position?.containerId),
      精神值: live.sanity,
      外貌: (live.appearanceChanges ?? []).map((change) => change.text),
      个性: (live.personalityChanges ?? []).map((change) => change.text),
    };
  }
  const protagonist = worldProtagonist(after);
  return {
    视角: `主角视角（${nameOfCharacter(after, protagonist)}）；只表达已结算的世界事实`,
    上回合状态: stateTables(before),
    '本回合变化': { 时间推进: `${minutes} 分钟`, 变化 },
    '本回合状态': 变化状态,
  };
}

function worldProtagonist(state: WorldState): string {
  return (state as unknown as { protagonistId: string }).protagonistId;
}
