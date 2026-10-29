// B3 settlement-task judges (Node side). The harness only produces evidence
// (prompts, raw model text, parsed output, completion timings); every semantic
// verdict is computed here, from the saved evidence. That keeps one judge for
// live runs and re-scoring of older archives.
//
// Verdict model:
//   structure  boolean  — output shape parsed and matches the task codec
//   semantics  pass | fail | review
//                      — `review` means the remaining question cannot be
//                        decided automatically (free-text plausibility), so the
//                        sample must NOT be counted as passing.
// Every non-passing verdict carries reasons; every passing verdict carries the
// assertions it actually checked.
//
// Automatic checks are deliberately narrow and evidence-bound:
//   - attribution: a text's first mentioned roster character is its subject;
//   - action vs goal: goal/plan sentences are not actions (§6.1);
//   - consumed input: re-executing the player command is forbidden for the
//     protagonist; other characters still act from their own tasks (§6.1);
//   - results: per-member attribution, dice agreement, and traceability to the
//     frozen action / task goals / roll evidence;
//   - updates: entity ownership, stage order, and the §6.3 causal chain
//     (personality requires an achieved task; sanity requires a personality
//     change) plus the probe's declared change expectation;
//   - continuation: the two §8.1 conditions must be stated (candidate + planned
//     action + protagonist relevance); "tasks incomplete" alone is not a reason.

const GOAL_WORDS = /需要|应该|打算|想要|愿意|必须|准备|试图|计划|希望|决定要/;
const STATE_CLAIM = /精神值|理智值|理智|生命值|血量|任务(达成|完成)|状态值|属性(值|变化)/;
const SUCCESS_WORDS = /成功|顺利|达成|完成|通过|做到了|搞定/;
const FAILURE_WORDS = /未|没能|没有|失败|落空|被挡|挡下|无效|失败|拒绝/;
const UPDATE_STAGES = ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'];
const UPDATE_FIELDS = {
  position: ['positionSet'], appearance: ['appearanceChanges'], tasks: ['tasksAchieved'],
  subtasks: ['subtasksAdded'], personality: ['personalityChanges'], sanity: ['sanitySet'],
};

const text = (value) => (typeof value === 'string' ? value : '');
const isObject = (value) => value != null && typeof value === 'object' && !Array.isArray(value);

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

export function taskOwnersOf(state) {
  const owners = {};
  for (const [actorId, actor] of Object.entries(state?.characters ?? {})) {
    for (const taskId of Object.keys(actor.tasks ?? {})) owners[taskId] = actorId;
  }
  return owners;
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

export function isGoalSentence(value) {
  return GOAL_WORDS.test(text(value));
}

export function hasStateClaim(value) {
  return STATE_CLAIM.test(text(value));
}

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

function rollEvidence(member) {
  const rolls = Array.isArray(member?.rollRefs) ? member.rollRefs : [];
  return rolls.map((roll) => ({
    admitted: roll?.admitted === true,
    result: typeof roll?.result === 'number' ? roll.result : null,
    targetId: roll?.targetId ?? null,
  }));
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

function makeJudge(id, structure, semantics, why, extra = {}) {
  return { id, structure, semantics, why: why ?? null, reasons: extra.reasons ?? (why ? [why] : []),
    reviews: extra.reviews ?? [], note: extra.note ?? null, checked: extra.checked ?? [] };
}

function fail(id, structure, why, extra = {}) {
  return makeJudge(id, structure, 'fail', why, extra);
}

function review(id, structure, why, extra = {}) {
  return makeJudge(id, structure, 'review', null, { ...extra, reviews: [...new Set([why, ...(extra.reviews ?? [])])] });
}

function pass(id, structure, note, checked = []) {
  return makeJudge(id, structure, 'pass', null, { note, checked });
}

// ---------- action ----------

function judgeAction(probe, context, mode) {
  const actor = probe.input?.actor ?? probe.call?.key ?? null;
  const out = probe.output ?? probe.call?.output ?? null;
  const inputText = text(probe.input?.advance?.inputText);
  const id = probe.id;
  if (!isObject(out) || (out.kind !== 'act' && out.kind !== 'skip')) return fail(id, false, `illegal or missing kind: ${JSON.stringify(out)}`);
  if (out.kind === 'skip') return pass(id, true, 'skip', ['legal kind']);
  if (!text(out.text).trim()) return fail(id, true, 'act without text');
  // 行动者身份由调度绑定（key=actor）；文本里没有名字不算错，但先把
  // 别的人物当主语就是人物归属错误。
  const subject = subjectActor(out.text, context);
  if (subject && subject !== actor) return fail(id, true, `action attributed to ${subject}, expected ${actor}: ${out.text}`);
  if (isGoalSentence(out.text)) return fail(id, true, `goal/plan is not an action: ${out.text}`);
  if (hasStateClaim(out.text)) return fail(id, true, `action claims a state change: ${out.text}`);
  const reusesCommand = inputText && normalize(out.text).includes(normalize(inputText));
  if (mode === 'consumed-protagonist' && reusesCommand) return fail(id, true, `consumed input re-executed: ${out.text}`);
  if (mode === 'pending-npc' && reusesCommand) return fail(id, true, `non-protagonist executes the player command: ${out.text}`);
  const reviews = [];
  if (mode === 'consumed-protagonist') reviews.push('spontaneous action after a consumed input needs semantic review');
  if (mode === 'pending-protagonist' && !reusesCommand) reviews.push('action deviates from the pending command; plausibility needs review');
  if (reviews.length) return review(id, true, reviews[0], { note: out.text, reviews, checked: ['attribution', 'not-a-goal', 'no-state-claim'] });
  return pass(id, true, out.text, ['attribution', 'not-a-goal', 'no-state-claim', 'command-reuse']);
}

// ---------- targets ----------

function judgeTargets(probe, context) {
  const out = probe.output ?? probe.call?.output ?? null;
  const id = probe.id;
  if (!isObject(out) || !Array.isArray(out.targets)) return fail(id, false, 'targets array missing');
  // 当前 codec 是 {targets:[{targetId}]}；旧归档里是字符串数组，两种都读。
  const targets = out.targets.map((entry) => (typeof entry === 'string' ? entry : entry?.targetId));
  if (targets.some((target) => typeof target !== 'string' || !target)) return fail(id, true, `targets must be non-empty ids: ${JSON.stringify(out.targets)}`);
  const source = probe.input?.sourceId;
  if (targets.includes(source)) return fail(id, true, `source targets itself: ${JSON.stringify(targets)}`);
  const unknown = targets.filter((target) => !context.roster.includes(target));
  if (unknown.length) return fail(id, true, `targets outside the roster: ${JSON.stringify(unknown)}`);
  if (new Set(targets).size !== targets.length) return fail(id, true, `duplicate targets: ${JSON.stringify(targets)}`);
  const named = actorMentions(probe.input?.actionText, context).filter((entry) => entry.id !== source).map((entry) => entry.id);
  const directed = probe.expect?.directed ?? (named.length ? named[0] : null);
  if (probe.expect?.directed || (directed && probe.input?.actionText)) {
    const wanted = directed;
    if (!targets.includes(wanted)) return fail(id, true, `expected ${wanted} in ${JSON.stringify(targets)}`);
    if (targets.length !== 1) return fail(id, true, `expected exactly ${wanted}, got ${JSON.stringify(targets)}`);
    return pass(id, true, `targets=${JSON.stringify(targets)}`, ['named-target-selected']);
  }
  if (probe.expect?.solo && targets.length !== 0) return fail(id, true, `expected empty, got ${JSON.stringify(targets)}`);
  return pass(id, true, `targets=${JSON.stringify(targets)}`, ['roster-and-self checks']);
}

// ---------- reaction ----------

function judgeReaction(probe, context) {
  const out = probe.output ?? probe.call?.output ?? null;
  const id = probe.id;
  const member = probe.input?.memberId;
  const output = typeof out === 'string' ? out : isObject(out) ? text(out.text) : '';
  if (!output.trim()) return fail(id, Boolean(output), 'reaction is empty');
  const subject = subjectActor(output, context);
  if (member && subject && subject !== member) return fail(id, true, `reaction attributed to ${subject}, expected ${member}: ${output}`);
  if (hasStateClaim(output)) return fail(id, true, `reaction claims a state change: ${output}`);
  const sourceAction = text(probe.call?.context?.sourceActionText ?? probe.expect?.sourceActionText);
  if (sourceAction && copiesAction(output, sourceAction)) return fail(id, true, `reaction copies the source action: ${output}`);
  return pass(id, true, output, ['attribution', 'no-state-claim', 'not-a-copy']);
}

// ---------- results ----------

function resultClause(output, member, context) {
  const source = text(output);
  const own = context.names[member.memberId];
  const others = context.roster.filter((id) => id !== member.memberId).map((id) => context.names[id]);
  let clause = source;
  for (const name of others) {
    const index = clause.indexOf(name);
    if (index > 0) { clause = clause.slice(0, index); break; }
  }
  return { clause, own };
}

function judgeResults(probe, context) {
  const out = probe.output ?? probe.call?.output ?? null;
  const id = probe.id;
  const members = probe.input?.members ?? [];
  if (!isObject(out)) return fail(id, false, 'results must be an object');
  const keys = Object.keys(out).sort();
  if (!members.length) {
    // 旧归档没有保存 results 的输入上下文：只能核对键集合与人物归属，
    // 不能宣称结果可溯源于冻结行动——归入待复核。
    const unknown = keys.filter((key) => !context.roster.includes(key));
    if (unknown.length) return fail(id, true, `results keys outside the roster: ${JSON.stringify(unknown)}`);
    if (keys.some((key) => !text(out[key]).trim())) return fail(id, true, 'results contain an empty text');
    for (const key of keys) {
      const subject = subjectActor(out[key], context);
      if (subject && subject !== key) return fail(id, true, `${key} result is acted by ${subject}: ${out[key]}`);
    }
    return review(id, true, 'result context was not archived: traceability and dice agreement unverified',
      { note: JSON.stringify(out), checked: ['keys', 'naming'] });
  }
  const wanted = members.map((member) => member.memberId).sort();
  if (keys.join(',') !== wanted.join(',')) return fail(id, true, `results keys ${keys} != [${wanted}]`);
  if (keys.some((key) => !text(out[key]).trim())) return fail(id, true, 'results contain an empty text');
  for (const member of members) {
    const value = text(out[member.memberId]);
    if (!value.trim()) return fail(id, true, `result for ${member.memberId} is empty`);
    const subject = subjectActor(value, context);
    if (subject && subject !== member.memberId) {
      return fail(id, true, `result for ${member.memberId} is acted by ${subject}: ${value}`);
    }
    const evidence = [text(member.actionText), ...taskGoalsOf(context, member.memberId)];
    const traceable = evidence.some((entry) => sharedBigram(value, entry, context));
    if (!traceable) return fail(id, true, `result for ${member.memberId} is not traceable to the frozen action or its tasks: ${value}`);
    const rolls = rollEvidence(member);
    if (rolls.length) {
      const { clause } = resultClause(value, member, context);
      const rejected = rolls.every((roll) => !roll.admitted);
      const admitted = rolls.some((roll) => roll.admitted);
      if (rejected && SUCCESS_WORDS.test(clause)) return fail(id, true, `rejected roll described as success (${member.memberId}): ${value}`);
      if (admitted && FAILURE_WORDS.test(clause) && !SUCCESS_WORDS.test(clause)) {
        return fail(id, true, `admitted roll described as failure (${member.memberId}): ${value}`);
      }
    }
  }
  return review(id, true, 'result plausibility (invented events beyond the frozen actions) needs human review', {
    note: JSON.stringify(out), checked: ['per-member attribution', 'roster actors', 'traceability', 'dice agreement'],
  });
}

// ---------- updates ----------

export function auditUpdates(calls, expectation, context) {
  const reasons = [];
  const reviews = [];
  const batchTasks = new Set();
  const batchPersonality = new Set();
  for (const call of calls) {
    for (const [entity, delta] of Object.entries(call.changes ?? {})) {
      if (!isObject(delta)) continue;
      for (const task of delta.subtasksAdded ?? []) if (isObject(task) && typeof task.id === 'string') batchTasks.add(`${entity}:${task.id}`);
      for (const change of delta.personalityChanges ?? []) if (isObject(change) && typeof change.id === 'string') batchPersonality.add(`${entity}:${change.id}`);
    }
  }
  let last = -1;
  for (const call of calls) {
    if (!isObject(call)) { reasons.push('update call must be an object'); continue; }
    const stageIndex = UPDATE_STAGES.indexOf(call.stage);
    if (stageIndex < 0) { reasons.push(`illegal stage ${call.stage}`); continue; }
    if (stageIndex <= last) reasons.push(`out-of-order/duplicate stage ${call.stage}`);
    last = stageIndex;
    if (expectation.stage && call.stage !== expectation.stage) reasons.push(`stage ${call.stage} != ${expectation.stage}`);
    if (!isObject(call.changes)) { reasons.push(`changes of ${call.stage} must be an object`); continue; }
    const allowed = UPDATE_FIELDS[call.stage];
    for (const [entity, delta] of Object.entries(call.changes)) {
      if (!context.roster.includes(entity)) reasons.push(`entity ${entity} not in roster`);
      if (!isObject(delta)) { reasons.push(`delta of ${entity} must be an object`); continue; }
      for (const key of Object.keys(delta)) {
        if (key === 'entityId') continue;
        if (!allowed.includes(key)) reasons.push(`field ${key} is not allowed in ${call.stage}`);
      }
      for (const taskId of delta.tasksAchieved ?? []) {
        const owner = context.owners[taskId];
        if (!owner && !batchTasks.has(`${entity}:${taskId}`)) reasons.push(`tasksAchieved ${taskId} is not in the state or produced by this batch`);
        else if (owner && owner !== entity) reasons.push(`task ${taskId} is owned by ${owner}, not ${entity}`);
      }
      for (const change of (delta.personalityChanges ?? [])) {
        if (!isObject(change) || !text(change.id) || !text(change.text) || !Array.isArray(change.supersedes)) {
          reasons.push(`invalid personality change for ${entity} (id/text/supersedes required)`);
        }
      }
      for (const change of (delta.appearanceChanges ?? [])) {
        if (!isObject(change) || !text(change.id) || !text(change.text) || !Array.isArray(change.supersedes)) {
          reasons.push(`invalid appearance change for ${entity} (id/text/supersedes required)`);
        }
      }
      if (delta.sanitySet !== undefined) {
        if (!Number.isInteger(delta.sanitySet) || delta.sanitySet < 0 || delta.sanitySet > 100) reasons.push(`sanitySet must be an integer in [0,100], got ${JSON.stringify(delta.sanitySet)}`);
        const before = context.state?.characters?.[entity]?.sanity;
        if (Number.isInteger(before) && Math.abs(delta.sanitySet - before) > 30) reviews.push(`large sanity jump ${before}->${delta.sanitySet} for ${entity} needs review`);
      }
      if (delta.positionSet !== undefined) {
        const position = delta.positionSet;
        if (!isObject(position) || typeof position.containerId !== 'string' || !context.locations[position.containerId]) {
          reasons.push(`invalid positionSet for ${entity}`);
        }
      }
    }
  }
  // §6.3 causal chain, evaluated over the whole batch/call.
  for (const call of calls) {
    for (const [entity, delta] of Object.entries(call?.changes ?? {})) {
      if (!isObject(delta)) continue;
      const hasTasks = (delta.tasksAchieved?.length ?? 0) > 0;
      const hasPersonality = (delta.personalityChanges?.length ?? 0) > 0;
      const hasSanity = delta.sanitySet !== undefined;
      if (hasPersonality && !hasTasks) reasons.push(`${entity} personality change without an achieved task`);
      if (hasSanity && !hasPersonality) reasons.push(`${entity} sanity change without a personality change`);
    }
  }
  if (expectation.forbidAnyChange) {
    for (const call of calls) {
      for (const [entity, delta] of Object.entries(call?.changes ?? {})) {
        if (!isObject(delta)) continue;
        if ((delta.tasksAchieved?.length ?? 0) || (delta.personalityChanges?.length ?? 0) || delta.sanitySet !== undefined) {
          reasons.push(`unexpected change for ${entity} (${JSON.stringify(delta)})`);
        }
      }
    }
  }
  for (const [entity, tasks] of Object.entries(expectation.expectTasks ?? {})) {
    const found = new Set(calls.flatMap((call) => Object.entries(call?.changes ?? {})
      .filter(([key]) => key === entity).flatMap(([, delta]) => delta?.tasksAchieved ?? [])));
    for (const taskId of tasks) if (!found.has(taskId)) reasons.push(`expected ${entity} to achieve ${taskId}`);
  }
  for (const entity of expectation.expectSanityFor ?? []) {
    const found = calls.some((call) => call?.changes?.[entity]?.sanitySet !== undefined);
    if (!found) reasons.push(`expected ${entity} to receive a recalculated sanity value`);
  }
  return { reasons, reviews };
}

function normalizeCalls(probe) {
  const out = probe.output ?? probe.call?.output ?? null;
  const stage = probe.expect?.stage ?? probe.input?.stage ?? null;
  const calls = Array.isArray(out) ? out : isObject(out) ? [out] : null;
  return { out, calls, stage };
}

function judgeUpdates(probe, context) {
  const id = probe.id;
  const { out, calls, stage } = normalizeCalls(probe);
  if (!calls) return fail(id, false, stage ? 'stage call must be one object' : 'merged updates must be an array');
  if (stage && Array.isArray(out)) return fail(id, false, `stage ${stage} call returned an array`);
  if (!stage && !Array.isArray(out)) return fail(id, false, 'merged updates returned a single object');
  const { reasons, reviews } = auditUpdates(calls, probe.expect ?? {}, context);
  if (reasons.length) return fail(id, true, reasons.join('; '), { reasons });
  if (reviews.length) return review(id, true, reviews[0], { reviews, note: JSON.stringify(out) });
  return pass(id, true, `${calls.length} call(s): ${calls.map((call) => call.stage).join(',')}`, ['stage/fields/order', 'entity ownership', 'causality', 'expectation']);
}

// ---------- continuation ----------

function judgeContinuation(probe, context) {
  const id = probe.id;
  // 结论字段（kind/candidates/nextRoundId）与判断字段（plannedAction/
  // protagonistRelevance）在端口处分离：wire 只保留结论，判断产物留在
  // call.output。判分读模型的原始判断，不读被剥离后的结论。
  const out = probe.call?.output ?? probe.output ?? null;
  if (!isObject(out) || (out.kind !== 'continue' && out.kind !== 'handback')) return fail(id, false, `illegal or missing kind: ${JSON.stringify(out)}`);
  const expectation = probe.expect?.continuation ?? 'judgment';
  const plannedAction = text(out.plannedAction);
  const relevance = text(out.protagonistRelevance);
  const candidates = Array.isArray(out.candidateCharacterIds) ? out.candidateCharacterIds : [];
  if (out.kind === 'handback') {
    if (expectation === 'continue-required') return fail(id, true, 'clear protagonist-related driver was handed back');
    if (plannedAction || relevance) return review(id, true, 'handback carries a stated action/relevance; needs review', { reviews: ['handback rationale'], note: JSON.stringify(out) });
    return pass(id, true, 'handback', ['legal kind', 'no stated driver']);
  }
  if (expectation === 'handback-required') return fail(id, true, 'no driving action was expected, model continued');
  if (!candidates.length) return fail(id, true, 'continue without candidate characters');
  const unknown = candidates.filter((candidate) => !context.roster.includes(candidate));
  if (unknown.length) return fail(id, true, `candidates outside the roster: ${JSON.stringify(unknown)}`);
  const dropped = (probe.call?.backfills ?? []).filter((entry) => entry.kind === 'candidate_dropped_not_in_roster'
    || entry.kind === 'candidates_backfilled_roster');
  if (dropped.length) return fail(id, true, `invalid candidateCharacterIds: ${JSON.stringify(dropped)}`);
  if (!plannedAction) return fail(id, true, 'continue without a planned action (the §8.1 likelihood condition is unstated)');
  if (isGoalSentence(plannedAction)) return fail(id, true, `planned action is a goal/plan sentence, not an action: ${plannedAction}`);
  if (!relevance) return fail(id, true, 'continue without a protagonist relevance statement (the §8.1 relation condition is unstated)');
  if (!relevance.includes(context.protagonist) && !relevance.includes(context.names[context.protagonist])) {
    return fail(id, true, `protagonist relevance does not reference the protagonist: ${relevance}`);
  }
  if (/无关|没有关系|不涉及|不影响主角|与主角无关/.test(relevance)) {
    return fail(id, true, `relevance states the action is unrelated to the protagonist but still continues: ${relevance}`);
  }
  if (expectation === 'continue-required' && probe.expect?.driver && !candidates.includes(probe.expect.driver)) {
    return fail(id, true, `candidate ${JSON.stringify(candidates)} does not include the driving character ${probe.expect.driver}`);
  }
  if (expectation === 'handback-expected') return review(id, true, 'continued where the premise suggests handing back; needs review', { note: JSON.stringify(out) });
  return review(id, true, 'planned action plausibility (large-likelihood + protagonist relation) needs human review', {
    note: JSON.stringify(out), checked: ['legal kind', 'candidates', 'planned action stated', 'protagonist relevance stated'],
  });
}

// ---------- probe dispatch ----------

const OLD_CONTINUATION = new Set(['continuation_more']);

export function judgeProbe(probe, context) {
  const id = probe.id;
  const fixtureExpect = probe.expect ?? {};
  if (probe.failure && !probe.call?.output) return fail(id, false, probe.failure);
  switch (id) {
    case 'action_pending': return judgeAction(probe, context, 'pending-protagonist');
    case 'action_consumed':
    case 'action_consumed_protagonist':
      return judgeAction(probe, context, 'consumed-protagonist');
    case 'action_nonactor':
    case 'action_consumed_npc':
      return judgeAction(probe, context, fixtureExpect.advance === 'pending' ? 'pending-npc' : 'consumed-npc');
    case 'targets_directed': return judgeTargets(probe, context);
    case 'targets_solo': return judgeTargets(probe, context);
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
    case 'continuation_more': {
      if (OLD_CONTINUATION.has(id) && !probe.expect) {
        return review(id, true, 'original probe predates the §8.1 two-condition judgement; expectation rebuilt, not counted as passing', {
          note: JSON.stringify(probe.output ?? probe.call?.output ?? null),
        });
      }
      return judgeContinuation(probe, context);
    }
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
      return review(id, false, `no judge for probe ${id}`);
  }
}

// ---------- scene records ----------

export function judgeScene(scene, context) {
  const errors = [];
  const reviews = [];
  const narrationFallbacks = [];
  let modelCalls = 0;
  let programCalls = 0;
  const playerInput = text(scene.playerInput);
  const addReview = (entry) => reviews.push(entry);
  for (const call of scene.modelTasks ?? []) {
    if (call.source === 'program') { programCalls += 1; continue; }
    modelCalls += 1;
    const output = call.output ?? null;
    const label = `${call.task}:${call.key}`;
    if (call.error) { errors.push({ call: label, error: call.error }); continue; }
    if (call.validationError) { errors.push({ call: label, error: call.validationError }); continue; }
    switch (call.task) {
      case 'action': {
        if (!isObject(output)) { errors.push({ call: label, error: 'action output is not an object' }); break; }
        if (output.kind === 'skip') break;
        if (output.kind !== 'act' || !text(output.text).trim()) { errors.push({ call: label, error: `illegal action ${JSON.stringify(output)}` }); break; }
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
        if (!isObject(output) || !Array.isArray(output.targets)) { errors.push({ call: label, error: 'targets array missing' }); break; }
        if (output.targets.some((target) => !context.roster.includes(target))) errors.push({ call: label, error: `targets outside the roster: ${JSON.stringify(output.targets)}` });
        if (output.targets.includes(call.key)) errors.push({ call: label, error: 'source targets itself' });
        if ((call.backfills ?? []).some((entry) => entry.kind === 'target_dropped_not_in_roster')) {
          errors.push({ call: label, error: `target dropped (not in roster): ${JSON.stringify(call.backfills)}` });
        }
        break;
      }
      case 'reaction': {
        const reactionText = typeof output === 'string' ? output : isObject(output) && typeof output.text === 'string' ? output.text : '';
        if (!reactionText.trim()) { errors.push({ call: label, error: 'reaction is empty' }); break; }
        const member = call.context?.memberId;
        const subject = subjectActor(reactionText, context);
        if (member && subject && subject !== member) errors.push({ call: label, error: `reaction attributed to ${subject}, expected ${member}: ${reactionText}` });
        if (!member) addReview({ call: label, review: 'reaction member context was not archived' });
        if (hasStateClaim(reactionText)) errors.push({ call: label, error: `reaction claims a state change: ${reactionText}` });
        if (call.context?.sourceActionText && copiesAction(reactionText, call.context.sourceActionText)) errors.push({ call: label, error: 'reaction copies the source action' });
        break;
      }
      case 'results': {
        const members = call.context?.members ?? [];
        if (!isObject(output)) { errors.push({ call: label, error: 'results must be an object' }); break; }
        const judged = judgeResults({ id: label, input: { members }, output, call }, context);
        if (judged.semantics === 'fail') errors.push({ call: label, error: judged.why });
        else if (judged.semantics === 'review') addReview({ call: label, review: judged.reviews[0] });
        break;
      }
      case 'updates': {
        const calls = Array.isArray(output) ? output : [output];
        const { reasons, reviews: updateReviews } = auditUpdates(calls, {}, context);
        if (reasons.length) errors.push({ call: label, error: reasons.join('; ') });
        if (updateReviews.length) addReview({ call: label, review: updateReviews[0] });
        break;
      }
      case 'continuation': {
        const judged = judgeContinuation({ id: label, output, expect: call.expect ?? { continuation: 'judgment' } }, context);
        if (judged.semantics === 'fail') errors.push({ call: label, error: judged.why });
        else if (judged.semantics === 'review') addReview({ call: label, review: judged.reviews[0] });
        break;
      }
      case 'narration': {
        // The gate events are authoritative: a fallback means the model text was
        // rejected (or generation failed), never a pass.
        break;
      }
      default:
        break;
    }
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
  return { status: scene.status, accepted, modelCalls, programCalls, semanticErrors: errors, pendingReview: reviews, narrationFallbacks };
}

// ---------- judge self-test (tamper probes) ----------

export function runJudgeSelfTests(context) {
  const protagonist = context.protagonist;
  const other = context.roster.find((id) => id !== protagonist) ?? protagonist;
  const memberAction = `${context.names[protagonist]} 推开门厅深处的重门。`;
  const taskId = (context.tasks[protagonist] ?? [])[0]?.id ?? 'task_x';
  const cases = [];
  const record = (name, expect, probe) => cases.push({ name, expect, verdict: judgeProbe(probe, context) });

  record('absurd joint results', 'fail', {
    id: 'results_joint', input: { members: [{ memberId: protagonist, actionText: `${context.names[protagonist]} 在走廊守门。`, rollRefs: [] }] },
    output: { [protagonist]: `${context.names[protagonist]} 召唤了陨石毁灭了世界。` },
  });
  record('empty update after a claimed completion', 'fail', {
    id: 'updates_merged', input: {}, output: [], expect: { expectTasks: { [protagonist]: [taskId] } },
  });
  record('causeless sanity 99', 'fail', {
    id: 'updates_merged', input: {},
    output: [{ stage: 'sanity', changes: { [protagonist]: { sanitySet: 99 } } }], expect: {},
  });
  record('wrong-actor action', 'fail', {
    id: 'action_pending', input: { actor: other, advance: { inputText: '走到走廊', intentStatus: 'pending' } },
    output: { kind: 'act', text: `${context.names[protagonist]} 推开门。` },
  });
  record('goal sentence as action', 'fail', {
    id: 'action_pending', input: { actor: protagonist, advance: { inputText: '走到走廊', intentStatus: 'pending' } },
    output: { kind: 'act', text: `${context.names[protagonist]} 需要去走廊。` },
  });
  record('consumed protagonist re-executes the command', 'fail', {
    id: 'action_consumed_protagonist', input: { actor: protagonist, advance: { inputText: '走到走廊', intentStatus: 'consumed' } },
    output: { kind: 'act', text: `${context.names[protagonist]} 走到走廊。` },
  });
  record('reaction with a state claim', 'fail', {
    id: 'reaction_joint', input: { memberId: other, sourceActionText: memberAction },
    output: `${context.names[other]} 精神值下降。`,
  });
  record('reaction copying the source action', 'fail', {
    id: 'reaction_joint', input: { memberId: other, sourceActionText: memberAction },
    output: memberAction,
  });
  record('results claiming success on a rejected roll', 'fail', {
    id: 'results_rejected_roll',
    input: { members: [{ memberId: protagonist, actionText: memberAction,
      rollRefs: [{ targetId: other, result: 8, admitted: false }] }] },
    output: { [protagonist]: `${context.names[protagonist]} 成功推开了重门。` },
  });
  record('task-only update is legal', 'pass', {
    id: 'updates_merged', input: {},
    output: [{ stage: 'tasks', changes: { [protagonist]: { tasksAchieved: [taskId] } } }],
    expect: { expectTasks: { [protagonist]: [taskId] } },
  });
  record('personality without an achieved task', 'fail', {
    id: 'updates_merged', input: {},
    output: [{ stage: 'personality', changes: { [protagonist]: { personalityChanges: [
      { id: 'draft_1', text: '更谨慎', supersedes: [] }] } } }],
  });
  record('continue without the §8.1 conditions', 'fail', {
    id: 'continuation_likely_related', input: {},
    output: { kind: 'continue', candidateCharacterIds: [other], nextRoundId: 'round_x' },
    expect: { continuation: 'judgment' },
  });
  record('continue with both conditions is not auto-passed', 'review', {
    id: 'continuation_likely_related', input: {},
    output: { kind: 'continue', candidateCharacterIds: [other], nextRoundId: 'round_x',
      plannedAction: `${context.names[other]} 拦住主角。`, protagonistRelevance: `目标是主角 ${context.names[protagonist]}。` },
    expect: { continuation: 'judgment' },
  });
  record('handback where a clear driver existed', 'fail', {
    id: 'continuation_likely_related', input: {},
    output: { kind: 'handback' }, expect: { continuation: 'continue-required', driver: other },
  });
  record('continue where no driver existed', 'fail', {
    id: 'continuation_done', input: {},
    output: { kind: 'continue', candidateCharacterIds: [other], nextRoundId: 'round_x',
      plannedAction: `${context.names[other]} 继续走。`, protagonistRelevance: `主角 ${context.names[protagonist]} 在场。` },
    expect: { continuation: 'handback-required' },
  });
  const failed = cases.filter((entry) => entry.verdict.semantics !== entry.expect);
  return { cases: cases.map((entry) => ({ name: entry.name, expect: entry.expect, got: entry.verdict.semantics,
    why: entry.verdict.why, reviews: entry.verdict.reviews, structure: entry.verdict.structure })), failed: failed.length };
}

// ---------- reporting ----------

export function summarizeProbes(probes) {
  const counts = { probes: probes.length, structurePass: 0, semanticsPass: 0, semanticsFail: 0, pendingReview: 0 };
  for (const probe of probes) {
    if (probe.judgment?.structure) counts.structurePass += 1;
    if (probe.judgment?.semantics === 'pass') counts.semanticsPass += 1;
    else if (probe.judgment?.semantics === 'fail') counts.semanticsFail += 1;
    else counts.pendingReview += 1;
  }
  const decided = counts.semanticsPass + counts.semanticsFail;
  return { ...counts, structureRate: round(counts.structurePass / Math.max(1, counts.probes)),
    semanticsRate: round(counts.semanticsPass / Math.max(1, decided)), autoDecided: decided };
}

const round = (value) => Number(value.toFixed(3));
