/** Frozen B3 evaluation samples. Derived from the T01 school-world scenario
 * semantics (actors person_a…person_f, corridor/hall, the shelf task) and
 * hand-frozen on 2026-10-25 — the corpus is a committed fixture that does
 * not drift with the traces; per-sample provenance notes record the origin.
 * Every input matches the shape the scheduler actually declares for the
 * task (schedule.ts decision inputs), so the eval exercises the real
 * encode→engine→decode path. */
import type { ModelTask } from '../schedule';
import type { Json } from '../types';

export interface B3Sample {
  id: string;
  task: ModelTask;
  key: string;
  input: Json;
  note: string;
}

/** A compact, shape-true working-state fragment of the T01 world.
 * 2026-10-25 schema 合规修正：initial 补齐 engineVersion/schemaVersion/
 * protagonistId（此前未落盘的报告对应修正前夹具）。 */
export const T01_WORKING_STATE: Json = {
  engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_school', protagonistId: 'person_c',
  time: { calendar: 'gregorian', dateTime: '2026-09-01T11:59:02', instantOrdinal: 0 },
  initial: {
    worldId: 'world_school',
    engineVersion: 'world-engine-v1',
    schemaVersion: 1,
    protagonistId: 'person_c',
    initialTime: { calendar: 'gregorian', dateTime: '2026-09-01T08:00:00', instantOrdinal: 0 },
    locations: { corridor: { id: 'corridor', name: '走廊', parentLocationId: null, initialAppearance: '两侧是储物柜。' } },
    items: { item_key: { id: 'item_key', name: '钥匙', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '一把黄铜钥匙。' } },
    characters: {
      person_a: { id: 'person_a', name: '学生A', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '穿校服的学生。', initialPersonality: '谨慎', initialSanity: 10, tasks: {} },
      person_b: { id: 'person_b', name: '学生B', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '靠窗站着。', initialPersonality: '外向', initialSanity: 10, tasks: {} },
      person_c: { id: 'person_c', name: '主角', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '刚转学来。', initialPersonality: '好奇', initialSanity: 10, tasks: { task_shelf: { id: 'task_shelf', ownerId: 'person_c', parentTaskId: null, goal: '取回柜子里的东西', status: 'pending' } } },
    },
  },
  locations: { corridor: { id: 'corridor', appearanceChanges: [] } },
  items: { item_key: { id: 'item_key', appearanceChanges: [], position: { containerId: 'corridor', slotId: null, relativeTo: null } } },
  characters: {
    person_a: { id: 'person_a', appearanceChanges: [], position: { containerId: 'corridor', slotId: null, relativeTo: null }, personalityChanges: [], sanity: 10, tasks: {} },
    person_b: { id: 'person_b', appearanceChanges: [], position: { containerId: 'corridor', slotId: null, relativeTo: null }, personalityChanges: [], sanity: 10, tasks: {} },
    person_c: { id: 'person_c', appearanceChanges: [], position: { containerId: 'corridor', slotId: null, relativeTo: null }, personalityChanges: [], sanity: 10, tasks: { task_shelf: { id: 'task_shelf', ownerId: 'person_c', parentTaskId: null, goal: '取回柜子里的东西', status: 'pending' } } },
  },
};

const T01_NOTE = 'T01 school 世界派生（person_a 行动链：推门→牵连→结算→更新），2026-10-25 冻结';
const T01_NOTE_2 = 'T01 school 世界派生（第二个冻结变体），2026-10-25 冻结';

export const B3_SAMPLES: B3Sample[] = [
  { id: 'action-1', task: 'action', key: 'person_a', input: { actor: 'person_a', workingState: T01_WORKING_STATE }, note: T01_NOTE },
  { id: 'action-2', task: 'action', key: 'person_c', input: { actor: 'person_c', workingState: T01_WORKING_STATE }, note: T01_NOTE_2 },
  { id: 'targets-1', task: 'targets', key: 'person_a', input: { sourceId: 'person_a', actionText: '用力推开走廊尽头的门', workingState: T01_WORKING_STATE }, note: T01_NOTE },
  { id: 'targets-2', task: 'targets', key: 'person_c', input: { sourceId: 'person_c', actionText: '从储物柜里取出钥匙', workingState: T01_WORKING_STATE }, note: T01_NOTE_2 },
  { id: 'results-1', task: 'results', key: 'group_a', input: { groupId: 'group_a', workingState: T01_WORKING_STATE }, note: T01_NOTE },
  { id: 'results-2', task: 'results', key: 'group_b', input: { groupId: 'group_b', workingState: T01_WORKING_STATE }, note: T01_NOTE_2 },
  { id: 'updates-batch-1', task: 'updates', key: 'group_a', input: { groupId: 'group_a', mode: 'group', workingState: T01_WORKING_STATE }, note: `${T01_NOTE}；批量模式（无 stage）` },
  { id: 'updates-split-1', task: 'updates', key: 'group_a#sanity', input: { groupId: 'group_a', mode: 'group', workingState: T01_WORKING_STATE, stage: 'sanity' }, note: `${T01_NOTE}；拆分模式第二阶段——§6.3 阶梯：workingState 已是 Python preview 应用前序候选后的状态（2026-10-26 随 #5 更新，输入不再携带 priorStages/appliedDelta）` },
  { id: 'continuation-1', task: 'continuation', key: 'round_1', input: { round: { roundId: 'round_1', trigger: 'player', order: ['person_a', 'person_c'], cursor: 2, actedIds: ['person_a', 'person_c'], visitedIds: ['person_a', 'person_c'], conclusion: null }, head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' }, workingState: T01_WORKING_STATE }, note: T01_NOTE },
  { id: 'continuation-2', task: 'continuation', key: 'round_2', input: { round: { roundId: 'round_2', trigger: 'automatic', order: ['person_b'], cursor: 0, actedIds: [], visitedIds: [], conclusion: null }, head: { pointId: 'p2', version: 1, stateDigest: 'd2', narrationStatus: 'ready' }, workingState: T01_WORKING_STATE }, note: `${T01_NOTE}；automatic 轮变体` },
  { id: 'initial-1', task: 'initial', key: 'initial', input: null, note: T01_NOTE },
  { id: 'initial-2', task: 'initial', key: 'initial', input: null, note: `${T01_NOTE_2}；自由构建变体` },
  { id: 'time-1', task: 'time', key: 'successor:p1', input: { head: { pointId: 'p1', version: 1, stateDigest: 'd1', narrationStatus: 'pending' }, workingState: T01_WORKING_STATE }, note: T01_NOTE },
  { id: 'time-2', task: 'time', key: 'successor:p2', input: { head: { pointId: 'p2', version: 1, stateDigest: 'd2', narrationStatus: 'ready' }, workingState: T01_WORKING_STATE }, note: `${T01_NOTE}；零时长 instant 变体` },
  { id: 'pointPlan-1', task: 'pointPlan', key: 'round_1', input: { round: { roundId: 'round_1', trigger: 'player', order: ['person_a', 'person_c'], cursor: 0, actedIds: [], visitedIds: [], conclusion: null }, head: { pointId: 'root_0', version: 0, stateDigest: 'd0', narrationStatus: 'ready' } }, note: T01_NOTE },
  { id: 'pointPlan-2', task: 'pointPlan', key: 'round_2', input: { round: { roundId: 'round_2', trigger: 'automatic', order: ['person_b'], cursor: 0, actedIds: [], visitedIds: [], conclusion: null }, head: { pointId: 'p2', version: 1, stateDigest: 'd2', narrationStatus: 'ready' } }, note: `${T01_NOTE}；automatic 轮变体` },
  { id: 'narration-1', task: 'narration', key: 'root_0', input: { pointId: 'root_0', before: null, delta: { timeAdvance: null, entityDeltas: {} }, after: T01_WORKING_STATE, perspective: '主角视角（person_c「C」）；只表达已结算的世界事实' }, note: `${T01_NOTE}；§7.1 四件套输入（根点：before=null、空 Δ）——2026-10-26 随 #6 接线更新，声明形状=调度器组装输出` },
  { id: 'narration-2', task: 'narration', key: 'p1', input: { pointId: 'p1', before: T01_WORKING_STATE, delta: { timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, entityDeltas: { person_a: { entityId: 'person_a', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } } }, after: T01_WORKING_STATE, perspective: '主角视角（person_c「C」）；只表达已结算的世界事实' }, note: `${T01_NOTE_2}；§7.1 四件套输入（p1：before/Δ/after 全量）——2026-10-26 随 #6 接线更新` },
  { id: 'reaction-1', task: 'reaction', key: 'person_a', input: { sourceId: 'person_a', memberId: 'person_b', rollId: 'roll_1', workingState: T01_WORKING_STATE }, note: T01_NOTE },
  { id: 'reaction-2', task: 'reaction', key: 'person_a', input: { sourceId: 'person_a', memberId: 'person_c', rollId: 'roll_2', workingState: T01_WORKING_STATE }, note: T01_NOTE_2 },
];
