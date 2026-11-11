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

/** Results decide what the frozen action did, not whether a task goal is
 * already true. Pending goals in the scene line prime the model to write
 * “成功完成…任务” as a fact (d101); keep the scene but drop that待办 suffix. */
function describeResultCharacter(state: WorldState, id: Id): string {
  return describeCharacter(state, id, false).replace(/；待办=.*$/u, '');
}

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

/** What the settled result actually was. The four directions are the product's
 * vocabulary for a player-visible outcome; 「未受影响」 covers a legitimate
 * no-change result and is not a mechanic word. */
export type ResultOutcome = 'completed' | 'failed' | 'blocked' | 'unaffected';
export const RESULT_OUTCOMES: ResultOutcome[] = ['completed', 'failed', 'blocked', 'unaffected'];

interface Fact {
  text: string;
  memberIds: Id[];
  /** Executor of this result. Required by the product contract: a fact must say
   * who acted, not only who received the sentence. */
  actorId: Id;
  /** Recipient/target when the action had one. */
  targetId?: Id;
  /** The action actually performed, in the model's own words (never the pending
   * task goal, never the player's declared text copied as a success). */
  action?: string;
  outcome: ResultOutcome;
  /** Whether actor/outcome came from the answer or were derived from the
   * member list and judgement label. Kept so the page can show a derived row. */
  actorSource: 'model' | 'derived';
  outcomeSource: 'model' | 'derived';
  targetSource?: 'model' | 'derived';
  /** The model omitted this actor's judgement row, so a derived outcome is not a
   * claim about direction: 02/06 must treat `text` as the only result content
   * for such a fact. */
  implicit?: true;
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
  /** Repeated rows for a member already judged. The first row stands; the
   * rest are evidence that the model repeated itself, never a failed turn. */
  duplicateJudgments?: { memberId: Id; label: string; reason: string }[];
  /** Extra judgments for people outside the frozen group. They may describe
   * what the model saw, but they never settle a non-member; they are kept in
   * evidence and dropped from the committed result. */
  dropped?: { memberId: Id; label: string; reason: 'not_a_group_member' }[];
  /** Facts dropped because they explain another character's action for a
   * member whose own action provably did not happen (all rolls denied). */
  droppedFacts?: { memberIds: Id[]; original: string; reason: 'explains_another_character' | 'inactive_no_result' | 'duplicates_another_member' | 'no_result_text' }[];
  /** Members whose judgement row the model omitted and which had no declared
   * roll target; they are recorded as no_change and must be visible in evidence. */
  implicitJudgments?: Id[];
  /** A written outcome that disagreed with the judgement or the sentence and was
   * replaced by the judgement-derived direction. */
  outcomeAdjusted?: { actorId: Id; original: string; written: ResultOutcome; derived: ResultOutcome; why: string }[];
  /** An effects row that contradicted the frozen admission; the frozen value
   * was written instead of re-asking the group. */
  effectsAdjusted?: { memberId: Id; targetId: Id; written: boolean; frozen: boolean }[];
  /** An item possessive that named the wrong character; the frozen owner was
   * written instead so the observation survives. */
  ownershipAdjusted?: { original: string; from: string; to: string; item: string }[];
  /** The player's own first-person sentence rewritten to the protagonist's
   * name outside dialogue. */
  firstPersonAdjusted?: { original: string; text: string }[];
  /** Members with no result sentence after the last repair; the point settles
   * without inventing one. */
  missingFactMembers?: Id[];
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
        required: ['memberId', 'label', 'reason'],
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
          // Structured result fields (04 contract): who acted, on whom, what
          // was actually done, and which of the four outcome directions holds.
          actorId: { type: 'string' },
          targetId: { type: 'string' },
          action: { type: 'string' },
          outcome: { enum: [...RESULT_OUTCOMES] },
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
  // The last attempt drops a fact that has no visible result instead of failing
  // the point: old runs (95dc, 415c, d101, a178) answered only
  // 路明非成功完成自己的参赛选择… and the old product accepted that as a result.
  // Today it is repaired once (the repair often writes the real walk/read), and
  // if the repair repeats the claim the fact is dropped and recorded so the
  // turn still settles instead of ending with 世界没有完成.
  let attempts = 0;
  const lenient = () => attempts >= 3;
  try {
    const answer = await callJson(engine, prompt, {
      maxTokens: options.maxTokens?.results ?? 420,
      temperature: options.temperature ?? 0,
      timeoutMs: options.timeoutMs,
      maxPromptChars: options.maxPromptChars,
      // A question group needs two complete member results; 9623's turn 2 wrote
      // one member per attempt (lu then nono) and died on the second. A third
      // attempt costs ~9 s on a failing point but saves the whole turn (73 s,
      // no prose). The repair now names the missing facts, not just the row.
      maxAttempts: 3,
      jsonSchema: RESULTS_SCHEMA,
      validate: (value) => {
        attempts += 1;
        readResultsAnswer(value, members, workingState, { dropEmptyResults: lenient() });
      },
      // A retry has to name the frozen members: the 3turn 9623 repair answered
      // nono only while the group was lu+nono, so «missing judgment for lu» alone
      // did not stop it from omitting the player again.
      feedback: `本组只有 ${members.map((member) => `${workingState.initial.characters[member.memberId]?.name ?? member.memberId}(${member.memberId})`).join('、')}；judgments 必须每人一条，且 memberId 只能是这些 id；facts 每人至少一条；不要给场景里的其他人写 judgment。`,
    });
    calls = answer.calls;
    // The accepted answer settled under the same rule the last attempt used.
    const parsedAnswer = readResultsAnswer(answer.value, members, workingState, { dropEmptyResults: lenient() });
    const value = normalizeResults(parsedAnswer, members);
    const evidence = makeEvidence(key, answer.calls, false, undefined, {
      groupId,
      memberIds: members.map((member) => member.memberId),
      rollReceiptCount: members.reduce((sum, member) => sum + member.rolls.length, 0),
      factCount: parsedAnswer.facts.length,
      // Structured result records for the narration composer and the reviewer:
      // executor, recipient, performed action and outcome direction.
      facts: parsedAnswer.facts,
      sanitizedFacts: parsedAnswer.sanitized ?? [],
      memberFactCoverage: members.map((member) => ({
        memberId: member.memberId,
        factCount: parsedAnswer.facts.filter((fact) => fact.memberIds.includes(member.memberId)).length,
      })),
      labels: parsedAnswer.judgments.map((judgment) => `${judgment.memberId}:${judgment.label}`),
      duplicateJudgments: parsedAnswer.duplicateJudgments ?? [],
      droppedNonMemberJudgments: parsedAnswer.dropped ?? [],
      droppedFacts: parsedAnswer.droppedFacts ?? [],
      implicitJudgments: parsedAnswer.implicitJudgments ?? [],
      outcomeAdjusted: parsedAnswer.outcomeAdjusted ?? [],
      effectsAdjusted: parsedAnswer.effectsAdjusted ?? [],
      ownershipAdjusted: parsedAnswer.ownershipAdjusted ?? [],
      firstPersonAdjusted: parsedAnswer.firstPersonAdjusted ?? [],
      missingFactMembers: parsedAnswer.missingFactMembers ?? [],
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
    // The effects row is fully determined by the frozen admission: printing it
    // as a value to copy removes the 35ad failure where the model wrote
    // reacted=true for an admitted=false target and the whole group was re-asked
    // (23.6 s for nothing).
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
    .map((id) => state.characters[id] ? describeResultCharacter(state, id) : describeItem(state, id));
  // Show one row per member, not one row in total: with a single-row example a
  // 2-member dialogue group (9623 turn 2, lu+nono) answered one member's row per
  // attempt, twice in a row.
  const exampleRows = members.slice(0, 2).map((member) => (
    `{"memberId":"${member.memberId}","label":"achieved|partial|not_achieved|blocked|no_change","reason":"一句话理由"}`
  ));
  const exampleFacts = members.slice(0, 4)
    .map((member) => `{"text":"${state.initial.characters[member.memberId]?.name ?? member.memberId}做了什么/看到什么","memberIds":["${member.memberId}"],"actorId":"${member.memberId}","outcome":"completed"}`);
  return [
    '你是中文跑团游戏的共同结算器。只输出 JSON，不要解释。',
    '下面是一个已经冻结的结算组：行动已经确认，骰点已经落定。请统一结算全组行动，写清实际发生了什么。',
    '规则：',
    '- 只能使用下面出现的人物、地点、物品；不得新增人物、地点、物品、往事、线索或任务。',
    '- 一个成员的行动可以成功、部分成功、失败或被制止；行动被接纳不等于目标达成。',
    '- 骰点 准入=false 表示该目标这次没有被迫反应；已行动人物不会再次反应。不要写 effects：谁反应了由程序按冻结的准入值填写。',
    '- memberId、targetId 用括号里的 id 或人物全名；不要照抄“成员id/目标id”这类格式占位符。',
    '- label 只描述这次行动的直接结果（achieved/partial/not_achieved/blocked/no_change），不代表任务达成；任务达成由后续阶段单独判断。',
    '- judgments 恰好写本组每个成员一条；场景里没有行动的其他人不是成员，不要 judge 他们，也不要给他们的 judgment 写 effect。',
    '- reason 一句话，20 字以内；facts 每人一句，短句即可。',
    '- facts 每个成员一条自己的行动结果（共同的可以归多人），memberIds 只能填本组成员；不写其他人物的行动，不抄判定理由。',
    '- 不写“任务完成/任务达成/目标达成/成功完成/奖励”这类结论；failed/blocked 照实写，保留“没有/未/被阻止”。',
    '- 例：行动是“沿着服务巷走，看清墙上的演习规则牌”，事实写“路明非走到服务巷，看见墙上的规则牌”；不要写“完成参赛选择/任务”。',
    '- 行动里有走/进入就先写走到哪，有查看就再写看到什么：73f3 只写了看懂规则牌，走路从结果里丢了。',
    '- 例：行动是“我向诺诺问现在的局势”，事实写“路明非问诺诺红蓝两方现在在哪，诺诺摇头说不知道”；不要写“骰点未获取，因此未能达成目标”。',
    '- fact 带字段：actorId=执行者（本组成员）、targetId=受事（可省）、action=实际动作、outcome=completed/failed/blocked/unaffected。',
    '- failed/blocked 照实写，保留“没有/未/被阻止”；任务目标、骰点资格、判定理由都不是事实。',
    `本组：${groupId}`,
    '成员：',
    ...memberLines,
    '场景（只用于写事实；不是本组成员，不要给场景人物写 judgment 或 effect）：',
    ...scene,
    '输出格式（示例里的 id 都是本组真实 id；judgments 和 facts 都要每人一条）：',
    `{"judgments":[${exampleRows.join(',')}],"facts":[${exampleFacts.join(',')}]}`,
    '现在输出 JSON：',
  ].join('\n');
}

/** Character ids the text actually names. Used to keep a results fact on this
 * group's own action: a fact that names nobody (an empty room, a door) is
 * allowed, but a fact whose only subject is a character outside the group is
 * the judgement's explanation of that character's action, not this group's
 * result. */
/** Replace 我/咱 outside Chinese quotation marks. Speech inside quotes is the
 * character's own words and must not be rewritten. */
function replaceFirstPersonOutsideQuotes(text: string, name: string): string {
  let out = '';
  let quoted = 0;
  for (const char of text) {
    if (char === '“' || char === '‘' || char === '「') quoted += 1;
    if ((char === '”' || char === '’' || char === '」') && quoted > 0) quoted -= 1;
    out += quoted === 0 && (char === '我' || char === '咱') ? name : char;
  }
  return out;
}

function mentionedCharacterIds(state: WorldState, text: string): Id[] {
  const found: Id[] = [];
  for (const id of Object.keys(state.initial.characters).sort()) {
    const name = state.initial.characters[id]?.name;
    if (!name) continue;
    if (text.includes(String(name)) || (id.length > 3 && text.includes(id))) found.push(id);
  }
  return found;
}

/** Read the answer into ids. A unique full name resolves to its id; an unknown
 * or placeholder reference is a named error so the retry prompt can fix it, and
 * is never defaulted to some entity. */
function readResultsAnswer(
  value: unknown,
  members: GroupMember[],
  state: WorldState,
  options: { dropEmptyResults?: boolean } = {},
): ResultsAnswer {
  const answer = asRecord(value);
  if (!Array.isArray(answer.judgments)) throw new Error('judgments must be an array');
  if (!Array.isArray(answer.facts) || answer.facts.length === 0) throw new Error('facts must be a non-empty array');
  const memberById = new Map(members.map((member) => [member.memberId, member]));
  const seen = new Set<Id>();
  const judgments: Judgment[] = [];
  const duplicateJudgments: NonNullable<ResultsAnswer['duplicateJudgments']> = [];
  const dropped: NonNullable<ResultsAnswer['dropped']> = [];
  const effectsAdjusted: NonNullable<ResultsAnswer['effectsAdjusted']> = [];
  for (const rawJudgment of answer.judgments) {
    if (!isRecord(rawJudgment)) throw new Error('judgment must be an object');
    const rawMemberId = asString(rawJudgment.memberId);
    const memberId = resolveCharacterId(state, rawMemberId);
    if (!memberId) throw new Error(referenceError(state, rawMemberId, 'character', members[0]?.memberId));
    const member = memberById.get(memberId);
    if (rawJudgment.effects != null && !Array.isArray(rawJudgment.effects)) {
      throw new Error(`effects must be an array for ${rawMemberId || memberId}`);
    }
    if (!member) {
      // A scene bystander is not part of the freeze. An observation with no
      // effect is noise that must not fail the turn; an effect would settle a
      // person the dice never covered, so that stays an error.
      if (Array.isArray(rawJudgment.effects) && rawJudgment.effects.length) {
        throw new Error(`judgment for non-member ${rawMemberId}${memberId !== rawMemberId ? ` (${memberId})` : ''}; 未冻结人物不能写 effect；本组只有 ${members.map((row) => row.memberId).join(',')}`);
      }
      dropped.push({ memberId, label: asString(rawJudgment.label), reason: 'not_a_group_member' });
      continue;
    }
    if (seen.has(memberId)) {
      // 10turn turn 5: a single-member group answered with three rows for the
      // same player (no_change / partial / not_achieved) on all three attempts
      // and the turn died on «duplicate judgment for lu». Repeating a member is
      // a format slip, not an impossible world: the first row is the model's
      // primary judgement, later rows are kept as evidence and ignored.
      duplicateJudgments.push({
        memberId,
        label: asString(rawJudgment.label),
        reason: typeof rawJudgment.reason === 'string' ? rawJudgment.reason : '',
      });
      continue;
    }
    seen.add(memberId);
    const label = asString(rawJudgment.label);
    if (!LABELS.has(label)) throw new Error(`invalid label for ${memberId}: ${label}`);
    if (typeof rawJudgment.reason !== 'string') throw new Error(`missing reason for ${memberId}`);
    // Who reacted is frozen, not judged: the reaction lane already decided it
    // from the rolls, and nothing downstream reads effects[].reacted. The model
    // no longer writes effects (06-to-04-effects-actor-row: asking the actor's
    // row to describe the reaction it caused is what produced
    // reacted=true for an admitted=false target twice). A written row is kept
    // only as evidence of what the model said.
    const effects: Judgment['effects'] = member.rolls.map((roll) => ({
      targetId: roll.targetId,
      reacted: roll.admitted,
    }));
    const frozenByTarget = new Map(effects.map((row) => [row.targetId, row.reacted]));
    if (Array.isArray(rawJudgment.effects)) {
      for (const rawEffect of rawJudgment.effects) {
        if (!isRecord(rawEffect)) continue;
        const rawTarget = asString(rawEffect.targetId);
        const targetId = rawTarget ? resolveCharacterId(state, rawTarget) : null;
        if (!targetId || !frozenByTarget.has(targetId)) {
          // A target the freeze never covered is still worth reporting: it means
          // the model settled somebody the dice did not.
          throw new Error(`effect for undeclared target ${rawTarget ?? ''}; ${memberId} 的判定目标只有 ${[...frozenByTarget.keys()].join(',') || '无'}`);
        }
        if (typeof rawEffect.reacted === 'boolean' && rawEffect.reacted !== frozenByTarget.get(targetId)) {
          effectsAdjusted.push({ memberId, targetId, written: rawEffect.reacted, frozen: frozenByTarget.get(targetId) === true });
        }
      }
    }
    judgments.push({ memberId, label: label as Judgment['label'], reason: rawJudgment.reason, effects });
  }
  // A judgement row is evidence, not state: the six stages read facts, never
  // labels, and nothing downstream consumes effects[].reacted (the reaction lane
  // already decided from the frozen rolls). 3turn 9623's turn 2 (a lu+nono
  // question group) failed twice in a row because the model wrote one row per
  // attempt; the missing row is now recorded and the only hard requirement left
  // is that every member's result is described in facts.
  const implicit: Id[] = [];
  for (const member of members) {
    if (seen.has(member.memberId)) continue;
    // effects follow the same rule the validator enforces on a written row:
    // a target reacts exactly when its roll was admitted.
    const effects = member.rolls.map((roll) => ({ targetId: roll.targetId, reacted: roll.admitted }));
    judgments.push({
      memberId: member.memberId,
      label: 'no_change',
      reason: '模型漏写这一行；按无变化记录，effects 由已冻结的准入结果补齐',
      effects,
    });
    implicit.push(member.memberId);
  }
  // A member whose action provably did not happen — the group judged it
  // not_achieved and every one of its rolls was denied — has no result to
  // narrate. Requiring a fact for it made the model copy its judgement reason
  // into facts (736a/9623: 路明非未被掀开袖口，未看到规则牌…), which then
  // contradicted the player group's settled walk/read.
  const inactive = new Set<Id>(judgments
    .filter((judgment) => judgment.label === 'not_achieved'
      && memberById.get(judgment.memberId)!.rolls.length > 0
      && memberById.get(judgment.memberId)!.rolls.every((roll) => !roll.admitted))
    .map((judgment) => judgment.memberId));
  const factRecipients = new Set<Id>();
  // Resolve a fact's member list before its text is judged: an inactive member's
  // mechanics-only line is dropped, a live member's line is repaired.
  const recipientsFor = (rawFact: unknown): Id[] => {
    const raw = isRecord(rawFact) && Array.isArray(rawFact.memberIds) ? rawFact.memberIds.map(asString).filter(Boolean) : [];
    const ids: Id[] = [];
    for (const value of raw) {
      const id = resolveCharacterId(state, value);
      if (id && memberById.has(id) && !ids.includes(id)) ids.push(id);
    }
    return ids;
  };
  const knownNumbers = knownDigitRuns(state, members);
  const facts: Fact[] = [];
  const sanitized: SanitizedFact[] = [];
  const adjustments: NonNullable<ResultsAnswer['outcomeAdjusted']> = [];
  const ownershipAdjusted: NonNullable<ResultsAnswer['ownershipAdjusted']> = [];
  const firstPersonAdjusted: NonNullable<ResultsAnswer['firstPersonAdjusted']> = [];
  const missingFactMembers: Id[] = [];
  const droppedFacts: NonNullable<ResultsAnswer['droppedFacts']> = [];
  /** Members whose only answer was dropped (a wrapper duplicate or an empty
   * result), so the per-member “must have a fact” check does not turn a
   * recorded drop into an abort. */
  const coveredByDrop = new Set<Id>();
  const actionHint = members
    .map((member) => `${state.initial.characters[member.memberId]?.name ?? member.memberId}：${member.actionText}`)
    .join('；');
  for (const rawFact of answer.facts) {
    if (!isRecord(rawFact)) throw new Error('fact must be an object');
    const original = asString(rawFact.text);
    if (!original) throw new Error('fact text must be non-empty');
    // 10turn turn 4 (run 2026-11-11T0928-94ef): the accepted group_72 answer
    // copied the prompt's example text verbatim — «秦越做了什么/看到什么» — and
    // the six stages settled on it. A template is not a result.
    if (isExampleFactText(original)) {
      if (!options.dropEmptyResults) {
        throw new Error(`fact is the format example, not a result: ${original}。只写这次行动的直接可见结果（${actionHint}）。`);
      }
      const droppedIds = recipientsFor(rawFact);
      droppedFacts.push({ memberIds: droppedIds, original, reason: 'no_result_text' });
      for (const id of droppedIds) coveredByDrop.add(id);
      continue;
    }
    const cleaned = sanitizeFactText(original);
    if (!cleaned.text || !cleaned.text.replace(FACT_PUNCTUATION, '')) {
      // A member who provably did nothing (all rolls denied, judged
      // not_achieved) has no observable result to narrate: 09-product-03turn-73f3's
      // reaction group answered 路明非未被判定为反应 for nono and the whole turn
      // died on a mechanics-only fact. Drop it and let the point settle with no
      // fact for that member instead of inventing one.
      if (recipientsFor(rawFact).every((id) => inactive.has(id))) {
        droppedFacts.push({ memberIds: recipientsFor(rawFact), original, reason: 'inactive_no_result' });
        continue;
      }
      if (!options.dropEmptyResults) {
        throw new Error(`fact only asserted completion or mechanics, no action result left: ${original}。只写这次行动的直接可见结果（${actionHint}），不要写任务、选择、规则或奖励结论。`);
      }
      const droppedIds = recipientsFor(rawFact);
      droppedFacts.push({ memberIds: droppedIds, original, reason: 'no_result_text' });
      for (const id of droppedIds) coveredByDrop.add(id);
      continue;
    }
    for (const number of cleaned.text.match(/\d+/g) ?? []) {
      if (!knownNumbers.has(number)) throw new Error(`unverified number in fact: ${number}`);
    }
    // Structured fields: actor is the executor, target the recipient, outcome
    // the direction. An old answer without them is still accepted (derived),
    // but a field the model did write must be right.
    const rawActor = asString(rawFact.actorId);
    const rawTarget = asString(rawFact.targetId);
    const rawAction = asString(rawFact.action);
    const rawOutcome = asString(rawFact.outcome);
    if (rawOutcome && !RESULT_OUTCOMES.includes(rawOutcome as ResultOutcome)) {
      throw new Error(`unknown outcome ${rawOutcome}; outcome 只能是 ${RESULT_OUTCOMES.join('/')}`);
    }
    if (rawAction && rawAction.replace(FACT_PUNCTUATION, '').length > 60) {
      throw new Error(`action too long for a result: ${rawAction}`);
    }
    if (rawAction) {
      for (const { pattern, label } of COMPLETION_CLAIMS) {
        pattern.lastIndex = 0;
        if (pattern.test(rawAction)) throw new Error(`action is a task/goal claim (${label}), not what the actor did: ${rawAction}`);
      }
      // A task word alone is not a claim (“拿起任务单” is an action); only the
      // completion/direction wording makes it a goal restatement.
      if (/(?:完成|达成|执行|符合)[^，。；.,;!?]*(?:任务|目标|要求)/u.test(rawAction)
        || /(?:任务|目标)[^，。；.,;!?]*(?:完成|达成)/u.test(rawAction)) {
        throw new Error(`action must be the performed action, not a task or goal: ${rawAction}`);
      }
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
    // The fact must be this group's own action result. 736a's reaction group
    // answered with 路明非未被掀开袖口，未看到规则牌… — the judgement's
    // explanation of 路明非, who the other group already settled as walking in
    // and reading the sign. Committing it would hand the narrator a fact that
    // contradicts the point and no result for the reacting member.
    let mentioned = mentionedCharacterIds(state, cleaned.text);
    // “路明非的红色识别带” when the band belongs to 诺诺 is an item-ownership
    // flip: d531 turn 2 wrote exactly that. Only an explicit possessive whose
    // item resolves in the frozen state is checked, so ordinary prose is not
    // touched.
    if (mentioned.length) {
      for (const ownerId of mentioned) {
        const ownerName = state.initial.characters[ownerId]?.name;
        if (!ownerName) continue;
        const items = Object.values(state.initial.items);
        // Prefer the item whose full name is in the sentence: 诺诺的红色识别带 is
        // the precise band, while several items share the bare 红色识别带.
        const full = items.filter((item) => {
          const name = String(item.name ?? '');
          return name.startsWith(`${ownerName}的`) && cleaned.text.includes(name);
        });
        const candidates = full.length
          ? full.map((item) => ({ item, itemName: String(item.name ?? '') }))
          // A wrong possessive (路明非的红色识别带 when the band is 诺诺's) has no
          // full-name match. Only a bare name whose holder is another mentioned
          // character is the band the sentence means; without that it would
          // match 凯撒的红色识别带 as well (the 1e59 replay caught this).
          : items
            .map((item) => ({ item, bare: String(item.name ?? '').replace(/^[^的]{1,6}的/u, '') }))
            .filter(({ item, bare }) => {
              const holderId = state.items[item.id]?.position.containerId;
              return bare && bare !== String(item.name ?? '')
                && cleaned.text.includes(`${ownerName}的${bare}`)
                && holderId != null && holderId !== ownerId
                && (memberById.has(holderId) || mentioned.includes(holderId));
            })
            .map(({ item, bare }) => ({ item, itemName: bare }));
        for (const { item, itemName } of candidates) {
          const holderId = state.items[item.id]?.position.containerId;
          const holder = holderId ? state.initial.characters[holderId]?.name : undefined;
          if (!holderId || !holder || holderId === ownerId) continue;
          // The frozen state says whose item it is; a possessive that names
          // another character is a slip, not a new fact (d531 turn 2 and 1e59
          // turn 3 both wrote 路明非的红色识别带 while the band is 诺诺's).
          // Rewriting the owner keeps the fact (the six stages and next-turn
          // knowledge need the observation) instead of spending a retry on it.
          const swapped = cleaned.text.split(`${ownerName}的${itemName}`).join(`${holder}的${itemName}`);
          if (swapped === cleaned.text) continue;
          cleaned.text = swapped;
          ownershipAdjusted.push({ original, from: ownerName, to: holder, item: itemName });
        }
      }
    }
    // An ownership swap can remove the only mention of the wrong owner; the
    // “another character's action” check must read the corrected sentence.
    if (ownershipAdjusted.length) mentioned = mentionedCharacterIds(state, cleaned.text);
    if (mentioned.length && mentioned.every((id) => !recipientIds.includes(id))) {
      // When the recipients provably did nothing, the fact is the judgement's
      // explanation of somebody else's action: drop it instead of spending a
      // repair call or committing a contradiction.
      if (recipientIds.every((id) => inactive.has(id))) {
        droppedFacts.push({ memberIds: recipientIds, original, reason: 'explains_another_character' });
        continue;
      }
      const names = mentioned.map((id) => state.initial.characters[id]?.name ?? id).join('、');
      const inGroup = mentioned.some((id) => memberById.has(id));
      throw new Error(`fact names only ${names}, who ${inGroup ? 'belong to another group of this turn' : `${names.length > 1 ? 'are' : 'is'} not in this group`}; 只写本组成员自己的行动结果（${actionHint}），不要写其他人物的行动或判定理由。`);
    }
    // A mechanics clause can take the subject with it. If the remaining result
    // is a continuation (“且未被允许反应”), prefix the recipient's display name
    // so the fact is still a natural action result.
    const mechanicsRemoved = cleaned.removed.some((label) => MECHANIC_TERMS.some((term) => term.label === label));
    if (mechanicsRemoved) {
      const recipientName = state.initial.characters[recipientIds[0]]?.name;
      // Never prepend a name in front of another character's name: that build
      // produced “诺诺路明非未被掀开袖口”.
      const startsWithCharacter = Object.values(state.initial.characters)
        .some((character) => character.name && cleaned.text.startsWith(String(character.name)));
      if (recipientName && !startsWithCharacter && !cleaned.text.includes(String(recipientName))) {
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
    })) {
      if (!options.dropEmptyResults) {
        throw new Error(`fact only asserted completion or mechanics, no action result left: ${original}。只写这次行动的直接可见结果（${actionHint}），不要写任务、选择、规则或奖励结论。`);
      }
      droppedFacts.push({ memberIds: recipientIds, original, reason: 'no_result_text' });
      for (const id of recipientIds) coveredByDrop.add(id);
      continue;
    }
    // Actor: the model may name it, but only a group member can be the executor
    // of this group's result. Absent, the first attributed member is used and
    // the fact is marked derived.
    let actorId = recipientIds[0];
    let actorSource: Fact['actorSource'] = 'derived';
    if (rawActor) {
      const resolved = resolveCharacterId(state, rawActor);
      if (!resolved) throw new Error(referenceError(state, rawActor, 'character', recipientIds[0]));
      if (!memberById.has(resolved)) throw new Error(`actor ${rawActor} is not a group member; 本组只有 ${members.map((row) => row.memberId).join(',')}`);
      actorId = resolved;
      actorSource = 'model';
    }
    let targetId: Id | undefined;
    let targetSource: Fact['targetSource'];
    if (rawTarget) {
      const resolved = resolveCharacterId(state, rawTarget) ?? resolveEntityId(state, rawTarget);
      if (!resolved) throw new Error(referenceError(state, rawTarget, 'entity', recipientIds[0]));
      if (resolved === actorId) throw new Error(`target ${rawTarget} is the actor itself; 受事/目标不能是执行者`);
      targetId = resolved;
      targetSource = 'model';
    } else {
      // A question/hand-off often omits targetId while the sentence names the
      // declared target (bed9: 路明非问诺诺… with a frozen lu→nono roll). The
      // declared target is frozen state, so deriving it invents nothing.
      const declaredTargets = [...new Set(memberById.get(actorId)?.rolls.map((roll) => roll.targetId) ?? [])]
        .filter((id) => mentioned.includes(id) && id !== actorId);
      if (declaredTargets.length === 1) {
        targetId = declaredTargets[0];
        targetSource = 'derived';
      }
    }
    let outcome: ResultOutcome;
    let outcomeSource: Fact['outcomeSource'] = 'derived';
    if (rawOutcome) {
      outcome = rawOutcome as ResultOutcome;
      outcomeSource = 'model';
    } else {
      const label = judgments.find((judgment) => judgment.memberId === actorId)?.label ?? 'no_change';
      outcome = label === 'achieved' || label === 'partial' ? 'completed'
        : label === 'blocked' ? 'blocked'
          : label === 'not_achieved' ? 'failed' : 'unaffected';
    }
    // A written outcome can disagree with the group's own judgement or with the
    // sentence (d531's reacted=true re-ask, bed9's blocked while 未被阻止, 9eae's
    // blocked on an answer, 08f4's not_achieved + completed). Aborting the point
    // kills the whole turn for a direction word, so the written direction is
    // dropped and re-derived from the model's own judgement label; the fact text
    // — the part the six stages and next-turn knowledge read — is kept. This is
    // still the model's judgement, not an invented result.
    if (outcomeSource === 'model') {
      const judgment = judgments.find((row) => row.memberId === actorId);
      const label = judgment?.label;
      const derived: ResultOutcome = label === 'achieved' || label === 'partial' ? 'completed'
        : label === 'blocked' ? 'blocked'
          : label === 'not_achieved' ? 'failed' : 'unaffected';
      const reason = judgment?.reason ?? '';
      const obstruction = /被(?:阻止|拦住|拦下|拦|挡|按|拽|推|制住)|无法|没能|不能|阻止|拦住|拦下|挡住/u.test(cleaned.text);
      const contradictsLabel = (label === 'blocked' && outcome === 'completed')
        || (label === 'not_achieved' && outcome === 'completed')
        || (label === 'achieved' && (outcome === 'blocked' || outcome === 'unaffected'))
        || (label === 'no_change' && outcome === 'completed');
      const contradictsReason = outcome === 'blocked' && /未被(?:阻止|拦住|拦下)|没有被(?:阻止|拦住)/u.test(reason);
      const blockedWithoutCue = outcome === 'blocked' && !obstruction;
      if (contradictsLabel || contradictsReason || blockedWithoutCue) {
        adjustments.push({
          actorId,
          original,
          written: outcome,
          derived,
          why: contradictsReason ? 'reason_says_not_blocked' : blockedWithoutCue ? 'blocked_without_cue' : 'judgement_direction',
        });
        outcome = derived;
        outcomeSource = 'derived';
      }
    }
    // A fact that is the member's declared action restated is not a result:
    // 35ad turn 3 answered the player's own sentence (我请诺诺带我走…路线)
    // verbatim with outcome completed, so the “result” asserted the player's
    // declaration had already succeeded.
    // Only the player's typed sentence is written in the first person, so a
    // fact about the protagonist that still says “我” is that sentence copied,
    // not a description of what happened.
    const actorIdForFact = recipientIds[0];
    if (actorIdForFact === state.protagonistId && /[我咱]/u.test(cleaned.text)) {
      // 1e59 turn 3: 路明非请诺诺带我走一条… is the player's typed sentence, not
      // a description. The subject is frozen (protagonist), so the pronoun is
      // rewritten to the character's name outside dialogue; a line whose only
      // “我” is quoted speech keeps it.
      const name = state.initial.characters[actorIdForFact]?.name;
      const swapped = name ? replaceFirstPersonOutsideQuotes(cleaned.text, String(name)) : cleaned.text;
      if (swapped !== cleaned.text) {
        cleaned.text = swapped;
        firstPersonAdjusted.push({ original, text: swapped });
      }
      if (name && /[我咱]/u.test(cleaned.text) && !/[“'‘「]/.test(cleaned.text)) {
        throw new Error(`fact is the player's own “我” sentence, not a third-person result: ${original}。用第三人称写实际发生的执行、尝试、受阻或失败（${actionHint}）。`);
      }
    }
    // “甲未能。” is what is left after a stripped task clause: a dangling
    // negation is not a result. The 60-char action hint tells the repair what to
    // write instead.
    const residue = recipientIds
      .reduce((text, recipient) => {
        const name = state.initial.characters[recipient]?.name;
        return name ? text.replace(String(name), '') : text;
      }, cleaned.text.replace(FACT_PUNCTUATION, ''))
      .replace(/(?:未能|没能|没有|未|无法|不)/gu, '');
    if (!residue) {
      if (!options.dropEmptyResults) {
        throw new Error(`fact only asserted completion or mechanics, no action result left: ${original}。只写这次行动的直接可见结果（${actionHint}）。`);
      }
      droppedFacts.push({ memberIds: recipientIds, original, reason: 'no_result_text' });
      for (const id of recipientIds) coveredByDrop.add(id);
      continue;
    }
    for (const recipient of recipientIds) factRecipients.add(recipient);
    facts.push({
      text: cleaned.text,
      memberIds: recipientIds,
      actorId,
      ...(targetId ? { targetId } : {}),
      ...(rawAction ? { action: rawAction } : {}),
      outcome,
      actorSource,
      outcomeSource,
      ...(targetSource ? { targetSource } : {}),
      ...(implicit.includes(actorId) ? { implicit: true as const } : {}),
    });
    if (cleaned.removed.length) sanitized.push({ memberIds: recipientIds, original, text: cleaned.text, removed: cleaned.removed });
  }
  // A combined group prompt makes the small model repeat one member's whole
  // sentence inside another member's fact (1e59 turn 3: nono's line appeared
  // verbatim inside lu's result). The other member's own fact already carries
  // it, so the wrapper is dropped instead of attributing her action to him.
  dropDuplicatedFacts(facts, droppedFacts, coveredByDrop);
  if (facts.length) {
    factRecipients.clear();
    for (const fact of facts) for (const id of fact.memberIds) factRecipients.add(id);
  }
  for (const member of members) {
    if (factRecipients.has(member.memberId)) continue;
    if (inactive.has(member.memberId)) continue;
    if (coveredByDrop.has(member.memberId)) continue;
    // The repair named the member twice and the answer still has no sentence for
    // it. Killing the point leaves the player with a stop and no prose; settling
    // with the facts that exist and recording the gap invents nothing.
    if (options.dropEmptyResults) {
      missingFactMembers.push(member.memberId);
      continue;
    }
    const names = members.map((row) => `${state.initial.characters[row.memberId]?.name ?? row.memberId}(${row.memberId})`).join('、');
    const missing = state.initial.characters[member.memberId]?.name ?? member.memberId;
    throw new Error(`no fact attributed to ${member.memberId}（${missing}）; facts 必须给本组每个成员各一条自己的结果（本组：${names}），例：${missing}做了什么、看到或听到什么。已冻结的行动：${actionHint}`);
  }
  return {
    judgments, facts, dropped,
    ...(duplicateJudgments.length ? { duplicateJudgments } : {}),
    ...(sanitized.length ? { sanitized } : {}),
    ...(droppedFacts.length ? { droppedFacts } : {}),
    ...(implicit.length ? { implicitJudgments: implicit } : {}),
    ...(adjustments.length ? { outcomeAdjusted: adjustments } : {}),
    ...(effectsAdjusted.length ? { effectsAdjusted } : {}),
    ...(ownershipAdjusted.length ? { ownershipAdjusted } : {}),
    ...(firstPersonAdjusted.length ? { firstPersonAdjusted } : {}),
    ...(missingFactMembers.length ? { missingFactMembers } : {}),
  };
}

/** The results prompt writes its example fact as «<name>做了什么/看到什么».
 * A model that copies it has written no result; keeping it would settle the
 * template as the world's fact. */
export function isExampleFactText(text: string): boolean {
  const compact = text.replace(/\s+/gu, '');
  return /做了什么\/看到什么|做了什么\/看到了什么|做了什么\/听见了什么/u.test(compact);
}

/** Remove a fact that only wraps another member's fact text. The wrapper must
 * be short (a prefix like “路明非请诺诺带我走…，”), and the contained fact must
 * be a full sentence of at least 12 punctuation-free characters, so ordinary
 * overlap between two genuine results is untouched. */
function dropDuplicatedFacts(
  facts: Fact[],
  dropped: NonNullable<ResultsAnswer['droppedFacts']>,
  coveredByDrop: Set<Id>,
): void {
  if (facts.length < 2) return;
  const bare = facts.map((fact) => fact.text.replace(FACT_PUNCTUATION, ''));
  for (let i = facts.length - 1; i >= 0; i -= 1) {
    for (let j = 0; j < facts.length; j += 1) {
      if (i === j) continue;
      const inner = bare[j];
      if (!inner || inner.length < 12) continue;
      if (facts[i].actorId === facts[j].actorId) continue;
      if (!bare[i].includes(inner)) continue;
      const wrapper = bare[i].replace(inner, '');
      if (wrapper.length > 40) continue;
      dropped.push({ memberIds: facts[i].memberIds, original: facts[i].text, reason: 'duplicates_another_member' });
      for (const id of facts[i].memberIds) coveredByDrop.add(id);
      facts.splice(i, 1);
      break;
    }
  }
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
  // A negative result is an outcome, not a completion claim: “未能完成翻越”
  // must stay negative. Only the task/goal wording is stripped.
  { pattern: /未能完成(?:任务|目标|参赛选择)/g, label: '未能完成任务' },
  { pattern: /未达成(?:任务|目标)/g, label: '未达成任务' },
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
  let tailOfRemoved = false;
  for (const clause of clauses) {
    const labels = MECHANIC_TERMS.filter(({ pattern }) => {
      pattern.lastIndex = 0;
      return pattern.test(clause);
    }).map(({ label }) => label);
    if (labels.length) {
      removed.push(...labels);
      tailOfRemoved = true;
      continue;
    }
    // The tail of a removed mechanics clause (“骰点未被触发，因此未被接纳”) is
    // still the judgement's explanation, not an action result.
    // Only a causal tail is the judgement's conclusion; an additive tail
    // (“且未被允许反应”) carries a distinct result and stays.
    if (tailOfRemoved && /^(?:因此|所以|因而)/u.test(clause.trim())) {
      removed.push('判定尾句');
      continue;
    }
    tailOfRemoved = false;
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
