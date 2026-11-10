/** Common-group results (R07/R08): every frozen action, every actual roll
 * receipt, one joint settlement, facts attributed to the members they belong
 * to. Denied/already-acted rolls are accepted as observation; they never
 * become a reaction and never make an action succeed. */
import type { Id, Json, WorldState } from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import { callJson, JsonCallError, joinedMs, joinedRaw } from './engine-call';
import type { ModelCallEvidence, SettlementEvidence, SettlementOptions, SettlementOutcome } from './types';
import {
  asInteger, asRecord, asString, errorText, isRecord, toJson,
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

interface ResultsAnswer {
  judgments: Judgment[];
  facts: Fact[];
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
      validate: (value) => validateResultsAnswer(value, members, workingState),
    });
    calls = answer.calls;
    const value = normalizeResults(answer.value as ResultsAnswer, members);
    const evidence = makeEvidence(key, answer.calls, false, undefined, {
      groupId,
      memberIds: members.map((member) => member.memberId),
      rollReceiptCount: members.reduce((sum, member) => sum + member.rolls.length, 0),
      factCount: (answer.value as ResultsAnswer).facts.length,
      memberFactCoverage: members.map((member) => ({
        memberId: member.memberId,
        factCount: (answer.value as ResultsAnswer).facts.filter((fact) => fact.memberIds.includes(member.memberId)).length,
      })),
      labels: (answer.value as ResultsAnswer).judgments.map((judgment) => `${judgment.memberId}:${judgment.label}`),
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
    const fallbackText = '本组结算未能确认新的结果。';
    const value: Record<Id, string> = Object.fromEntries(members.map((member) => [member.memberId, fallbackText]));
    const evidence = makeEvidence(key, calls, true, message, {
      groupId,
      memberIds: members.map((member) => member.memberId),
      fallbackText,
      reason: 'conservative_no_change_after_model_failure',
    });
    const outcome: SettlementOutcome<Record<Id, string>> = {
      value,
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
  return [
    '你是中文跑团游戏的共同结算器。只输出 JSON，不要解释。',
    '下面是一个已经冻结的结算组：行动已经确认，骰点已经落定。请统一结算全组行动，写清实际发生了什么。',
    '规则：',
    '- 只能使用下面出现的人物、地点、物品；不得新增人物、地点、物品、往事、线索或任务。',
    '- 一个成员的行动可以成功、部分成功、失败或被制止；行动被接纳不等于目标达成。',
    '- 骰点 准入=false 表示该目标这次没有被迫反应；effects 中该 target 的 reacted 必须为 false。已行动人物不会再次反应。',
    '- label 只描述这次行动的直接结果（achieved/partial/not_achieved/blocked/no_change），不代表任务达成；任务达成由后续阶段单独判断。',
    '- 每个成员至少获得一条结果事实；共同发生的事实可以同时归属多个成员。',
    `本组：${groupId}`,
    '成员：',
    ...memberLines,
    '场景：',
    ...scene,
    '输出格式：',
    '{"judgments":[{"memberId":"成员id","label":"achieved|partial|not_achieved|blocked|no_change","reason":"一句话理由","effects":[{"targetId":"目标id","reacted":true或false}]}],"facts":[{"text":"结果事实","memberIds":["成员id"]}]}',
    '现在输出 JSON：',
  ].join('\n');
}

function validateResultsAnswer(value: unknown, members: GroupMember[], state: WorldState): void {
  const answer = asRecord(value);
  if (!Array.isArray(answer.judgments)) throw new Error('judgments must be an array');
  if (!Array.isArray(answer.facts) || answer.facts.length === 0) throw new Error('facts must be a non-empty array');
  const memberById = new Map(members.map((member) => [member.memberId, member]));
  const seen = new Set<Id>();
  for (const rawJudgment of answer.judgments) {
    if (!isRecord(rawJudgment)) throw new Error('judgment must be an object');
    const memberId = asString(rawJudgment.memberId);
    const member = memberById.get(memberId);
    if (!member) throw new Error(`judgment for unknown member ${memberId || '?'}`);
    if (seen.has(memberId)) throw new Error(`duplicate judgment for ${memberId}`);
    seen.add(memberId);
    const label = asString(rawJudgment.label);
    if (!LABELS.has(label)) throw new Error(`invalid label for ${memberId}: ${label}`);
    if (typeof rawJudgment.reason !== 'string') throw new Error(`missing reason for ${memberId}`);
    if (!Array.isArray(rawJudgment.effects)) throw new Error(`effects must be an array for ${memberId}`);
    const expected = new Map(member.rolls.map((roll) => [roll.targetId, roll.admitted]));
    const effectIds = new Set<Id>();
    for (const rawEffect of rawJudgment.effects) {
      if (!isRecord(rawEffect)) throw new Error(`effect must be an object for ${memberId}`);
      const targetId = asString(rawEffect.targetId);
      // A small model sometimes lists an item or a bystander as an "effect"
      // target. Those are not roll targets, so they cannot gate a reaction:
      // drop the line instead of throwing away the whole joint settlement.
      if (!expected.has(targetId)) continue;
      if (effectIds.has(targetId)) throw new Error(`duplicate effect target ${targetId}`);
      effectIds.add(targetId);
      if (typeof rawEffect.reacted !== 'boolean') throw new Error(`reacted must be boolean for ${targetId}`);
      if (rawEffect.reacted !== expected.get(targetId)) {
        throw new Error(`reacted=${rawEffect.reacted} contradicts admitted=${expected.get(targetId)} for ${memberId}->${targetId}`);
      }
    }
    for (const targetId of expected.keys()) {
      // An un-admitted roll needs no reaction; a missing line already means
      // "no reaction" and cannot contradict the dice.
      if (expected.get(targetId) === true && !effectIds.has(targetId)) {
        throw new Error(`missing effect for admitted target ${memberId}->${targetId}`);
      }
    }
  }
  for (const member of members) if (!seen.has(member.memberId)) throw new Error(`missing judgment for ${member.memberId}`);
  const factRecipients = new Set<Id>();
  const knownNumbers = knownDigitRuns(state, members);
  for (const rawFact of answer.facts) {
    if (!isRecord(rawFact)) throw new Error('fact must be an object');
    const text = asString(rawFact.text);
    if (!text) throw new Error('fact text must be non-empty');
    for (const number of text.match(/\d+/g) ?? []) {
      if (!knownNumbers.has(number)) throw new Error(`unverified number in fact: ${number}`);
    }
    const recipientIds = Array.isArray(rawFact.memberIds) ? rawFact.memberIds.map(asString).filter(Boolean) : [];
    if (!recipientIds.length) throw new Error('fact must name at least one member');
    if (new Set(recipientIds).size !== recipientIds.length) throw new Error('fact repeats a member');
    for (const recipient of recipientIds) {
      if (!memberById.has(recipient)) throw new Error(`fact names unknown member ${recipient}`);
      factRecipients.add(recipient);
    }
  }
  for (const member of members) if (!factRecipients.has(member.memberId)) throw new Error(`no fact attributed to ${member.memberId}`);
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
