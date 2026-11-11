/** Automatic continuation (R10): the model proposes follow-up actions and
 * judges each as likely + related to the protagonist. Only both-true actions
 * continue. A model failure never becomes a handback; only a completed
 * assessment with no accepted candidate is a model handback. Runaway chains are
 * closed by explainable no-progress / repeated-semantics rules, not by a
 * default zero or one call cap. */
import type { EntityDelta, Id, Json, TimeAdvance, WorldState } from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import { callJson, JsonCallError, joinedMs, joinedRaw } from './engine-call';
import type {
  ContinuationPolicyOptions, ModelCallEvidence, SettlementConclusion, SettlementEvidence,
  SettlementOptions, SettlementOutcome,
} from './types';
import { asRecord, asString, errorText, isRecord, normalizeChangeText, referenceError, resolveCharacterId, toJson } from './support';
import type { RoundProgressEvidence } from './support';
import { describeCharacter, describeDelta, visibleCharacters } from '../../prompt';

interface RoundPoint {
  pointId: Id;
  timeAdvance: TimeAdvance | null;
  entityDeltas: Record<Id, EntityDelta>;
}

interface ContinuationInput {
  roundId: Id;
  trigger: string;
  workingState: WorldState;
  roundChanges: RoundPoint[];
  headPointId: Id | null;
  roundProgress: RoundProgressEvidence | null;
}

interface Candidate {
  characterId: Id;
  text: string;
}

interface ContinuationPolicyState {
  noProgressStreak: number;
  repeatStreak: number;
  continues: number;
  lastAccepted: string;
  /** Every candidate signature accepted earlier in this submission. A later
   * round cannot replay it even if a different candidate was accepted in
   * between; this is the consumed-action identity, not a call cap. */
  consumed: Set<string>;
  /** Signatures accepted in this session with the world digest they left
   * behind. Survives `reset()`: a new player turn does not make the same
   * automatic action new again. */
  remembered: Map<string, string>;
}

export interface ContinuationPolicyDecision {
  allow: boolean;
  reason: 'progress' | 'no_progress' | 'repeated_candidate' | 'abstract_task_goal' | 'safety_cap';
  anomaly: boolean;
  noProgressStreak: number;
  repeatStreak: number;
  continues: number;
  consumedCount: number;
}

export const continuationPolicy: Required<ContinuationPolicyOptions> = {
  noProgressRounds: 2,
  // Consumed candidates stop immediately; this is only a secondary safety net
  // for a caller that does not expose consumed identity. It is intentionally
  // not a one-call cap: different follow-ups with real progress may continue.
  repeatRounds: 2,
  maxAutoContinuations: null,
  maxCandidates: 8,
};

export class ContinuationPolicy {
  private readonly options: Required<ContinuationPolicyOptions>;
  private state: ContinuationPolicyState = {
    noProgressStreak: 0, repeatStreak: 0, continues: 0, lastAccepted: '', consumed: new Set<string>(), remembered: new Map(),
  };

  constructor(options: ContinuationPolicyOptions = {}) {
    this.options = {
      noProgressRounds: positiveInteger(options.noProgressRounds, continuationPolicy.noProgressRounds),
      repeatRounds: positiveInteger(options.repeatRounds, continuationPolicy.repeatRounds),
      maxAutoContinuations: options.maxAutoContinuations === undefined ? continuationPolicy.maxAutoContinuations : options.maxAutoContinuations,
      maxCandidates: positiveInteger(options.maxCandidates, continuationPolicy.maxCandidates),
    };
  }

  get maxCandidates(): number { return this.options.maxCandidates; }

  reset(): void {
    // `remembered` deliberately survives: the 10turn run proposed the same
    // automatic beat in three consecutive turns because a new submission
    // cleared every identity the previous one had consumed.
    this.state = {
      noProgressStreak: 0, repeatStreak: 0, continues: 0, lastAccepted: '', consumed: new Set<string>(),
      remembered: this.state.remembered,
    };
  }

  /** A program rule rejected the proposal before judgment. It is a visible
   * policy stop, not a model handback and not a fake progress observation. */
  reject(reason: 'abstract_task_goal'): ContinuationPolicyDecision {
    return {
      allow: false,
      reason,
      anomaly: false,
      noProgressStreak: this.state.noProgressStreak,
      repeatStreak: this.state.repeatStreak,
      continues: this.state.continues,
      consumedCount: this.state.consumed.size,
    };
  }

  observe(
    _roundChanges: RoundPoint[],
    accepted: Candidate[],
    progressEvidence?: RoundProgressEvidence | null,
    trigger = 'automatic',
  ): ContinuationPolicyDecision {
    // Only the port's before/after evidence counts. The old field test treated
    // a repeated positionSet as progress; callers without evidence get a
    // conservative no-progress observation instead of a false advance.
    const progress = progressEvidence?.progress === true;
    // The player's own no-state-change action (for example reading a sign) is
    // a legitimate action, not an automatic no-progress round. Count the
    // streak only for automatic rounds; new actions/facts/time/state reset it.
    this.state.noProgressStreak = progress || trigger !== 'automatic'
      ? 0
      : this.state.noProgressStreak + 1;
    const signatures = accepted
      .map((candidate) => `${candidate.characterId}:${normalizeChangeText(candidate.text)}`)
      .sort();
    const signature = signatures.join('|');
    const consumedRepeat = signatures.some((row) => this.state.consumed.has(row));
    const worldDigest = progressEvidence?.worldDigest ?? '';
    const repeatedEarlierTurn = Boolean(worldDigest)
      && signatures.some((row) => this.state.remembered.get(row) === worldDigest);
    this.state.repeatStreak = consumedRepeat
      ? this.state.repeatStreak + 1
      : signature && signature === this.state.lastAccepted
        ? this.state.repeatStreak + 1
        : 0;
    this.state.lastAccepted = signature;
    this.state.continues += 1;
    const base = {
      noProgressStreak: this.state.noProgressStreak,
      repeatStreak: this.state.repeatStreak,
      continues: this.state.continues,
      consumedCount: this.state.consumed.size,
    };
    if (this.options.maxAutoContinuations != null && this.state.continues > this.options.maxAutoContinuations) {
      return { allow: false, reason: 'safety_cap', anomaly: true, ...base };
    }
    // Consumed identity is checked before the softer consecutive-repeat rule:
    // A -> B -> A must stop exactly like A -> A.
    if (consumedRepeat) {
      return { allow: false, reason: 'repeated_candidate', anomaly: false, ...base };
    }
    // The same automatic action, proposed in an earlier turn, with the world
    // byte-identical apart from the clock: nothing happened since it ran, so
    // running it again would settle the same thing. A real world change
    // releases the signature.
    if (repeatedEarlierTurn) {
      return { allow: false, reason: 'repeated_candidate', anomaly: false, ...base };
    }
    if (this.state.noProgressStreak >= this.options.noProgressRounds) {
      return { allow: false, reason: 'no_progress', anomaly: false, ...base };
    }
    if (this.state.repeatStreak >= this.options.repeatRounds) {
      return { allow: false, reason: 'repeated_candidate', anomaly: false, ...base };
    }
    for (const row of signatures) this.state.consumed.add(row);
    if (worldDigest) {
      for (const row of signatures) this.state.remembered.set(row, worldDigest);
      // Bound the memory: a long session must not grow without limit.
      if (this.state.remembered.size > 200) {
        const oldest = this.state.remembered.keys().next().value;
        if (oldest != null) this.state.remembered.delete(oldest);
      }
    }
    return { allow: true, reason: 'progress', anomaly: false, ...base, consumedCount: this.state.consumed.size };
  }
}

const CANDIDATES_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['candidates'],
  properties: {
    candidates: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['characterId', 'text'],
        properties: { characterId: { type: 'string' }, text: { type: 'string' } },
      },
    },
  },
};

const JUDGMENTS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['judgments'],
  properties: {
    judgments: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['candidateId', 'likely', 'related', 'reason'],
        properties: {
          candidateId: { type: 'string' },
          characterId: { type: 'string' },
          text: { type: 'string' },
          likely: { type: 'boolean' },
          related: { type: 'boolean' },
          reason: { type: 'string' },
        },
      },
    },
  },
};

export class ContinuationRunner {
  private readonly policy: ContinuationPolicy;
  private readonly nextRoundId?: () => Id;
  private readonly onTaskCallback?: SettlementOptions['onTask'];

  constructor(private readonly engine: InferenceEngine, options: SettlementOptions = {}) {
    this.policy = new ContinuationPolicy(options.continuation);
    this.nextRoundId = options.nextRoundId;
    this.onTaskCallback = options.onTask;
  }

  reset(): void {
    this.policy.reset();
  }

  async run(key: Id, input: Json): Promise<SettlementOutcome<SettlementConclusion>> {
    const started = performance.now();
    const parsed = parseContinuationInput(input);
    if ('error' in parsed) return failure(key, parsed.error, started);
    const { workingState, roundChanges, roundId } = parsed;
    const proposalPrompt = buildCandidatePrompt(parsed, this.policy.maxCandidates);
    let calls: ModelCallEvidence[] = [];
    try {
      const proposal = await callJson(this.engine, proposalPrompt, {
        maxTokens: 220,
        temperature: 0,
        timeoutMs: 60_000,
        maxPromptChars: 8000,
        jsonSchema: CANDIDATES_SCHEMA,
        validate: (value) => { readCandidates(value, workingState, this.policy.maxCandidates); },
      });
      calls = proposal.calls;
      const read = readCandidates(proposal.value, workingState, this.policy.maxCandidates);
      const { candidates } = read;
      if (!candidates.length) {
        const abstractGoal = read.rejected.some((row) => row.reason === 'abstract_task_goal');
        if (abstractGoal) {
          const decision = this.policy.reject('abstract_task_goal');
          return this.policyStop(key, calls, started, decision, {
            candidates: [],
            rejectedCandidates: read.rejected,
            accepted: [],
            proposalPromptChars: proposalPrompt.length,
            roundProgress: parsed.roundProgress,
          });
        }
        return this.handback(key, calls, started, {
          reason: read.rejected.length ? 'no_eligible_candidate' : 'model_no_candidate',
          candidates: [],
          rejectedCandidates: read.rejected,
          accepted: [],
          proposalPromptChars: proposalPrompt.length,
          roundProgress: parsed.roundProgress,
        });
      }
      const judgmentPrompt = buildJudgmentPrompt(parsed, candidates);
      const judgment = await callJson(this.engine, judgmentPrompt, {
        maxTokens: 320,
        temperature: 0,
        timeoutMs: 60_000,
        maxPromptChars: 8000,
        jsonSchema: JUDGMENTS_SCHEMA,
        validate: (value) => readJudgments(value, candidates, workingState),
      });
      calls = [...calls, ...judgment.calls];
      const judgments = readJudgments(judgment.value, candidates, workingState);
      const accepted = acceptedCandidates(candidates, judgments);
      if (!accepted.length) {
        return this.handback(key, calls, started, {
          reason: 'no_likely_related_candidate',
          candidates,
          accepted: [],
          judgments,
          proposalPromptChars: proposalPrompt.length,
          judgmentPromptChars: judgmentPrompt.length,
          roundProgress: parsed.roundProgress,
        });
      }
      const decision = this.policy.observe(roundChanges, accepted, parsed.roundProgress, parsed.trigger);
      if (!decision.allow) {
        // A policy stop is NOT a model handback. The model said this follow-up
        // is likely and protagonist-related; only the no-progress/repeat/safety
        // rule ends the chain. The local transport hardcodes
        // `closedBy:'model'` on every handback, so emitting a handback here
        // would write a decision the model never made. Return a visible stop
        // with the policy reason instead; the caller surfaces it and keeps the
        // state exactly as committed. See `policyStop` below.
        return this.policyStop(key, calls, started, decision, {
          candidates,
          accepted,
          judgments,
          rejectedCandidates: read.rejected,
          proposalPromptChars: proposalPrompt.length,
          judgmentPromptChars: judgmentPrompt.length,
          roundProgress: parsed.roundProgress,
        });
      }
      const nextRoundId = this.nextRoundId ? this.nextRoundId() : autoRoundId();
      if (nextRoundId === roundId) {
        return failure(key, 'continuation_round_id_reused', started, calls);
      }
      const value: SettlementConclusion = {
        kind: 'continue',
        closedBy: 'model',
        cancelReason: null,
        candidateCharacterIds: accepted.map((candidate) => candidate.characterId),
        nextRoundId,
      };
      const evidence = makeEvidence(key, calls, false, undefined, {
        decision: 'continue',
        reason: 'likely_and_related',
        policy: decision,
        candidates,
        accepted,
        judgments,
        rejectedCandidates: read.rejected,
        nextRoundId,
        proposalPromptChars: proposalPrompt.length,
        judgmentPromptChars: judgmentPrompt.length,
        roundProgress: parsed.roundProgress,
      });
      const outcome: SettlementOutcome<SettlementConclusion> = {
        value,
        raw: joinedRaw(calls),
        ms: joinedMs(calls),
        fallback: false,
        evidence,
      };
      this.onTask(key, outcome, proposalPrompt.length + judgmentPrompt.length);
      return outcome;
    } catch (error) {
      calls = error instanceof JsonCallError ? error.calls : calls;
      const message = errorText(error);
      const outcome = failure(key, message, started, calls);
      this.onTask(key, outcome, proposalPrompt.length);
      return outcome;
    }
  }

  private handback(
    key: Id,
    calls: ModelCallEvidence[],
    started: number,
    detail: Record<string, unknown>,
  ): SettlementOutcome<SettlementConclusion> {
    const evidence = makeEvidence(key, calls, false, undefined, { decision: 'handback', ...detail });
    const outcome: SettlementOutcome<SettlementConclusion> = {
      value: { kind: 'handback', closedBy: 'model', cancelReason: null },
      raw: joinedRaw(calls),
      ms: joinedMs(calls),
      fallback: false,
      evidence,
    };
    this.onTask(key, outcome, calls.reduce((sum, call) => sum + call.prompt.length, 0));
    return outcome;
  }

  /** The chain ended on a program rule, not on the model's judgment. The
   * outcome has no conclusion value, so the adapter cannot accidentally record
   * `closedBy:'model'`; the error text carries the explainable reason. */
  private policyStop(
    key: Id,
    calls: ModelCallEvidence[],
    started: number,
    decision: ContinuationPolicyDecision,
    detail: Record<string, unknown>,
  ): SettlementOutcome<SettlementConclusion> {
    const reason = `continuation_policy_${decision.reason}`;
    const evidence = makeEvidence(key, calls, false, reason, {
      decision: 'policy_stop',
      anomaly: decision.anomaly,
      policy: decision,
      ...detail,
    });
    const outcome: SettlementOutcome<SettlementConclusion> = {
      value: null,
      raw: joinedRaw(calls),
      ms: joinedMs(calls),
      fallback: false,
      error: reason,
      evidence,
    };
    this.onTask(key, outcome, calls.reduce((sum, call) => sum + call.prompt.length, 0));
    return outcome;
  }

  private onTask(key: Id, outcome: SettlementOutcome<SettlementConclusion>, promptChars: number): void {
    this.onTaskCallback?.('continuation', key, {
      ms: outcome.ms,
      fallback: outcome.fallback,
      error: outcome.error,
      raw: outcome.raw,
      promptChars,
    });
  }
}

export function createContinuationRunner(engine: InferenceEngine, options: SettlementOptions = {}): ContinuationRunner {
  return new ContinuationRunner(engine, options);
}

function positiveInteger(value: number | undefined, fallback: number): number {
  return value == null || !Number.isInteger(value) || value < 1 ? fallback : value;
}

let roundSequence = 0;

function autoRoundId(): Id {
  roundSequence += 1;
  return `round_auto_${Date.now().toString(36)}_${roundSequence}`;
}

function parseContinuationInput(input: Json): ContinuationInput | { error: string } {
  const data = asRecord(input);
  const state = data.workingState;
  if (!isRecord(state) || !isRecord(state.initial) || !isRecord(state.initial.characters)
    || !isRecord(state.initial.items) || !isRecord(state.initial.locations)
    || !isRecord(state.characters) || !isRecord(state.items) || !isRecord(state.locations)) {
    return { error: 'continuation_missing_working_state' };
  }
  const world = state as unknown as WorldState;
  const round = asRecord(data.round);
  const roundId = asString(round.roundId);
  if (!roundId) return { error: 'continuation_missing_round_id' };
  if (round.conclusion != null) return { error: 'continuation_round_already_concluded' };
  if (!Array.isArray(data.roundChanges)) return { error: 'continuation_missing_round_changes' };
  const roundChanges: RoundPoint[] = [];
  const pointIds = new Set<Id>();
  for (const raw of data.roundChanges) {
    if (!isRecord(raw)) return { error: 'continuation_round_change_not_object' };
    const pointId = asString(raw.pointId);
    if (!pointId) return { error: 'continuation_round_change_without_point' };
    if (pointIds.has(pointId)) return { error: `continuation_duplicate_point:${pointId}` };
    pointIds.add(pointId);
    const entityDeltas = isRecord(raw.entityDeltas) ? raw.entityDeltas as Record<Id, EntityDelta> : {};
    roundChanges.push({
      pointId,
      timeAdvance: isRecord(raw.timeAdvance) ? raw.timeAdvance as unknown as TimeAdvance : null,
      entityDeltas,
    });
  }
  const head = asRecord(data.head);
  const headPointId = asString(head.pointId) || null;
  if (headPointId && roundChanges.length && roundChanges[roundChanges.length - 1].pointId !== headPointId) {
    return { error: `continuation_head_mismatch:${roundChanges[roundChanges.length - 1].pointId}->${headPointId}` };
  }
  const rawProgress = asRecord(data.roundProgress);
  const roundProgress = typeof rawProgress.progress === 'boolean'
    ? rawProgress as unknown as RoundProgressEvidence
    : null;
  return {
    roundId,
    trigger: asString(round.trigger) || 'player',
    workingState: world,
    roundChanges,
    headPointId,
    roundProgress,
  };
}

function buildCandidatePrompt(input: ContinuationInput, maxCandidates: number): string {
  const state = input.workingState;
  const protagonist = state.protagonistId;
  const visible = visibleCharacters(state, protagonist).filter((id) => id !== protagonist);
  const changes = input.roundChanges.length
    ? input.roundChanges.map((point) => {
      const time = point.timeAdvance
        ? `时间推进 ${point.timeAdvance.duration.amount} ${point.timeAdvance.duration.unit}。`
        : '';
      return `- ${point.pointId}：${time}${describeDelta(point.entityDeltas, state)}`;
    }).join('\n')
    : '- 本轮没有已提交的状态变化。';
  return [
    '你是中文跑团游戏的自动推进判断器。只输出 JSON，不要解释。',
    '根据主角、当前世界和本轮状态变化，列出可能紧接着发生的、与主角相关的后续行动。',
    '规则：',
    '- 只列大概率真的会发生、并且和主角当前处境或目标直接相关的行动。',
    '- 只列主角同场景的其他人物；主角自己的下一步由玩家决定，不能列为自动推进。',
    '- 普通闲聊、等待、场景切换、需要玩家决定的事都不要列。',
    '- 不要重复玩家输入，不要把候选当成已经发生；不要新增人物、地点、物品或往事。',
    '- 没有值得自动推进的行动就返回空数组。',
    `主角：${describeCharacter(state, protagonist)}`,
    `同地点人物：\n${visible.map((id) => describeCharacter(state, id, false)).join('\n') || '无'}`,
    `本轮状态变化：\n${changes}`,
    `当前时间：${state.time.dateTime}`,
    // A literal placeholder in the format example is copied verbatim: 35ad turn
    // 3 answered four candidates with characterId "人物id" and died on the fatal
    // placeholder check after two calls. Show a real id, and when nobody is in
    // the room say so instead of offering an example.
    visible.length
      ? `输出 {"candidates":[{"characterId":"${visible[0]}","text":"一句话行动"}]}，最多 ${maxCandidates} 条；characterId 只能用上面人物的真实 id（如 ${visible[0]}）或全名；没有合适的人就返回空数组。`
      : '同地点没有其他人物：返回 {"candidates":[]}，不要写任何 characterId。',
  ].join('\n');
}

interface CandidateRead {
  candidates: Candidate[];
  rejected: { characterId: string; text: string; reason: string }[];
}

/** Automatic rounds may only carry characters the action lane will actually
 * judge. The protagonist's next action belongs to the player (the action lane
 * refuses to let a model write it, and a consumed player command is never
 * replayed), and a character outside the protagonist's room is skipped by that
 * lane. Proposing either would create an empty automatic round. Such
 * candidates are dropped with a recorded reason instead of silently becoming a
 * "no follow-up" handback. */
function readCandidates(value: unknown, state: WorldState, maxCandidates: number): CandidateRead {
  const rows = asRecord(value).candidates;
  if (!Array.isArray(rows)) throw new Error('candidates must be an array');
  if (rows.length > maxCandidates) throw new Error(`candidate_budget_exceeded:${rows.length}>${maxCandidates}`);
  const seen = new Set<string>();
  const candidates: Candidate[] = [];
  const rejected: CandidateRead['rejected'] = [];
  const protagonistRoom = visibleCharacters(state, state.protagonistId);
  const inScene = new Set(protagonistRoom);
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('candidate must be an object');
    const rawCharacterId = asString(raw.characterId);
    const text = asString(raw.text);
    const characterId = resolveCharacterId(state, rawCharacterId);
    if (!characterId) throw new Error(referenceError(state, rawCharacterId, 'character', visibleCharacters(state, state.protagonistId).find((id) => id !== state.protagonistId)));
    if (!text) throw new Error(`empty continuation text for ${characterId}`);
    const key = `${characterId}:${normalizeChangeText(text)}`;
    if (seen.has(key)) throw new Error(`duplicate continuation candidate ${characterId}`);
    seen.add(key);
    if (characterId === state.protagonistId) {
      rejected.push({ characterId, text, reason: 'protagonist_action_belongs_to_player' });
      continue;
    }
    if (!inScene.has(characterId)) {
      rejected.push({ characterId, text, reason: 'character_outside_protagonist_scene' });
      continue;
    }
    if (isAbstractTaskGoal(state, characterId, text)) {
      // The 21c3/95dc traces show the same task-goal sentence being proposed as
      // an executable follow-up after it was already settled. A goal is not an
      // action: accepting it would turn settlement into a second planner and
      // replay the same abstract sentence. The proposal can still contain a
      // concrete follow-up; only this row is dropped.
      rejected.push({ characterId, text, reason: 'abstract_task_goal' });
      continue;
    }
    candidates.push({ characterId, text });
  }
  return { candidates, rejected };
}

/** A candidate that is verbatim the owner's task goal is a restatement of the
 * objective, not a new executable action. Keep the rule semantic: only the
 * actual task-goal text counts, and only when the goal is worded as an
 * objective/arrangement rather than a single concrete act. */
function isAbstractTaskGoal(state: WorldState, characterId: Id, text: string): boolean {
  const target = normalizeChangeText(text);
  if (!target) return false;
  const rows = [
    ...Object.values(state.initial.characters[characterId]?.tasks ?? {}),
    ...Object.values(state.characters[characterId]?.tasks ?? {}),
  ];
  const goal = rows
    .map((task) => task.goal)
    .find((row) => {
      const normalized = normalizeChangeText(row);
      return normalized === target
        || (target.length >= 12 && (normalized.startsWith(target) || target.startsWith(normalized)));
    });
  if (!goal) return false;
  return /(?:而不|以便|确保|争取|避免|让|使|可执行|掩护|能够|作为)/u.test(goal);
}

function buildJudgmentPrompt(input: ContinuationInput, candidates: Candidate[]): string {
  const state = input.workingState;
  return [
    '你是中文跑团游戏的自动推进判断器。只输出 JSON，不要解释。',
    '对每个候选行动分别判断：',
    '- likely：在这条世界线中是否大概率真的发生；',
    '- related：是否与主角当前处境或目标直接相关。',
    '只有两者都为 true 才允许自动推进。普通客套、无关人物、需要玩家选择的事都判 false。',
    `主角：${describeCharacter(state, state.protagonistId)}`,
    `当前时间：${state.time.dateTime}`,
    '候选：',
    ...candidates.map((candidate, index) => `- c${index + 1}：${candidate.characterId}：${candidate.text}`),
    '输出 {"judgments":[{"candidateId":"c1","likely":true或false,"related":true或false,"reason":"一句话理由"}]}。',
  ].join('\n');
}

function readJudgments(value: unknown, candidates: Candidate[], state: WorldState): Record<string, { likely: boolean; related: boolean; reason: string }> {
  const rows = asRecord(value).judgments;
  if (!Array.isArray(rows)) throw new Error('judgments must be an array');
  const expected = new Map(candidates.map((candidate) => [candidateKey(candidate), candidate]));
  const byCandidateId = new Map(candidates.map((candidate, index) => [`c${index + 1}`, candidate]));
  const seen = new Set<string>();
  const judgments: Record<string, { likely: boolean; related: boolean; reason: string }> = {};
  for (const raw of rows) {
    if (!isRecord(raw)) throw new Error('judgment must be an object');
    const candidateId = asString(raw.candidateId);
    const candidate = candidateId ? byCandidateId.get(candidateId) : undefined;
    const rawCharacterId = asString(raw.characterId);
    const characterId = rawCharacterId ? (resolveCharacterId(state, rawCharacterId) ?? rawCharacterId) : '';
    const text = asString(raw.text);
    const key = candidate ? candidateKey(candidate) : `${characterId}:${normalizeChangeText(text)}`;
    if (!expected.has(key)) throw new Error(`judgment for unknown candidate ${candidateId || key || '?'}`);
    if (seen.has(key)) throw new Error(`duplicate judgment for ${key}`);
    seen.add(key);
    if (typeof raw.likely !== 'boolean' || typeof raw.related !== 'boolean') throw new Error(`judgment booleans missing for ${key}`);
    if (typeof raw.reason !== 'string') throw new Error(`judgment reason missing for ${key}`);
    judgments[key] = { likely: raw.likely, related: raw.related, reason: raw.reason };
  }
  if (seen.size !== candidates.length) throw new Error(`judgment coverage incomplete: ${seen.size}/${candidates.length}`);
  return judgments;
}

function candidateKey(candidate: Candidate): string {
  return `${candidate.characterId}:${normalizeChangeText(candidate.text)}`;
}

function acceptedCandidates(candidates: Candidate[], judgments: Record<string, { likely: boolean; related: boolean }>): Candidate[] {
  const seen = new Set<Id>();
  const accepted: Candidate[] = [];
  for (const candidate of candidates) {
    const judgment = judgments[`${candidate.characterId}:${normalizeChangeText(candidate.text)}`];
    if (judgment?.likely && judgment.related && !seen.has(candidate.characterId)) {
      seen.add(candidate.characterId);
      accepted.push(candidate);
    }
  }
  return accepted;
}

function makeEvidence(
  key: Id,
  calls: ModelCallEvidence[],
  fallback: boolean,
  error: string | undefined,
  detail: Record<string, unknown>,
): SettlementEvidence {
  return {
    task: 'continuation',
    key,
    raw: joinedRaw(calls),
    ms: joinedMs(calls),
    fallback,
    error,
    calls,
    detail: toJson(detail),
  };
}

function failure(key: Id, error: string, started: number, calls: ModelCallEvidence[] = []): SettlementOutcome<SettlementConclusion> {
  return {
    value: null,
    raw: joinedRaw(calls),
    ms: calls.length ? joinedMs(calls) : performance.now() - started,
    fallback: false,
    error,
    evidence: {
      task: 'continuation',
      key,
      raw: joinedRaw(calls),
      ms: calls.length ? joinedMs(calls) : performance.now() - started,
      fallback: false,
      error,
      calls,
      detail: toJson({ reason: error, decision: 'failed' }),
    },
  };
}
