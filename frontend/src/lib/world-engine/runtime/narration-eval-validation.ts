/** Validation samples for the narration evaluation: the same committed-packet
 * shape as `narration-eval-samples.ts`, frozen after the 2026-10-28 grader
 * fixes and template supplement, over a DIFFERENT surface (学生C/学生D/老师,
 * 食堂/操场/宿舍/图书馆).
 *
 * 口径（2026-10-28 二轮复核更正）：冻结时它们是留出集——当时的全部校准与放宽
 * 决策确实只来自 nv-* 主集。但 requireTime 首轮重跑后，`hv-sanity-1` 的采纳稿
 * 「学生D的精神值从12降至9」直接推动了两处判分器修正（值槽位「值一路」误杀、
 * 强签名 swap 的 bound 跳过），并进入了回归测试。因此这六例此后参与了校准，
 * 现在是验证集（validation set）：其成绩如实保留，但「样本外、未参与校准」
 * 的说法不再成立；真正样本外的检查需要从当前头另行冻结新集。
 *
 * Same contracts as the main corpus: `mechanical` stays inside the old
 * exact-clause gate; `reference` is a human rendering that must pass under
 * requireTime (positive fixture); `forbidden` lists the mutations the grader
 * must recognise. */
import type { TimeAdvance } from '../types';
import type { CommittedNarration } from './committed-narration';
import type { NarrationEvalSample } from './narration-eval-samples';

const ANCHOR = (pointId: string) => ({ worldId: 'world_school', pointId, version: 1,
  stateDigest: 'e'.repeat(64), previousPointId: 'root_school' });
const CANTEEN_WORLD_LOCATIONS = ['食堂', '操场', '宿舍', '图书馆'];
const CANTEEN_WORLD_CAST = ['学生C', '学生D', '老师'];

export const NARRATION_EVAL_VALIDATION_SAMPLES: NarrationEvalSample[] = [
  {
    id: 'hv-move-1', category: 'movement', note: '验证：位置变化，学生C 食堂→操场，3 分钟；参照用走向＋约三分钟',
    packet: { anchor: ANCHOR('p_hv_move_1'), facts: [
      { id: 'person_c:position', actorId: 'person_c', name: '学生C', kind: 'moved',
        fromId: 'canteen', from: '食堂', toId: 'playground', to: '操场' },
    ] },
    time: { amount: 3, unit: 'minute' }, locations: CANTEEN_WORLD_LOCATIONS, roster: CANTEEN_WORLD_CAST,
    mechanical: '学生C从食堂来到操场。',
    reference: '学生C走向操场，前后约三分钟。',
    forbidden: ['学生C从操场走到食堂（方向反转）', '学生C推开栅栏冲进操场（新增事件）'],
  },
  {
    id: 'hv-sanity-1', category: 'task_personality_sanity', note: '验证：仅精神值下降，学生C 12→9，2 分钟',
    packet: { anchor: ANCHOR('p_hv_sanity_1'), facts: [
      { id: 'person_c:sanity', actorId: 'person_c', name: '学生C', kind: 'sanity_changed', from: 12, to: 9 },
    ] },
    time: { amount: 2, unit: 'minute' }, locations: CANTEEN_WORLD_LOCATIONS, roster: CANTEEN_WORLD_CAST,
    mechanical: '学生C的精神值由12降至9。',
    reference: '学生C的精神值一路从12降到了9，前后大约两分钟。',
    forbidden: ['精神值从12变为8（数值错误）', '学生D的精神值从12降到了9（人物互换）'],
  },
  {
    id: 'hv-task-pers-1', category: 'task_personality_sanity',
    note: '验证：任务→人格→精神值联动，学生D「整理图书角」＋变得沉默＋11→13，1 分钟；参照用提升至',
    packet: { anchor: ANCHOR('p_hv_task_pers_1'), facts: [
      { id: 'person_d:task:task_shelf', actorId: 'person_d', name: '学生D', kind: 'task_achieved',
        taskId: 'task_shelf', goal: '整理图书角' },
      { id: 'person_d:personality:chg_d_1', actorId: 'person_d', name: '学生D', kind: 'personality_changed',
        changeId: 'chg_d_1', text: '变得沉默' },
      { id: 'person_d:sanity', actorId: 'person_d', name: '学生D', kind: 'sanity_changed', from: 11, to: 13 },
    ] },
    time: { amount: 1, unit: 'minute' }, locations: CANTEEN_WORLD_LOCATIONS, roster: CANTEEN_WORLD_CAST,
    mechanical: '学生D已达成任务「整理图书角」。学生D形成了新的人格描述「变得沉默」。学生D的精神值由11升至13。',
    reference: '学生D完成了任务「整理图书角」，人也变得沉默，精神值提升至13。前后不过一分钟。',
    forbidden: ['学生D完成了任务「帮主角熟悉校园」（任务替换）', '精神值提升至15（数值错误）',
      '学生C完成了任务「整理图书角」（人物互换）'],
  },
  {
    id: 'hv-refused-1', category: 'refused_action', note: '验证：被拒绝的行动，无实体 Δ，只有 2 秒',
    packet: { anchor: ANCHOR('p_hv_refused_1'), facts: [] },
    time: { amount: 2, unit: 'second' }, locations: CANTEEN_WORLD_LOCATIONS, roster: CANTEEN_WORLD_CAST,
    mechanical: '',
    reference: '学生C停在原地，两秒钟就这样过去了。',
    forbidden: ['学生C走到了图书馆（拒绝的行动被叙述成发生）', '学生C站在食堂（无事实的站位）'],
  },
  {
    id: 'hv-empty-1', category: 'no_change', note: '验证：空增量，只有 10 分钟流逝',
    packet: { anchor: ANCHOR('p_hv_empty_1'), facts: [] },
    time: { amount: 10, unit: 'minute' }, locations: CANTEEN_WORLD_LOCATIONS, roster: CANTEEN_WORLD_CAST,
    mechanical: '',
    reference: '十分钟后，一切照旧，没有新的变化。',
    forbidden: ['学生C站在食堂（无事实的站位）', '老师完成了任务「整理图书角」（无事实的任务）'],
  },
  {
    id: 'hv-multi-opposite-1', category: 'multi_character',
    note: '验证：两名角色一句内反向移动，学生C 宿舍→食堂，学生D 食堂→宿舍，4 秒',
    packet: { anchor: ANCHOR('p_hv_opposite_1'), facts: [
      { id: 'person_c:position', actorId: 'person_c', name: '学生C', kind: 'moved',
        fromId: 'dorm', from: '宿舍', toId: 'canteen', to: '食堂' },
      { id: 'person_d:position', actorId: 'person_d', name: '学生D', kind: 'moved',
        fromId: 'canteen', from: '食堂', toId: 'dorm', to: '宿舍' },
    ] },
    time: { amount: 4, unit: 'second' }, locations: CANTEEN_WORLD_LOCATIONS, roster: CANTEEN_WORLD_CAST,
    mechanical: '学生C从宿舍来到食堂。学生D从食堂来到宿舍。',
    reference: '四秒钟里，学生C从宿舍走进了食堂，学生D则从食堂回到了宿舍。',
    forbidden: ['学生C从食堂走到宿舍（两人方向互换）', '学生D从宿舍走到食堂（两人方向互换）'],
  },
];
