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
}

export interface SettlementPortSummary {
  submissions: number;
  calls: PortCallRecord[];
  totalMs: number;
  byTask: Record<string, { calls: number; modelCalls: number; ms: number; fallbacks: number }>;
}

export interface SettlementModelPort extends WorldModelPort {
  /** Every fact settled so far for the current point, verbatim, with the
   * protagonist's own group first. A reaction group answers after the player's
   * group and used to overwrite the player's result in the caller's single
   * `lastResultsText` slot, so the walk/read outcome never reached narration
   * and the result beat was composed from nothing.
   *
   * No `名字：` prefix: the constrained result fact is verified as a sentence
   * that must appear in the prose verbatim, and a label turns it into
   * `路明非：路明非沿着…` — the same speaker-label leak that reached the page
   * from the labeled results lines. */
  settledFactLines(): string[];
  /** Start a new player-submission account. Called by the page right before it
   * hands the text to the session; the port does not consume the text. */
  beginSubmission(inputText: string): void;
  /** Close the account and return it. Safe to call when no submission is open. */
  endSubmission(): PortSubmission | null;
  summary(): SettlementPortSummary;
  reset(): void;
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
  const portOptions: SettlementPortOptions = { ...options, requireTaskSupport: true };
  const updates: UpdatesRunner = createUpdatesRunner(engine, portOptions);
  const continuation = new ContinuationRunner(engine, options);
  const calls: PortCallRecord[] = [];
  let submission: PortSubmission | null = null;

  let roundStartState: WorldState | null = null;
  let roundActionTexts: string[] = [];
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

  function captureResults(input: Json, value: unknown): void {
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
    }
  }

  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      if (task === 'results') {
        const outcome = await runResults(engine, key, input, options);
        const value = unwrap('results', key, null, outcome);
        captureResults(input, value);
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
          // The controller only accepts a Conclusion value; a null value is a
          // visible stop (policy rule or model failure), never a handback.
          return unwrap('continuation', key, null, outcome) as unknown as Json;
        } finally {
          roundStartState = null;
          roundActionTexts = [];
          roundFacts = [];
          // The round's point is over; the next results call starts a new one.
          settledLines = [];
        }
      }
      if (options.fallback) return options.fallback.generate(task, key, input);
      throw new Error(`settlement_port_has_no_handler:${task}`);
    },

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
      roundStartState = null;
      roundActionTexts = [];
      roundFacts = [];
      consumedActions.clear();
      consumedFacts.clear();
      settledLines = [];
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

    reset(): void {
      calls.length = 0;
      submission = null;
      settledLines = [];
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

function readStage(input: Json): string | null {
  if (input == null || typeof input !== 'object' || Array.isArray(input)) return null;
  const stage = (input as Record<string, unknown>).stage;
  return typeof stage === 'string' ? stage : null;
}

export type { SettlementConclusion };
export { OWNED as SETTLEMENT_PORT_TASKS };
