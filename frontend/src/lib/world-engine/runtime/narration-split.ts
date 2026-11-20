/** Narration expression-split pipeline — rule baseline (v0, zero model
 * calls). Splits the plan's §7.1 narration interface (Sₜ₋₁, Δₜ, Sₜ,
 * perspective) into four stages: locate (read the structured delta),
 * select (which fragments are worth expressing — v0 rule: every located
 * change with text is expressible), organize (six-step field order,
 * entity-grouped), compose (deterministic template sentences). Small-model
 * candidates replace stages 2–4 behind these same interfaces later.
 * Intermediate products are per-inference working data, never archived.
 *
 * Known v0 limits (each is an evaluation question, not a silent choice):
 * - timeAdvance 属于 Δ（§5.2），time fragment is ALWAYS emitted; whether
 *   "到点"语义（如 12:00 使「坚持到中午」达成）需要显式报时属于内容选择
 *   规则的评价问题，v0 只表达时间流逝＋任务达成。
 * - carried items' implicit path changes are not narrated (only direct
 *   deltas — 携带物品不给后代伪造直接更新，§3.2).
 * - supersedes-only changes (text=null) express nothing new at v0.
 * - sanity is realized as a plain value statement; naturalness is
 *   human-rated.
 * - perspective is accepted per §7.1 but templates are perspective-neutral
 *   at v0. */
import type { Change, EntityDelta, Id, Position, Task, TimeAdvance, WorldState } from '../types';

// ---------- 展示名解析（内容选择与评测共用） ----------

export function entityName(state: WorldState, id: Id): string {
  return state.initial.characters[id]?.name ?? state.initial.items[id]?.name ?? state.initial.locations[id]?.name ?? id;
}

export function containerName(state: WorldState, position: Position | null | undefined): string | null {
  if (!position) return null;
  const id = position.containerId;
  return state.initial.locations[id]?.name ?? state.initial.items[id]?.name ?? state.initial.characters[id]?.name ?? null;
}

// ---------- stage 1：变化定位（程序直接读取 Δ，零模型） ----------

export interface LocatedChange {
  entityId: Id;
  field: 'position' | 'appearance' | 'taskAchieved' | 'subtaskAdded' | 'personality' | 'sanity';
  change?: Change;
  taskIds?: Id[];
  tasks?: Task[];
  fromPosition?: Position | null;
  toPosition?: Position;
  sanity?: { from: number; to: number };
}

export function locateChanges(before: WorldState, delta: Record<Id, EntityDelta>): LocatedChange[] {
  const located: LocatedChange[] = [];
  for (const [entityId, d] of Object.entries(delta)) {
    const live = before.characters[entityId] ?? before.items[entityId];
    if (d.positionSet) located.push({ entityId, field: 'position', fromPosition: live?.position ?? null, toPosition: d.positionSet });
    for (const change of d.appearanceChanges ?? []) located.push({ entityId, field: 'appearance', change });
    if (d.tasksAchieved?.length) located.push({ entityId, field: 'taskAchieved', taskIds: d.tasksAchieved });
    if (d.subtasksAdded?.length) located.push({ entityId, field: 'subtaskAdded', tasks: d.subtasksAdded });
    for (const change of d.personalityChanges ?? []) located.push({ entityId, field: 'personality', change });
    if (d.sanitySet != null) {
      const from = live && 'sanity' in live ? live.sanity : Number.NaN;
      located.push({ entityId, field: 'sanity', sanity: { from, to: d.sanitySet } });
    }
  }
  return located;
}

// ---------- stage 2：内容选择（v0 规则：Δ 皆可述；对照小模型打分） ----------

export type Fragment =
  | { kind: 'time'; source: string; amount: number; unit: TimeAdvance['duration']['unit'] }
  | { kind: 'position'; source: string; entityId: Id; name: string; fromName: string | null; toName: string }
  | { kind: 'appearance'; source: string; entityId: Id; name: string; text: string }
  | { kind: 'taskAchieved'; source: string; entityId: Id; name: string; goal: string }
  | { kind: 'newTask'; source: string; entityId: Id; name: string; goal: string }
  | { kind: 'personality'; source: string; entityId: Id; name: string; text: string }
  | { kind: 'sanity'; source: string; entityId: Id; name: string; from: number; to: number };

export function selectContent(located: LocatedChange[], before: WorldState, timeAdvance: TimeAdvance): Fragment[] {
  const fragments: Fragment[] = [];
  // timeAdvance 属于 Δ（§5.2）——空增量样本也必须述时间；有变化的时间点同样述时间。
  fragments.push({ kind: 'time', source: 'timeAdvance', amount: timeAdvance.duration.amount, unit: timeAdvance.duration.unit });
  for (const c of located) {
    const name = entityName(before, c.entityId);
    if (c.field === 'position') {
      fragments.push({ kind: 'position', source: `delta.${c.entityId}.positionSet`, entityId: c.entityId, name, fromName: containerName(before, c.fromPosition), toName: containerName(before, c.toPosition) ?? String(c.toPosition?.containerId ?? '') });
    } else if (c.field === 'appearance' || c.field === 'personality') {
      if (c.change?.text == null) continue; // 纯解除（text=null）v0 无新内容可述
      fragments.push({ kind: c.field, source: `delta.${c.entityId}.${c.field}Changes`, entityId: c.entityId, name, text: c.change.text });
    } else if (c.field === 'taskAchieved') {
      for (const taskId of c.taskIds ?? []) {
        const goal = before.characters[c.entityId]?.tasks[taskId]?.goal;
        fragments.push({ kind: 'taskAchieved', source: `delta.${c.entityId}.tasksAchieved`, entityId: c.entityId, name, goal: goal ?? taskId });
      }
    } else if (c.field === 'subtaskAdded') {
      for (const task of c.tasks ?? []) fragments.push({ kind: 'newTask', source: `delta.${c.entityId}.subtasksAdded`, entityId: c.entityId, name, goal: task.goal });
    } else {
      fragments.push({ kind: 'sanity', source: `delta.${c.entityId}.sanitySet`, entityId: c.entityId, name, from: c.sanity!.from, to: c.sanity!.to });
    }
  }
  return fragments;
}

// ---------- stage 3：组织表达（v0 规则：六步字段序；对照小模型） ----------

const FIELD_RANK: Record<Fragment['kind'], number> = { time: 0, position: 1, appearance: 2, taskAchieved: 3, newTask: 3, personality: 4, sanity: 5 };

export interface ExpressionPlan {
  ordered: Fragment[];
  /** 称呼表（v0=展示名恒定）；键为片段实体 ID。 */
  address: Record<Id, string>;
  /** 被省略的片段（v0 恒空——省略属选择性描述，交给后续规则/模型）。 */
  omitted: Fragment[];
}

export interface OrganizeContext {
  /** 可选的叙事缓存辅助（近期已述内容）；缓存缺失时仍按原状态接口生成，
   * 不形成新的存档依赖。v0 未启用重复抑制——重复计入重复率评分。 */
  recentNarrations?: readonly string[];
  /** §7.1 主角视角约束——v0 未产生效果（评价问题）。 */
  perspective?: string;
}

export function organizeExpression(fragments: Fragment[], context: OrganizeContext = {}): ExpressionPlan {
  void context;
  const ordered = [...fragments].sort((a, b) => FIELD_RANK[a.kind] - FIELD_RANK[b.kind] || ('entityId' in a ? a.entityId : '').localeCompare('entityId' in b ? b.entityId : ''));
  const address: Record<Id, string> = {};
  for (const f of ordered) if ('entityId' in f) address[f.entityId] = f.name;
  return { ordered, address, omitted: [] };
}

// ---------- stage 4：成句（v0=模板句；对照专用小条件生成模型） ----------

const CN_SMALL = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];
export const UNIT_CN: Record<TimeAdvance['duration']['unit'], string> = { second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' };
export const cnNum = (n: number): string => (Number.isInteger(n) && n >= 0 && n <= 10 ? CN_SMALL[n] : String(n));

export function composeSentences(plan: ExpressionPlan, perspective: string = ''): string {
  // perspective 按 §7.1 接收；v0 模板为视角中立，未产生效果——这是声明的
  // v0 未实现能力（评价问题），不是已验证的视角约束。
  void perspective;
  const sentences: string[] = [];
  for (const f of plan.ordered) {
    if (f.kind === 'time') sentences.push(`约${cnNum(f.amount)}${UNIT_CN[f.unit]}过去了。`);
    else if (f.kind === 'position') sentences.push(f.fromName ? `${f.name}从${f.fromName}来到了${f.toName}。` : `${f.name}来到了${f.toName}。`);
    else if (f.kind === 'appearance' || f.kind === 'personality') sentences.push(f.text.includes(f.name) ? `${f.text}。` : `${f.name}${f.text}。`);
    else if (f.kind === 'taskAchieved') sentences.push(`${f.name}完成了任务「${f.goal}」。`);
    else if (f.kind === 'newTask') sentences.push(`${f.name}有了一个新任务：${f.goal}。`);
    else sentences.push(`${f.name}的理智值${f.to > f.from ? '升为' : '降为'}${f.to}。`);
  }
  return sentences.join('');
}

// ---------- 全链入口 ----------

/** Input sanity gate: the AFTER state must already reflect every delta field
 * — the pipeline narrates committed facts, not intentions. Gives the §7.1
 * `after` input a real role instead of an unused parameter. */
export function assertDeltaConsistent(before: WorldState, delta: Record<Id, EntityDelta>, after: WorldState): void {
  for (const [entityId, d] of Object.entries(delta)) {
    // 地点也能出现在增量里（§9.2 字段权限：地点只接收外貌变化）——此前缺
    // 地点分支，合法的地点外貌增量会被这里误拒。
    const afterEntity = after.characters[entityId] ?? after.items[entityId] ?? after.locations[entityId];
    if (!afterEntity) throw new Error(`narration input: delta entity ${entityId} missing from after state`);
    if (d.positionSet) {
      // 地点没有位置字段（地点树首版固定）——带 positionSet 的地点增量在
      // apply 层就非法，不该到达叙事层。
      if (!('position' in afterEntity) || JSON.stringify(afterEntity.position) !== JSON.stringify(d.positionSet)) {
        throw new Error(`narration input: ${entityId} position does not reflect the delta`);
      }
    }
    for (const c of [...(d.appearanceChanges ?? []), ...(d.personalityChanges ?? [])]) {
      const storedAppearance = afterEntity.appearanceChanges.find((x) => x.id === c.id);
      const storedPersonality = 'personalityChanges' in afterEntity ? afterEntity.personalityChanges.find((x) => x.id === c.id) : undefined;
      const stored = storedAppearance ?? storedPersonality;
      if (!stored || stored.text !== c.text) throw new Error(`narration input: change ${c.id} missing or mismatched in after state`);
    }
    const afterCharacter = after.characters[entityId];
    if (d.sanitySet != null && (!afterCharacter || afterCharacter.sanity !== d.sanitySet)) {
      throw new Error(`narration input: ${entityId} sanity does not reflect the delta`);
    }
    for (const tid of d.tasksAchieved ?? []) {
      const task = afterCharacter?.tasks?.[tid];
      if (!task || task.status !== 'achieved') throw new Error(`narration input: task ${tid} not achieved in after state`);
    }
    for (const t of d.subtasksAdded ?? []) {
      if (!afterCharacter?.tasks?.[t.id]) throw new Error(`narration input: subtask ${t.id} missing from after state`);
    }
  }
}

export interface NarrationInput {
  before: WorldState;
  delta: Record<Id, EntityDelta>;
  after: WorldState;
  timeAdvance: TimeAdvance;
  /** §7.1 主角视角约束。v0 接收并透传，模板未产生效果（声明的未实现能力）。 */
  perspective: string;
}

export interface NarrationPipelineResult {
  located: LocatedChange[];
  fragments: Fragment[];
  plan: ExpressionPlan;
  text: string;
}

export function runNarrationPipeline(input: NarrationInput): NarrationPipelineResult {
  assertDeltaConsistent(input.before, input.delta, input.after);
  const located = locateChanges(input.before, input.delta);
  const fragments = selectContent(located, input.before, input.timeAdvance);
  const plan = organizeExpression(fragments, { perspective: input.perspective });
  const text = composeSentences(plan, input.perspective);
  return { located, fragments, plan, text };
}
