/** Public contract of the committed-narration strategy.
 *
 * The strategy receives a read-only fact packet (`CommittedNarration`), the
 * caller-serialized model input string and an `InferenceEngine`. It never
 * builds a second state serializer, never writes world state, and never hides
 * a rejected draft: every attempt, its raw output, timings and issues are
 * returned so the page can show a truthful display state and the caller can
 * choose its own fallback.
 */
import type { Id, TimeAdvance } from '../../types';
import type { CompletionEvidence, InferenceEngine } from '../../runtime/engine';
import type { AlignmentResult } from '../../runtime/narration-alignment';
import type { CommittedNarration, NarrationFact } from '../../runtime/committed-narration';

export const NARRATION_STRATEGY_VERSION = 'committed-narration-strategy-v2';

export type NarrationIssueKind =
  /** Contradictions reported by the fact-alignment grader. */
  | 'fact_actor_swap' | 'fact_direction_reversed' | 'fact_wrong_number' | 'fact_wrong_time'
  | 'fact_task_claimed' | 'fact_movement_claimed' | 'fact_position_claimed' | 'fact_event_added'
  /** A settled change that the prose never expresses. */
  | 'fact_omitted'
  | 'time_missing'
  /** Fabricated continuity: a promise or a past event with no committed or
   * previously accepted source. */
  | 'promise_without_fact' | 'past_without_fact'
  /** Shape and length problems. */
  | 'empty_narration' | 'too_short' | 'truncated' | 'premature_closure'
  /** Repetition across turns or inside one draft. */
  | 'echo_prior' | 'loop_repeated_sentence' | 'loop_repeated_clause'
  /** Viewpoint / knowledge boundary. */
  | 'perspective_leak' | 'knowledge_leak' | 'unlicensed_entity'
  /** The model copied the instructions instead of writing prose. */
  | 'prompt_echo'
  /** Sentence that binds no fact and contradicts nothing: soft evidence only. */
  | 'unverified_sentence'
  /** Transport evidence. A cancelled or timed-out call never becomes accepted. */
  | 'cancelled' | 'timeout' | 'engine_error';

export interface NarrationIssue {
  kind: NarrationIssueKind;
  severity: 'hard' | 'soft';
  /** 0-based attempt that produced the issue. */
  attempt: number;
  detail: string;
  sentence?: string;
}

/** The caller owns fact projection and serialization. This policy only states
 * which names/events are licensed, how long the scene should be, how many
 * repairs are allowed, and where the viewpoint sits. Nothing here is state. */
export interface NarrationPolicy {
  /** Whose scene this is. Non-POV interiority is a perspective leak. */
  viewpoint?: { id?: Id; name: string } | null;
  /** Display names of every character in the world (actor-swap detection). */
  roster?: string[];
  /** Display names of every location in the world (unlicensed movement). */
  locations?: string[];
  /** Already-true positions the scene may state without a position fact. */
  knownPositions?: { name: string; location: string }[];
  /** Every display name in the world. Names absent from the serialized input,
   * the fact packet and `priorText` are unlicensed: the small model must not
   * pull them from pretraining. */
  knownEntities?: string[];
  /** Extra names the caller licensed (visible items, scene props). */
  visibleEntities?: string[];
  /** Event verbs the player's committed action licenses for this point. */
  licensedEvents?: string[];
  /** Hidden knowledge (secrets, other characters' private goals). A substring
   * match is a hard knowledge leak. Guidance never repeats these strings. */
  forbiddenKnowledge?: string[];
  /** Committed time advance for this point (Δ, not a wall clock). */
  time?: TimeAdvance | null;
  /** Require the prose to state the elapsed duration. Default: true for an
   * `elapsed` advance with amount > 0, false for instant/zero advances. */
  requireTime?: boolean;
  /** Hard floor for a scene. Default 120 characters. */
  minChars?: number;
  /** Target length used by truncated/premature-closure guidance. Default 260. */
  targetChars?: number;
  /** Char-bigram overlap with `priorText` above which the draft echoes. */
  maxPriorOverlap?: number;
  /** Bounded repairs; every retry is included in the end-to-end timing. */
  maxAttempts?: number;
  maxTokens?: number;
  /** Truncated drafts may grow up to this ceiling on retry. */
  maxTokensCeiling?: number;
  temperature?: number;
  retryTemperature?: number;
  seed?: number;
  /** Per-engine-call timeout. Default 150 s. */
  timeoutMs?: number;
  /** End-to-end budget covering every attempt. Default 300 s. */
  deadlineMs?: number;
  /** Optional task text (instruct models). Inserted directly before the body
   * marker so the caller's fact serialization is left untouched. */
  instruction?: string;
  /** 'regenerate' asks for a new draft; 'revise' also shows the previous one. */
  revisionMode?: 'regenerate' | 'revise';
  stop?: string[];
  /** Full prompt override. The default only inserts guidance before the body
   * marker; it never re-serializes facts. */
  composePrompt?: (args: ComposePromptArgs) => string;
}

export interface ComposePromptArgs {
  inputText: string;
  attempt: number;
  guidance: string;
  previousDraft: string | null;
  instruction: string | null;
}

export interface NarrationLedger {
  viewpoint: { id: Id | null; name: string } | null;
  /** Changes that must be expressed for the draft to be accepted. */
  mandatory: NarrationFact[];
  /** True scene facts that may be expressed but are not required. */
  optional: NarrationFact[];
  actorNames: string[];
  locationNames: string[];
  licensedEntities: string[];
  allowedEvents: string[];
  /** Promise verbs already present in the serialized input, previous accepted
   * prose, or explicitly licensed by the caller. */
  licensedPromises: string[];
  /** Strong past-time markers already present in the serialized input or
   * previous accepted prose. */
  licensedPastMarkers: string[];
  time: TimeAdvance | null;
  requireTime: boolean;
  forbiddenKnowledge: string[];
}

export interface NarrationMetrics {
  chars: number;
  sentences: number;
  paragraphs: number;
  dialogueRatio: number;
  mandatoryFacts: number;
  mandatoryExpressed: number;
  unverifiedSentences: number;
  /** Char-bigram overlap with `priorText`; null when there is no prior text. */
  echoRatio: number | null;
  repeatedSentences: number;
  repeatedClauses: number;
}

export interface NarrationAttempt {
  attempt: number;
  prompt: string;
  promptChars: number;
  raw: string;
  cleaned: string;
  finishReason: string | null;
  error: string | null;
  durationMs: number;
  firstTokenMs: number | null;
  completion: CompletionEvidence | null;
  alignment: AlignmentResult | null;
  issues: NarrationIssue[];
  metrics: NarrationMetrics | null;
  accepted: boolean;
  cancelled: boolean;
  timedOut: boolean;
  progressEvents: number;
}

export interface NarrationTimings {
  /** Wall time from call start to return, including every retry. */
  totalMs: number;
  attemptMs: number[];
  attemptsMs: number;
  firstTokenMs: number | null;
  deadlineExceeded: boolean;
}

/** What the page may render. `verified: false` text is provisional: it is
 * either still streaming or a rejected/cancelled draft. Only
 * `status: 'accepted'` may be committed as this point's narration. */
export type NarrationDisplayState =
  | { status: 'streaming'; attempt: number; text: string; verified: false; elapsedMs: number }
  | { status: 'accepted'; attempt: number; text: string; verified: true; elapsedMs: number }
  | { status: 'rejected'; attempt: number; text: string; verified: false; elapsedMs: number; issues: NarrationIssue[] }
  | { status: 'cancelled'; attempt: number; text: string; verified: false; elapsedMs: number }
  | { status: 'failed'; attempt: number; text: string; verified: false; elapsedMs: number; issues: NarrationIssue[] };

export interface GeneratedNarration {
  /** Best non-interrupted draft. Empty when every attempt was cancelled. */
  text: string;
  rawAttempts: NarrationAttempt[];
  accepted: boolean;
  issues: NarrationIssue[];
  timings: NarrationTimings;
  strategyVersion: string;
  status: 'accepted' | 'rejected' | 'cancelled' | 'timeout' | 'error';
  ledger: NarrationLedger;
  metrics: NarrationMetrics | null;
  /** Index into `rawAttempts` matching `text`, or null when `text` is empty. */
  attemptIndex: number | null;
  /** Last display state emitted to `onProgress`. */
  display: NarrationDisplayState;
}

export interface GenerateCommittedNarrationInput {
  engine: InferenceEngine;
  /** Read-only committed facts. Build it with `projectCommittedNarration` or
   * the caller's own projector; the strategy does not re-derive state. */
  committed: CommittedNarration;
  /** The serialized model input (lane 01 / caller). Injected, never rebuilt. */
  inputText: string;
  /** Previous accepted narration for continuity, echo detection and licensing. */
  priorText?: string | null;
  signal?: AbortSignal;
  onProgress?: (state: NarrationDisplayState) => void;
  policy?: NarrationPolicy;
}
