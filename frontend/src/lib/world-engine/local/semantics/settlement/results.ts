/** Common-group results (R07/R08): every frozen action, every actual roll
 * receipt, one joint settlement, facts attributed to the members they belong
 * to. Denied/already-acted rolls are accepted as observation; they never
 * become a reaction and never make an action succeed. */
import type { Id, Json, WorldState } from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import { callJson, JsonCallError, joinedMs, joinedRaw } from './engine-call';
import type { ModelCallEvidence, SettlementEvidence, SettlementOptions, SettlementOutcome } from './types';
import {
  asInteger, asRecord, asString, errorText, isRecord, referenceError, resolveCharacterId, resolveEntityId, toJson,
} from './support';
import { describeCharacter, describeItem, sameRoomItems, visibleCharacters } from '../../prompt';

interface RollReceipt {
  targetId: Id;
  rollId: Id;
  result: number;
  eligible: boolean;
  admitted: boolean;
}

interface GroupMember {
  memberId: Id;
  actionText: string;
  rolls: RollReceipt[];
}

interface ResultsInput {
  groupId: Id;
  members: GroupMember[];
  workingState: WorldState;
}

interface Judgment {
  memberId: Id;
  label: 'achieved' | 'partial' | 'not_achieved' | 'blocked' | 'no_change';
  reason: string;
  effects: { targetId: Id; reacted: boolean }[];
}

interface Fact {
  text: string;
  memberIds: Id[];
}

interface SanitizedFact {
  memberIds: Id[];
  original: string;
  text: string;
  removed: string[];
}

interface ResultsAnswer {
  judgments: Judgment[];
  facts: Fact[];
  /** A result fact may not assert task/success completion; the action label is
   * the result. Removed claims stay in evidence so the fallback composer can
   * never turn a pending task row into "行动成功完成". */
  sanitized?: SanitizedFact[];
  /** Extra judgments for people outside the frozen group. They may describe
   * what the model saw, but they never settle a non-member; they are kept in
   * evidence and dropped from the committed result. */
  dropped?: { memberId: Id; label: string; reason: 'not_a_group_member' }[];
}

const LABELS = new Set(['achieved', 'partial', 'not_achieved', 'blocked', 'no_change']);

const RESULTS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['judgments', 'facts'],
  properties: {
    judgments: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['memberId', 'label', 'reason', 'effects'],
        properties: {
          memberId: { type: 'string' },
          label: { enum: [...LABELS] },
          reason: { type: 'string' },
          effects: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['targetId', 'reacted'],
              properties: { targetId: { type: 'string' }, reacted: { type: 'boolean' } },
            },
          },
        },
      },
    },
    facts: {
      type: 'array',
      minItems: 1,
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['text', 'memberIds'],
        properties: {
          text: { type: 'string' },
          memberIds: { type: 'array', minItems: 1, items: { type: 'string' } },
        },
      },
    },
  },
};

export async function runResults(
  engine: InferenceEngine,
  key: Id,
  input: Json,
  options: SettlementOptions = {},
): Promise<SettlementOutcome<Record<Id, string>>> {
  const started = performance.now();
  const parsed = parseResultsInput(input);
  if ('error' in parsed) {
    return failure(key, parsed.error, started);
  }
  const { groupId, members, workingState } = parsed;
  const prompt = buildResultsPrompt(groupId, members, workingState);
  let calls: ModelCallEvidence[] = [];
  try {
    const answer = await callJson(engine, prompt, {
      maxTokens: options.maxTokens?.results ?? 420,
      temperature: options.temperature ?? 0,
      timeoutMs: options.timeoutMs,
      maxPromptChars: options.maxPromptChars,
      jsonSchema: RESULTS_SCHEMA,
      validate: (value) => { readResultsAnswer(value, members, workingState); },
    });
    calls = answer.calls;
    const parsedAnswer = readResultsAnswer(answer.value, members, workingState);
    const value = normalizeResults(parsedAnswer, members);
    const evidence = makeEvidence(key, answer.calls, false, undefined, {
      groupId,
      memberIds: members.map((member) => member.memberId),
      rollReceiptCount: members.reduce((sum, member) => sum + member.rolls.length, 0),
      factCount: parsedAnswer.facts.length,
      sanitizedFacts: parsedAnswer.sanitized ?? [],
      memberFactCoverage: members.map((member) => ({
        memberId: member.memberId,
        factCount: parsedAnswer.facts.filter((fact) => fact.memberIds.includes(member.memberId)).length,
      })),
      labels: parsedAnswer.judgments.map((judgment) => `${judgment.memberId}:${judgment.label}`),
      droppedNonMemberJudgments: parsedAnswer.dropped ?? [],
      deniedRolls: members.flatMap((member) => member.rolls
        .filter((roll) => !roll.admitted)
        .map((roll) => ({ sourceId: member.memberId, targetId: roll.targetId, rollId: roll.rollId, result: roll.result, eligible: roll.eligible }))),
    });
    const outcome: SettlementOutcome<Record<Id, string>> = {
      value,
      raw: joinedRaw(calls),
      ms: joinedMs(calls),
      fallback: false,
      evidence,
    };
    options.onTask?.('results', key, { ms: outcome.ms, fallback: false, raw: outcome.raw, promptChars: prompt.length });
    return outcome;
  } catch (error) {
    calls = error instanceof JsonCallError ? error.calls : calls;
    const message = errorText(error);
    // A repair that still fails aborts the frozen point. A made-up
    // "conservative result" would invent facts the model never judged and
    // would let the six-stage settlement commit a partial common group.
    const evidence = makeEvidence(key, calls, true, message, {
      groupId,
      memberIds: members.map((member) => member.memberId),
      declaredTargets: members.map((member) => ({ memberId: member.memberId, targetIds: member.rolls.map((roll) => roll.targetId) })),
      reason: 'point_aborted_after_repair',
    });
    const outcome: SettlementOutcome<Record<Id, string>> = {
      value: null,
      raw: joinedRaw(calls),
      ms: joinedMs(calls),
      fallback: true,
      error: message,
      evidence,
    };
    options.onTask?.('results', key, { ms: outcome.ms, fallback: true, error: message, raw: outcome.raw, promptChars: prompt.length });
    return outcome;
  }
}

function parseResultsInput(input: Json): ResultsInput | { error: string } {
  const data = asRecord(input);
  const state = data.workingState;
  if (!isRecord(state) || !isRecord(state.initial) || !isRecord(state.initial.characters)
    || !isRecord(state.initial.items) || !isRecord(state.initial.locations)
    || !isRecord(state.characters) || !isRecord(state.items) || !isRecord(state.locations)) {
    return { error: 'results_missing_working_state' };
  }
  const world = state as unknown as WorldState;
  const groupId = asString(data.groupId);
  if (!groupId) return { error: 'results_missing_group_id' };
  if (!Array.isArray(data.members) || data.members.length === 0) return { error: 'results_missing_members' };
  const members: GroupMember[] = [];
  const memberIds = new Set<Id>();
  const rollIds = new Set<Id>();
  for (const rawMember of data.members) {
    if (!isRecord(rawMember)) return { error: 'results_member_not_object' };
    const memberId = asString(rawMember.memberId);
    if (!memberId || !world.characters[memberId]) return { error: `results_unknown_member:${memberId || '?'}` };
    if (memberIds.has(memberId)) return { error: `results_duplicate_member:${memberId}` };
    memberIds.add(memberId);
    const actionText = asString(rawMember.actionText);
    if (!actionText) return { error: `results_missing_action:${memberId}` };
    const rolls: RollReceipt[] = [];
    const targets = new Set<Id>();
    const rollRefs = rawMember.rollRefs ?? [];
    if (!Array.isArray(rollRefs)) return { error: `results_roll_refs_not_array:${memberId}` };
    for (const rawRoll of rollRefs) {
      if (!isRecord(rawRoll)) return { error: `results_roll_not_object:${memberId}` };
      const targetId = asString(rawRoll.targetId);
      const rollId = asString(rawRoll.rollId);
      const result = asInteger(rawRoll.result);
      if (!targetId || !world.characters[targetId]) return { error: `results_unknown_roll_target:${memberId}` };
      if (!rollId) return { error: `results_missing_roll_id:${memberId}` };
      if (rollIds.has(rollId)) return { error: `results_duplicate_roll:${rollId}` };
      rollIds.add(rollId);
      if (result == null || result < 1 || result > 20) return { error: `results_invalid_roll_result:${rollId}` };
      if (typeof rawRoll.eligible !== 'boolean' || typeof rawRoll.admitted !== 'boolean') {
        return { error: `results_incomplete_roll_receipt:${rollId}` };
      }
      if (rawRoll.admitted && !rawRoll.eligible) return { error: `results_inconsistent_admission:${rollId}` };
      if (targets.has(targetId)) return { error: `results_duplicate_roll_target:${memberId}:${targetId}` };
      targets.add(targetId);
      rolls.push({ targetId, rollId, result, eligible: rawRoll.eligible, admitted: rawRoll.admitted });
    }
    members.push({ memberId, actionText, rolls });
  }
  for (const member of members) {
    for (const roll of member.rolls) {
      if (roll.admitted && !memberIds.has(roll.targetId)) {
        return { error: `results_admitted_target_not_member:${member.memberId}->${roll.targetId}` };
      }
    }
  }
  return { groupId, members, workingState: world };
}

function buildResultsPrompt(groupId: Id, members: GroupMember[], state: WorldState): string {
  const memberLines = members.map((member) => {
    const name = state.initial.characters[member.memberId]?.name ?? member.memberId;
    const rolls = member.rolls.length
      ? member.rolls.map((roll) => {
        const targetName = state.initial.characters[roll.targetId]?.name ?? roll.targetId;
        return `目标${targetName}(${roll.targetId}) 骰点=${roll.result} 资格=${roll.eligible} 准入=${roll.admitted}`;
      }).join('；')
      : '无判定';
    return `- ${name}（id=${member.memberId}）行动：${member.actionText}\n  判定：${rolls}`;
  });
  const sceneIds = new Set<Id>([...members.map((member) => member.memberId)]);
  for (const member of members) {
    for (const id of visibleCharacters(state, member.memberId)) sceneIds.add(id);
    for (const id of sameRoomItems(state, member.memberId)) sceneIds.add(id);
    for (const roll of member.rolls) sceneIds.add(roll.targetId);
  }
  const scene = [...sceneIds].filter((id) => state.characters[id] || state.items[id])
    .map((id) => state.characters[id] ? describeCharacter(state, id, false) : describeItem(state, id));
  const exampleMember = members[0];
  const exampleTarget = exampleMember.rolls[0]?.targetId;
  const exampleEffects = exampleTarget ? `[{"targetId":"${exampleTarget}","reacted":true或false}]` : '[]';
  return [
    '你是中文跑团游戏的共同结算器。只输出 JSON，不要解释。',
    '下面是一个已经冻结的结算组：行动已经确认，骰点已经落定。请统一结算全组行动，写清实际发生了什么。',
    '规则：',
    '- 只能使用下面出现的人物、地点、物品；不得新增人物、地点、物品、往事、线索或任务。',
    '- 一个成员的行动可以成功、部分成功、失败或被制止；行动被接纳不等于目标达成。',
    '- 骰点 准入=false 表示该目标这次没有被迫反应；effects 中该 target 的 reacted 必须为 false。已行动人物不会再次反应。',
    '- effects 必须恰好覆盖该成员判定里列出的每个目标各一条，不多不少；不要把判定之外的人物写进 effects。',
    '- memberId、targetId 用括号里的 id 或人物全名；不要照抄“成员id/目标id”这类格式占位符。',
    '- label 只描述这次行动的直接结果（achieved/partial/not_achieved/blocked/no_change），不代表任务达成；任务达成由后续阶段单独判断。',
    '- judgments 恰好写本组每个成员一条；场景里没有行动的其他人不是成员，不要 judge 他们，也不要给他们的 judgment 写 effect。',
    '- 每个成员至少获得一条结果事实；共同发生的事实可以同时归属多个成员；facts 的 memberIds 只能填本组成员。',
    '- facts 只写这次行动的直接结果；不得写“任务完成/任务达成/目标达成/行动成功完成/成功完成/成功执行行动/任务要求/奖励”这类任务或成功结论。',
    `本组：${groupId}`,
    '成员：',
    ...memberLines,
    '场景（只用于写事实；不是本组成员，不要给场景人物写 judgment 或 effect）：',
    ...scene,
    '输出格式（示例里的 id 都是本组真实 id；没有判定目标的成员 effects 写 []）：',
    `{"judgments":[{"memberId":"${exampleMember.memberId}","label":"achieved|partial|not_achieved|blocked|no_change","reason":"一句话理由","effects":${exampleEffects}}],"facts":[{"text":"结果事实","memberIds":["${exampleMember.memberId}"]}]}`,
    '现在输出 JSON：',
  ].join('\n');
}

/** Read the answer into ids. A unique full name resolves to its id; an unknown
 * or placeholder reference is a named error so the retry prompt can fix it, and
 * is never defaulted to some entity. */
function readResultsAnswer(value: unknown, members: GroupMember[], state: WorldState): ResultsAnswer {
  const answer = asRecord(value);
  if (!Array.isArray(answer.judgments)) throw new Error('judgments must be an array');
  if (!Array.isArray(answer.facts) || answer.facts.length === 0) throw new Error('facts must be a non-empty array');
  const memberById = new Map(members.map((member) => [member.memberId, member]));
  const seen = new Set<Id>();
  const judgments: Judgment[] = [];
  const dropped: NonNullable<ResultsAnswer['dropped']> = [];
  for (const rawJudgment of answer.judgments) {
    if (!isRecord(rawJudgment)) throw new Error('judgment must be an object');
    const rawMemberId = asString(rawJudgment.memberId);
    const memberId = resolveCharacterId(state, rawMemberId);
    if (!memberId) throw new Error(referenceError(state, rawMemberId, 'character', members[0]?.memberId));
    const member = memberById.get(memberId);
    if (!Array.isArray(rawJudgment.effects)) throw new Error(`effects must be an array for ${rawMemberId || memberId}`);
    if (!member) {
      // A scene bystander is not part of the freeze. An observation with no
      // effect is noise that must not fail the turn; an effect would settle a
      // person the dice never covered, so that stays an error.
      if (rawJudgment.effects.length) {
        throw new Error(`judgment for non-member ${rawMemberId}${memberId !== rawMemberId ? ` (${memberId})` : ''}; 未冻结人物不能写 effect；本组只有 ${members.map((row) => row.memberId).join(',')}`);
      }
      dropped.push({ memberId, label: asString(rawJudgment.label), reason: 'not_a_group_member' });
      continue;
    }
    if (seen.has(memberId)) throw new Error(`duplicate judgment for ${memberId}`);
    seen.add(memberId);
    const label = asString(rawJudgment.label);
    if (!LABELS.has(label)) throw new Error(`invalid label for ${memberId}: ${label}`);
    if (typeof rawJudgment.reason !== 'string') throw new Error(`missing reason for ${memberId}`);
    const expected = new Map(member.rolls.map((roll) => [roll.targetId, roll.admitted]));
    const effectIds = new Set<Id>();
    const effects: Judgment['effects'] = [];
    for (const rawEffect of rawJudgment.effects) {
      if (!isRecord(rawEffect)) throw new Error(`effect must be an object for ${memberId}`);
      const rawTargetId = asString(rawEffect.targetId);
      const targetId = resolveCharacterId(state, rawTargetId);
      if (!targetId) {
        // A known entity that is not a rolled target is the real "undeclared
        // target" shape; only a value that names nothing is an unknown id.
        if (resolveEntityId(state, rawTargetId)) {
          throw new Error(`effect for undeclared target ${rawTargetId}; ${memberId} 的判定目标只有 ${[...expected.keys()].join(',') || '无'}`);
        }
        throw new Error(referenceError(state, rawTargetId, 'character', member.rolls[0]?.targetId));
      }
      if (!expected.has(targetId)) {
        throw new Error(`effect for undeclared target ${rawTargetId}${targetId !== rawTargetId ? ` (${targetId})` : ''}; ${memberId} 的判定目标只有 ${[...expected.keys()].join(',') || '无'}`);
      }
      if (effectIds.has(targetId)) throw new Error(`duplicate effect target ${targetId}`);
      effectIds.add(targetId);
      if (typeof rawEffect.reacted !== 'boolean') throw new Error(`reacted must be boolean for ${targetId}`);
      if (rawEffect.reacted !== expected.get(targetId)) {
        throw new Error(`reacted=${rawEffect.reacted} contradicts admitted=${expected.get(targetId)} for ${memberId}->${targetId}`);
      }
      effects.push({ targetId, reacted: rawEffect.reacted });
    }
    for (const targetId of expected.keys()) {
      if (!effectIds.has(targetId)) throw new Error(`missing effect for ${memberId}->${targetId}`);
    }
    judgments.push({ memberId, label: label as Judgment['label'], reason: rawJudgment.reason, effects });
  }
  for (const member of members) if (!seen.has(member.memberId)) throw new Error(`missing judgment for ${member.memberId}`);
  const factRecipients = new Set<Id>();
  const knownNumbers = knownDigitRuns(state, members);
  const facts: Fact[] = [];
  const sanitized: SanitizedFact[] = [];
  for (const rawFact of answer.facts) {
    if (!isRecord(rawFact)) throw new Error('fact must be an object');
    const original = asString(rawFact.text);
    if (!original) throw new Error('fact text must be non-empty');
    const cleaned = sanitizeFactText(original);
    if (!cleaned.text || !cleaned.text.replace(FACT_PUNCTUATION, '')) {
      throw new Error(`fact only asserted completion or mechanics, no action result left: ${original}`);
    }
    for (const number of cleaned.text.match(/\d+/g) ?? []) {
      if (!knownNumbers.has(number)) throw new Error(`unverified number in fact: ${number}`);
    }
    const rawRecipients = Array.isArray(rawFact.memberIds) ? rawFact.memberIds.map(asString).filter(Boolean) : [];
    if (!rawRecipients.length) throw new Error('fact must name at least one member');
    const recipientIds = rawRecipients.map((raw) => {
      const id = resolveCharacterId(state, raw);
      if (!id) throw new Error(referenceError(state, raw, 'character', members[0]?.memberId));
      if (!memberById.has(id)) throw new Error(`fact names non-member ${raw}${id !== raw ? ` (${id})` : ''}; facts 的 memberIds 只能填本组成员 ${members.map((row) => row.memberId).join(',')}`);
      return id;
    });
    if (new Set(recipientIds).size !== recipientIds.length) throw new Error('fact repeats a member');
    // A mechanics clause can take the subject with it. If the remaining result
    // is a continuation (“且未被允许反应”), prefix the recipient's display name
    // so the fact is still a natural action result.
    const mechanicsRemoved = cleaned.removed.some((label) => MECHANIC_TERMS.some((term) => term.label === label));
    if (mechanicsRemoved) {
      const recipientName = state.initial.characters[recipientIds[0]]?.name;
      if (recipientName && !cleaned.text.includes(String(recipientName))) {
        const continuation = cleaned.text.replace(/^(?:且|并且|并|但|却|而)/u, '');
        cleaned.text = `${recipientName}${continuation}`;
      }
    }
    // A stripped fact that is only the recipient's display name (95dc's
    // “路明非成功完成…完成任务”) is still a completion claim, not an action.
    const nameOnly = cleaned.text.replace(FACT_PUNCTUATION, '');
    if (recipientIds.some((recipient) => {
      const name = state.initial.characters[recipient]?.name;
      return Boolean(name) && nameOnly === String(name).replace(FACT_PUNCTUATION, '');
    })) throw new Error(`fact only asserted completion or mechanics, no action result left: ${original}`);
    for (const recipient of recipientIds) factRecipients.add(recipient);
    facts.push({ text: cleaned.text, memberIds: recipientIds });
    if (cleaned.removed.length) sanitized.push({ memberIds: recipientIds, original, text: cleaned.text, removed: cleaned.removed });
  }
  for (const member of members) if (!factRecipients.has(member.memberId)) throw new Error(`no fact attributed to ${member.memberId}`);
  return {
    judgments, facts, dropped,
    ...(sanitized.length ? { sanitized } : {}),
  };
}

const FACT_PUNCTUATION = /[\s，、；。！？.,;!?]/gu;

/** Mechanics vocabulary is not an action result. The d101 fact reached the
 * narration draft as “诺诺：未，因为路明非的骰点且无法反应。”. A clause that
 * carries dice/check/boolean vocabulary is removed; if the remaining result
 * has no subject, the recipient's display name is prefixed. A fact that leaves
 * no action result aborts instead of narrating mechanics. */
const MECHANIC_TERMS: { pattern: RegExp; label: string }[] = [
  { pattern: /骰点/g, label: '骰点' },
  { pattern: /骰子/g, label: '骰子' },
  { pattern: /判定/g, label: '判定' },
  { pattern: /(?:资格|判定)\s*为\s*(?:true|false)/g, label: '资格/判定布尔值' },
  { pattern: /为\s*(?:true|false)/g, label: '布尔值' },
];

const COMPLETION_CLAIMS: { pattern: RegExp; label: string }[] = [
  { pattern: /行动成功完成/g, label: '行动成功完成' },
  { pattern: /成功完成行动/g, label: '成功完成行动' },
  { pattern: /成功执行行动/g, label: '成功执行行动' },
  { pattern: /成功完成任务/g, label: '成功完成任务' },
  // The 95dc model wrote the task goal as a verb-object claim:
  // “成功完成自己的参赛选择并完成任务”. Strip the whole task clause, not
  // just the contiguous 任务完成 string.
  { pattern: /(?<!未)(?:成功)?完成(?:了)?[^，。；.,;!?]*(?:任务|目标|参赛选择)[^，。；.,;!?]*/g, label: '完成任务' },
  { pattern: /完成了任务/g, label: '完成了任务' },
  { pattern: /任务完成/g, label: '任务完成' },
  { pattern: /任务达成/g, label: '任务达成' },
  { pattern: /目标达成/g, label: '目标达成' },
  { pattern: /未达成目标/g, label: '未达成目标' },
  { pattern: /未完成任务/g, label: '未完成任务' },
  { pattern: /任务未完成/g, label: '任务未完成' },
  { pattern: /未能完成/g, label: '未能完成' },
  { pattern: /未达成/g, label: '未达成' },
  { pattern: /完成目标/g, label: '完成目标' },
  { pattern: /目标完成/g, label: '目标完成' },
  { pattern: /符合规则要求/g, label: '符合规则要求' },
  { pattern: /资格为\s*(?:true|false)/g, label: '资格为布尔值' },
  { pattern: /资格\s*[=:：]\s*(?:true|false)/g, label: '资格为布尔值' },
  { pattern: /成功完成/g, label: '成功完成' },
];

/** Completion/task claims are not action facts. Keep the observable result and
 * drop only the claim, so the later composer cannot say a pending task finished. */
function stripMechanicClauses(text: string): { text: string; removed: string[] } {
  const removed: string[] = [];
  let out = '';
  const clauses = text.match(/[^，。；！？.,;!?]+[，。；！？.,;!?]?/gu) ?? [];
  for (const clause of clauses) {
    const labels = MECHANIC_TERMS.filter(({ pattern }) => {
      pattern.lastIndex = 0;
      return pattern.test(clause);
    }).map(({ label }) => label);
    if (labels.length) {
      removed.push(...labels);
      continue;
    }
    out += clause;
  }
  return { text: out, removed };
}

function sanitizeFactText(text: string): { text: string; removed: string[] } {
  const mechanics = stripMechanicClauses(text);
  let out = mechanics.text;
  const removed: string[] = [...mechanics.removed];
  for (const { pattern, label } of COMPLETION_CLAIMS) {
    const matches = out.match(pattern);
    if (!matches) continue;
    removed.push(...matches.map(() => label));
    out = out.replace(pattern, '');
  }
  out = out
    .replace(/，\s*(?=[，。；！？.,;!?]|$)/g, '')
    .replace(/、\s*(?=[，。；！？.,;!?]|$)/g, '')
    .replace(/；\s*(?=[，。；！？.,;!?]|$)/g, '')
    .replace(/[，、；]\s*(?:因此|所以|因而)\s*([。；！？.,;!?]?)$/u, '$1')
    .replace(/^[，、；\s]+/, '')
    .trim();
  return { text: out, removed };
}

function normalizeResults(answer: ResultsAnswer, members: GroupMember[]): Record<Id, string> {
  return Object.fromEntries(members.map((member) => {
    const texts = answer.facts
      .filter((fact) => fact.memberIds.includes(member.memberId))
      .map((fact) => fact.text.trim())
      .filter(Boolean);
    return [member.memberId, texts.join('\n')];
  }));
}

function knownDigitRuns(state: WorldState, members: GroupMember[]): Set<number | string> {
  const known = new Set<string>();
  const add = (value: string | number | null | undefined) => {
    if (value == null) return;
    for (const run of String(value).match(/\d+/g) ?? []) known.add(run);
  };
  add(state.time.dateTime);
  for (const character of Object.values(state.characters)) add(character.sanity);
  for (const member of members) {
    add(member.actionText);
    for (const roll of member.rolls) add(roll.result);
  }
  for (const location of Object.values(state.initial.locations)) { add(location.name); add(location.initialAppearance); }
  for (const item of Object.values(state.initial.items)) { add(item.name); add(item.initialAppearance); }
  for (const character of Object.values(state.initial.characters)) {
    add(character.name);
    add(character.initialAppearance);
    add(character.initialPersonality);
    for (const task of Object.values(character.tasks)) add(task.goal);
  }
  return known;
}

function makeEvidence(
  key: Id,
  calls: ModelCallEvidence[],
  fallback: boolean,
  error: string | undefined,
  detail: Record<string, unknown>,
): SettlementEvidence {
  return {
    task: 'results',
    key,
    raw: joinedRaw(calls),
    ms: joinedMs(calls),
    fallback,
    error,
    calls,
    detail: toJson(detail),
  };
}

function failure(key: Id, error: string, started: number): SettlementOutcome<Record<Id, string>> {
  return {
    value: null,
    raw: '',
    ms: performance.now() - started,
    fallback: false,
    error,
    evidence: {
      task: 'results',
      key,
      raw: '',
      ms: performance.now() - started,
      fallback: false,
      error,
      calls: [],
      detail: toJson({ reason: error }),
    },
  };
}
