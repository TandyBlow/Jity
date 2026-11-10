/** Public types for the settlement lane. The handler output schemas are the
 * existing model-task schemas: results = Record<Id, string>, updates =
 * UpdatesCall (split stage) or UpdatesCall[] (one merged call), continuation =
 * Conclusion. Evidence is additive and never becomes a world fact. */
import type { Id, Json } from '../../../types';
import type { UpdatesCall, UpdatesStage } from '../../../schedule';
import type { InferenceEngine } from '../../../runtime/engine';

export type SettlementTask = 'results' | 'updates' | 'continuation';

export interface ContinuationPolicyOptions {
  /** Consecutive auto rounds with no committed entity change before a policy
   * handback. This is a no-progress rule, not a call-count limit. */
  noProgressRounds?: number;
  /** Consecutive identical accepted candidate sets before a policy handback.
   * A changed state with the same literal follow-up is still a loop. */
  repeatRounds?: number;
  /** Optional runaway safety ceiling. null (the default) means continuation
   * is never closed by a call count; normal handback is decided by the model
   * plus the no-progress/repeat rules above. */
  maxAutoContinuations?: number | null;
  /** Maximum candidate follow-ups the model may propose in one assessment. */
  maxCandidates?: number;
}

export interface SettlementOptions {
  continuation?: ContinuationPolicyOptions;
  maxTokens?: Partial<Record<SettlementTask, number>>;
  temperature?: number;
  timeoutMs?: number;
  /** Reject a prompt that does not fit instead of silently truncating state. */
  maxPromptChars?: number;
  /** New task budget for one updates call. Exceeding it is a visible failure,
   * never a partial success. */
  maxNewTasks?: number;
  /** Test/embedded allocator for the automatic round identity. The default
   * uses a timestamp plus a local counter. */
  nextRoundId?: () => Id;
  onTask?: (task: SettlementTask, key: string, detail: ModelTaskDetail) => void;
}

export interface ModelTaskDetail {
  ms: number;
  fallback: boolean;
  error?: string;
  raw?: string;
  promptChars?: number;
}

export interface ModelCallEvidence {
  prompt: string;
  raw: string;
  ms: number;
  attempt: number;
  error?: string;
}

export interface SettlementEvidence {
  task: SettlementTask;
  key: string;
  raw: string;
  ms: number;
  fallback: boolean;
  error?: string;
  calls: ModelCallEvidence[];
  /** Lane-specific structural/coverage evidence. Never committed as state. */
  detail: Json;
}

/** value=null means no candidate may be committed (hard input/protocol/model
 * failure). results/updates may return a conservative no-change candidate with
 * fallback=true and an error; continuation never converts failure to handback. */
export interface SettlementOutcome<T> {
  value: T | null;
  raw: string;
  ms: number;
  fallback: boolean;
  error?: string;
  evidence: SettlementEvidence;
}

export interface SettlementHandlers {
  results(key: Id, input: Json): Promise<SettlementOutcome<Record<Id, string>>>;
  updates(key: Id, input: Json): Promise<SettlementOutcome<SettlementUpdates>>;
  continuation(key: Id, input: Json): Promise<SettlementOutcome<SettlementConclusion>>;
  /** Clear no-progress/repeat streaks and the local continuation counter. */
  resetContinuation(): void;
  /** Clear all in-flight batch memory. The controller owns committed state. */
  reset(): void;
}

/** The existing schedule output shapes, imported rather than redefined. */
export type SettlementUpdates = UpdatesCall[] | UpdatesCall;

export type SettlementConclusion =
  | { kind: 'continue'; closedBy: 'model'; cancelReason: null; candidateCharacterIds: Id[]; nextRoundId: Id }
  | { kind: 'handback'; closedBy: 'model'; cancelReason: null };

export type { UpdatesCall, UpdatesStage };

export interface SettlementConfig {
  engine: InferenceEngine;
  options?: SettlementOptions;
}
