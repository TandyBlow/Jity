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
import type { Id, Json } from '../../types';
import type { InferenceEngine } from '../../runtime/engine';
import type { ModelTask } from '../../schedule';
import type { WorldModelPort } from '../../controller';
import { runResults } from '../semantics/settlement/results';
import { createUpdatesRunner, type UpdatesRunner } from '../semantics/settlement/updates';
import { ContinuationRunner } from '../semantics/settlement/continuation';
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
  const updates: UpdatesRunner = createUpdatesRunner(engine, options);
  const continuation = new ContinuationRunner(engine, options);
  const calls: PortCallRecord[] = [];
  let submission: PortSubmission | null = null;

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

  return {
    async generate(task: ModelTask, key: string, input: Json): Promise<Json> {
      if (task === 'results') {
        return unwrap('results', key, null, await runResults(engine, key, input, options)) as unknown as Json;
      }
      if (task === 'updates') {
        const stage = readStage(input);
        const outcome = await updates.run(key, input);
        return unwrap('updates', key, stage, outcome) as unknown as Json;
      }
      if (task === 'continuation') {
        const outcome = await continuation.run(key, input);
        // The controller only accepts a Conclusion value; a null value is a
        // visible stop (policy rule or model failure), never a handback.
        return unwrap('continuation', key, null, outcome) as unknown as Json;
      }
      if (options.fallback) return options.fallback.generate(task, key, input);
      throw new Error(`settlement_port_has_no_handler:${task}`);
    },

    beginSubmission(inputText: string): void {
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
      updates.reset();
      continuation.reset();
    },
  };
}

function readStage(input: Json): string | null {
  if (input == null || typeof input !== 'object' || Array.isArray(input)) return null;
  const stage = (input as Record<string, unknown>).stage;
  return typeof stage === 'string' ? stage : null;
}

export type { SettlementConclusion };
export { OWNED as SETTLEMENT_PORT_TASKS };
