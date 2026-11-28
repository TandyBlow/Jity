/** Public types for the settlement lane. The handler output schemas are the
 * existing model-task schemas: results = Record<Id, string>, updates =
 * UpdatesCall (split stage) or UpdatesCall[] (one merged call), continuation =
 * Conclusion. Evidence is additive and never becomes a world fact. */
import type { EntityDelta, Id, Json, TimeAdvance, WorldState } from '../../../types';
import type { UpdatesCall, UpdatesStage } from '../../../schedule';
import type { InferenceEngine } from '../../../runtime/engine';
import type { AcceptedContinuationEvent } from '../../micro/events';
import type { RoundProgressEvidence } from './support';

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
  /** Strict micro-only arm (S06): no semantic LLM may be called; stages that
   * would fall back to the model return a recorded conservative result. */
  microOnly?: boolean;
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
  /** Evaluation arm: state the unknown-target rule explicitly in the results
   * prompt (untargeted entity ⇒ not_achieved/blocked). Default off. */
  unknownEntityRule?: boolean;
  /** Evaluation arm: list only the actors/items named by the action in the
   * results prompt instead of the whole visible scene (mobile prefill cut). */
  compactPrompts?: boolean;
  /** Evaluation arm: a worked blocked example for an unknown target. */
  unknownEntityExample?: boolean;
  /** Deterministic guard (default on): a results fact naming an unregistered
   * entity fails validation and is retried; pass false to reproduce old runs. */
  strictKnownEntities?: boolean;
  onTask?: (task: SettlementTask, key: string, detail: ModelTaskDetail) => void;
  /** Experimental micro workflow: a task head answers results before the LLM.
   * Returning null or failing validation falls back to the LLM call. */
  microResults?: MicroResultsFn;
  /** Experimental micro workflow: the movement head answers the position half
   * of the merged scene stage; a null or rejected answer falls back. */
  microUpdates?: MicroUpdatesFn;
  /** Experimental micro workflow: structured event records plus four heads
   * decide continuation before any LLM proposal call. A null answer (model
   * missing/failed) falls back to the existing LLM path. */
  microContinuation?: MicroContinuationFn;
  /** Experimental micro workflow: task/fact verifier. A null or low-confidence
   * answer falls back to the LLM verifier. */
  microTaskVerifier?: MicroTaskVerifierFn;
  /** Experimental micro workflow: condition-level task proposer. It keeps a
   * session ledger and proposes only tasks whose conditions are all supported. */
  microTaskProposer?: MicroTaskProposerFn;
  /** Experimental: goal-level task stage (candidate pairs + goal/fact verifier)
   * that can replace the tasks LLM call when enabled. */
  microGoalTasks?: MicroGoalTasksFn;
  /** Experimental: program/template subtask proposer replacing the subtasks LLM. */
  microSubtasks?: MicroSubtasksFn;
  /** Experimental structured scene arm: apply `去向=` facts directly and skip
   * the merged position prompt when nothing looks uncertain. */
  programScene?: boolean;
  /** Experimental: one small position question per affected entity; any
   * rejection falls back to the merged scene call. */
  localPosition?: boolean;
  /** Product default: a new task achievement must cite a settled result fact
   * (or a time basis). Unit fixtures may leave this off, but the page port
   * never does. */
  requireTaskSupport?: boolean;
  /** How the tasks stage asks for its answer.
   *
   * 'roster': the prompt prints a complete answer that names every affected
   * character under `unchanged`, and the model must reproduce the roster. A 0.6B
   * copies that skeleton: across 171 recorded task-stage answers it never once
   * moved a character out of `unchanged`, and no real 0.6B run produced an
   * achievement either (2/2 probes, 2026-11-11).
   *
   * 'achieved' (default): the model asserts only the characters whose task
   * condition is now met (with a fact basis); the program applies "everyone else
   * unchanged", which is the conservative default it already knows. The same
   * probes achieve the right task under this contract; keep 'roster' only as a
   * comparison arm. */
  tasksContract?: 'roster' | 'achieved';
}

export interface ModelTaskDetail {
  ms: number;
  fallback: boolean;
  error?: string;
  raw?: string;
  promptChars?: number;
  /** Per-stage model time for an updates task, so a slow turn can be attributed
   * without waiting for the whole submission to close. */
  stageMs?: Record<string, number>;
  stages?: string[];
  /** Affected projection for this updates group (which owners/rows were judged). */
  scope?: { mode?: string; affectedCharacters?: number; unaffectedCharacters?: number; affectedTaskIds?: string[]; unaffectedTaskIds?: string[]; taskRows?: number } | null;
  /** Who produced the accepted value: the LLM, a micro model, or a program rule. */
  source?: 'model' | 'micro' | 'rule' | 'program' | 'fallback';
  /** One model attempt inside a task, not the accepted task result. */
  attempt?: boolean;
}

/** Micro results port: the page's task head answers per member; a null answer
 * falls back to the LLM. The returned value goes through the same validators
 * as a model answer (`readResultsAnswer` / known-entity / normalize). */
export interface MicroResultsRequest {
  groupId: Id;
  members: Array<{
    memberId: Id; actionText: string; rolls: Array<{ result: number; eligible: boolean; admitted: boolean }>;
    /** Structured action fields when the action lane produced them. */
    structured?: import('../actions/structure').ActionStructure;
  }>;
  state: WorldState;
}

export interface MicroResultsAnswer {
  judgments: Array<{ memberId: Id; label: string; reason: string }>;
  facts: Array<{ text: string; memberIds: Id[]; actorId?: Id; outcome?: string }>;
}

export type MicroResultsFn = (request: MicroResultsRequest) => Promise<MicroResultsAnswer | null> | MicroResultsAnswer | null;

/** Micro updates port: one movement verdict per scanned entity. Positions are
 * the only half a head can source; appearances stay with the LLM unless the
 * answer supplies them. The returned positions go through `readPositionChanges`
 * and the missing-move check, then the kernel's `projectStage`. */
export interface MicroUpdatesRequest {
  groupId: Id | null;
  results: Record<Id, string>;
  state: WorldState;
  /** Projection's affected movable entities, already validated. */
  scanned: Id[];
  /** Projection's affected appearance entities (informational). */
  appearance: Id[];
}

export interface MicroUpdatesAnswer {
  positions: Array<{ entityId: Id; containerId: Id; slotId?: Id | null }>;
  /** Omitted means the appearance half was not answered here. */
  appearances?: Array<{ entityId: Id; op: string; recordIds: Id[]; text: string | null }>;
}

export type MicroUpdatesFn = (request: MicroUpdatesRequest) => Promise<MicroUpdatesAnswer | null> | MicroUpdatesAnswer | null;

/** Micro continuation port: four judgements decide whether an automatic round
 * follows and which characters act in it. A null answer falls back to the LLM
 * proposal+judgement pair; an explicit handback is a real model decision. */
export interface MicroContinuationScores {
  novelty: number;
  unfinished: number;
  necessity: number;
  intervene: number;
}

export interface MicroContinuationCandidate {
  characterId: Id;
  text: string;
  category: string;
  scores: MicroContinuationScores;
  repeat: 'new' | 'new_world' | 'same_world';
}

export interface MicroContinuationRequest {
  roundId: Id;
  trigger: string;
  state: WorldState;
  roundChanges: Array<{ pointId: Id; timeAdvance: TimeAdvance | null; entityDeltas: Record<Id, EntityDelta> }>;
  roundProgress: RoundProgressEvidence | null;
  /** Follow-ups accepted earlier in this submission/session. */
  history: AcceptedContinuationEvent[];
}

export interface MicroContinuationAnswer {
  decision: 'continue' | 'handback';
  reason: string;
  /** 'rule' is the direct-rule comparison arm; 'micro' ran the heads. */
  source?: 'micro' | 'rule';
  candidates: MicroContinuationCandidate[];
  accepted: MicroContinuationCandidate[];
  rejected: Array<{ characterId: Id; text: string; reason: string }>;
}

export type MicroContinuationFn = (
  request: MicroContinuationRequest,
) => Promise<MicroContinuationAnswer | null> | MicroContinuationAnswer | null;

export interface MicroTaskSupport {
  characterId: Id;
  taskId: Id;
  goal: string;
  ownerName: string;
  factText: string;
  /** Proposer's per-condition model labels; when present the verifier uses
   * them instead of re-checking conditions lexically. */
  conditions?: Array<{ label: string; state: 'none' | 'keyword' | 'attempt' | 'satisfied' }>;
}

export interface MicroTaskVerdict {
  characterId: Id;
  taskId: Id;
  satisfied: 'yes' | 'partial' | 'no';
  confidence: number;
  reason: string;
}

export type MicroTaskVerifierFn = (request: {
  supports: MicroTaskSupport[];
  state: WorldState;
}) => Promise<MicroTaskVerdict[] | null> | MicroTaskVerdict[] | null;

export interface MicroTaskProposerRequest {
  state: WorldState;
  facts: Array<{ id: string; memberId: Id; text: string }>;
}

export interface MicroTaskConditionUpdate {
  taskId: Id;
  conditionId: string;
  label: 'none' | 'keyword' | 'attempt' | 'satisfied';
  factId: string;
  text: string;
}

export interface MicroTaskProposal {
  supports: Array<{
    characterId: Id; taskId: Id; basis: string; basisText?: string;
    conditions?: Array<{ label: string; state: 'none' | 'keyword' | 'attempt' | 'satisfied' }>;
  }>;
  updates: MicroTaskConditionUpdate[];
  pending: Array<{ taskId: Id; matched: number; total: number; missing: string[] }>;
}

export type MicroTaskProposerFn = (
  request: MicroTaskProposerRequest,
) => Promise<MicroTaskProposal | null> | MicroTaskProposal | null;

export interface MicroGoalTasksRequest {
  state: WorldState;
  facts: Array<{ id: string; memberId: Id; text: string }>;
  /** Owners whose tasks the stage may decide; the projection already narrowed
   * the roster, so the port never scans tasks outside the affected set. */
  ownerIds: Id[];
}

export interface MicroGoalTasksResult {
  achieved: Array<{ characterId: Id; taskId: Id; basis: string; score: number }>;
  /** Every scored pair, kept as evidence (never committed to state). */
  scored: Array<{ characterId: Id; taskId: Id; basis: string; score: number }>;
  source: 'micro';
}

/** Goal-level task stage: candidate pairs + a goal/fact verifier, replacing the
 * tasks LLM call. Returning null is a port failure; an empty achieved list is a
 * legitimate "no task changed". */
export type MicroGoalTasksFn = (
  request: MicroGoalTasksRequest,
) => Promise<MicroGoalTasksResult | null> | MicroGoalTasksResult | null;

export interface MicroSubtaskCandidate {
  characterId: Id;
  parentTaskId: Id;
  goal: string;
  basis: string;
}

export interface MicroSubtaskProposal {
  subtasks: MicroSubtaskCandidate[];
  source: 'program' | 'micro';
}

/** Program/template subtask proposer. Returning null is a port failure; an
 * empty list is a legitimate "no new goal this point". */
export type MicroSubtasksFn = (
  request: { state: WorldState; facts: Array<{ id: string; memberId: Id; text: string }>; ownerIds: Id[] },
) => Promise<MicroSubtaskProposal | null> | MicroSubtaskProposal | null;

export interface ModelCallEvidence {
  prompt: string;
  raw: string;
  ms: number;
  attempt: number;
  error?: string;
  /** A truncated/interrupted call keeps its partial text here instead of
   * throwing the paid output away (the task book requires every truncation to
   * be explicit in evidence). */
  truncated?: boolean;
  finishReason?: string | null;
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
 * failure). results and updates abort the point after a failed repair instead
 * of inventing a conservative result or committing empty stage deltas;
 * continuation never converts a failure into a handback. */
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
