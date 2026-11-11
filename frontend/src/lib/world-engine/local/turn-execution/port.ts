/** Product model port for the settlement half of one turn.
 *
 * The controller asks the model for three semantic tasks (`results`,
 * `updates`, `continuation`). This port answers exactly those three from the
 * settlement lane and forwards everything else (action/targets/reaction,
 * narration, opening) to the caller's port, so the product can compose ports
 * per responsibility without copying one lane's logic into another.
 *
 * What this port guarantees:
 *   - one joint `results` judgement per frozen group (every frozen member and
 *     every admitted/denied roll receipt in the prompt, facts attributed to
 *     members);
 *   - six updates stages in the fixed order position -> appearance -> tasks ->
 *     subtasks -> personality -> sanity, with later stages reading the state
 *     after earlier stages were applied; task and personality scans cover the
 *     whole registered cast, not just the viewpoint's room;
 *   - continuation asks the model for likely + protagonist-related follow-ups
 *     first, then judges each candidate, and only continues on both-true; a
 *     policy stop (no progress / repeated candidate / safety cap) is a visible
 *     stop, never a fabricated `closedBy:'model'` handback;
 *   - every call and its timing is recorded so the whole player submission can
 *     be accounted (this port never measures only the narration call).
 *
 * The port does not own scheduling, freezing, dice, commit or narration order:
 * the controller does. It also never writes `closedBy` on its own.
 */
import type { Id, Json, WorldState } from '../../types';
import type { InferenceEngine } from '../../runtime/engine';
import type { ModelTask } from '../../schedule';
import type { WorldModelPort } from '../../controller';
import { runResults } from '../semantics/settlement/results';
import type { ResultOutcome } from '../semantics/settlement/results';
import { createUpdatesRunner, type UpdatesRunner } from '../semantics/settlement/updates';
import { ContinuationRunner } from '../semantics/settlement/continuation';
import { roundProgressFromState, type RoundProgressEvidence } from '../semantics/settlement/support';
import type {
  SettlementConclusion, SettlementOptions, SettlementOutcome, SettlementTask,
} from '../semantics/settlement/types';

export interface PortCallRecord {
  task: ModelTask;
  key: Id;
  stage: string | null;
  ms: number;
  promptChars: number;
  fallback: boolean;
  error?: string;
  /** Calls the model actually made, including validation retries. */
  calls: number;
  evidenceCalls: number;
  /** Updates stages in the order this task ran them (merged or split). */
  stages?: string[];
  /** What the results answer settled, as committed: the executor, the optional
   * recipient, the action and the direction. This is the whole record 06 and 01
   * need — no prose check is implied, and no `名字：` label is present. */
  facts?: Omit<SettledFact, 'playerGroup'>[];
  /** Facts that were dropped as noise, with the reason (a denied reaction, a
   * fact about another group). Visible so a zero-fact point is not a mystery. */
  droppedFacts?: { memberIds: string[]; reason: string; original: string }[];
  /** A written outcome that disagreed with the judgement and was replaced by
   * the judgement-derived direction (d531/bed9/9eae/08f4 all lost a turn to a
   * direction word). */
  outcomeAdjusted?: { actorId: string; written: string; derived: string; why: string }[];
  /** Members whose judgement row the model omitted; their outcome is derived,
   * not asserted. */
  implicitJudgments?: string[];
  /** Rows the model repeated for a member already judged; the first row stood. */
  duplicateJudgments?: { memberId: string; label: string; reason: string }[];
  /** An effects row that contradicted the frozen admission and was corrected
   * from it (09-frozen-raw-6186 turn 2 aborted the turn on this). */
  effectsAdjusted?: { memberId: string; targetId: string; written: boolean; frozen: boolean }[];
  /** An item possessive that named the wrong character and was rewritten to the
   * frozen owner. */
  ownershipAdjusted?: { from: string; to: string; item: string }[];
  /** The player's own first-person sentence rewritten to the protagonist's name
   * outside dialogue. */
  firstPersonAdjusted?: string[];
  /** How many characters the stage answers covered. The full cast is a product
   * requirement, and this is the lightweight proof 09 can read from the page.
   * `taskRows` is the full-world task-row count, never a scene-only subset. */
  coverage?: {
    tasks: number; personality: number; taskRows?: number; mode?: string;
    /** Actual per-character task decisions; empty rows are counted, not
     * committed. An all-empty set is visible here, so coverage cannot be
     * mistaken for semantic agreement. */
    achievedByCharacter?: { characterId: string; taskIds: string[] }[];
    assertedUnchanged?: number;
    /** Affected-projection audit: the model saw the affected owners/rows, the
     * program carried the rest with a no-dependency basis. */
    affectedCharacters?: number;
    unaffectedCharacters?: string[];
    affectedTaskIds?: string[];
    unaffectedTaskIds?: string[];
    rejectedTaskIds?: { characterId: string; taskId: string; reason: string }[];
    supports?: { characterId: string; taskId: string; basis: string }[];
  };
  /** Model time per updates stage, for finding which stage made a turn slow. */
  stageMs?: Record<string, number>;
  /** What the completed round actually did. The continuation policy uses
   * this instead of counting filled position fields as progress. */
  roundProgress?: RoundProgressEvidence;
  /** Failed calls keep the raw model output (bounded) and each attempt's time
   * and error, so a placeholder/unknown-reference repair is auditable. */
  raw?: string;
  rawChars?: number;
  attempts?: { ms: number; error?: string; rawChars: number }[];
}

export interface PortSubmission {
  inputText: string;
  startedAtMs: number;
  endedAtMs: number | null;
  calls: PortCallRecord[];
  resultsCalls: number;
  updatesCalls: number;
  continuationCalls: number;
  continuationDecision: string | null;
  stops: string[];
  /** Structured settled results of this submission, protagonist group first.
   * 06 shows them per point; 02 writes the result sentence from them. */
  settledFacts?: SettledFact[];
}

export interface SettlementPortSummary {
  submissions: number;
  calls: PortCallRecord[];
  totalMs: number;
  byTask: Record<string, { calls: number; modelCalls: number; ms: number; fallbacks: number }>;
}

export interface SettlementModelPort extends WorldModelPort {
  /** Every fact settled so far for the current point, with the protagonist's
   * own group first. This is settlement input (six stages, next-turn world
   * knowledge), NOT a prose contract: the runtime shows the model's own prose
   * unchanged and never verifies or rewrites it against these sentences
   * (2026-11-11 raw-output decision).
   *
   * No `名字：` prefix: a label turns a fact into `路明非：路明非沿着…`, a
   * speaker-label leak that is not a fact about the world. */
  settledFactLines(): string[];
  /** Structured settled results for the same point, protagonist group first.
   * Each record names the executor, the recipient (when any), the performed
   * action and one of the four outcome directions. The page/02 use these to
   * describe what happened without parsing the prose sentence. */
  settledFacts(): SettledFact[];
  /** Start a new player-submission account. Called by the page right before it
   * hands the text to the session; the port does not consume the text. */
  beginSubmission(inputText: string): void;
  /** Close the account and return it. Safe to call when no submission is open. */
  endSubmission(): PortSubmission | null;
  summary(): SettlementPortSummary;
  /** The automatic proposal the last continuation accepted, in the order the
   * model proposed it. The action lane must freeze THIS text as the automatic
   * point's action; without it the 0.6B wrote the previous point's result
   * sentence again (9711 turn 4, 10turn-4b1e turn 6: proposal «向诺诺问清红蓝两方
   * 局势», frozen action «林亦舟蹲下，掀开路明非的袖口查看伤口»). Empty after a
   * handback and after a new player submission. Evidence only: it never
   * changes settlement, and the port does not verify the action lane against
   * it beyond the no-progress account in `roundProgress`. */
  acceptedProposal(): { characterId: string; text: string }[];
  /** Drop one proposal after the action lane froze it, so a second automatic
   * point in the same round is not handed the same proposal twice. The
   * no-progress account keeps its own copy and is unaffected. */
  consumeProposal(characterId: string): void;
  reset(): void;
}

/** One settled result record, as committed by the results stage. */
export interface SettledFact {
  text: string;
  memberIds: string[];
  actorId: string;
  targetId?: string;
  action?: string;
  outcome: ResultOutcome;
  actorSource: 'model' | 'derived';
  outcomeSource: 'model' | 'derived';
  /** The actor's judgement row was missing; a derived outcome is not asserted. */
  implicit?: true;
  playerGroup: boolean;
}

export interface SettlementPortOptions extends SettlementOptions {
  /** Port for every task this lane does not own (action/targets/reaction,
   * narration, initial, time, pointPlan). Missing handlers surface a clear
   * error instead of inventing an answer. */
  fallback?: WorldModelPort | null;
  now?: () => number;
}

const OWNED: SettlementTask[] = ['results', 'updates', 'continuation'];

export function createSettlementModelPort(
  engine: InferenceEngine,
  options: SettlementPortOptions = {},
): SettlementModelPort {
  const now = options.now ?? (() => (typeof performance === 'undefined' ? Date.now() : performance.now()));
  /** Per-point settled facts, in settlement order. Cleared when the round ends
   * (continuation) and when a submission starts. */
  let settledLines: { playerGroup: boolean; line: string }[] = [];
  let settledRecords: SettledFact[] = [];
  const portOptions: SettlementPortOptions = { ...options, requireTaskSupport: true };
  const updates: UpdatesRunner = createUpdatesRunner(engine, portOptions);
  const continuation = new ContinuationRunner(engine, options);
  const calls: PortCallRecord[] = [];
  let submission: PortSubmission | null = null;

  let roundStartState: WorldState | null = null;
  let roundActionTexts: string[] = [];
  /** The automatic proposal that the last continuation accepted, if any. The
   * next point's frozen action must be about that proposal; when it is not, the
   * action lane handed the point a stale action (10turn 9711 turn 4). */
  let acceptedProposal: { characterId: string; text: string }[] = [];
  /** Same rows, kept for the no-progress account after the action lane consumed
   * the proposal (see `consumeProposal`). */
  let settledProposal: { characterId: string; text: string }[] = [];
  /** Facts already settled by automatic points in this submission. A point
   * whose facts restate one of them did not move the story, however the model
   * worded it (9711 turn 4 settled the same wound-check sentence twice). */
  let automaticFacts: string[] = [];
  let roundFacts: string[] = [];
  const consumedActions = new Set<string>();
  const consumedFacts = new Set<string>();

  function record(task: ModelTask, key: Id, outcome: SettlementOutcome<unknown>, stage: string | null): void {
    const record: PortCallRecord = {
      task,
      key,
      stage,
      ms: outcome.ms,
      promptChars: outcome.evidence.calls.reduce((sum, call) => sum + call.prompt.length, 0),
      fallback: outcome.fallback,
      error: outcome.error,
      calls: outcome.evidence.calls.length,
      evidenceCalls: outcome.evidence.calls.filter((call) => !call.error).length,
    };
    const detail = outcome.evidence.detail as {
      stages?: { stage?: string }[];
      taskCoverageIds?: unknown[];
      personalityCoverageIds?: unknown[];
    } | null;
    if (Array.isArray(detail?.stages)) {
      record.stages = detail.stages.map((row) => String(row.stage));
      const stageMs: Record<string, number> = {};
      for (const row of detail.stages) {
        const stage = String(row.stage ?? '');
        const ms = Number((row as { ms?: unknown }).ms);
        if (stage && Number.isFinite(ms)) stageMs[stage] = Math.round(ms);
      }
      if (Object.keys(stageMs).length) record.stageMs = stageMs;
    }
    const scope = (outcome.evidence.detail as { taskScope?: {
      taskRows?: unknown; mode?: unknown; achievedByCharacter?: unknown; assertedUnchanged?: unknown; rejectedTaskIds?: unknown; supports?: unknown;
      affectedCharacters?: unknown; unaffectedCharacters?: unknown; affectedTaskIds?: unknown; unaffectedTaskIds?: unknown;
    } } | null)?.taskScope;
    if (Array.isArray(detail?.taskCoverageIds) || Array.isArray(detail?.personalityCoverageIds) || scope) {
      record.coverage = {
        tasks: detail?.taskCoverageIds?.length ?? 0,
        personality: detail?.personalityCoverageIds?.length ?? 0,
        ...(Number.isFinite(Number(scope?.taskRows)) ? { taskRows: Number(scope?.taskRows) } : {}),
        ...(typeof scope?.mode === 'string' ? { mode: scope.mode } : {}),
        ...(Array.isArray(scope?.achievedByCharacter)
          ? { achievedByCharacter: scope.achievedByCharacter as { characterId: string; taskIds: string[] }[] }
          : {}),
        ...(Number.isFinite(Number(scope?.assertedUnchanged)) ? { assertedUnchanged: Number(scope?.assertedUnchanged) } : {}),
        ...(Number.isFinite(Number(scope?.affectedCharacters)) ? { affectedCharacters: Number(scope?.affectedCharacters) } : {}),
        ...(Array.isArray(scope?.unaffectedCharacters) ? { unaffectedCharacters: scope.unaffectedCharacters as string[] } : {}),
        ...(Array.isArray(scope?.affectedTaskIds) ? { affectedTaskIds: scope.affectedTaskIds as string[] } : {}),
        ...(Array.isArray(scope?.unaffectedTaskIds) ? { unaffectedTaskIds: scope.unaffectedTaskIds as string[] } : {}),
        ...(Array.isArray(scope?.rejectedTaskIds)
          ? { rejectedTaskIds: scope.rejectedTaskIds as { characterId: string; taskId: string; reason: string }[] }
          : {}),
        ...(Array.isArray(scope?.supports)
          ? { supports: scope.supports as { characterId: string; taskId: string; basis: string }[] }
          : {}),
      };
    }
    if (task === 'results' && !outcome.error) {
      const settled = outcome.evidence.detail as {
        facts?: SettledFact[];
        droppedFacts?: { memberIds?: string[]; reason?: string; original?: string }[];
        outcomeAdjusted?: { actorId?: string; written?: string; derived?: string; why?: string }[];
        implicitJudgments?: string[];
        duplicateJudgments?: { memberId: string; label: string; reason: string }[];
        effectsAdjusted?: { memberId?: string; targetId?: string; written?: boolean; frozen?: boolean }[];
        ownershipAdjusted?: { from?: string; to?: string; item?: string }[];
        firstPersonAdjusted?: { original?: string; text?: string }[];
      } | null;
      if (Array.isArray(settled?.facts)) {
        record.facts = settled.facts.map((fact) => ({
          text: String(fact.text),
          memberIds: (fact.memberIds ?? []).map(String),
          actorId: String(fact.actorId),
          ...(fact.targetId ? { targetId: String(fact.targetId) } : {}),
          ...(fact.action ? { action: String(fact.action) } : {}),
          outcome: fact.outcome,
          actorSource: fact.actorSource,
          outcomeSource: fact.outcomeSource,
          ...(fact.implicit ? { implicit: true as const } : {}),
        }));
      }
      if (Array.isArray(settled?.droppedFacts) && settled.droppedFacts.length) {
        record.droppedFacts = settled.droppedFacts.map((row) => ({
          memberIds: (row.memberIds ?? []).map(String),
          reason: String(row.reason ?? ''),
          original: String(row.original ?? ''),
        }));
      }
      if (Array.isArray(settled?.outcomeAdjusted) && settled.outcomeAdjusted.length) {
        record.outcomeAdjusted = settled.outcomeAdjusted.map((row) => ({
          actorId: String(row.actorId ?? ''),
          written: String(row.written ?? ''),
          derived: String(row.derived ?? ''),
          why: String(row.why ?? ''),
        }));
      }
      if (Array.isArray(settled?.duplicateJudgments) && settled.duplicateJudgments.length) {
        record.duplicateJudgments = settled.duplicateJudgments;
      }
      if (Array.isArray(settled?.implicitJudgments) && settled.implicitJudgments.length) {
        record.implicitJudgments = settled.implicitJudgments.map(String);
      }
      if (Array.isArray(settled?.effectsAdjusted) && settled.effectsAdjusted.length) {
        record.effectsAdjusted = settled.effectsAdjusted.map((row) => ({
          memberId: String(row.memberId ?? ''),
          targetId: String(row.targetId ?? ''),
          written: row.written === true,
          frozen: row.frozen === true,
        }));
      }
      if (Array.isArray(settled?.ownershipAdjusted) && settled.ownershipAdjusted.length) {
        record.ownershipAdjusted = settled.ownershipAdjusted.map((row) => ({
          from: String(row.from ?? ''), to: String(row.to ?? ''), item: String(row.item ?? ''),
        }));
      }
      if (Array.isArray(settled?.firstPersonAdjusted) && settled.firstPersonAdjusted.length) {
        record.firstPersonAdjusted = settled.firstPersonAdjusted.map((row) => String(row.text ?? ''));
      }
    }
    const progress = (outcome.evidence.detail as { roundProgress?: RoundProgressEvidence } | null)?.roundProgress;
    if (progress) record.roundProgress = progress;
    if (outcome.error) {
      record.raw = outcome.evidence.raw.slice(0, 4000);
      record.rawChars = outcome.evidence.raw.length;
      record.attempts = outcome.evidence.calls.map((call) => ({
        ms: Math.round(call.ms),
        error: call.error,
        rawChars: call.raw.length,
      }));
    }
    calls.push(record);
    if (submission) {
      submission.calls.push(record);
      if (task === 'results') submission.resultsCalls += 1;
      if (task === 'updates') submission.updatesCalls += 1;
      if (task === 'continuation') {
        submission.continuationCalls += 1;
        const detail = outcome.evidence.detail as { decision?: string } | null;
        submission.continuationDecision = detail?.decision ?? null;
      }
      if (outcome.error) submission.stops.push(`${task}:${outcome.error}`);
    }
  }

  function unwrap<T>(task: SettlementTask, key: Id, stage: string | null, outcome: SettlementOutcome<T>): T {
    record(task, key, outcome, stage);
    if (outcome.value == null) {
      throw new Error(`settlement_failed:${task}:${outcome.error ?? 'no_candidate'}`);
    }
    return outcome.value;
  }

  function captureRoundStart(input: Json): void {
    if (roundStartState) return;
    const state = stateOf(input);
    if (state) roundStartState = structuredClone(state);
  }

  function captureResults(input: Json, value: unknown, detail?: Json): void {
    captureRoundStart(input);
    if (input != null && typeof input === 'object' && !Array.isArray(input)) {
      const members = (input as { members?: unknown }).members;
      if (Array.isArray(members)) {
        for (const member of members) {
          if (member == null || typeof member !== 'object') continue;
          const text = (member as { actionText?: unknown }).actionText;
          const memberId = (member as { memberId?: unknown }).memberId;
          if (typeof text === 'string' && text.trim()) {
            // Identity includes the actor: two characters may legitimately use
            // the same short phrase, and that is not a replayed action.
            const label = typeof memberId === 'string' && memberId.trim()
              ? `${memberId.trim()}:${text.trim()}`
              : text.trim();
            roundActionTexts.push(label);
          }
        }
      }
    }
    if (value != null && typeof value === 'object' && !Array.isArray(value)) {
      const state = (input as { workingState?: WorldState }).workingState;
      const player = state?.protagonistId ?? null;
      const members = (input as { members?: unknown }).members;
      const groupIds = Array.isArray(members)
        ? members.map((member) => (member != null && typeof member === 'object' ? (member as { memberId?: unknown }).memberId : null))
          .filter((id): id is string => typeof id === 'string')
        : [];
      const playerGroup = Boolean(player && groupIds.includes(player));
      for (const fact of Object.values(value as Record<string, unknown>)) {
        if (typeof fact !== 'string' || !fact.trim()) continue;
        roundFacts.push(fact.trim());
        settledLines.push({ playerGroup, line: fact.trim() });
      }
      const detailRecord = detail != null && typeof detail === 'object' && !Array.isArray(detail)
        ? detail as Record<string, unknown> : {};
      const structured = Array.isArray(detailRecord.facts) ? detailRecord.facts : [];
      for (const row of structured) {
        if (row == null || typeof row !== 'object') continue;
        const fact = row as Partial<SettledFact>;
        if (typeof fact.text !== 'string' || !fact.text.trim()) continue;
        if (!Array.isArray(fact.memberIds) || !fact.memberIds.length) continue;
        if (typeof fact.actorId !== 'string' || !fact.actorId) continue;
        if (typeof fact.outcome !== 'string') continue;
        settledRecords.push({
          text: fact.text.trim(),
          memberIds: fact.memberIds.map(String),
          actorId: fact.actorId,
          ...(typeof fact.targetId === 'string' && fact.targetId ? { targetId: fact.targetId } : {}),
          ...(typeof fact.action === 'string' && fact.action ? { action: fact.action } : {}),
          outcome: fact.outcome as ResultOutcome,
          actorSource: fact.actorSource === 'model' ? 'model' : 'derived',
          outcomeSource: fact.outcomeSource === 'model' ? 'model' : 'derived',
          ...(fact.implicit === true ? { implicit: true as const } : {}),
          playerGroup,
        });
      }
      // The point's facts must survive the round: continuation clears the live
      // list, so a submission snapshot taken at endSubmission() used to be empty
      // (bed9de41's run recorded settledFacts: null although two groups had
      // settled). Keep the current point's copy on the open submission.
      if (submission) {
        const facts = settledFacts();
        if (facts.length) submission.settledFacts = facts;
      }
    }
  }

  function settledFacts(): SettledFact[] {
    const ordered = [
      ...settledRecords.filter((entry) => entry.playerGroup),
      ...settledRecords.filter((entry) => !entry.playerGroup),
    ];
    const seen = new Set<string>();
    return ordered.filter((entry) => {
      if (seen.has(entry.text)) return false;
      seen.add(entry.text);
      return true;
    });
  }

  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      if (task === 'results') {
        const outcome = await runResults(engine, key, input, options);
        const value = unwrap('results', key, null, outcome);
        captureResults(input, value, outcome.evidence.detail);
        return value as unknown as Json;
      }
      if (task === 'updates') {
        const stage = readStage(input);
        captureRoundStart(input);
        const outcome = await updates.run(key, input);
        return unwrap('updates', key, stage, outcome) as unknown as Json;
      }
      if (task === 'continuation') {
        const before = roundStartState;
        const after = stateOf(input);
        let enriched = input;
        if (before && after) {
          const computed = await roundProgressFromState({
            before,
            after,
            facts: roundFacts,
            actions: roundActionTexts,
            knownFacts: consumedFacts,
            knownActions: consumedActions,
            // The controller applies time before settlement, so the before
            // snapshot may already contain the new clock. The settled point's
            // timeAdvance is the authoritative event and must still count.
            timeAdvanced: roundAdvancedTime(input),
            // 10turn turns 8-10: an automatic point proposed «在器材棚内寻找
            // 护目镜» and the results lane settled «检查了相机备用电池»; because
            // every point also advanced the clock, each one counted as progress
            // and the chain ran five points (330 s) repeating the same beat. An
            // automatic round only progresses if its facts cover its proposal.
            ...(readTrigger(input) === 'automatic'
              ? {
                actionSettled: settledCoversActions(roundActionTexts, settledRecords, after)
                  && actionFollowsProposal(settledProposal, roundActionTexts, after)
                  && !restatesAutomaticFact(roundFacts, automaticFacts),
              }
              : {}),
          });
          for (const action of computed.newActions) consumedActions.add(action);
          for (const fact of computed.newFacts) consumedFacts.add(fact);
          enriched = {
            ...(input as Record<string, unknown>),
            roundProgress: computed.evidence,
          } as unknown as Json;
        }
        try {
          const outcome = await continuation.run(key, enriched);
          // Remember what the accepted proposal was about, so the next point can
          // check that its frozen action is that proposal and not an old sentence.
          const detail = outcome.evidence.detail as { candidates?: { characterId?: string; text?: string }[]; accepted?: { characterId?: string; text?: string }[] } | null;
          const acceptedIds = new Set(
            (Array.isArray(detail?.accepted) ? detail.accepted : [])
              .map((row) => row?.characterId)
              .filter((id): id is string => typeof id === 'string'),
          );
          const candidates = Array.isArray(detail?.candidates) ? detail.candidates : [];
          acceptedProposal = candidates
            .filter((row) => typeof row?.characterId === 'string' && typeof row?.text === 'string'
              && (acceptedIds.size === 0 || acceptedIds.has(row.characterId)))
            .map((row) => ({ characterId: row.characterId as string, text: row.text as string }));
          settledProposal = acceptedProposal.map((row) => ({ ...row }));
          if (readTrigger(input) === 'automatic') {
            for (const fact of roundFacts) automaticFacts.push(fact);
          }
          // The controller only accepts a Conclusion value; a null value is a
          // visible stop (policy rule or model failure), never a handback.
          return unwrap('continuation', key, null, outcome) as unknown as Json;
        } finally {
          roundStartState = null;
          roundActionTexts = [];
          roundFacts = [];
          // The round's point is over; the next results call starts a new one.
          settledLines = [];
          settledRecords = [];
        }
      }
      if (options.fallback) return options.fallback.generate(task, key, input);
      throw new Error(`settlement_port_has_no_handler:${task}`);
    },

    settledFacts,

    settledFactLines(): string[] {
      const ordered = [
        ...settledLines.filter((entry) => entry.playerGroup),
        ...settledLines.filter((entry) => !entry.playerGroup),
      ];
      const seen = new Set<string>();
      return ordered.map((entry) => entry.line).filter((line) => {
        if (seen.has(line)) return false;
        seen.add(line);
        return true;
      });
    },

    beginSubmission(inputText: string): void {
      // A new player submission is a new chain: candidate identity, round
      // progress and the policy streak all start fresh. Resetting here is what
      // lets a later turn legitimately repeat an action that was consumed in
      // the previous turn.
      continuation.reset();
      automaticFacts = [];
      acceptedProposal = [];
      settledProposal = [];
      roundStartState = null;
      roundActionTexts = [];
      roundFacts = [];
      consumedActions.clear();
      consumedFacts.clear();
      settledLines = [];
      settledRecords = [];
      submission = {
        inputText,
        startedAtMs: now(),
        endedAtMs: null,
        calls: [],
        resultsCalls: 0,
        updatesCalls: 0,
        continuationCalls: 0,
        continuationDecision: null,
        stops: [],
      };
    },

    endSubmission(): PortSubmission | null {
      if (!submission) return null;
      submission.endedAtMs = now();
      const facts = settledFacts();
      if (facts.length) submission.settledFacts = facts;
      const done = submission;
      submission = null;
      return done;
    },

    summary(): SettlementPortSummary {
      const byTask: SettlementPortSummary['byTask'] = {};
      for (const call of calls) {
        const row = byTask[call.task] ?? { calls: 0, modelCalls: 0, ms: 0, fallbacks: 0 };
        row.calls += 1;
        row.modelCalls += call.calls;
        row.ms += call.ms;
        if (call.fallback) row.fallbacks += 1;
        byTask[call.task] = row;
      }
      return {
        submissions: calls.length ? 1 : 0,
        calls: [...calls],
        totalMs: calls.reduce((sum, call) => sum + call.ms, 0),
        byTask,
      };
    },

    acceptedProposal(): { characterId: string; text: string }[] {
      return acceptedProposal.map((row) => ({ ...row }));
    },

    consumeProposal(characterId: string): void {
      acceptedProposal = acceptedProposal.filter((row) => row.characterId !== characterId);
    },

    reset(): void {
      calls.length = 0;
      submission = null;
      settledLines = [];
      settledRecords = [];
      roundStartState = null;
      roundActionTexts = [];
      roundFacts = [];
      consumedActions.clear();
      consumedFacts.clear();
      updates.reset();
      continuation.reset();
    },
  };
}

function stateOf(input: Json): WorldState | null {
  if (input == null || typeof input !== 'object' || Array.isArray(input)) return null;
  const state = (input as { workingState?: unknown }).workingState;
  return state != null && typeof state === 'object' ? state as WorldState : null;
}

function roundAdvancedTime(input: Json): boolean {
  if (input == null || typeof input !== 'object' || Array.isArray(input)) return false;
  const points = (input as { roundChanges?: unknown }).roundChanges;
  if (!Array.isArray(points)) return false;
  return points.some((point) => {
    if (point == null || typeof point !== 'object' || Array.isArray(point)) return false;
    const advance = (point as { timeAdvance?: unknown }).timeAdvance;
    if (advance == null || typeof advance !== 'object' || Array.isArray(advance)) return false;
    const duration = (advance as { duration?: unknown }).duration;
    if (duration == null || typeof duration !== 'object' || Array.isArray(duration)) return false;
    const amount = (duration as { amount?: unknown }).amount;
    return typeof amount === 'number' && Number.isFinite(amount) && amount > 0;
  });
}

function readTrigger(input: Json): string | null {
  if (input == null || typeof input !== 'object' || Array.isArray(input)) return null;
  const round = (input as { round?: unknown }).round;
  if (round == null || typeof round !== 'object' || Array.isArray(round)) return null;
  const trigger = (round as { trigger?: unknown }).trigger;
  return typeof trigger === 'string' ? trigger : null;
}

/** Did this point's settled facts cover the action the point proposed? Shared
 * content is a run of three or more characters, or a world entity name of two
 * or more characters. A proposal settled as something else did not happen. */
function settledCoversActions(
  actions: string[],
  records: SettledFact[],
  state: WorldState,
): boolean {
  if (!actions.length) return true;
  const names = [
    ...Object.values(state.initial.locations ?? {}).map((row) => row?.name),
    ...Object.values(state.initial.items ?? {}).map((row) => row?.name),
    ...Object.values(state.initial.characters ?? {}).map((row) => row?.name),
  ].filter((name): name is string => typeof name === 'string' && name.length >= 2);
  for (const label of actions) {
    const separator = label.indexOf(':');
    const memberId = separator > 0 ? label.slice(0, separator) : '';
    const action = separator > 0 ? label.slice(separator + 1) : label;
    const own = records.filter((record) => !memberId || record.memberIds.includes(memberId));
    const covered = own.some((record) => sharesContent(action, record.text, names));
    if (!covered) return false;
  }
  return true;
}

/** The point's frozen action must be about the proposal the continuation just
 * accepted. 10turn 9711 turn 4: fingel was proposed «确认护目镜佩戴情况», and the
 * action lane froze «芬格尔蹲下，掀开路明非的袖口查看伤口» — the previous point's
 * result with a new subject — so results settled that old sentence again and the
 * chain ran four points to the 300 s deadline. A proposal that the action does
 * not mention means the point is not the event the chain asked for. */
function actionFollowsProposal(
  proposal: { characterId: string; text: string }[],
  actions: string[],
  state: WorldState,
): boolean {
  if (!proposal.length || !actions.length) return true;
  const names = [
    ...Object.values(state.initial.locations ?? {}).map((row) => row?.name),
    ...Object.values(state.initial.items ?? {}).map((row) => row?.name),
    ...Object.values(state.initial.characters ?? {}).map((row) => row?.name),
  ].filter((name): name is string => typeof name === 'string' && name.length >= 2);
  for (const label of actions) {
    const separator = label.indexOf(':');
    const memberId = separator > 0 ? label.slice(0, separator) : '';
    const action = separator > 0 ? label.slice(separator + 1) : label;
    const own = proposal.filter((row) => !memberId || row.characterId === memberId);
    if (!own.length) continue;
    if (!own.some((row) => sharesContent(row.text, action, names))) return false;
  }
  return true;
}

/** Does one of this point's facts restate a fact an automatic point already
 * settled? Containment (shared character bigrams over the smaller set) >= 0.85
 * catches a reworded repeat (9711: «芬格尔蹲下并掀开路明非的袖口查看伤口» after
 * «芬格尔掀开路明非的袖口查看伤口» = 0.93) while a reworded question (0.71) or a
 * different finding in the same place (0.60) stays below it. */
function restatesAutomaticFact(facts: string[], earlier: string[]): boolean {
  if (!facts.length || !earlier.length) return false;
  const bigrams = (text: string): Set<string> => {
    const chars = [...text.replace(/[\s，。；：、！？…—,.!?:;'"“”‘’（）()]/gu, '')];
    const set = new Set<string>();
    for (let index = 0; index + 2 <= chars.length; index += 1) set.add(chars.slice(index, index + 2).join(''));
    return set;
  };
  for (const fact of facts) {
    const mine = bigrams(fact);
    if (!mine.size) continue;
    for (const other of earlier) {
      const theirs = bigrams(other);
      let shared = 0;
      for (const gram of mine) if (theirs.has(gram)) shared += 1;
      const smaller = Math.min(mine.size, theirs.size);
      if (smaller > 0 && shared / smaller >= 0.85) return true;
    }
  }
  return false;
}

function sharesContent(action: string, fact: string, names: string[]): boolean {
  if (names.some((name) => action.includes(name) && fact.includes(name))) return true;
  const chars = [...action];
  for (let index = 0; index + 3 <= chars.length; index += 1) {
    if (fact.includes(chars.slice(index, index + 3).join(''))) return true;
  }
  return false;
}

function readStage(input: Json): string | null {
  if (input == null || typeof input !== 'object' || Array.isArray(input)) return null;
  const stage = (input as Record<string, unknown>).stage;
  return typeof stage === 'string' ? stage : null;
}

export type { SettlementConclusion };
export { OWNED as SETTLEMENT_PORT_TASKS };
