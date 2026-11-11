/** Product-facing contracts for narration candidate selection.
 *
 * One settled point goes in; one submitted narration goes out. The selection
 * layer is the only place that decides which candidate writes the scene, and
 * it keeps two things honest:
 *
 *   - the page only submits prose the candidate itself accepted (`adopted`);
 *   - everything else returns `fallback`, so the existing in-model path keeps
 *     producing the text the player already sees today.
 *
 * Candidate identities, model names and verification issue codes are internal
 * evidence. Nothing in this file is rendered to the player.
 */
import type { EntityDelta, Id, TimeAdvance, WorldState } from '../../../types';
import type { CommittedNarration } from '../../../runtime/committed-narration';
import type { CompletionEvidence, InferenceEngine } from '../../../runtime/engine';
import type { BeatSceneContext, NarrationIssue, NarrationPolicy } from '../trained-generation/types';

/** The settled point the controller already hands to `narration()`.
 *
 * `before`/`delta`/`after` are the same records the state kernel sealed; the
 * selection layer projects them read-only and never re-derives a change.
 * `delta.entityDeltas` is the sealed delta of this point only.
 */
export interface NarrationPoint {
  pointId: Id;
  before: WorldState | null;
  delta: { timeAdvance?: TimeAdvance | null; entityDeltas?: Record<Id, EntityDelta> };
  after: WorldState;
  /** The player's committed action for this point (already accepted). */
  playerInput?: string;
  /** Settled result lines of this point, used only as visible scene material. */
  settledResults?: string[];
  /** 04's structured settled records: who acted, on whom, what action and which
   * outcome direction. Meaning is checked against these, not against wording. */
  settledFacts?: StructuredSettledFact[];
  /** Previous narration the candidate accepted for this world, if any. */
  priorText?: string | null;
  /** Recent accepted events, newest last. Scene material, never new facts. */
  recentEvents?: string[];
  signal?: AbortSignal;
}

/** Real generation increments from the candidate. `text` is the candidate's
 * own partial prose; it is never synthesized here. */
export interface NarrationProgress {
  text: string;
  elapsedMs: number;
  verified: boolean;
  attempt: number;
}

/** Read-only inputs every candidate receives. `facts` and `inputText` are
 * projections of the same settled point; a candidate never writes them. */
export interface PreparedNarration {
  facts: CommittedNarration;
  /** Lane 01 result serializer output; null when the projection refused the
   * point (then candidates that require a serialized input are skipped). */
  inputText: string | null;
  inputError: string | null;
  policy: NarrationPolicy;
  scene: BeatSceneContext;
  viewpointId: Id;
  viewpointName: string;
  /** Facts this round must express (moved / task / personality / sanity). */
  mandatoryFactIds: string[];
}

export interface CandidateIssueSummary {
  kind: string;
  severity: 'hard' | 'soft' | 'detail';
  attempt?: number;
}

/** What one candidate produced. `accepted` is the candidate's own verdict;
 * `grade` states where the text came from, not how good it is. */
export interface CandidateNarrationResult {
  candidateId: string;
  route: NarrationCandidate['route'];
  text: string;
  accepted: boolean;
  grade: 'candidate' | 'candidate_unverified' | 'candidate_with_program_sentences' | 'program';
  status: 'accepted' | 'rejected' | 'cancelled' | 'timeout' | 'error';
  /** Internal one-line reason for the fallback record. Never player-facing. */
  reason: string | null;
  issues: CandidateIssueSummary[];
  attempts: number;
  promptChars: number;
  timings: { totalMs: number; attemptMs: number[]; firstTokenMs: number | null };
  strategyVersion: string;
  /** True when every sentence came from the candidate's own program fallback
   * rather than generated prose (B's `all_beats_fell_back`). */
  allFellBack: boolean;
  detail?: Record<string, unknown>;
}

export interface CandidateAvailability {
  available: boolean;
  /** Internal code such as `module_missing`, `input_unavailable`. */
  reason: string | null;
}

export interface CandidateRunArgs {
  engine: InferenceEngine;
  point: NarrationPoint;
  prepared: PreparedNarration;
  onProgress?: (progress: NarrationProgress) => void;
  /** Candidate-specific knobs. The selection layer sets `mode` for the
   * constrained route; no candidate may use it to change facts. */
  policy?: {
    mode?: 'program' | 'model';
    sceneMode?: 'beats' | 'scene';
    /** Whole-scene prompt shape: `serialized` is the training shape for the
     * fine-tuned checkpoints; `prose-facts` is the closed-book shape measured
     * for the deployable instruct model. */
    promptShape?: 'serialized' | 'prose-facts';
  };
}

/** One shipped adaptation of a candidate group. `id` and `label` stay
 * internal: the product page never shows them. */
export interface NarrationCandidate {
  id: 'trained' | 'instruct' | 'constrained';
  route: 'trained' | 'instruct' | 'constrained';
  /** Module + strategy identity recorded in evidence. */
  version: string;
  label: string;
  /** Modules and model requirements, for availability and diagnostics. */
  requires: { modules: string[]; template: string };
  /** Product default gate: a candidate whose real-model evidence is not
   * positive must be enabled explicitly (internal QA switch), never silently. */
  productDefault: boolean;
  availability(point: NarrationPoint, prepared: PreparedNarration): CandidateAvailability;
  run(args: CandidateRunArgs): Promise<CandidateNarrationResult>;
}

/** One settled result record as committed by the settlement (04). */
export interface StructuredSettledFact {
  text: string;
  actorId: string;
  targetId?: string;
  action?: string;
  outcome: 'completed' | 'failed' | 'blocked' | 'unaffected';
  /** The actor's judgement row was missing: the outcome is not asserted. */
  implicit?: true;
}

export type NarrationRunResult =
  | {
    kind: 'adopted';
    candidateId: string;
    route: NarrationCandidate['route'];
    text: string;
    accepted: true;
    /** `program` means every beat came from the deterministic realizer: it is
     * a labelled downgrade, never model prose. `mixed` means some sentences
     * are model prose and some are program realizations: it is shown with a
     * visible note and never counted as fully model-written. */
    grade: 'candidate' | 'program' | 'mixed';
    /** Per-sentence provenance for the page and evidence. */
    segments: Array<{ id: string; kind: string; source: string; text: string }>;
    beatCounts: { model: number; program: number; other: number };
    issues: CandidateIssueSummary[];
    timings: CandidateNarrationResult['timings'];
    promptChars: number;
    strategyVersion: string;
    attempts: number;
    /** Candidate-specific evidence (composers, coverage, beat plan). */
    detail?: Record<string, unknown> | null;
    completion: CompletionEvidence;
  }
  | {
    kind: 'fallback';
    /** Candidate that was tried, or null when selection stayed on the
     * in-model path without a candidate run. */
    candidateId: string | null;
    grade: 'program_fallback';
    /** Internal reason chain, e.g. `rejected:trained|fact_omitted`. */
    reason: string;
    /** Player-facing sentence explaining the degraded text, or null. */
    notice: string | null;
    /** Internal evidence of the last candidate attempt: its own text, issue
     * list, timings and candidate-specific detail. Never rendered. */
    detail?: Record<string, unknown>;
    /** A non-empty model scene the candidate wrote but its own gate rejected.
     * It is preserved and labelled as an unverified draft instead of being
     * thrown away for program text; it never counts as accepted prose. */
    draft?: {
      text: string;
      candidateId: string | null;
      route: NarrationCandidate['route'] | null;
      grade: 'candidate_unverified' | 'program' | 'mixed' | string;
      issues: CandidateIssueSummary[];
      /** Full prompt size of the candidate run (never the text length). */
      promptChars: number;
      timings: CandidateNarrationResult['timings'];
      strategyVersion: string | null;
      segments?: Array<{ id: string; kind: string; source: string; text: string }>;
      beatCounts?: { model: number; program: number; other: number };
      detail?: Record<string, unknown> | null;
    };
  };

export interface NarrationRunnerOptions {
  engine: InferenceEngine;
  /** Constrained route only: `program` never calls the model; `model` writes
   * one verified beat per engine call. Internal. */
  constrainedMode?: 'program' | 'model';
  /** Trained beats route only: `beats` (default) writes one committed fact at a
   * time; `scene` asks for the whole scene from the serialized input. Internal. */
  trainedMode?: 'beats' | 'scene';
  /** Whole-scene prompt shape for the trained route: `serialized` (training
   * shape for the fine-tuned checkpoints) or `prose-facts` (closed-book shape
   * measured for the deployable instruct model). Internal. */
  trainedPromptShape?: 'serialized' | 'prose-facts';
  /** How the candidate's plain-text prompts reach this engine. `chatml` wraps
   * each prompt like the page's in-model writer when the loaded model is a chat
   * model; `none` (default) passes prompts through unchanged. Internal. */
  engineTemplate?: 'none' | 'chatml';
  /** Internal selection. `auto` uses product-default candidates only. */
  candidate?: NarrationCandidate['id'] | 'auto' | 'builtin';
  /** Test seam: replace the shipped list. Never set by the page. */
  candidates?: NarrationCandidate[];
  temperature?: number;
  retryTemperature?: number;
  maxTokens?: number;
  maxTokensCeiling?: number;
  timeoutMs?: number;
  deadlineMs?: number;
  minChars?: number;
  targetChars?: number;
}

export interface ProgramFallback {
  text: string;
  strategyVersion: string;
  timings: CandidateNarrationResult['timings'];
  issues: CandidateIssueSummary[];
}

export interface NarrationRunner {
  /** Selection actually in force, for QA scripts and console diagnostics. */
  readonly selection: { requested: string; available: string[]; productDefault: string | null };
  generate(point: NarrationPoint, onProgress?: (progress: NarrationProgress) => void): Promise<NarrationRunResult>;
  /** Labelled program fallback for a round the in-model writer could not accept.
   * It never calls a model, never replaces accepted prose, and returns null when
   * the constrained candidate cannot write this point. */
  generateProgram(point: NarrationPoint): Promise<ProgramFallback | null>;
}

export type { NarrationIssue };
