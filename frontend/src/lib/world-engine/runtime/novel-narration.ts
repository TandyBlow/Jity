import type { RuleNarrationInput, PolishAttempt } from './rule-session';
import type { CommittedNarration } from './committed-narration';
import { alignNarration } from './narration-alignment';
import type { WorldState } from '../types';

const active = (items: { active: boolean; text: string | null }[]) =>
  items.filter((item) => item.active && item.text).map((item) => item.text as string);

function place(state: WorldState, id: string): string {
  return state.initial.locations[id]?.name ?? id;
}

function readableState(state: WorldState, ids: Set<string>) {
  const characters: Record<string, unknown> = {};
  const items: Record<string, unknown> = {};
  const locations: Record<string, unknown> = {};
  for (const id of ids) {
    const character = state.characters[id];
    const characterInitial = state.initial.characters[id];
    if (character && characterInitial) {
      characters[characterInitial.name] = {
        位置: place(state, character.position.containerId),
        外貌: [characterInitial.initialAppearance, ...active(character.appearanceChanges)].filter(Boolean),
        个性: [characterInitial.initialPersonality, ...active(character.personalityChanges)].filter(Boolean),
        任务: Object.values(character.tasks).map(({ goal, status }) => ({ 目标: goal, 状态: status })),
      };
    }
    const item = state.items[id];
    const itemInitial = state.initial.items[id];
    if (item && itemInitial) items[itemInitial.name] = {
      位置: place(state, item.position.containerId),
      外貌: [itemInitial.initialAppearance, ...active(item.appearanceChanges)].filter(Boolean),
    };
    const location = state.locations[id];
    const locationInitial = state.initial.locations[id];
    if (location && locationInitial) locations[locationInitial.name] = {
      外貌: [locationInitial.initialAppearance, ...active(location.appearanceChanges)].filter(Boolean),
    };
  }
  return { 地点: locations, 人物: characters, 物品: items };
}

/** A prose input from the committed before/delta/after records, not the strict fact-phrase prompt. */
export function buildNovelNarrationPrompt(input: RuleNarrationInput, packet: CommittedNarration, attempt: PolishAttempt): string {
  const changedIds = Object.keys(input.delta.entityDeltas);
  const ids = new Set<string>([input.after.protagonistId, ...changedIds]);
  // Keep named characters in the protagonist's ending location, even if unchanged.
  const protagonist = input.after.characters[input.after.protagonistId];
  if (protagonist) {
    for (const [id, character] of Object.entries(input.after.characters)) {
      if (character.position.containerId === protagonist.position.containerId) ids.add(id);
    }
    ids.add(protagonist.position.containerId);
  }
  if (input.before) for (const id of changedIds) {
    const previous = input.before.characters[id] ?? input.before.items[id];
    if (previous) ids.add(previous.position.containerId);
  }
  const deltas: Record<string, unknown> = {};
  for (const [id, delta] of Object.entries(input.delta.entityDeltas)) {
    const name = input.after.initial.characters[id]?.name ?? input.after.initial.items[id]?.name ??
      input.after.initial.locations[id]?.name ?? id;
    deltas[name] = {
      ...(delta.positionSet ? { 移动到: place(input.after, delta.positionSet.containerId) } : {}),
      ...(delta.sanitySet !== undefined ? { 精神值: delta.sanitySet } : {}),
      ...(delta.tasksAchieved?.length ? { 完成任务: delta.tasksAchieved.map((task) =>
        input.after.characters[id]?.tasks[task]?.goal ?? task) } : {}),
      ...(delta.subtasksAdded?.length ? { 新任务: delta.subtasksAdded.map((task) => task.goal) } : {}),
      ...(delta.appearanceChanges?.length ? { 外貌变化: delta.appearanceChanges.map((c) => ({ 描述: c.text, 取代: c.supersedes })) } : {}),
      ...(delta.personalityChanges?.length ? { 个性变化: delta.personalityChanges.map((c) => ({ 描述: c.text, 取代: c.supersedes })) } : {}),
    };
  }
  const payload = {
    视角: input.perspective,
    上回合状态: input.before ? readableState(input.before, ids) : null,
    本回合变化: { 时间推进: input.delta.timeAdvance?.duration ?? null, 变化: deltas },
    本回合状态: readableState(input.after, ids),
    已确认事实: packet.facts.map((fact) => ({ id: fact.id, 人物: fact.name, 类型: fact.kind })),
  };
  const feedback = attempt.previous ? `上次正文未通过检查：${attempt.previous.reason}。这次重新生成，不照抄上次正文。\n` : '';
  return `根据已确认的游戏世界状态写一段自然的中文小说正文，约200至400字。保持主角视角，描写场景、动作、感受和必要对话；不要使用状态字段名，不要罗列事实。状态变化已经结算，不能把完成的任务写成尚未完成，也不能增加新人物、物品、地点、任务结果、重要事件或人物关系。允许不改变游戏事实的细节描写。直接输出正文，不要标题。\n${feedback}输入：\n${JSON.stringify(payload)}\n正文：`;
}

/** Conservative known-fact checks. This cannot prove a passage contains no hallucinations. */
export function validateNovelNarration(packet: CommittedNarration, text: string, time?: { amount: number; unit: 'second' | 'minute' | 'hour' | 'day' | 'month' | 'year' } | null) {
  if (!text.trim()) return { accepted: false, reason: 'empty_narration' };
  const verdict = alignNarration(packet, text, { time, requireTime: false });
  // Minor physical gestures are literary detail; flagging every such verb would make
  // prose impossible. Other detected contradictions still reject the passage.
  const severeAddedEvent = /攻击|开枪|砸碎|点燃|踹开|踢开|撕开|捡起|拾起|锁上|夺走|杀死|打伤/;
  const blocking = verdict.violations.filter((violation) =>
    violation.kind !== 'added_event' || severeAddedEvent.test(violation.sentence));
  const required = new Set(packet.facts.filter((fact) => fact.kind === 'moved' || fact.kind === 'task_achieved').map((fact) => fact.id));
  const missing = verdict.coverage.filter((item) => required.has(item.id) && !item.expressed);
  if (blocking.length) return { accepted: false, reason: blocking[0].kind };
  if (missing.length) return { accepted: false, reason: 'missing_changed_fact' };
  return { accepted: true, reason: null };
}
