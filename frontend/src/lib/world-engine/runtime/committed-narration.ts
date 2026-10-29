/** Narrow narration baseline: only saved get_state records may enter this
 * application path. Validate their lineage and before/delta/after agreement,
 * then expose position and sanity facts. Proposals/results text is absent. */
import type { DataMap, Id, TimeAdvance } from '../types';

export type CommittedRead = DataMap['get_state'];
export type NarrationFact = { id: string; actorId: Id; name: string } & (
  { kind: 'at'; locationId: Id; location: string }
  | { kind: 'moved'; fromId: Id; from: string; toId: Id; to: string }
  | { kind: 'sanity'; value: number }
  | { kind: 'sanity_changed'; from: number; to: number }
  | { kind: 'task_achieved'; taskId: Id; goal: string }
  | { kind: 'personality_changed'; changeId: Id; text: string }
);
export interface CommittedNarration {
  anchor: { worldId: Id; pointId: Id; version: number; stateDigest: string; previousPointId: Id | null };
  facts: NarrationFact[];
}
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function projectCommittedNarration(after: CommittedRead, before: CommittedRead | null): CommittedNarration {
  if (!after.stateDigest || !after.pointId || !Number.isSafeInteger(after.version) || after.version < 0) throw new Error('narration_anchor_missing');
  if (after.previousPointId === null) {
    if (before !== null || after.version !== 0 || Object.keys(after.entityDeltas).length || after.timeAdvance !== null) throw new Error('narration_root_record_invalid');
  } else if (!before || before.pointId !== after.previousPointId || before.version + 1 !== after.version
    || before.state.worldId !== after.state.worldId || after.timeAdvance === null) throw new Error('narration_read_lineage_mismatch');
  if (before && (!same(before.state.initial, after.state.initial) || !same(before.state.items, after.state.items)
    || !same(before.state.locations, after.state.locations))) throw new Error('unsupported_narration_world_change');
  const facts: NarrationFact[] = [];
  const names = new Set<string>();
  const characters = Object.keys(after.state.characters).sort();
  if (before && !same(characters, Object.keys(before.state.characters).sort())) throw new Error('narration_roster_changed');
  for (const [id, delta] of Object.entries(after.entityDeltas)) {
    if (delta.entityId !== id || !after.state.characters[id]
      || Object.keys(delta).some((key) => !['entityId', 'positionSet', 'sanitySet', 'tasksAchieved', 'personalityChanges'].includes(key))) throw new Error('unsupported_committed_delta');
    if (delta.positionSet === null || delta.sanitySet === null) throw new Error('unsupported_null_delta');
    // §6.3 因果链是「任务达成 → 可能的个性变化 → 对应人物理智重算」：任务达成
    // 可以独立存在（个性变化只是可能发生），个性变化必须伴随本批任务达成，
    // 理智值必须伴随个性变化。旧规则把三件套当作同有同无，会逼模型编造个性/
    // 理智来迎合叙事投影——那不是设计。
    const hasTasks = (delta.tasksAchieved?.length ?? 0) > 0;
    const hasPersonality = (delta.personalityChanges?.length ?? 0) > 0;
    if (hasPersonality && !hasTasks) throw new Error('narration_personality_requires_task');
    if (delta.sanitySet !== undefined && !hasPersonality) throw new Error('narration_sanity_requires_personality');
  }
  for (const actorId of characters) {
    const actor = after.state.characters[actorId];
    const name = after.state.initial.characters[actorId]?.name;
    const previous = before?.state.characters[actorId];
    const delta = after.entityDeltas[actorId];
    if (!name || names.has(name) || (previous && before!.state.initial.characters[actorId].name !== name)) throw new Error('narration_actor_name_ambiguous');
    names.add(name);
    if (!Number.isFinite(actor.sanity)) throw new Error('narration_number_invalid');
    const location = after.state.initial.locations[actor.position.containerId]?.name;
    if (!location || actor.position.slotId != null || actor.position.relativeTo != null) throw new Error('unsupported_narration_position');
    const base = { actorId, name };
    if (previous && !same(previous.appearanceChanges, actor.appearanceChanges)) throw new Error('unrecorded_appearance_change');
    if (delta?.positionSet !== undefined) {
      if (!previous || !same(delta.positionSet, actor.position)) throw new Error('committed_position_delta_disagrees');
      const from = before!.state.initial.locations[previous.position.containerId]?.name;
      if (!from) throw new Error('narration_source_location_missing');
      facts.push({ ...base, id: `${actorId}:position`, kind: 'moved', fromId: previous.position.containerId, from, toId: actor.position.containerId, to: location });
    } else {
      if (previous && !same(previous.position, actor.position)) throw new Error('unrecorded_position_change');
      facts.push({ ...base, id: `${actorId}:position`, kind: 'at', locationId: actor.position.containerId, location });
    }
    // 任务达成事实独立于个性/理智：task-only Δ 是合法的结算结果（§6.3）。
    for (const taskId of delta?.tasksAchieved ?? []) {
      const oldTask = previous?.tasks[taskId];
      const task = actor.tasks[taskId];
      if (!oldTask || oldTask.status !== 'pending' || !task || task.status !== 'achieved' || task.goal !== oldTask.goal
        || task.ownerId !== actorId || oldTask.ownerId !== actorId) throw new Error('committed_task_cause_disagrees');
      facts.push({ ...base, id: `${actorId}:task:${taskId}`, kind: 'task_achieved', taskId, goal: task.goal });
    }
    for (const change of delta?.personalityChanges ?? []) {
      const stored = actor.personalityChanges.find((entry) => entry.id === change.id);
      if (!change.text || !stored || stored.text !== change.text || !same(stored.supersedes, change.supersedes)
        || stored.sourcePointId !== after.pointId || stored.sourceSequence !== after.version || !stored.active
        || change.supersedes.length) throw new Error('committed_personality_cause_disagrees');
      facts.push({ ...base, id: `${actorId}:personality:${change.id}`, kind: 'personality_changed', changeId: change.id, text: change.text });
    }
    if (delta?.sanitySet !== undefined) {
      if (!previous || delta.sanitySet !== actor.sanity) throw new Error('committed_numeric_delta_disagrees');
      facts.push({ ...base, id: `${actorId}:sanity`, kind: 'sanity_changed', from: previous.sanity, to: actor.sanity });
    } else {
      if (previous && previous.sanity !== actor.sanity) throw new Error('unrecorded_numeric_change');
      facts.push({ ...base, id: `${actorId}:sanity`, kind: 'sanity', value: actor.sanity });
    }
    if (previous) {
      const expectedTasks = structuredClone(previous.tasks);
      for (const taskId of delta?.tasksAchieved ?? []) {
        if (!expectedTasks[taskId]) throw new Error('committed_task_cause_disagrees');
        expectedTasks[taskId].status = 'achieved';
      }
      if (!same(expectedTasks, actor.tasks)) throw new Error('unrecorded_task_change');
      const previousIds = new Set(previous.personalityChanges.map((change) => change.id));
      const newChanges = actor.personalityChanges.filter((change) => !previousIds.has(change.id));
      if (!same(actor.personalityChanges.filter((change) => previousIds.has(change.id)), previous.personalityChanges)
        || !same(newChanges.map((change) => change.id), (delta?.personalityChanges ?? []).map((change) => change.id))) throw new Error('unrecorded_personality_change');
    }
  }
  return { anchor: { worldId: after.state.worldId, pointId: after.pointId, version: after.version,
    stateDigest: after.stateDigest, previousPointId: after.previousPointId }, facts };
}

/** A small, explicit paraphrase language. Unknown clauses fail closed;
 * keyword/number presence alone cannot prove absence of invented events. */
export function factPhrases(fact: NarrationFact): string[] {
  switch (fact.kind) {
    case 'at': return [`${fact.name}位于${fact.location}`, `${fact.name}现在在${fact.location}`];
    case 'moved': return [`${fact.name}从${fact.from}走到${fact.to}`, `${fact.name}从${fact.from}来到${fact.to}`];
    case 'sanity': return [`${fact.name}的精神值为${fact.value}`, `${fact.name}当前精神值是${fact.value}`];
    case 'sanity_changed': return [`${fact.name}的精神值从${fact.from}变为${fact.to}`,
      `${fact.name}的精神值由${fact.from}${fact.to < fact.from ? '降至' : '升至'}${fact.to}`];
    case 'task_achieved': return [`${fact.name}完成了任务「${fact.goal}」`, `${fact.name}已达成任务「${fact.goal}」`];
    case 'personality_changed': return [`${fact.name}的人格变化为「${fact.text}」`, `${fact.name}形成了新的人格描述「${fact.text}」`];
  }
}
const TIME_UNIT_CN: Record<TimeAdvance['duration']['unit'], string> =
  { second: '秒', minute: '分钟', hour: '小时', day: '天', month: '个月', year: '年' };
const CN_TIME_DIGITS = ['零', '一', '两', '三', '四', '五', '六', '七', '八', '九', '十'];
const cnAmount = (n: number) => (Number.isInteger(n) && n >= 0 && n <= 10 ? CN_TIME_DIGITS[n] : String(n));

export interface NarrationRenderOptions {
  /** §5.2：timeAdvance 属于 Δ。给出时模板先述本点时间；空事实包不再输出空串，
   * 改用「时间 + 没有新的变化」固定句式。关闭 2026-10-28 归档记录的两个已知
   * 缺口（模板从不写时间、空增量点输出空串）。 */
  time?: { amount: number; unit: TimeAdvance['duration']['unit'] } | null;
}
export function renderCommittedNarration(packet: CommittedNarration, options: NarrationRenderOptions = {}): string {
  const time = options.time ?? null;
  const elapsed = time ? `约${cnAmount(time.amount)}${TIME_UNIT_CN[time.unit]}过去了` : null;
  if (packet.facts.length === 0) return elapsed ? `${elapsed}，没有新的变化。` : '';
  const body = packet.facts.map((fact) => `${factPhrases(fact)[0]}。`).join('');
  return elapsed ? `${elapsed}。${body}` : body;
}
export function checkFactNarration(packet: CommittedNarration, text: string): { ok: boolean; reason: string | null } {
  const seen = new Set<string>();
  const clauses = text.split(/[。！？\n]+/).map((part) => part.trim()).filter(Boolean);
  for (const clause of clauses) {
    const matches = packet.facts.filter((fact) => factPhrases(fact).includes(clause));
    if (matches.length !== 1) return { ok: false, reason: 'unknown_or_ambiguous_clause' };
    if (seen.has(matches[0].id)) return { ok: false, reason: 'duplicate_fact' };
    seen.add(matches[0].id);
  }
  return seen.size === packet.facts.length ? { ok: true, reason: null } : { ok: false, reason: 'missing_fact' };
}

export function selectFactNarration(packet: CommittedNarration, modelText: string,
  options: NarrationRenderOptions = {}): { text: string; accepted: boolean; reason: string | null } {
  const verdict = checkFactNarration(packet, modelText);
  return { text: verdict.ok ? modelText : renderCommittedNarration(packet, options), accepted: verdict.ok, reason: verdict.reason };
}
