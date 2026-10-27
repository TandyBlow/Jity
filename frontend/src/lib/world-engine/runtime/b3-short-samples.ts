/** Six explicit, fact-checkable probes. These are small standalone world
 * states, not a claim to have rerun the frozen 20-case B3 corpus. */
import type { Json } from '../types';
import type { B3Sample } from './b3-samples';

const position = (containerId: string) => ({ containerId, slotId: null, relativeTo: null });
const time = { calendar: 'gregorian', dateTime: '2026-10-27T09:00:00', instantOrdinal: 0 };
const task = { id: 'task_watch', ownerId: 'person_a', parentTaskId: null, goal: '留在走廊守门，不碰盒子', status: 'pending' };
export const SHORT_STATE = {
  engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_short', protagonistId: 'person_c', time,
  initial: { engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_short', protagonistId: 'person_c', initialTime: time,
    locations: { corridor: { id: 'corridor', name: '走廊', parentLocationId: null, initialAppearance: '明亮的走廊，通往门厅。' },
      hall: { id: 'hall', name: '门厅', parentLocationId: null, initialAppearance: '安静的门厅。' } },
    items: { box: { id: 'box', name: '盒子', initialPosition: position('corridor'), initialAppearance: '盒盖关闭。' } },
    characters: {
      person_a: { id: 'person_a', name: '林川', initialPosition: position('corridor'), initialAppearance: '穿灰衣。', initialPersonality: '谨慎，恪守职责', initialSanity: 10, tasks: { task_watch: task } },
      person_c: { id: 'person_c', name: '周宁', initialPosition: position('corridor'), initialAppearance: '穿蓝衣。', initialPersonality: '好奇', initialSanity: 10, tasks: {} },
    } },
  locations: { corridor: { id: 'corridor', appearanceChanges: [] }, hall: { id: 'hall', appearanceChanges: [] } },
  items: { box: { id: 'box', position: position('corridor'), appearanceChanges: [] } },
  characters: {
    person_a: { id: 'person_a', position: position('corridor'), appearanceChanges: [], personalityChanges: [], sanity: 10, tasks: { task_watch: task } },
    person_c: { id: 'person_c', position: position('corridor'), appearanceChanges: [], personalityChanges: [], sanity: 10, tasks: {} },
  },
};
const moved = structuredClone(SHORT_STATE);
moved.characters.person_a.position = position('hall');

export const B3_SHORT_SAMPLES: B3Sample[] = [
  { id: 'action-npc', task: 'action', key: 'person_a', input: {
    actor: 'person_a', advance: { inputText: '我打开盒盖。', intentStatus: 'pending' }, workingState: SHORT_STATE,
  }, note: '人物归属反例：林川守门，主角周宁要开盒。林川可 skip 或继续守门，不得替周宁开盒。' },
  { id: 'action-player', task: 'action', key: 'person_c', input: {
    actor: 'person_c', advance: { inputText: '我打开盒盖。', intentStatus: 'pending' }, workingState: SHORT_STATE,
  }, note: '人物判断正例：同一状态换 actor 为主角周宁，应尝试打开盒盖，不能把尝试写成已结算的新事实。' },
  { id: 'updates-position', task: 'updates', key: 'group_move#position', input: {
    groupId: 'group_move', mode: 'group', stage: 'position', priorStages: [], appliedDelta: {},
    results: { person_a: '林川已从走廊走进门厅。周宁仍在走廊，盒子位置未变。' }, workingState: SHORT_STATE,
  }, note: '精确期待：只有 person_a.positionSet.containerId=hall；其余实体不得变化。' },
  { id: 'updates-sanity', task: 'updates', key: 'group_sanity#sanity', input: {
    groupId: 'group_sanity', mode: 'group', stage: 'sanity', priorStages: [], appliedDelta: {},
    results: { person_a: '林川的精神值从10降为8，其余人物状态与位置未变。' }, workingState: SHORT_STATE,
  }, note: '精确期待：只有 person_a.sanitySet=8，不能减到2或改动主角。' },
  { id: 'narration-root', task: 'narration', key: 'root_short', input: {
    pointId: 'root_short', before: null, delta: { timeAdvance: null, entityDeltas: {} }, after: SHORT_STATE,
    perspective: '周宁视角。仅描述当前已知事实，不发生新动作。',
  }, note: '起始事实：两人在走廊，林川守门，盒盖关闭。不得写成打开盒子、得到物品或有人离开。' },
  { id: 'narration-move', task: 'narration', key: 'point_short', input: {
    pointId: 'point_short', before: SHORT_STATE,
    delta: { timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } }, entityDeltas: {
      person_a: { entityId: 'person_a', positionSet: position('hall') },
    } }, after: moved, perspective: '周宁视角。林川走入门厅，周宁留在走廊，盒盖仍关闭；不得补写别的事件。',
  }, note: '位置变化事实：移动者林川，留在走廊者周宁。盒子未移动也未打开。before/Δ/after 一致。' },
];

/** These explicit checks are stricter than the old length-only floor.
 * Prose still receives a separate recorded human-quality review. */
export function judgeShortSample(id: string, value: Json): string | null {
  const output = value as Record<string, Json>;
  if (id === 'action-npc') {
    if (output.kind === 'skip') return null;
    const text = String(output.text);
    return /林川|person_a/.test(text) && /守|警戒|原地/.test(text) && !/开.*盒|周宁.*行动/.test(text)
      ? null : 'NPC 行动归属或守门职责不符';
  }
  if (id === 'action-player') return output.kind === 'act' && /周宁|person_c|主角/.test(String(output.text)) && /开.*盒/.test(String(output.text))
    ? null : '主角未按待处理命令尝试打开盒盖';
  if (id.startsWith('updates-')) {
    const changes = output.changes as Record<string, Record<string, Json>>;
    if (Object.keys(changes).join() !== 'person_a') return '更新遗漏林川或改动其他实体';
    const delta = changes.person_a;
    if (id === 'updates-sanity') return JSON.stringify(delta) === '{"sanitySet":8}' ? null : '精神值应设为8，且不得增加其他变化';
    const set = delta.positionSet as Record<string, Json>;
    return Object.keys(delta).join() === 'positionSet' && set.containerId === 'hall' && set.slotId === null && set.relativeTo === null
      ? null : '位置必须仅将林川设为门厅';
  }
  const text = String(value);
  if (text.length < 10) return '叙事过短';
  if (/钥匙|死亡|受伤|鲜血|枪|打开.{0,3}盒|盒.{0,3}打开/.test(text)) return '叙事添加了未提交的物品、伤害或开盒事件';
  if (id === 'narration-move' && (!/林川/.test(text) || !/门厅/.test(text))) return '叙事遗漏实际移动者或目的地';
  return null;
}
