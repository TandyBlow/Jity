/** Frozen samples for the narration-split experiment: the expression
 * pipeline (变化定位 → 内容选择 → 组织表达 → 成句) is evaluated over the
 * ORIGINAL narration input of design/browser-world-state-workflow.md §7.1
 * (Sₜ₋₁, Δₜ, Sₜ, protagonist perspective) — no new schema fields, no
 * action history, no event log. States are typed as WorldState / InitialState
 * (NOT Json) so missing fields fail compilation — the shared `initial`
 * carries engineVersion/schemaVersion/protagonistId, per the 2026-10-25
 * schema-conformance review.
 *
 * Scoring contract (2026-10-25 review): requiredFacts is the MACHINE-
 * CHECKABLE form of the frozen requirements; every mustExpress entry must
 * appear exactly once as a requiredFact phrase (asserted by the scorer).
 * Checks are sentence-scoped (a fact must be asserted within one sentence —
 * cross-sentence token leakage cannot pass). timePassage guards appear on
 * every sample beyond the mustExpress mirror: timeAdvance 属于 Δ (§5.2), so
 * a WRONG duration is a fact error. mayMention is optional content (omitting
 * is not an error); mustNotFabricate lists factual errors only — repeating a
 * previously narrated true state is a repetition/naturalness concern; only
 * re-describing an old change as happening AGAIN fails. Personality/sanity
 * changes always co-occur with a taskAchieved in the same delta (§6.3 step
 * 5); tasks referenced by deltas exist in the sample's initial state.
 * Derived from the T01 school-world semantics; hand-frozen 2026-10-25 — the
 * corpus is a committed fixture that does not drift with the traces. */
import type { EntityDelta, Id, InitialState, Task, TimeAdvance, WorldState, WorldTime } from '../types';

export type NarrationSplitCategory =
  | 'position'
  | 'appearance'
  | 'task_achieved'
  | 'personality_sanity'
  | 'multi_entity'
  | 'empty_delta'
  | 'continuity';

/** 机器可核对的必述事实：phrase 与 mustExpress 条目一一对应（timePassage
 * 守卫条目除外——它们不对应 mustExpress，只守卫时间陈述的事实正确性）。 */
export type RequiredFact =
  | { kind: 'position'; entityId: Id; fromName: string; toName: string; phrase: string }
  | { kind: 'appearanceText'; entityId: Id; text: string; phrase: string }
  | { kind: 'taskGoal'; entityId: Id; goal: string; phrase: string }
  | { kind: 'personalityText'; entityId: Id; text: string; phrase: string }
  | { kind: 'sanityValue'; entityId: Id; value: number; phrase: string }
  | { kind: 'timePassage'; amount: number; unit: TimeAdvance['duration']['unit']; phrase: string }
  | { kind: 'timeReached'; hour: number; phrase: string };

export interface NarrationSplitSample {
  id: string;
  category: NarrationSplitCategory;
  /** 连续多点子集：同 series 样本按序链接（前点 after = 后点 before）。 */
  series?: string;
  note: string;
  /** 原方案 §7.1 叙事接口输入：前状态、增量、后状态、时间推进、主角视角约束。 */
  before: WorldState;
  after: WorldState;
  delta: Record<Id, EntityDelta>;
  timeAdvance: TimeAdvance;
  perspective: string;
  /** 必述核心事实（人类可读形式；遗漏=事实遗漏）。 */
  mustExpress: string[];
  /** 机器可核对形式（判分器唯一依据；见 RequiredFact 说明）。 */
  requiredFacts: RequiredFact[];
  /** 可选内容（不说不算错，说了影响自然度评分）。 */
  mayMention?: string[];
  /** 禁止捏造的内容（仅事实错误；重复提及真实状态不在此列）。 */
  mustNotFabricate: string[];
}

const PROVENANCE = 'T01 school 世界派生（叙事表达拆分实验），2026-10-25 冻结；2026-10-25 schema 合规修正＋判分契约修正';
const PERSPECTIVE = '主角视角（person_c「主角」）；只表达已结算的世界事实，允许选择性描述（§8.2）';

/** S₀：完整 InitialState（engineVersion/schemaVersion/protagonistId 齐备）。
 * person_b 携带待达成的 task_intro，作为 ns-pers-1 个性/理智变化的合法触发来源。 */
const NS_INITIAL: InitialState = {
  worldId: 'world_school',
  engineVersion: 'world-engine-v1',
  schemaVersion: 1,
  protagonistId: 'person_c',
  initialTime: { calendar: 'gregorian', dateTime: '2026-09-01T08:00:00', instantOrdinal: 0 },
  locations: {
    corridor: { id: 'corridor', name: '走廊', parentLocationId: null, initialAppearance: '两侧是储物柜。' },
    hall: { id: 'hall', name: '大厅', parentLocationId: null, initialAppearance: '空旷的大厅，光线明亮。' },
  },
  items: { item_key: { id: 'item_key', name: '钥匙', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '一把黄铜钥匙。' } },
  characters: {
    person_a: { id: 'person_a', name: '学生A', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '穿校服的学生。', initialPersonality: '谨慎', initialSanity: 10, tasks: {} },
    person_b: { id: 'person_b', name: '学生B', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '靠窗站着。', initialPersonality: '外向', initialSanity: 10, tasks: { task_intro: { id: 'task_intro', ownerId: 'person_b', parentTaskId: null, goal: '帮主角熟悉校园', status: 'pending' } } },
    person_c: { id: 'person_c', name: '主角', initialPosition: { containerId: 'corridor', slotId: null, relativeTo: null }, initialAppearance: '刚转学来。', initialPersonality: '好奇', initialSanity: 10, tasks: { task_shelf: { id: 'task_shelf', ownerId: 'person_c', parentTaskId: null, goal: '取回柜子里的东西', status: 'pending' } } },
  },
};

const IN_CORRIDOR = { containerId: 'corridor', slotId: null, relativeTo: null } as const;
const IN_HALL = { containerId: 'hall', slotId: null, relativeTo: null } as const;

const LOCATIONS_BASE: WorldState['locations'] = {
  corridor: { id: 'corridor', appearanceChanges: [] },
  hall: { id: 'hall', appearanceChanges: [] },
};
const ITEMS_BASE: WorldState['items'] = {
  item_key: { id: 'item_key', appearanceChanges: [], position: IN_CORRIDOR },
};
const CHARACTERS_BASE: WorldState['characters'] = {
  person_a: { id: 'person_a', appearanceChanges: [], position: IN_CORRIDOR, personalityChanges: [], sanity: 10, tasks: {} },
  person_b: { id: 'person_b', appearanceChanges: [], position: IN_CORRIDOR, personalityChanges: [], sanity: 10, tasks: { task_intro: { id: 'task_intro', ownerId: 'person_b', parentTaskId: null, goal: '帮主角熟悉校园', status: 'pending' } } },
  person_c: { id: 'person_c', appearanceChanges: [], position: IN_CORRIDOR, personalityChanges: [], sanity: 10, tasks: { task_shelf: { id: 'task_shelf', ownerId: 'person_c', parentTaskId: null, goal: '取回柜子里的东西', status: 'pending' } } },
};

const at = (dateTime: string, instantOrdinal = 0): WorldTime => ({ calendar: 'gregorian', dateTime, instantOrdinal });
const elapsed = (amount: number, unit: TimeAdvance['duration']['unit']): TimeAdvance => ({ boundary: 'elapsed', duration: { amount, unit } });

/** A working state over the frozen base with per-section overrides — keeps
 * each sample's before/after readable as a diff against the shared base. */
function nsState(time: WorldTime, overrides: { initial?: InitialState; locations?: WorldState['locations']; items?: WorldState['items']; characters?: WorldState['characters'] } = {}): WorldState {
  return {
    engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_school', protagonistId: 'person_c',
    time, initial: overrides.initial ?? NS_INITIAL,
    locations: overrides.locations ?? LOCATIONS_BASE,
    items: overrides.items ?? ITEMS_BASE,
    characters: overrides.characters ?? CHARACTERS_BASE,
  };
}

function withCharacter(base: WorldState['characters'], id: Id, patch: Partial<WorldState['characters'][Id]>): WorldState['characters'] {
  return { ...base, [id]: { ...base[id], ...patch } } as WorldState['characters'];
}
function withItem(base: WorldState['items'], id: Id, patch: Partial<WorldState['items'][Id]>): WorldState['items'] {
  return { ...base, [id]: { ...base[id], ...patch } } as WorldState['items'];
}
function withLocation(base: WorldState['locations'], id: Id, patch: Partial<WorldState['locations'][Id]>): WorldState['locations'] {
  return { ...base, [id]: { ...base[id], ...patch } } as WorldState['locations'];
}
/** 任务来源完整性：增量引用的任务必须在 S₀ 里（运行中不能新增根任务）。 */
function withInitialTask(base: InitialState, ownerId: Id, task: Task): InitialState {
  const owner = base.characters[ownerId];
  return { ...base, characters: { ...base.characters, [ownerId]: { ...owner, tasks: { ...owner.tasks, [task.id]: task } } } };
}

const SHELF_DONE = { tasks: { task_shelf: { id: 'task_shelf', ownerId: 'person_c', parentTaskId: null, goal: '取回柜子里的东西', status: 'achieved' } } } as const;
const INTRO_DONE = { tasks: { task_intro: { id: 'task_intro', ownerId: 'person_b', parentTaskId: null, goal: '帮主角熟悉校园', status: 'achieved' } } } as const;
const KEY_DUST = '黄铜钥匙的表面蒙上了一层灰尘';
const NOON_TASK = { id: 'task_noon', ownerId: 'person_a', parentTaskId: null, goal: '坚持到中午', status: 'pending' } as const;
const NOON_TASK_DONE = { ...NOON_TASK, status: 'achieved' } as const;
/** ns-task-time-1 专用 S₀：task_noon 登记在初始任务里。 */
const INITIAL_WITH_NOON = withInitialTask(NS_INITIAL, 'person_a', NOON_TASK);

export const NARRATION_SPLIT_SAMPLES: NarrationSplitSample[] = [
  {
    id: 'ns-pos-1', category: 'position', note: `${PROVENANCE}；位置变化`,
    before: nsState(at('2026-09-01T11:59:02')),
    after: nsState(at('2026-09-01T12:01:02'), { characters: withCharacter(CHARACTERS_BASE, 'person_a', { position: IN_HALL }) }),
    delta: { person_a: { entityId: 'person_a', positionSet: IN_HALL } },
    timeAdvance: elapsed(2, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['学生A 从走廊移动到了大厅'],
    requiredFacts: [
      { kind: 'timePassage', amount: 2, unit: 'minute', phrase: '时间流逝约两分钟（Δ 守卫）' },
      { kind: 'position', entityId: 'person_a', fromName: '走廊', toName: '大厅', phrase: '学生A 从走廊移动到了大厅' },
    ],
    mustNotFabricate: ['移动的方式与经过（奔跑、推门声等未保存内容）', '其他实体未保存的变化'],
  },
  {
    id: 'ns-appear-1', category: 'appearance', note: `${PROVENANCE}；外貌变化`,
    before: nsState(at('2026-09-01T11:59:02')),
    after: nsState(at('2026-09-01T12:00:02'), { items: withItem(ITEMS_BASE, 'item_key', { appearanceChanges: [{ id: 'chg_key_1', text: KEY_DUST, supersedes: [], sourcePointId: 'p_appear', sourceSequence: 1, active: true }] }) }),
    delta: { item_key: { entityId: 'item_key', appearanceChanges: [{ id: 'chg_key_1', text: KEY_DUST, supersedes: [] }] } },
    timeAdvance: elapsed(1, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['钥匙表面蒙上了灰尘'],
    requiredFacts: [
      { kind: 'timePassage', amount: 1, unit: 'minute', phrase: '时间流逝约一分钟（Δ 守卫）' },
      { kind: 'appearanceText', entityId: 'item_key', text: KEY_DUST, phrase: '钥匙表面蒙上了灰尘' },
    ],
    mustNotFabricate: ['钥匙变脏的原因或经过'],
  },
  {
    id: 'ns-loc-appear-1', category: 'appearance', note: `${PROVENANCE}；地点外貌变化（§9.2 字段权限：地点只接收外貌变化。此前 assertDeltaConsistent 缺地点分支会误拒这条合法增量——2026-10-25 复核补）`,
    before: nsState(at('2026-09-01T11:59:02')),
    after: nsState(at('2026-09-01T12:00:02'), { locations: withLocation(LOCATIONS_BASE, 'corridor', { appearanceChanges: [{ id: 'chg_corr_1', text: '两侧的储物柜都被关上了', supersedes: [], sourcePointId: 'p_loc', sourceSequence: 1, active: true }] }) }),
    delta: { corridor: { entityId: 'corridor', appearanceChanges: [{ id: 'chg_corr_1', text: '两侧的储物柜都被关上了', supersedes: [] }] } },
    timeAdvance: elapsed(1, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['两侧的储物柜都被关上了'],
    requiredFacts: [
      { kind: 'timePassage', amount: 1, unit: 'minute', phrase: '时间流逝约一分钟（Δ 守卫）' },
      { kind: 'appearanceText', entityId: 'corridor', text: '两侧的储物柜都被关上了', phrase: '两侧的储物柜都被关上了' },
    ],
    mustNotFabricate: ['柜门被谁关上等未保存经过'],
  },
  {
    id: 'ns-task-1', category: 'task_achieved', note: `${PROVENANCE}；任务达成（行动驱动）`,
    before: nsState(at('2026-09-01T11:59:02')),
    after: nsState(at('2026-09-01T12:01:02'), { characters: withCharacter(CHARACTERS_BASE, 'person_c', SHELF_DONE) }),
    delta: { person_c: { entityId: 'person_c', tasksAchieved: ['task_shelf'] } },
    timeAdvance: elapsed(2, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['主角完成了任务「取回柜子里的东西」'],
    requiredFacts: [
      { kind: 'timePassage', amount: 2, unit: 'minute', phrase: '时间流逝约两分钟（Δ 守卫）' },
      { kind: 'taskGoal', entityId: 'person_c', goal: '取回柜子里的东西', phrase: '主角完成了任务「取回柜子里的东西」' },
    ],
    mustNotFabricate: ['为解释达成而编造的具体动作经过（§8.2）'],
  },
  {
    id: 'ns-task-time-1', category: 'task_achieved', note: `${PROVENANCE}；纯时间达成变体（§8.2：时间推进可产生 tasksAchieved，无需动作证据即可叙述；§11.1 同型夹具）。task_noon 已登记在该样本 S₀ 的 person_a 初始任务中。「时间已到中午」是必述事实——规则基线若只述时间流逝与任务达成，按遗漏如实记录`,
    before: nsState(at('2026-09-01T11:59:00'), { initial: INITIAL_WITH_NOON, characters: withCharacter(CHARACTERS_BASE, 'person_a', { tasks: { task_noon: NOON_TASK } }) }),
    after: nsState(at('2026-09-01T12:00:00'), { initial: INITIAL_WITH_NOON, characters: withCharacter(CHARACTERS_BASE, 'person_a', { tasks: { task_noon: NOON_TASK_DONE } }) }),
    delta: { person_a: { entityId: 'person_a', tasksAchieved: ['task_noon'] } },
    timeAdvance: elapsed(1, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['时间已到中午', '学生A 的任务「坚持到中午」达成'],
    requiredFacts: [
      { kind: 'timeReached', hour: 12, phrase: '时间已到中午' },
      { kind: 'taskGoal', entityId: 'person_a', goal: '坚持到中午', phrase: '学生A 的任务「坚持到中午」达成' },
      { kind: 'timePassage', amount: 1, unit: 'minute', phrase: '时间流逝约一分钟（Δ 守卫）' },
    ],
    mustNotFabricate: ['无动作证据时复述动作经过——§8.2 只要求述时间与当前状态'],
  },
  {
    id: 'ns-pers-1', category: 'personality_sanity', note: `${PROVENANCE}；个性与理智变化——补入合法触发：同一点内 task_intro 达成（§6.3 步骤 5：个性变化仅在存在新达成任务时执行）`,
    before: nsState(at('2026-09-01T11:59:02')),
    after: nsState(at('2026-09-01T12:00:02'), { characters: withCharacter(CHARACTERS_BASE, 'person_b', { ...INTRO_DONE, personalityChanges: [{ id: 'chg_b_1', text: '变得健谈', supersedes: [], sourcePointId: 'p_pers', sourceSequence: 1, active: true }], sanity: 12 }) }),
    delta: { person_b: { entityId: 'person_b', tasksAchieved: ['task_intro'], personalityChanges: [{ id: 'chg_b_1', text: '变得健谈', supersedes: [] }], sanitySet: 12 } },
    timeAdvance: elapsed(1, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['学生B 的任务「帮主角熟悉校园」达成', '学生B 的个性变得健谈', '学生B 的理智值变为 12'],
    requiredFacts: [
      { kind: 'timePassage', amount: 1, unit: 'minute', phrase: '时间流逝约一分钟（Δ 守卫）' },
      { kind: 'taskGoal', entityId: 'person_b', goal: '帮主角熟悉校园', phrase: '学生B 的任务「帮主角熟悉校园」达成' },
      { kind: 'personalityText', entityId: 'person_b', text: '变得健谈', phrase: '学生B 的个性变得健谈' },
      { kind: 'sanityValue', entityId: 'person_b', value: 12, phrase: '学生B 的理智值变为 12' },
    ],
    mustNotFabricate: ['变化的未保存原因事件（任务达成如何具体发生的经过）'],
  },
  {
    id: 'ns-multi-1', category: 'multi_entity', note: `${PROVENANCE}；同点多实体变化`,
    before: nsState(at('2026-09-01T11:59:02')),
    after: nsState(at('2026-09-01T12:01:02'), {
      items: withItem(ITEMS_BASE, 'item_key', { appearanceChanges: [{ id: 'chg_key_1', text: KEY_DUST, supersedes: [], sourcePointId: 'p_multi', sourceSequence: 1, active: true }] }),
      characters: withCharacter(withCharacter(CHARACTERS_BASE, 'person_a', { position: IN_HALL }), 'person_c', SHELF_DONE),
    }),
    delta: {
      person_a: { entityId: 'person_a', positionSet: IN_HALL },
      item_key: { entityId: 'item_key', appearanceChanges: [{ id: 'chg_key_1', text: KEY_DUST, supersedes: [] }] },
      person_c: { entityId: 'person_c', tasksAchieved: ['task_shelf'] },
    },
    timeAdvance: elapsed(2, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['学生A 位于大厅', '钥匙表面蒙上了灰尘', '主角完成了任务「取回柜子里的东西」'],
    requiredFacts: [
      { kind: 'timePassage', amount: 2, unit: 'minute', phrase: '时间流逝约两分钟（Δ 守卫）' },
      { kind: 'position', entityId: 'person_a', fromName: '走廊', toName: '大厅', phrase: '学生A 位于大厅' },
      { kind: 'appearanceText', entityId: 'item_key', text: KEY_DUST, phrase: '钥匙表面蒙上了灰尘' },
      { kind: 'taskGoal', entityId: 'person_c', goal: '取回柜子里的东西', phrase: '主角完成了任务「取回柜子里的东西」' },
    ],
    mustNotFabricate: ['三条变化之间未保存的因果关联'],
  },
  {
    id: 'ns-empty-1', category: 'empty_delta', note: `${PROVENANCE}；只有时间流逝的空增量（§8.2：必述=时间；现状为可选内容）`,
    before: nsState(at('2026-09-01T11:59:02')),
    after: nsState(at('2026-09-01T12:01:02')),
    delta: {},
    timeAdvance: elapsed(2, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['时间流逝了约两分钟'],
    requiredFacts: [
      { kind: 'timePassage', amount: 2, unit: 'minute', phrase: '时间流逝了约两分钟' },
    ],
    mayMention: ['当前场景（走廊中的学生A、学生B 与主角）'],
    mustNotFabricate: ['任何未保存的动作经过（如「敲门但无人回应」）——§8.2'],
  },
  {
    id: 'ns-cont-1', category: 'continuity', series: 'ns-cont', note: `${PROVENANCE}；连续三时间点第 1 点（位置）——重复与指代检查序列`,
    before: nsState(at('2026-09-01T12:00:00')),
    after: nsState(at('2026-09-01T12:00:02'), { characters: withCharacter(CHARACTERS_BASE, 'person_a', { position: IN_HALL }) }),
    delta: { person_a: { entityId: 'person_a', positionSet: IN_HALL } },
    timeAdvance: elapsed(2, 'second'), perspective: PERSPECTIVE,
    mustExpress: ['学生A 从走廊到了大厅'],
    requiredFacts: [
      { kind: 'timePassage', amount: 2, unit: 'second', phrase: '时间流逝约两秒（Δ 守卫）' },
      { kind: 'position', entityId: 'person_a', fromName: '走廊', toName: '大厅', phrase: '学生A 从走廊到了大厅' },
    ],
    mustNotFabricate: ['移动的方式与经过'],
  },
  {
    id: 'ns-cont-2', category: 'continuity', series: 'ns-cont', note: `${PROVENANCE}；连续三时间点第 2 点（外貌）`,
    before: nsState(at('2026-09-01T12:00:02'), { characters: withCharacter(CHARACTERS_BASE, 'person_a', { position: IN_HALL }) }),
    after: nsState(at('2026-09-01T12:02:02'), {
      characters: withCharacter(withCharacter(CHARACTERS_BASE, 'person_a', { position: IN_HALL }), 'person_b', { appearanceChanges: [{ id: 'chg_b_2', text: '额头上渗出了汗珠', supersedes: [], sourcePointId: 'cp2', sourceSequence: 1, active: true }] }),
    }),
    delta: { person_b: { entityId: 'person_b', appearanceChanges: [{ id: 'chg_b_2', text: '额头上渗出了汗珠', supersedes: [] }] } },
    timeAdvance: elapsed(2, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['学生B 额头上渗出了汗珠'],
    requiredFacts: [
      { kind: 'timePassage', amount: 2, unit: 'minute', phrase: '时间流逝约两分钟（Δ 守卫）' },
      { kind: 'appearanceText', entityId: 'person_b', text: '额头上渗出了汗珠', phrase: '学生B 额头上渗出了汗珠' },
    ],
    mustNotFabricate: ['出汗的原因'],
  },
  {
    id: 'ns-cont-3', category: 'continuity', series: 'ns-cont', note: `${PROVENANCE}；连续三时间点第 3 点（空增量）——重复提及真实状态不算捏造，计入重复率/自然度；只有把旧变化说成本点再次发生才是事实错误`,
    before: nsState(at('2026-09-01T12:02:02'), {
      characters: withCharacter(withCharacter(CHARACTERS_BASE, 'person_a', { position: IN_HALL }), 'person_b', { appearanceChanges: [{ id: 'chg_b_2', text: '额头上渗出了汗珠', supersedes: [], sourcePointId: 'cp2', sourceSequence: 1, active: true }] }),
    }),
    after: nsState(at('2026-09-01T12:07:02'), {
      characters: withCharacter(withCharacter(CHARACTERS_BASE, 'person_a', { position: IN_HALL }), 'person_b', { appearanceChanges: [{ id: 'chg_b_2', text: '额头上渗出了汗珠', supersedes: [], sourcePointId: 'cp2', sourceSequence: 1, active: true }] }),
    }),
    delta: {},
    timeAdvance: elapsed(5, 'minute'), perspective: PERSPECTIVE,
    mustExpress: ['时间又过去了五分钟'],
    requiredFacts: [
      { kind: 'timePassage', amount: 5, unit: 'minute', phrase: '时间又过去了五分钟' },
    ],
    mayMention: ['当前现状陈述（学生A 在大厅、学生B 额头有汗）——作为现状合法，作为再次发生非法'],
    mustNotFabricate: ['把旧变化说成本点再次发生（如「学生A 又移动了」）', '未保存的动作经过'],
  },
];
