/** Compact, deterministic state text for the on-device model. The model sees
 * names and ids (it must return ids), but no engine bookkeeping. Every section
 * is derived from the committed working state; nothing here invents facts. */
import type { EntityDelta, Id, StoredChange, Task, TimeAdvance, WorldState } from '../types';

export function activeText(changes: StoredChange[]): string[] {
  return changes.filter((change) => change.active && change.text).map((change) => change.text as string);
}

export function taskText(task: Task): string {
  return `${task.id}：${task.goal}（${task.status === 'achieved' ? '已完成' : '待办'}）`;
}

export function locationName(state: WorldState, id: Id): string {
  return state.initial.locations[id]?.name ?? state.initial.items[id]?.name ?? state.initial.characters[id]?.name ?? id;
}

/** Innermost location reached by following containers. */
export function roomOf(state: WorldState, entityId: Id): Id {
  let node = entityId;
  const seen = new Set<Id>();
  while (!state.initial.locations[node]) {
    if (seen.has(node)) return node;
    seen.add(node);
    const entity = state.characters[node] ?? state.items[node];
    if (!entity) return node;
    node = entity.position.containerId;
  }
  return node;
}

export function roomName(state: WorldState, entityId: Id): string {
  return locationName(state, roomOf(state, entityId));
}

export function visibleCharacters(state: WorldState, actorId: Id): Id[] {
  const room = roomOf(state, actorId);
  return Object.keys(state.characters).filter((id) => roomOf(state, id) === room).sort();
}

export function changedTexts(state: WorldState, id: Id): { appearance: string[]; personality: string[] } {
  const character = state.characters[id];
  if (!character) return { appearance: [], personality: [] };
  return { appearance: activeText(character.appearanceChanges), personality: activeText(character.personalityChanges) };
}

export function describeCharacter(state: WorldState, id: Id, detailed = true): string {
  const initial = state.initial.characters[id];
  const current = state.characters[id];
  if (!initial || !current) return `- ${id}`;
  const changes = changedTexts(state, id);
  const appearance = [initial.initialAppearance, ...changes.appearance].join('；');
  const personality = [initial.initialPersonality, ...changes.personality].join('；');
  const tasks = Object.values(current.tasks).map(taskText).join('；') || '无';
  const base = `- ${initial.name}（id=${id}）位置=${locationName(state, current.position.containerId)}${current.position.slotId ? `/${current.position.slotId}` : ''}；精神值=${current.sanity}；外貌=${appearance}；个性=${personality}；任务=${tasks}`;
  if (detailed) return base;
  const pending = Object.values(current.tasks).filter((task) => task.status !== 'achieved').slice(0, 2).map((task) => `${task.id}=${task.goal.slice(0, 24)}`).join('；');
  return `- ${initial.name}（id=${id}）位置=${locationName(state, current.position.containerId)}；精神=${current.sanity}${pending ? `；待办=${pending}` : ''}`;
}

export function describeLocation(state: WorldState, id: Id): string {
  const location = state.initial.locations[id];
  if (!location) return `- ${id}`;
  return `- ${location.name}（id=${id}）${location.parentLocationId ? `，上级=${locationName(state, location.parentLocationId)}` : ''}；${location.initialAppearance}`;
}

export function describeItem(state: WorldState, id: Id): string {
  const item = state.initial.items[id];
  const current = state.items[id];
  if (!item) return `- ${id}`;
  const appearance = [item.initialAppearance, ...activeText(current?.appearanceChanges ?? [])].join('；');
  return `- ${item.name}（id=${id}）位置=${locationName(state, current?.position.containerId ?? item.initialPosition.containerId)}；外貌=${appearance}`;
}

export function sameRoomItems(state: WorldState, actorId: Id): Id[] {
  const room = roomOf(state, actorId);
  return Object.keys(state.items).filter((id) => roomOf(state, id) === room).sort();
}

export function describeDelta(delta: Record<Id, EntityDelta>, state: WorldState): string {
  const lines: string[] = [];
  for (const [id, change] of Object.entries(delta)) {
    const bits: string[] = [];
    if (change.positionSet) bits.push(`位置→${locationName(state, change.positionSet.containerId)}`);
    if (change.sanitySet != null) bits.push(`精神值→${change.sanitySet}`);
    for (const item of change.appearanceChanges ?? []) bits.push(item.text == null ? `解除外貌（${item.supersedes.join('、')}）` : `新增外貌「${item.text}」`);
    for (const item of change.personalityChanges ?? []) bits.push(item.text == null ? `解除个性（${item.supersedes.join('、')}）` : `新增个性「${item.text}」`);
    for (const task of change.tasksAchieved ?? []) bits.push(`完成任务 ${task}`);
    for (const task of change.subtasksAdded ?? []) bits.push(`新增任务 ${task.id}「${task.goal}」`);
    if (bits.length) lines.push(`- ${id}：${bits.join('；')}`);
  }
  return lines.length ? lines.join('\n') : '- 本回合没有结算出变化。';
}

/** Legacy YuYan prose input (`yuyan-prose-legacy-v1`): the format the existing
 * 0.5B narration checkpoint was trained on. It intentionally contains no
 * instruction section: the model continues from 【正文】. The caller still
 * checks the produced text against the same settled facts. */
export function legacyNarrationInput(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState, view: Id): string {
  const changed = new Set(Object.keys(delta.entityDeltas ?? {}));
  const visible = new Set([view, ...visibleCharacters(after, view), ...changed]);
  const chars = [...visible].filter((id) => after.characters[id]).sort((a, b) => after.initial.characters[a]!.name.localeCompare(after.initial.characters[b]!.name, 'zh'));
  const locations = new Set<Id>();
  for (const id of chars) {
    let node = roomOf(after, id);
    for (let i = 0; i < 2 && node; i += 1) {
      locations.add(node);
      node = after.initial.locations[node]?.parentLocationId ?? '';
    }
  }
  const items = new Set<Id>();
  for (const id of changed) if (after.items[id]) items.add(id);
  for (const item of sameRoomItems(after, view)) items.add(item);
  const itemList = [...items].slice(0, 4).sort((a, b) => after.initial.items[a]!.name.localeCompare(after.initial.items[b]!.name, 'zh'));
  const locList = [...locations].slice(0, 6).sort((a, b) => after.initial.locations[a]!.name.localeCompare(after.initial.locations[b]!.name, 'zh'));
  const parts = [`【视角】主角视角（${after.initial.characters[view]?.name ?? view}）`];
  if (locList.length) parts.push(`【地点】${locList.map((id) => legacyLocation(after, id)).join('')}`);
  if (chars.length) parts.push(`【人物】${chars.map((id) => legacyCharacter(after, id)).join('')}`);
  if (itemList.length) parts.push(`【物品】${itemList.map((id) => legacyItem(after, id)).join('')}`);
  parts.push(`【变化】${legacyDelta(delta.timeAdvance ?? null, delta.entityDeltas ?? {}, before, after)}`);
  parts.push('【正文】');
  return parts.join('');
}

function squash(text: string): string {
  return text.replace(/[ \t\u3000]+/g, ' ').trim().replace(/[。；，]+$/u, '');
}

function legacyLocation(state: WorldState, id: Id): string {
  const location = state.initial.locations[id];
  if (!location) return '';
  const parent = location.parentLocationId ? `在${locationName(state, location.parentLocationId)}里` : '';
  return `${location.name}${parent ? `（${parent}）` : ''}：${squash(location.initialAppearance)}。`;
}

function legacyCharacter(state: WorldState, id: Id): string {
  const character = state.characters[id];
  const initial = state.initial.characters[id];
  if (!character || !initial) return '';
  const appearance = [initial.initialAppearance, ...activeText(character.appearanceChanges)].map(squash).filter(Boolean).join('、');
  const personality = [initial.initialPersonality, ...activeText(character.personalityChanges)].map(squash).filter(Boolean).join('、');
  const tasks = legacyTasks(character.tasks);
  return `${initial.name}：在${locationName(state, character.position.containerId)}${character.position.slotId ? `/${character.position.slotId}` : ''}，精神值${character.sanity}，外貌${appearance}，个性${personality}，任务${tasks}。`;
}

function legacyTasks(tasks: Record<Id, Task>): string {
  const all = Object.values(tasks);
  const roots = all.filter((task) => !task.parentTaskId);
  const children = all.filter((task) => task.parentTaskId);
  const ordered = [...roots, ...children];
  return ordered.map((task) => `${task.goal}（${task.status === 'achieved' ? '已完成' : '未完成'}）`).join('；') || '无';
}

function legacyItem(state: WorldState, id: Id): string {
  const item = state.initial.items[id];
  const current = state.items[id];
  if (!item) return '';
  const appearance = [item.initialAppearance, ...activeText(current?.appearanceChanges ?? [])].map(squash).filter(Boolean).join('、');
  return `${item.name}（在${locationName(state, current?.position.containerId ?? item.initialPosition.containerId)}里）：${appearance}。`;
}

function legacyDelta(time: TimeAdvance | null, delta: Record<Id, EntityDelta>, before: WorldState | null, after: WorldState): string {
  const bits: string[] = [];
  if (time) bits.push(`时间推进${time.duration.amount} ${time.duration.unit}。`);
  for (const [id, change] of Object.entries(delta)) {
    const name = after.initial.characters[id]?.name ?? after.initial.items[id]?.name ?? id;
    const type = after.characters[id] ? '人物' : '物品';
    const ops: string[] = [];
    if (change.positionSet) ops.push(`移动到${locationName(after, change.positionSet.containerId)}`);
    if (change.sanitySet != null) ops.push(`精神值变成${change.sanitySet}`);
    for (const item of change.appearanceChanges ?? []) {
      if (item.text == null) ops.push(`去掉外貌${item.supersedes.map((old) => squash(old)).join('、')}`);
      else ops.push(`多出外貌${squash(item.text)}`);
    }
    for (const item of change.personalityChanges ?? []) {
      if (item.text == null) ops.push(`去掉个性${item.supersedes.map((old) => squash(old)).join('、')}`);
      else ops.push(`多出个性${squash(item.text)}`);
    }
    for (const taskId of change.tasksAchieved ?? []) {
      const goal = after.characters[id]?.tasks[taskId]?.goal ?? before?.characters[id]?.tasks[taskId]?.goal ?? taskId;
      ops.push(`完成${goal}`);
    }
    for (const task of change.subtasksAdded ?? []) ops.push(`新任务${task.goal}`);
    if (ops.length) bits.push(`${name}（${type}）：${ops.join('，')}。`);
  }
  if (!delta || Object.keys(delta).length === 0) bits.push('这一回合没有结算出变化。');
  return bits.join('');
}

/** Instruct-model narration brief. A small instruct model copies long rule
 * lists and bullet dumps back out, so the brief is one short paragraph of
 * facts and two sentences of task. Nothing here invents state. */
export function instructNarrationInput(before: WorldState | null, delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> }, after: WorldState, view: Id, actionText = '', resultsText = '', draft = '', mode: 'scene' | 'repair' = 'scene'): { prompt: string; brief: string } {
  const name = after.initial.characters[view]?.name ?? view;
  const room = roomOf(after, view);
  const sentences: string[] = [];
  const declared = actionText.trim().replace(/^我/u, name);
  if (declared) sentences.push(`玩家这回合让${name}做的事：${declared}。`);
  if (resultsText.trim()) sentences.push(`这一回合的结算结果：${squash(resultsText).slice(0, 120)}。`);
  const time = after.time.dateTime.slice(11, 16);
  if (delta.timeAdvance) sentences.push(`时间到了${time}，过去${delta.timeAdvance.duration.amount}${timeUnitName(delta.timeAdvance.duration.unit)}。`);
  const own = delta.entityDeltas?.[view];
  if (own?.positionSet) {
    const from = before ? locationName(before, before.characters[view]?.position.containerId ?? '') : '';
    sentences.push(`${name}${from ? `从${from}` : ''}走到了${locationName(after, own.positionSet.containerId)}。`);
  }
  const appearance = after.initial.locations[room]?.initialAppearance;
  sentences.push(`${name}现在在${locationName(after, room)}${appearance ? `，${squash(appearance).slice(0, 160)}` : ''}。`);
  const props = sameRoomItems(after, view).slice(0, 3);
  for (const id of props) {
    const item = after.initial.items[id];
    if (!item) continue;
    const looks = [item.initialAppearance, ...activeText(after.items[id]?.appearanceChanges ?? [])].map(squash).filter(Boolean).join('，').slice(0, 40);
    sentences.push(`屋里有${item.name}${looks ? `，${looks}` : ''}。`);
  }
  const others = visibleCharacters(after, view).filter((id) => id !== view);
  for (const id of others.slice(0, 3)) {
    const other = after.initial.characters[id];
    const current = after.characters[id];
    const looks = [other.initialAppearance, ...activeText(current.appearanceChanges)].map(squash).filter(Boolean).join('，').slice(0, 70);
    const where = current.position.slotId ? locationName(after, room) : locationName(after, current.position.containerId);
    sentences.push(`${other.name}也在${where}${looks ? `，${looks}` : ''}。`);
  }
  for (const [id, change] of Object.entries(delta.entityDeltas ?? {})) {
    if (id === view) continue;
    const other = after.initial.characters[id]?.name ?? after.initial.items[id]?.name ?? id;
    if (change.positionSet) sentences.push(`${other}去了${locationName(after, change.positionSet.containerId)}。`);
    for (const taskId of change.tasksAchieved ?? []) sentences.push(`${other}完成了「${after.characters[id]?.tasks[taskId]?.goal ?? taskId}」。`);
    if (change.sanitySet != null && after.characters[id]) sentences.push(`${other}的精神值变成${change.sanitySet}。`);
  }
  if (!others.length) sentences.push('房间里没有别人。');
  const brief = sentences.join('');
  const prompt = draft
    ? [
      mode === 'repair'
        ? `你是中文小说作者。上一稿没能全部落在已结算事实上。请只把下面这段草稿改写成 ${name} 视角的小说正文，160 到 240 字。`
        : `你是中文小说作者。请把下面这段已经结算的事实草稿改写成 ${name} 视角的小说正文，160 到 240 字。`,
      '要求：只能使用草稿里明确写出的动作、位置、外观和结果；可以调整语序、连接词和短句节奏，但不得新增任何动作、对白、物品、人物、地点、数字、伤情、往事、心理活动或比喻；每个人物的伤势、衣物和物品只属于本人，不要用“他/她”把一个人的特征挪到另一个人身上；不要逐条复述草稿，不要把人物外貌列成清单；以动作为主线写成一个连续场景，环境和人物只保留与当前动作有关的一两笔；不要写标题、列表或 Markdown；分 2 到 3 段。',
      '事实草稿：',
      draft,
      '正文：',
    ].join(String.fromCharCode(10))
    : [
      `你是中文小说作者。下面是这一回合已经结算的事实，请写成 ${name} 视角的小说正文，160 到 240 字。`,
      '要求：只写事实里明确出现的动作、位置、外观和结果；不要复述这份清单；不要写时间、地点、人物之类的标题；不要用 Markdown；不要新增人物、地点、物品、事件、数字、伤情、往事或心理活动；事实里没有直接引用的原话时不要写对白；短句，分 2 到 3 段。',
      '事实：',
      brief,
      '正文：',
    ].join(String.fromCharCode(10));
  return { prompt, brief };
}

function timeUnitName(unit: TimeAdvance['duration']['unit']): string {
  return ({ second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' } as Record<string, string>)[unit] ?? unit;
}
