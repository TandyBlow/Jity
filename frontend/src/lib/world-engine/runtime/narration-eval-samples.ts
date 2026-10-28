/** Frozen samples for the second small-model narration batch: state alignment
 * and natural expression over the COMMITTED narration path (the one the page
 * uses). Each sample freezes a committed packet (`projectCommittedNarration`
 * output shape) plus the time passage, so the three arms — template, current
 * mechanical polish, natural model text — are graded against the same facts.
 *
 * Corpus (10 samples, hand-frozen 2026-10-28 from the T01 school semantics and
 * the rule-facts committed deltas; the corpus is a committed fixture and does
 * not drift with traces. 2026-10-28 review revision: nv-cont-3 additionally
 * freezes the standing fact its own reference and mayMention assert — see its
 * note; the other nine are unchanged):
 * - movement, task→personality→sanity coupling, two-actor point, task only,
 *   refused action (no entity delta at all), no change, and a three-point
 *   continuity series (movement → appearance → no change).
 *
 * `mechanical` is what the current page path can accept: one of the two
 * declared short-sentence variants per fact, concatenated (`checkFactNarration`
 * only accepts those exact clauses). `reference` is a human natural rendering
 * used for the human comparison and as a positive grader fixture — it is NOT
 * the only accepted wording; the grader is alignment-based, not phrase-based.
 *
 * `forbidden` lists claims the sample must never make. They are the mutation
 * seeds of the grader self-test: swapping the actor, reversing the direction,
 * changing a number, claiming an unfinished task, adding an event. */
import type { TimeAdvance } from '../types';
import type { CommittedNarration } from './committed-narration';

export type NarrationEvalCategory =
  | 'movement' | 'task_personality_sanity' | 'multi_character' | 'refused_action'
  | 'no_change' | 'continuity';

export interface NarrationEvalSample {
  id: string;
  category: NarrationEvalCategory;
  note: string;
  /** 已提交事实（committed-narration 的 facts 形状，模板与判分共用）。 */
  packet: CommittedNarration;
  /** §5.2：timeAdvance 属于 Δ，空增量点必述时间。 */
  time: { amount: number; unit: TimeAdvance['duration']['unit'] } | null;
  /** 世界内地点名册（拒绝行动的样本没有位置事实，靠它识别「移动了」的假声明）。 */
  locations: string[];
  /** 世界内角色名册：没有事实的角色也可能被模型错误地写进正文。 */
  roster: string[];
  /** 当前页面能接受的机械拼接（两条声明句型之一逐条拼接）。 */
  mechanical: string;
  /** 人工自然表达参照（人类比较用，不是唯一可接受写法）。 */
  reference: string;
  /** 该样本禁止出现的主张（判分器必须能识别）。 */
  forbidden: string[];
  /** 连续样本：同序列前点文本，用于重复率。 */
  previousText?: string;
}

const ANCHOR = (pointId: string) => ({ worldId: 'world_school', pointId, version: 1,
  stateDigest: 'f'.repeat(64), previousPointId: 'root_school' });
const SCHOOL_LOCATIONS = ['走廊', '大厅', '门厅', '教室'];
const SCHOOL_CAST = ['学生A', '学生B', '主角'];

export const NARRATION_EVAL_SAMPLES: NarrationEvalSample[] = [
  {
    id: 'nv-move-1', category: 'movement', note: '位置变化：学生A 走廊→大厅，时间约两分钟',
    packet: { anchor: ANCHOR('p_nv_move_1'), facts: [
      { id: 'person_a:position', actorId: 'person_a', name: '学生A', kind: 'moved',
        fromId: 'corridor', from: '走廊', toId: 'hall', to: '大厅' },
    ] },
    time: { amount: 2, unit: 'minute' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '学生A从走廊来到大厅。',
    reference: '学生A离开走廊，走进大厅，前后大约花了两分钟。',
    forbidden: ['学生A从大厅走到走廊（方向反转）', '学生A推开门冲进大厅（新增事件）'],
  },
  {
    id: 'nv-task-pers-sanity-1', category: 'task_personality_sanity',
    note: '任务→人格→精神值联动：学生B 达成「帮主角熟悉校园」，个性变得健谈，精神值 10→12',
    packet: { anchor: ANCHOR('p_nv_tps_1'), facts: [
      { id: 'person_b:task:task_intro', actorId: 'person_b', name: '学生B', kind: 'task_achieved',
        taskId: 'task_intro', goal: '帮主角熟悉校园' },
      { id: 'person_b:personality:chg_b_1', actorId: 'person_b', name: '学生B', kind: 'personality_changed',
        changeId: 'chg_b_1', text: '变得健谈' },
      { id: 'person_b:sanity', actorId: 'person_b', name: '学生B', kind: 'sanity_changed', from: 10, to: 12 },
    ] },
    time: { amount: 1, unit: 'minute' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '学生B已达成任务「帮主角熟悉校园」。学生B形成了新的人格描述「变得健谈」。学生B的精神值由10升至12。',
    reference: '带着主角在校园里转了一圈之后，学生B完成了任务「帮主角熟悉校园」。学生B也变得健谈起来，精神值从10升到了12。前后不过一分钟。',
    forbidden: ['精神值从10变为8（数值错误）', '主角完成了任务「帮主角熟悉校园」（人物互换）',
      '学生B完成了任务「取回柜子里的东西」（任务替换）'],
  },
  {
    id: 'nv-multi-1', category: 'multi_character', note: '同点多人物：学生A 走廊→大厅；主角已在大厅（无变化也要能述现状）',
    packet: { anchor: ANCHOR('p_nv_multi_1'), facts: [
      { id: 'person_a:position', actorId: 'person_a', name: '学生A', kind: 'moved',
        fromId: 'corridor', from: '走廊', toId: 'hall', to: '大厅' },
      { id: 'person_c:position', actorId: 'person_c', name: '主角', kind: 'at',
        locationId: 'hall', location: '大厅' },
    ] },
    time: { amount: 1, unit: 'minute' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '学生A从走廊来到大厅。主角现在在大厅。',
    reference: '学生A从走廊来到大厅时，主角已经在大厅里等着了。大约过了一分钟。',
    forbidden: ['主角从走廊走到大厅（人物互换＋方向）', '学生A位于大厅，主角从走廊走到大厅（人物互换）'],
  },
  {
    id: 'nv-task-only-1', category: 'task_personality_sanity', note: '仅任务达成（无位置/数值）：主角 取回柜子里的东西',
    packet: { anchor: ANCHOR('p_nv_task_1'), facts: [
      { id: 'person_c:task:task_shelf', actorId: 'person_c', name: '主角', kind: 'task_achieved',
        taskId: 'task_shelf', goal: '取回柜子里的东西' },
    ] },
    time: { amount: 30, unit: 'second' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '主角已达成任务「取回柜子里的东西」。',
    reference: '主角顺利完成了任务「取回柜子里的东西」，前后花了30秒。',
    forbidden: ['主角完成了任务「帮主角熟悉校园」（任务替换）', '学生B完成了任务「取回柜子里的东西」（人物互换）'],
  },
  {
    id: 'nv-refused-1', category: 'refused_action', note: '被拒绝的行动：意图「走到门厅」因理智不足未成立，无实体 Δ，只有 1 秒时间',
    packet: { anchor: ANCHOR('p_nv_refused_1'), facts: [] },
    time: { amount: 1, unit: 'second' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '',
    reference: '主角停在原地，没有往前迈步。一秒钟就这样过去了。',
    forbidden: ['主角走到了门厅（拒绝的行动被叙述成发生）', '主角推开走廊尽头的门（新增事件）'],
  },
  {
    id: 'nv-empty-1', category: 'no_change', note: '空增量：只有 5 分钟流逝，无任何实体变化',
    packet: { anchor: ANCHOR('p_nv_empty_1'), facts: [] },
    time: { amount: 5, unit: 'minute' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '',
    reference: '四周安静下来，五分钟过去了，没有新的变化。',
    forbidden: ['学生A走进了大厅（无事实的移动）', '主角完成了任务「取回柜子里的东西」（无事实的任务）'],
  },
  {
    id: 'nv-cont-1', category: 'continuity', note: '连续三点第 1 点：学生A 走廊→大厅，2 秒',
    packet: { anchor: ANCHOR('p_nv_cont_1'), facts: [
      { id: 'person_a:position', actorId: 'person_a', name: '学生A', kind: 'moved',
        fromId: 'corridor', from: '走廊', toId: 'hall', to: '大厅' },
    ] },
    time: { amount: 2, unit: 'second' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '学生A从走廊来到大厅。',
    reference: '两秒钟后，学生A已经从走廊走到了大厅。',
    forbidden: ['学生A从大厅走到了走廊（方向反转）'],
  },
  {
    id: 'nv-cont-2', category: 'continuity', note: '连续三点第 2 点：学生B 仍在大厅（现状陈述，本点无实体变化），2 分钟',
    packet: { anchor: ANCHOR('p_nv_cont_2'), facts: [
      { id: 'person_b:position', actorId: 'person_b', name: '学生B', kind: 'at',
        locationId: 'hall', location: '大厅' },
    ] },
    time: { amount: 2, unit: 'minute' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '学生B现在在大厅。',
    reference: '学生B还站在大厅里，两分钟就这么过去了。',
    forbidden: ['学生B从走廊走到大厅（本点没有移动事实）', '学生A位于大厅（人物互换）'],
  },
  {
    id: 'nv-cont-3', category: 'continuity',
    note: '连续三点第 3 点：空增量，5 分钟；重复提及前点现状合法，重演旧变化非法。2026-10-28 复核补冻：学生A 仍在大厅（本样本参照文本与 mayMention 均述及该现状，nv-cont-2 同型）——判分器修复零位置事实点的站位洞后，现状声明需要已提交事实背书',
    packet: { anchor: ANCHOR('p_nv_cont_3'), facts: [
      { id: 'person_a:position', actorId: 'person_a', name: '学生A', kind: 'at',
        locationId: 'hall', location: '大厅' },
    ] },
    time: { amount: 5, unit: 'minute' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '',
    reference: '学生A仍然待在大厅，五分钟又过去了。',
    previousText: '学生A从走廊走到大厅。学生B还站在大厅里，两分钟过去，他的呼吸慢慢平复了。',
    forbidden: ['学生A又从走廊走到了大厅（把旧变化说成再次发生）'],
  },
  {
    id: 'nv-multi-opposite-1', category: 'multi_character',
    note: '两名角色反向移动：学生A 走廊→大厅，学生B 大厅→走廊（互换检测的主用例）',
    packet: { anchor: ANCHOR('p_nv_opposite_1'), facts: [
      { id: 'person_a:position', actorId: 'person_a', name: '学生A', kind: 'moved',
        fromId: 'corridor', from: '走廊', toId: 'hall', to: '大厅' },
      { id: 'person_b:position', actorId: 'person_b', name: '学生B', kind: 'moved',
        fromId: 'hall', from: '大厅', toId: 'corridor', to: '走廊' },
    ] },
    time: { amount: 3, unit: 'second' }, locations: SCHOOL_LOCATIONS, roster: SCHOOL_CAST,
    mechanical: '学生A从走廊来到大厅。学生B从大厅来到走廊。',
    reference: '三秒钟里，学生A从走廊走进大厅，学生B正好从大厅出来，回到走廊。',
    forbidden: ['学生A从大厅走到走廊（两人方向互换）', '学生B从走廊走到大厅（两人方向互换）'],
  },
];
