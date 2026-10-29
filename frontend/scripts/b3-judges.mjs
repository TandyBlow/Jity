// B3 settlement-task judges (Node side). The harness only produces evidence
// (prompts, raw model text, parsed output, completion timings); every verdict
// is computed here, from the saved evidence. One judge serves live runs and
// re-scoring of older archives.
//
// Three independent facts per probe/call:
//   parsed    the raw text parsed as JSON (model output exists and is JSON)
//   codec     the parsed value satisfies the task's current shape/field contract
//   semantics pass | fail | review
//             `review` means the remaining question cannot be decided
//             automatically (free-text plausibility); it NEVER counts as a pass.
//
// Automatic checks are deliberately narrow and evidence-bound:
//   - attribution: if a roster name opens the text it must be the bound actor;
//     a text without any roster name is not misattribution (the call binds the actor);
//   - action vs goal: goal/plan sentences are not actions (§6.1);
//   - consumed input: the protagonist must not re-execute the player command;
//     other characters still act from their own tasks (§6.1);
//   - results: per-member attribution, dice agreement, traceability to the
//     frozen action / task goals / roll evidence;
//   - reactions: attribution, no state claims, not a copy of the source action,
//     traceable to the source action or the member's tasks (else fail);
//   - updates: codec (stage/fields/types), entity ownership, §6.3 causality
//     accumulated over the whole batch (anybody's achieved task may trigger
//     anybody's personality; personality+sanity stay paired per entity), plus
//     the probe's declared change expectation;
//   - continuation: the two §8.1 conditions must be stated (candidate + planned
//     action + protagonist relevance); "tasks incomplete" alone is not a reason.

const GOAL_WORDS = /需要|应该|打算|想要|愿意|必须|准备|试图|计划|希望|决定要/;
const STATE_CLAIM = /精神值|理智值|理智|生命值|血量|任务(达成|完成)|状态值|属性(值|变化)/;
// 骰点表述词表（复核轮 19 修正）：裸「未」会误伤“未来”，必须撤掉；
// “未成功/没有成功/未能/没能”是否定式成功表述，属于失败措辞，不属于成功措辞。
const NEGATED_SUCCESS = /未成功|没有成功|未能成功|没能成功|未能达成|没有达成|未达成|没有完成|未完成|没有通过|未通过|没有做到|未能|没能/;
const SUCCESS_NAKED = /成功|顺利|得手|达成|完成|通过|做到|搞定/;
const FAILURE_TRIGGERS = new RegExp(`${NEGATED_SUCCESS.source}|失败|落空|被挡|挡下|无效|拒绝`);
const STRIP_NEGATED = new RegExp(NEGATED_SUCCESS.source, 'g');

/** 成功措辞：先把否定式成功表述全部剥掉，再看剩下的部分里有没有裸成功词。
 *  “未成功”永远不再被当作成功表述。 */
function successWording(clause) {
  return SUCCESS_NAKED.test(text(clause).replace(STRIP_NEGATED, ''));
}

/** 失败措辞：不含裸「未」，但含未成功/失败/落空/被挡/无效/拒绝等明确否定。 */
function failureWording(clause) {
  return FAILURE_TRIGGERS.test(text(clause));
}

/** 纯判定句：剥掉人物名、标点与时点表述词后剩下零字符——
 *  这类句子正是提示词对未准入关系要求的写法，免于可追溯性检查
 *  （可追溯性检查会必判 untraceable，与契约直接冲突）。它不包含
 *  可造事件，骰点一致性由骰点规则单独把关。 */
const VERDICT_TOKENS = new RegExp(`${FAILURE_TRIGGERS.source}|${SUCCESS_NAKED.source}`, 'g');
function isPureVerdictClause(clause, context) {
  let residual = text(clause);
  for (const name of Object.values(context.names)) residual = residual.split(name).join('');
  residual = residual.replace(/[\s，。；、！？：,.!?;:：""''（）()【】\[\]]/g, '');
  residual = residual.replace(VERDICT_TOKENS, '');
  return residual.length === 0;
}
const UPDATE_STAGES = ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'];
const UPDATE_FIELDS = {
  position: ['positionSet'], appearance: ['appearanceChanges'], tasks: ['tasksAchieved'],
  subtasks: ['subtasksAdded'], personality: ['personalityChanges'], sanity: ['sanitySet'],
};

const text = (value) => (typeof value === 'string' ? value : '');
const isObject = (value) => value != null && typeof value === 'object' && !Array.isArray(value);
const round = (value) => Number(value.toFixed(3));

export function taskOwnersOf(state) {
  const owners = {};
  for (const [actorId, actor] of Object.entries(state?.characters ?? {})) {
    for (const taskId of Object.keys(actor.tasks ?? {})) owners[taskId] = actorId;
  }
  return owners;
}

export function buildContext(state, options = {}) {
  const characters = state?.initial?.characters ?? {};
  const roster = Object.keys(characters).sort();
  return {
    state,
    roster,
    protagonist: options.protagonist ?? state?.protagonistId ?? roster[0],
    names: Object.fromEntries(roster.map((id) => [id, characters[id]?.name ?? id])),
    locations: Object.fromEntries(Object.entries(state?.initial?.locations ?? {}).map(([id, value]) => [id, value?.name ?? id])),
    tasks: Object.fromEntries(roster.map((id) => [id, Object.values(state?.characters?.[id]?.tasks ?? {})
      .map((task) => ({ id: task.id, goal: task.goal, status: task.status }))])),
    owners: taskOwnersOf(state),
  };
}

/** Roster characters mentioned in a text, in order of first appearance. */
export function actorMentions(value, context) {
  const source = text(value);
  return context.roster
    .map((id) => ({ id, name: context.names[id], index: source.indexOf(context.names[id]) }))
    .filter((entry) => entry.index >= 0)
    .sort((a, b) => a.index - b.index || b.name.length - a.name.length);
}

export function subjectActor(value, context) {
  return actorMentions(value, context)[0]?.id ?? null;
}

export function isGoalSentence(value) { return GOAL_WORDS.test(text(value)); }
export function hasStateClaim(value) { return STATE_CLAIM.test(text(value)); }

function contentBigrams(value, context) {
  let stripped = text(value);
  for (const name of Object.values(context.names)) stripped = stripped.split(name).join('');
  stripped = stripped.replace(/[\s，。；、！？：,.!?;:："“”'‘’（）()【】\[\]]/g, '');
  const grams = new Set();
  for (let index = 0; index + 1 < stripped.length; index++) grams.add(stripped.slice(index, index + 2));
  return grams;
}

function sharedBigram(left, right, context) {
  const a = contentBigrams(left, context);
  const b = contentBigrams(right, context);
  for (const gram of a) if (b.has(gram)) return gram;
  return null;
}

function taskGoalsOf(context, actorId) {
  return (context.tasks[actorId] ?? []).map((task) => task.goal);
}

function traceableTo(value, evidence, context) {
  return evidence.some((entry) => text(entry).trim() && sharedBigram(value, entry, context));
}

function normalize(value) {
  return text(value).replace(/[\s，。；、！？：,.!?;:]/g, '');
}

/** 逐字相等，或共享 ≥8 字连续前缀：反应不得复述发起者的行动。 */
function copiesAction(candidate, source) {
  const a = normalize(candidate);
  const b = normalize(source);
  if (!a || !b) return false;
  if (a === b) return true;
  let shared = 0;
  while (shared < a.length && shared < b.length && a[shared] === b[shared]) shared += 1;
  return shared >= 8;
}

function targetIdsOf(value) {
  if (!Array.isArray(value)) return null;
  return value.map((entry) => (typeof entry === 'string' ? entry : isObject(entry) ? entry.targetId : null));
}

function makeJudge(id, parsed, codec, semantics, why, extra = {}) {
  return { id, parsed, codec, semantics, why: why ?? null,
    reasons: extra.reasons ?? (why ? [why] : []), reviews: extra.reviews ?? [],
    note: extra.note ?? null, checked: extra.checked ?? [] };
}

function fail(id, parsed, codec, why, extra = {}) {
  return makeJudge(id, parsed, codec, 'fail', why, extra);
}

function review(id, parsed, codec, why, extra = {}) {
  return makeJudge(id, parsed, codec, 'review', null, { ...extra, reviews: [...new Set([why, ...(extra.reviews ?? [])])] });
}

function pass(id, parsed, codec, note, checked = []) {
  return makeJudge(id, parsed, codec, 'pass', null, { note, checked });
}

function evidenceOf(probe) {
  const call = probe.call ?? null;
  const parsed = call ? call.parseError == null && call.output !== undefined && call.output !== null : false;
  return { call, parsed, raw: call?.raw ?? '', output: probe.output ?? call?.output ?? null, modelOutput: call?.output ?? null };
}

// ---------- action ----------

function judgeAction(probe, context, mode) {
  const { call, parsed, modelOutput } = evidenceOf(probe);
  const actor = probe.input?.actor ?? call?.key ?? null;
  const id = probe.id;
  const out = modelOutput;
  if (!parsed) return fail(id, false, false, `no parsed output: ${call?.parseError ?? probe.failure ?? 'missing'}`);
  if (!isObject(out) || (out.kind !== 'act' && out.kind !== 'skip')) return fail(id, true, false, `illegal kind: ${JSON.stringify(out)}`);
  if (out.kind === 'skip') return pass(id, true, true, 'skip', ['legal kind']);
  if (!text(out.text).trim() || typeof out.text !== 'string') return fail(id, true, true, 'act without text');
  // 行动者身份由调度绑定（key=actor）；文本里没有名字不算错，但先把
  // 别的人物当主语就是人物归属错误。
  const subject = subjectActor(out.text, context);
  if (subject && subject !== actor) return fail(id, true, true, `action attributed to ${subject}, expected ${actor}: ${out.text}`);
  if (isGoalSentence(out.text)) return fail(id, true, true, `goal/plan is not an action: ${out.text}`);
  if (hasStateClaim(out.text)) return fail(id, true, true, `action claims a state change: ${out.text}`);
  const inputText = text(probe.input?.advance?.inputText);
  const reusesCommand = inputText && normalize(out.text).includes(normalize(inputText));
  if (mode === 'consumed-protagonist' && reusesCommand) return fail(id, true, true, `consumed input re-executed: ${out.text}`);
  if (mode === 'pending-npc' && reusesCommand) return fail(id, true, true, `non-protagonist executes the player command: ${out.text}`);
  if (mode === 'consumed-protagonist') return review(id, true, true, 'spontaneous action after a consumed input needs semantic review', { note: out.text });
  if (mode === 'pending-protagonist' && !reusesCommand) return review(id, true, true, 'action deviates from the pending command; plausibility needs review', { note: out.text });
  return pass(id, true, true, out.text, ['attribution', 'not-a-goal', 'no-state-claim', 'command-reuse']);
}

// ---------- targets ----------

function judgeTargets(probe, context) {
  const { call, parsed, modelOutput } = evidenceOf(probe);
  const id = probe.id;
  if (!parsed) return fail(id, false, false, `no parsed output: ${call?.parseError ?? probe.failure ?? 'missing'}`);
  if (!isObject(modelOutput) || !Array.isArray(modelOutput.targets)) return fail(id, true, false, 'targets array missing');
  const targets = targetIdsOf(modelOutput.targets);
  if (targets.some((target) => typeof target !== 'string' || !target)) return fail(id, true, false, `targets must carry targetId: ${JSON.stringify(modelOutput.targets)}`);
  const source = probe.input?.sourceId;
  const unknown = targets.filter((target) => !context.roster.includes(target));
  if (targets.includes(source)) return fail(id, true, true, `source targets itself: ${JSON.stringify(targets)}`);
  if (unknown.length) return fail(id, true, true, `targets outside the roster: ${JSON.stringify(unknown)}`);
  if (new Set(targets).size !== targets.length) return fail(id, true, true, `duplicate targets: ${JSON.stringify(targets)}`);
  const named = actorMentions(probe.input?.actionText, context).filter((entry) => entry.id !== source).map((entry) => entry.id);
  const directed = probe.expect?.directed ?? (named.length ? named[0] : null);
  if (directed) {
    if (!targets.includes(directed)) return fail(id, true, true, `expected ${directed} in ${JSON.stringify(targets)}`);
    if (targets.length !== 1) return fail(id, true, true, `expected exactly ${directed}, got ${JSON.stringify(targets)}`);
    return pass(id, true, true, `targets=${JSON.stringify(targets)}`, ['named-target-selected']);
  }
  if (probe.expect?.solo && targets.length !== 0) return fail(id, true, true, `expected empty, got ${JSON.stringify(targets)}`);
  return pass(id, true, true, `targets=${JSON.stringify(targets)}`, ['roster-and-self checks']);
}

// ---------- reaction ----------

function judgeReaction(probe, context) {
  const { call, parsed, output } = evidenceOf(probe);
  const id = probe.id;
  const member = probe.input?.memberId;
  const reactionText = typeof output === 'string' ? output : isObject(output) && typeof output.text === 'string' ? output.text : '';
  if (!parsed) return fail(id, false, false, `no parsed output: ${call?.parseError ?? probe.failure ?? 'missing'}`);
  // 反应是纯文本任务；旧归档的 {text} 包装只是 harness 形状，仍接受。
  if (!reactionText.trim()) return fail(id, true, false, 'reaction is empty');
  const subject = subjectActor(reactionText, context);
  if (member && subject && subject !== member) return fail(id, true, true, `reaction attributed to ${subject}, expected ${member}: ${reactionText}`);
  if (hasStateClaim(reactionText)) return fail(id, true, true, `reaction claims a state change: ${reactionText}`);
  const sourceAction = text(call?.context?.sourceActionText ?? probe.expect?.sourceActionText ?? probe.input?.sourceActionText);
  if (sourceAction && copiesAction(reactionText, sourceAction)) return fail(id, true, true, `reaction copies the source action: ${reactionText}`);
  if (!sourceAction) {
    return review(id, true, true, 'source action context was not archived; traceability unverified',
      { note: reactionText, checked: ['attribution', 'no-state-claim'] });
  }
  const evidence = [sourceAction, ...taskGoalsOf(context, member)];
  if (!traceableTo(reactionText, evidence, context)) {
    return fail(id, true, true, `reaction is not traceable to the source action or the member's tasks: ${reactionText}`);
  }
  return review(id, true, true, 'reaction plausibility beyond attribution/traceability needs human review',
    { note: reactionText, checked: ['attribution', 'no-state-claim', 'not-a-copy', 'traceable'] });
}

// ---------- results ----------

function resultClause(output, member, context) {
  const source = text(output);
  const others = context.roster.filter((id) => id !== member.memberId).map((id) => context.names[id]);
  let clause = source;
  for (const name of others) {
    const index = clause.indexOf(name);
    if (index > 0) { clause = clause.slice(0, index); break; }
  }
  return clause;
}

function rollsOf(member) {
  return (Array.isArray(member?.rollRefs) ? member.rollRefs : []).map((roll) => ({
    admitted: roll?.admitted === true,
    result: typeof roll?.result === 'number' ? roll.result : null,
    targetId: roll?.targetId ?? null,
  }));
}

function judgeResults(probe, context) {
  const { call, parsed, modelOutput } = evidenceOf(probe);
  const id = probe.id;
  if (!parsed) return fail(id, false, false, `no parsed output: ${call?.parseError ?? probe.failure ?? 'missing'}`);
  if (!isObject(modelOutput)) return fail(id, true, false, 'results must be an object');
  const members = probe.input?.members ?? [];
  const keys = Object.keys(modelOutput).sort();
  if (!members.length) {
    // 旧归档没有保存 results 的输入上下文：只能核对键集合与人物归属，
    // 不能宣称结果可溯源于冻结行动——归入待复核。
    const unknown = keys.filter((key) => !context.roster.includes(key));
    if (unknown.length) return fail(id, true, true, `results keys outside the roster: ${JSON.stringify(unknown)}`);
    if (keys.some((key) => !text(modelOutput[key]).trim())) return fail(id, true, true, 'results contain an empty text');
    for (const key of keys) {
      const subject = subjectActor(modelOutput[key], context);
      if (subject && subject !== key) return fail(id, true, true, `${key} result is acted by ${subject}: ${modelOutput[key]}`);
    }
    return review(id, true, true, 'result context was not archived: traceability and dice agreement unverified',
      { note: JSON.stringify(modelOutput), checked: ['keys', 'naming'] });
  }
  const wanted = members.map((member) => member.memberId).sort();
  if (keys.join(',') !== wanted.join(',')) return fail(id, true, true, `results keys ${keys} != [${wanted}]`);
  if (keys.some((key) => !text(modelOutput[key]).trim())) return fail(id, true, true, 'results contain an empty text');
  // 每个成员的错误全部收集后才决定（复核轮 19）：首错即退会掩盖后续成员的
  // 真正违规（准入骰点被写成失败等）。
  const problems = [];
  const reviewNotes = [];
  for (const member of members) {
    const value = text(modelOutput[member.memberId]);
    const subject = subjectActor(value, context);
    if (subject && subject !== member.memberId) {
      problems.push(`result for ${member.memberId} is acted by ${subject}: ${value}`);
      continue;                                  // 后续检查对本成员无意义
    }
    const rolls = rollsOf(member);
    const clause = resultClause(value, member, context);
    const pureVerdict = isPureVerdictClause(clause, context);
    const rejected = rolls.length > 0 && rolls.every((roll) => !roll.admitted);
    const admittedSome = rolls.some((roll) => roll.admitted);
    if (rolls.length) {
      // 骰点一致性是硬规则：未准入写成功、准入写失败，都必须 fail，
      // 原因里带 [dice mismatch]，不与可追溯性混在一起。
      if (rejected && successWording(clause)) {
        problems.push(`rejected roll described as success (${member.memberId}): ${value} [dice mismatch]`);
        continue;
      }
      if (admittedSome && failureWording(clause) && !successWording(clause)) {
        problems.push(`admitted roll described as failure (${member.memberId}): ${value} [dice mismatch]`);
        continue;
      }
      const evidence = [text(member.actionText), ...taskGoalsOf(context, member.memberId)];
      if (!pureVerdict && !traceableTo(value, evidence, context)) {
        problems.push(`result for ${member.memberId} is not traceable to the frozen action or its tasks: ${value}`);
      }
    } else if (pureVerdict && (failureWording(clause) || successWording(clause))) {
      // 无骰点成员写裸成败判定：没有骰点证据支撑，不判 fail，也不算通过，
      // 归入待复核并写明。
      reviewNotes.push(`${member.memberId} wrote a bare success/failure verdict without any dice evidence`);
    } else {
      const evidence = [text(member.actionText), ...taskGoalsOf(context, member.memberId)];
      if (!traceableTo(value, evidence, context)) {
        problems.push(`result for ${member.memberId} is not traceable to the frozen action or its tasks: ${value}`);
      }
    }
  }
  if (problems.length) return fail(id, true, true, problems[0], { reasons: problems, checked: ['per-member attribution', 'roster actors', 'dice agreement', 'traceability'] });
  if (reviewNotes.length) return review(id, true, true, 'bare success/failure verdict without dice evidence needs human review',
    { note: JSON.stringify(modelOutput), reasons: reviewNotes,
      checked: ['per-member attribution', 'roster actors', 'pure-verdict exemption', 'dice evidence'] });
  return pass(id, true, true, 'results match roster, attribution, dice agreement and traceability/pure-verdict rules',
    ['per-member attribution', 'roster actors', 'traceability/pure-verdict', 'dice agreement']);
}

// ---------- updates ----------

/** Codec + semantics for an update batch. `priorStages` carries confirmed
 * evidence from calls the controller already applied (split ladder): the
 * causality chain is accumulated across the whole batch, never per delta. */
export function auditUpdates(calls, expectation, context) {
  const codec = [];
  const semantic = [];
  const reviews = [];
  const prior = expectation.priorStages ?? {};
  const batchTasks = new Map();        // entity -> Set(taskId) proven achieved
  const batchPersonality = new Map();  // entity -> Set(changeId) proven changed
  const add = (map, entity, id) => {
    if (!map.has(entity)) map.set(entity, new Set());
    map.get(entity).add(id);
  };
  for (const [entity, ids] of Object.entries(prior.tasksAchieved ?? {})) for (const id of ids) add(batchTasks, entity, id);
  for (const [entity, ids] of Object.entries(prior.personality ?? {})) for (const id of ids) add(batchPersonality, entity, id);
  const anyTask = () => [...batchTasks.values()].some((set) => set.size > 0);

  // 复核轮 19：合并批次的 stage 顺序不是契约——wire 的 entityDeltas 是
  // 每实体一组的字段集合，A 侧 kernel apply 与产品 structured-output 门都
  // 不依赖数组顺序（产品门注：pass through unnormalized）。顺序违规降级
  // 为 formatNotes 记录，不再让整轮死在格式偏好上；stage 合法性、字段
  // 白名单与批量因果链照旧是硬规则。
  const formatNotes = [];
  const seenStages = new Map();
  for (const call of calls) {
    if (!isObject(call)) { codec.push('update call must be an object'); continue; }
    const stageIndex = UPDATE_STAGES.indexOf(call.stage);
    if (stageIndex < 0) { codec.push(`illegal stage ${JSON.stringify(call.stage)}`); continue; }
    seenStages.set(call.stage, (seenStages.get(call.stage) ?? 0) + 1);
    if (expectation.stage && call.stage !== expectation.stage) codec.push(`stage ${call.stage} != ${expectation.stage}`);
    if (!isObject(call.changes)) { codec.push(`changes of ${call.stage} must be an object`); continue; }
    const allowed = UPDATE_FIELDS[call.stage];
    for (const [entity, delta] of Object.entries(call.changes)) {
      if (!context.roster.includes(entity)) { semantic.push(`entity ${entity} not in roster`); continue; }
      if (!isObject(delta)) { codec.push(`delta of ${entity} must be an object`); continue; }
      for (const key of Object.keys(delta)) {
        if (key === 'entityId') continue;
        if (!allowed.includes(key)) codec.push(`field ${key} is not allowed in ${call.stage}`);
      }
      for (const taskId of delta.tasksAchieved ?? []) {
        if (typeof taskId !== 'string' || !taskId) { codec.push(`tasksAchieved of ${entity} must hold id strings`); continue; }
        const owner = context.owners[taskId];
        if (!owner) {
          const produced = [...(batchTasks.get(entity) ?? [])].includes(taskId);
          if (!produced) semantic.push(`tasksAchieved ${taskId} is not in the state or produced by this batch`);
        } else if (owner !== entity) semantic.push(`task ${taskId} is owned by ${owner}, not ${entity}`);
      }
      for (const change of delta.appearanceChanges ?? []) {
        if (!isObject(change) || !text(change.id) || !text(change.text) || !Array.isArray(change.supersedes)) {
          codec.push(`invalid appearance change for ${entity} (id/text/supersedes required)`);
        }
      }
      for (const change of delta.personalityChanges ?? []) {
        if (!isObject(change) || !text(change.id) || !text(change.text) || !Array.isArray(change.supersedes)) {
          codec.push(`invalid personality change for ${entity} (id/text/supersedes required)`);
        }
      }
      for (const task of delta.subtasksAdded ?? []) {
        if (!isObject(task) || !text(task.id) || !text(task.goal) || task.ownerId !== entity || task.status !== 'pending') {
          codec.push(`invalid subtasksAdded item for ${entity}`);
        }
      }
      if (delta.sanitySet !== undefined) {
        if (!Number.isInteger(delta.sanitySet) || delta.sanitySet < 0 || delta.sanitySet > 100) {
          codec.push(`sanitySet must be an integer in [0,100], got ${JSON.stringify(delta.sanitySet)}`);
        } else {
          const before = context.state?.characters?.[entity]?.sanity;
          if (Number.isInteger(before) && Math.abs(delta.sanitySet - before) > 30) reviews.push(`large sanity jump ${before}->${delta.sanitySet} for ${entity} needs review`);
        }
      }
      if (delta.positionSet !== undefined) {
        const position = delta.positionSet;
        if (!isObject(position) || !text(position.containerId) || !context.locations[position.containerId]) {
          codec.push(`invalid positionSet for ${entity}`);
        }
      }
    }
  }
  // §6.3 causality, accumulated over the batch: tasks (anybody) unlock
  // personality; personality stays paired with sanity per entity.
  for (const call of calls) {
    if (!isObject(call) || !isObject(call.changes)) continue;
    for (const [entity, delta] of Object.entries(call.changes)) {
      if (!isObject(delta)) continue;
      for (const taskId of delta.tasksAchieved ?? []) add(batchTasks, entity, taskId);
      for (const change of delta.personalityChanges ?? []) {
        if (!anyTask()) semantic.push(`${entity} personality change without any achieved task in the batch`);
        if (isObject(change) && text(change.id)) add(batchPersonality, entity, change.id);
      }
      if (delta.sanitySet !== undefined) {
        const own = batchPersonality.get(entity);
        if (!own || own.size === 0) semantic.push(`${entity} sanity change without a personality change for the same character`);
      }
    }
  }
  if (expectation.forbidAnyChange) {
    for (const call of calls) {
      for (const [entity, delta] of Object.entries(call?.changes ?? {})) {
        if (!isObject(delta)) continue;
        if ((delta.tasksAchieved?.length ?? 0) || (delta.personalityChanges?.length ?? 0) || delta.sanitySet !== undefined) {
          semantic.push(`unexpected change for ${entity} (${JSON.stringify(delta)})`);
        }
      }
    }
  }
  for (const [entity, tasks] of Object.entries(expectation.expectTasks ?? {})) {
    const found = new Set(calls.flatMap((call) => Object.entries(call?.changes ?? {})
      .filter(([key]) => key === entity).flatMap(([, delta]) => delta?.tasksAchieved ?? [])));
    for (const taskId of tasks) if (!found.has(taskId)) semantic.push(`expected ${entity} to achieve ${taskId}`);
  }
  for (const entity of expectation.expectSanityFor ?? []) {
    const found = calls.some((call) => call?.changes?.[entity]?.sanitySet !== undefined);
    if (!found) semantic.push(`expected ${entity} to receive a recalculated sanity value`);
  }
  const duplicated = [...seenStages.entries()].filter(([, count]) => count > 1).map(([name]) => name);
  const orderNotes = [];
  if (duplicated.length) orderNotes.push(`duplicate stage ${duplicated.join(',')}`);
  // canonical-order drift: recorded, never fatal
  let previous = -1;
  for (const call of calls) {
    if (!isObject(call)) continue;
    const stageIndex = UPDATE_STAGES.indexOf(call.stage);
    if (stageIndex >= 0) {
      if (previous >= 0 && stageIndex < previous) orderNotes.push(`non-canonical order at ${call.stage}`);
      previous = stageIndex;
    }
  }
  formatNotes.push(...orderNotes);
  return { codec, semantic, reviews, formatNotes };
}

function judgeUpdates(probe, context) {
  const { call, parsed, modelOutput } = evidenceOf(probe);
  const id = probe.id;
  if (!parsed) return fail(id, false, false, `no parsed output: ${call?.parseError ?? probe.failure ?? 'missing'}`);
  const stage = probe.expect?.stage ?? probe.input?.stage ?? null;
  const calls = Array.isArray(modelOutput) ? modelOutput : isObject(modelOutput) ? [modelOutput] : null;
  if (!calls) return fail(id, true, false, 'updates must be an array or a single stage object');
  if (stage && Array.isArray(modelOutput)) return fail(id, true, false, `stage ${stage} call returned an array`);
  if (!stage && !Array.isArray(modelOutput)) return fail(id, true, false, 'merged updates returned a single object');
  const priorStages = probe.expect?.priorStages ?? call?.context?.priorStages ?? null;
  const { codec, semantic, reviews, formatNotes } = auditUpdates(calls,  { ...(probe.expect ?? {}), stage, priorStages }, context);
  if (codec.length) return fail(id, true, false, codec.join('; '), { reasons: [...codec, ...semantic] });
  if (semantic.length) return fail(id, true, true, semantic.join('; '), { reasons: semantic });
  if (reviews.length) return review(id, true, true, reviews[0],
    { reviews, note: formatNotes.length ? JSON.stringify({ output: modelOutput, formatNotes }) : JSON.stringify(modelOutput) });
  return pass(id, true, true, `${calls.length} call(s): ${calls.map((entry) => entry.stage).join(',')}`,
    ['codec', 'entity ownership', 'batch causality', 'expectation']);
}

// ---------- continuation ----------

function judgeContinuation(probe, context) {
  const { call } = evidenceOf(probe);
  const id = probe.id;
  // 结论字段（kind/candidates/nextRoundId）与判断字段（plannedAction/
  // protagonistRelevance）在端口处分离：wire 只保留结论，判断产物留在
  // call.output。判分读模型的原始判断。
  const out = call?.output ?? probe.output ?? null;
  const parsed = call ? call.parseError == null && call.output !== undefined && call.output !== null : false;
  if (!parsed) return fail(id, false, false, `no parsed output: ${call?.parseError ?? probe.failure ?? 'missing'}`);
  if (!isObject(out) || (out.kind !== 'continue' && out.kind !== 'handback')) return fail(id, true, false, `illegal kind: ${JSON.stringify(out)}`);
  const expectation = probe.expect?.continuation ?? 'judgment';
  const plannedAction = text(out.plannedAction);
  const relevance = text(out.protagonistRelevance);
  const candidates = Array.isArray(out.candidateCharacterIds) ? out.candidateCharacterIds : [];
  if (out.kind === 'handback') {
    if (expectation === 'continue-required') return fail(id, true, true, 'clear protagonist-related driver was handed back');
    if (plannedAction || relevance) return review(id, true, true, 'handback carries a stated action/relevance; needs review', { reviews: ['handback rationale'], note: JSON.stringify(out) });
    return pass(id, true, true, 'handback', ['legal kind', 'no stated driver']);
  }
  // continue 的 codec：候选数组与非空 nextRoundId，且两判断字段必须是字符串。
  const codecOk = candidates.every((candidate) => typeof candidate === 'string' && candidate)
    && text(out.nextRoundId) && typeof out.plannedAction === 'string' && typeof out.protagonistRelevance === 'string';
  if (!codecOk) return fail(id, true, false, 'continue is missing candidateCharacterIds/nextRoundId/plannedAction/protagonistRelevance');
  if (expectation === 'handback-required') return fail(id, true, true, 'no driving action was expected, model continued');
  const dropped = (call?.backfills ?? []).filter((entry) => entry.kind === 'candidate_dropped_not_in_roster'
    || entry.kind === 'candidates_backfilled_roster');
  if (dropped.length) return fail(id, true, true, `invalid candidateCharacterIds: ${JSON.stringify(dropped)}`);
  if (!candidates.length) return fail(id, true, true, 'continue without candidate characters');
  const unknown = candidates.filter((candidate) => !context.roster.includes(candidate));
  if (unknown.length) return fail(id, true, true, `candidates outside the roster: ${JSON.stringify(unknown)}`);
  if (!plannedAction) return fail(id, true, true, 'continue without a planned action (the §8.1 likelihood condition is unstated)');
  if (isGoalSentence(plannedAction)) return fail(id, true, true, `planned action is a goal/plan sentence, not an action: ${plannedAction}`);
  if (!relevance) return fail(id, true, true, 'continue without a protagonist relevance statement (the §8.1 relation condition is unstated)');
  if (!relevance.includes(context.protagonist) && !relevance.includes(context.names[context.protagonist])) {
    return fail(id, true, true, `protagonist relevance does not reference the protagonist: ${relevance}`);
  }
  if (/无关|没有关系|不涉及|不影响主角|与主角无关/.test(relevance)) {
    return fail(id, true, true, `relevance states the action is unrelated to the protagonist but still continues: ${relevance}`);
  }
  if (expectation === 'continue-required' && probe.expect?.driver && !candidates.includes(probe.expect.driver)) {
    return fail(id, true, true, `candidate ${JSON.stringify(candidates)} does not include the driving character ${probe.expect.driver}`);
  }
  if (expectation === 'handback-expected') return review(id, true, true, 'continued where the premise suggests handing back; needs review', { note: JSON.stringify(out) });
  return review(id, true, true, 'planned action plausibility (large-likelihood + protagonist relation) needs human review', {
    note: JSON.stringify(out), checked: ['codec', 'candidates', 'planned action stated', 'protagonist relevance stated'],
  });
}

// ---------- probe dispatch ----------

const OLD_CONTINUATION = new Set(['continuation_more']);

export function judgeProbe(probe, context) {
  const id = probe.id;
  const expect = probe.expect ?? {};
  switch (id) {
    case 'action_pending': return judgeAction(probe, context, 'pending-protagonist');
    case 'action_consumed':
    case 'action_consumed_protagonist':
      return judgeAction(probe, context, 'consumed-protagonist');
    case 'action_nonactor':
    case 'action_consumed_npc':
      return judgeAction(probe, context, expect.advance === 'pending' ? 'pending-npc' : 'consumed-npc');
    case 'targets_directed':
    case 'targets_solo':
      return judgeTargets(probe, context);
    case 'reaction_joint': return judgeReaction(probe, context);
    case 'results_joint':
    case 'results_rejected_roll':
    case 'results_admitted_roll':
      return judgeResults(probe, context);
    case 'updates_merged':
    case 'updates_none_expected':
    case 'updates_stage_tasks':
    case 'updates_stage_personality':
    case 'updates_stage_sanity':
      return judgeUpdates(probe, context);
    case 'continuation_more':
      if (OLD_CONTINUATION.has(id) && !probe.expect) {
        return review(id, true, false, 'original probe predates the §8.1 two-condition judgement; expectation rebuilt, not counted as passing', {
          note: JSON.stringify(probe.output ?? probe.call?.output ?? null),
        });
      }
      return judgeContinuation(probe, context);
    case 'continuation_likely_related':
    case 'continuation_unrelated':
    case 'continuation_done': {
      if (!probe.expect) {
        const characters = Object.values(probe.input?.workingState?.characters ?? {});
        const allAchieved = characters.flatMap((actor) => Object.values(actor.tasks ?? {})).every((task) => task.status === 'achieved');
        return judgeContinuation({ ...probe, expect: { continuation: allAchieved ? 'handback-required' : 'judgment' } }, context);
      }
      return judgeContinuation(probe, context);
    }
    default:
      return makeJudge(id, false, false, 'review', `no judge for probe ${id}`, { reviews: [`no judge for probe ${id}`] });
  }
}

// ---------- scene records ----------

export function judgeScene(scene, context) {
  const errors = [];
  const reviews = [];
  const narrationFallbacks = [];
  let modelCalls = 0;
  let programCalls = 0;
  let parsedCalls = 0;
  let codecCalls = 0;
  const playerInput = text(scene.playerInput);
  const addReview = (entry) => reviews.push(entry);
  for (const call of scene.modelTasks ?? []) {
    if (call.source === 'program') { programCalls += 1; continue; }
    modelCalls += 1;
    const output = call.output ?? null;
    const label = `${call.task}:${call.key}`;
    const parsed = call.parseError == null && output !== null;
    if (parsed) parsedCalls += 1;
    if (call.error) { errors.push({ call: label, error: call.error }); continue; }
    if (call.validationError) { errors.push({ call: label, error: call.validationError }); continue; }
    let codecOk = parsed;
    switch (call.task) {
      case 'action': {
        if (!isObject(output)) { errors.push({ call: label, error: 'action output is not an object' }); codecOk = false; break; }
        if (output.kind === 'skip') break;
        if (output.kind !== 'act' || !text(output.text).trim()) { errors.push({ call: label, error: `illegal action ${JSON.stringify(output)}` }); codecOk = false; break; }
        const subject = subjectActor(output.text, context);
        if (subject && subject !== call.key) errors.push({ call: label, error: `action attributed to ${subject}, expected ${call.key}: ${output.text}` });
        if (isGoalSentence(output.text)) errors.push({ call: label, error: `goal/plan is not an action: ${output.text}` });
        if (hasStateClaim(output.text)) errors.push({ call: label, error: `action claims a state change: ${output.text}` });
        if (playerInput && call.key !== context.protagonist && normalize(output.text).includes(normalize(playerInput))) {
          errors.push({ call: label, error: `non-protagonist executes the player command: ${output.text}` });
        }
        break;
      }
      case 'targets': {
        if (!isObject(output) || !Array.isArray(output.targets)) { errors.push({ call: label, error: 'targets array missing' }); codecOk = false; break; }
        const targets = targetIdsOf(output.targets);
        if (targets.some((target) => typeof target !== 'string' || !target)) {
          errors.push({ call: label, error: `targets must carry targetId: ${JSON.stringify(output.targets)}` });
          codecOk = false;
          break;
        }
        if (targets.some((target) => !context.roster.includes(target))) errors.push({ call: label, error: `targets outside the roster: ${JSON.stringify(targets)}` });
        if (targets.includes(call.key)) errors.push({ call: label, error: 'source targets itself' });
        if ((call.backfills ?? []).some((entry) => entry.kind === 'target_dropped_not_in_roster')) {
          errors.push({ call: label, error: `target dropped (not in roster): ${JSON.stringify(call.backfills)}` });
        }
        break;
      }
      case 'reaction': {
        const reactionText = typeof output === 'string' ? output : isObject(output) && typeof output.text === 'string' ? output.text : '';
        if (!reactionText.trim()) { errors.push({ call: label, error: 'reaction is empty' }); codecOk = false; break; }
        const member = call.context?.memberId;
        const subject = subjectActor(reactionText, context);
        if (member && subject && subject !== member) errors.push({ call: label, error: `reaction attributed to ${subject}, expected ${member}: ${reactionText}` });
        if (hasStateClaim(reactionText)) errors.push({ call: label, error: `reaction claims a state change: ${reactionText}` });
        if (call.context?.sourceActionText && copiesAction(reactionText, call.context.sourceActionText)) errors.push({ call: label, error: 'reaction copies the source action' });
        if (!member) addReview({ call: label, review: 'reaction member context was not archived' });
        if (!call.context?.sourceActionText) {
          addReview({ call: label, review: 'source action context was not archived; traceability unverified' });
        } else if (!traceableTo(reactionText, [call.context.sourceActionText, ...taskGoalsOf(context, member)], context)) {
          errors.push({ call: label, error: `reaction is not traceable to the source action or the member's tasks: ${reactionText}` });
        }
        break;
      }
      case 'results': {
        if (!isObject(output)) { errors.push({ call: label, error: 'results must be an object' }); codecOk = false; break; }
        const judged = judgeResults({ id: label, input: { members: call.context?.members ?? [] }, output, call }, context);
        if (judged.codec === false) codecOk = false;
        if (judged.semantics === 'fail') errors.push({ call: label, error: judged.why });
        else if (judged.semantics === 'review') addReview({ call: label, review: judged.reviews[0] });
        break;
      }
      case 'updates': {
        const calls = Array.isArray(output) ? output : [output];
        const { codec, semantic, reviews: updateReviews, formatNotes } = auditUpdates(calls, { priorStages: call.context?.priorStages ?? null }, context);
        if (codec.length) { codecOk = false; errors.push({ call: label, error: `codec: ${codec.join('; ')}` }); }
        if (semantic.length) errors.push({ call: label, error: `semantic: ${semantic.join('; ')}` });
        if (updateReviews.length) addReview({ call: label, review: updateReviews[0] });
        // formatNotes（顺序/重复/空阶段）只记录：wire 与 kernel 不依赖顺序。
        if (formatNotes.length) addReview({ call: label, review: `format (non-fatal): ${formatNotes.join('; ')}` });
        break;
      }
      case 'continuation': {
        const judged = judgeContinuation({ id: label, output, call, expect: call.expect ?? { continuation: 'judgment' } }, context);
        if (judged.codec === false) codecOk = false;
        if (judged.semantics === 'fail') errors.push({ call: label, error: judged.why });
        else if (judged.semantics === 'review') addReview({ call: label, review: judged.reviews[0] });
        break;
      }
      case 'narration':
        break;
      default:
        break;
    }
    if (codecOk && !call.error && !(call.validationError)) codecCalls += 1;
  }
  for (const event of scene.events ?? []) {
    if (event.kind === 'polishFallback') narrationFallbacks.push({ pointId: event.pointId, detail: event.detail });
    if (event.kind === 'narration' && !event.polished) narrationFallbacks.push({ pointId: event.pointId, reason: event.polishReason });
  }
  for (const entry of scene.narration ?? []) {
    if (entry.error) errors.push({ call: `narration:${entry.key}`, error: entry.error });
  }
  const status = scene.status === 'COMPLETED';
  const accepted = status && errors.length === 0 && reviews.length === 0 && narrationFallbacks.length === 0;
  return { status: scene.status, accepted, modelCalls, programCalls, parsedCalls, codecCalls,
    semanticErrors: errors, pendingReview: reviews, narrationFallbacks };
}

// ---------- judge self-test (tamper probes and legal positives) ----------

export function runJudgeSelfTests(context) {
  const protagonist = context.protagonist;
  const other = context.roster.find((id) => id !== protagonist) ?? protagonist;
  const memberAction = `${context.names[protagonist]} 推开门厅深处的重门。`;
  const taskId = (context.tasks[protagonist] ?? [])[0]?.id ?? 'task_x';
  const cases = [];
  const record = (name, expect, probe, check) => {
    const verdict = judgeProbe(probe, context);
    cases.push({ name, expect, got: verdict.semantics, codec: verdict.codec, why: verdict.why,
      reviews: verdict.reviews, ok: expect === verdict.semantics && (check ? check(verdict) : true) });
  };
  const callOf = (output, extra = {}) => ({ task: 'x', key: 'k', output, raw: JSON.stringify(output), parseError: null, ...extra });
  const probeOf = (id, input, output, expect, callExtra = {}) => ({ id, input, output: null, expect, call: callOf(output, callExtra) });

  record('absurd joint results', 'fail', probeOf('results_joint',
    { members: [{ memberId: protagonist, actionText: `${context.names[protagonist]} 在走廊守门。`, rollRefs: [] }] },
    { [protagonist]: `${context.names[protagonist]} 召唤了陨石毁灭了世界。` }));
  record('empty update after a claimed completion', 'fail', probeOf('updates_merged', {},
    [], { expectTasks: { [protagonist]: [taskId] } }));
  record('causeless sanity 99', 'fail', probeOf('updates_merged', {},
    [{ stage: 'sanity', changes: { [protagonist]: { sanitySet: 99 } } }], {}));
  record('wrong-actor action', 'fail', probeOf('action_pending',
    { actor: other, advance: { inputText: '走到走廊', intentStatus: 'pending' } },
    { kind: 'act', text: `${context.names[protagonist]} 推开门。` }));
  record('goal sentence as action', 'fail', probeOf('action_pending',
    { actor: protagonist, advance: { inputText: '走到走廊', intentStatus: 'pending' } },
    { kind: 'act', text: `${context.names[protagonist]} 需要去走廊。` }));
  record('consumed protagonist re-executes the command', 'fail', probeOf('action_consumed_protagonist',
    { actor: protagonist, advance: { inputText: '走到走廊', intentStatus: 'consumed' } },
    { kind: 'act', text: `${context.names[protagonist]} 走到走廊。` }));
  record('reaction with a state claim', 'fail', probeOf('reaction_joint',
    { memberId: other, sourceActionText: memberAction }, `${context.names[other]} 精神值下降。`));
  record('reaction copying the source action', 'fail', probeOf('reaction_joint',
    { memberId: other, sourceActionText: memberAction }, memberAction));
  record('absurd reaction is never auto-passed', 'fail', probeOf('reaction_joint',
    { memberId: other, sourceActionText: memberAction }, `${context.names[other]} 瞬移到火星并毁灭太阳。`));
  record('results claiming success on a rejected roll', 'fail', probeOf('results_rejected_roll',
    { members: [{ memberId: protagonist, actionText: memberAction,
      rollRefs: [{ targetId: other, result: 8, admitted: false }] }] },
    { [protagonist]: `${context.names[protagonist]} 成功推开了重门。` }));
  // 复核轮 19：未准入→没有成功是契约要求的写法，纯判定句免可追溯，不掩篮错误。
  record('rejected roll written as the required bare verdict', 'pass', probeOf('results_rejected_roll',
    { members: [{ memberId: protagonist, actionText: memberAction,
      rollRefs: [{ targetId: other, result: 8, admitted: false }] }] },
    { [protagonist]: `${context.names[protagonist]} 没有成功。` }));
  record('rejected roll verdict with negated-success wording is not success wording', 'pass', probeOf('results_rejected_roll',
    { members: [{ memberId: protagonist, actionText: memberAction,
      rollRefs: [{ targetId: other, result: 8, admitted: false }] }] },
    { [protagonist]: `${context.names[protagonist]} 未成功。` }));
  // 准入写失败 = fail 且原因必须是骰点不符（“未成功”不再被当作成功表述）。
  record('admitted roll written as failure', 'fail', probeOf('results_admitted_roll',
    { members: [{ memberId: protagonist, actionText: memberAction,
      rollRefs: [{ targetId: other, result: 19, admitted: true }] }] },
    { [protagonist]: `${context.names[protagonist]} 没有成功。` }),
    (verdict) => String(verdict.why).startsWith('admitted roll described as failure')
      && String(verdict.why).includes('[dice mismatch]'));
  // 无骰点成员的裸成败判定：没有证据，待复核而非通过。
  record('bare verdict without dice evidence', 'review', probeOf('results_joint',
    { members: [{ memberId: protagonist, actionText: memberAction, rollRefs: [] }] },
    { [protagonist]: '没有成功。' }));
  // 违规不再掩盖后续成员（复核轮 19）：首人写荒谬事件、次人骰点不符，
  // fail 的 reasons 必须同时包含两处。
  record('member errors are all collected, the first does not mask the second', 'fail',
    probeOf('results_joint',
      { members: [
        { memberId: protagonist, actionText: memberAction,
          rollRefs: [{ targetId: other, result: 8, admitted: false }] },
        { memberId: other, actionText: `${context.names[other]} 在门边见证。`, rollRefs: [] },
      ] },
      { [protagonist]: `${context.names[protagonist]} 召唤了陨石。`,
        [other]: `${context.names[other]} 成功了。` }),
    (verdict) => (verdict.reasons ?? []).length === 2
      && verdict.reasons.every((reason) => String(reason).includes(protagonist)
        || String(reason).includes(other)));
  record('legal task-only update', 'pass', probeOf('updates_merged', {},
    [{ stage: 'tasks', changes: { [protagonist]: { tasksAchieved: [taskId] } } }],
    { expectTasks: { [protagonist]: [taskId] } }));
  record('legal staged batch tasks->personality->sanity', 'pass', probeOf('updates_merged', {}, [
    { stage: 'tasks', changes: { [protagonist]: { tasksAchieved: [taskId] } } },
    { stage: 'personality', changes: { [protagonist]: { personalityChanges: [{ id: 'c1', text: '更谨慎', supersedes: [] }] } } },
    { stage: 'sanity', changes: { [protagonist]: { sanitySet: Math.max(0, (context.state.characters[protagonist].sanity ?? 10) - 1) } } },
  ], {}));
  record('legal cross-entity trigger: A task, B personality+sanity', 'pass', probeOf('updates_merged', {}, [
    { stage: 'tasks', changes: { [protagonist]: { tasksAchieved: [taskId] } } },
    { stage: 'personality', changes: { [other]: { personalityChanges: [{ id: 'c2', text: '变得警觉', supersedes: [] }] } } },
    { stage: 'sanity', changes: { [other]: { sanitySet: Math.max(0, (context.state.characters[other].sanity ?? 10) - 2) } } },
  ], {}));
  record('split personality stage with prior task evidence', 'pass', probeOf('updates_stage_personality', { stage: 'personality' },
    { stage: 'personality', changes: { [other]: { personalityChanges: [{ id: 'c3', text: '变得更果断', supersedes: [] }] } } },
    { stage: 'personality', priorStages: { tasksAchieved: { [protagonist]: [taskId] } } }));
  record('personality without any achieved task', 'fail', probeOf('updates_merged', {},
    [{ stage: 'personality', changes: { [protagonist]: { personalityChanges: [{ id: 'draft_1', text: '更谨慎', supersedes: [] }] } } }], {}));
  record('sanity without its own personality change', 'fail', probeOf('updates_merged', {},
    [{ stage: 'tasks', changes: { [protagonist]: { tasksAchieved: [taskId] } } },
      { stage: 'personality', changes: { [protagonist]: { personalityChanges: [{ id: 'c4', text: '更谨慎', supersedes: [] }] } } },
      { stage: 'sanity', changes: { [other]: { sanitySet: 9 } } }], {}));
  record('illegal stage is a codec failure', 'fail', probeOf('updates_merged', {},
    [{ stage: 'appearanceChanges', changes: {} }], {}), (verdict) => verdict.codec === false);
  record('continue without the §8.1 conditions', 'fail', probeOf('continuation_likely_related', {},
    { kind: 'continue', candidateCharacterIds: [other], nextRoundId: 'round_x', plannedAction: '', protagonistRelevance: '' },
    { continuation: 'judgment' }));
  record('continue with both conditions is not auto-passed', 'review', probeOf('continuation_likely_related', {},
    { kind: 'continue', candidateCharacterIds: [other], nextRoundId: 'round_x',
      plannedAction: `${context.names[other]} 拦住主角。`, protagonistRelevance: `目标是主角 ${context.names[protagonist]}。` },
    { continuation: 'judgment' }));
  record('handback where a clear driver existed', 'fail', probeOf('continuation_likely_related', {},
    { kind: 'handback', plannedAction: '', protagonistRelevance: '' }, { continuation: 'continue-required', driver: other }));
  record('continue where no driver existed', 'fail', probeOf('continuation_done', {},
    { kind: 'continue', candidateCharacterIds: [other], nextRoundId: 'round_x',
      plannedAction: `${context.names[other]} 继续走。`, protagonistRelevance: `主角 ${context.names[protagonist]} 在场。` },
    { continuation: 'handback-required' }));

  // scene-level: the product codec target shape must be accepted.
  const scene = { status: 'COMPLETED', playerInput: '', modelTasks: [
    { task: 'targets', key: protagonist, source: 'model', output: { targets: [{ targetId: other }] },
      raw: JSON.stringify({ targets: [{ targetId: other }] }), parseError: null },
  ] };
  const sceneVerdict = judgeScene(scene, context);
  cases.push({ name: 'scene accepts the {targetId} codec shape', expect: 'pass',
    got: sceneVerdict.semanticErrors.length === 0 && sceneVerdict.codecCalls === 1 ? 'pass' : 'fail',
    codec: sceneVerdict.codecCalls === 1, why: sceneVerdict.semanticErrors[0]?.error ?? null,
    reviews: sceneVerdict.pendingReview, ok: sceneVerdict.semanticErrors.length === 0 && sceneVerdict.codecCalls === 1 });

  const failed = cases.filter((entry) => !entry.ok);
  return { cases, failed: failed.length };
}

// ---------- reporting ----------

export function summarizeProbes(probes) {
  const counts = { probes: probes.length, parsedPass: 0, codecPass: 0, semanticsPass: 0, semanticsFail: 0, pendingReview: 0 };
  for (const probe of probes) {
    const judgment = probe.judgment ?? {};
    if (judgment.parsed) counts.parsedPass += 1;
    if (judgment.codec) counts.codecPass += 1;
    if (judgment.semantics === 'pass') counts.semanticsPass += 1;
    else if (judgment.semantics === 'fail') counts.semanticsFail += 1;
    else counts.pendingReview += 1;
  }
  const decided = counts.semanticsPass + counts.semanticsFail;
  return {
    ...counts,
    parsedRate: round(counts.parsedPass / Math.max(1, counts.probes)),
    codecRate: round(counts.codecPass / Math.max(1, counts.probes)),
    overallPassRate: round(counts.semanticsPass / Math.max(1, counts.probes)),
    autoDecided: decided,
    autoPassRate: round(counts.semanticsPass / Math.max(1, decided)),
  };
}
