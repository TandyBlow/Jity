/** Public contract of the A-route candidate: complete Chinese narration from a
 * native instruct model (Qwen2.5-1.5B-Instruct / Qwen3-1.7B, ChatML).
 *
 * The call shape is compatible with lane 02's `generateCommittedNarration`
 * (`{ engine, committed, inputText, priorText, signal, onProgress, policy }`).
 * Extra optional fields carry the REAL visible projection: `state` / `before` /
 * `delta` from the settled world, the player's committed action, and the
 * settled result lines. The candidate never writes world state; it only turns
 * a settled point into prose plus an honest verdict.
 *
 * `policy` is not a second state model. It holds writing constraints (length,
 * retries, viewpoint, lengths, optional scene material for callers that have no
 * state) and nothing that could override the facts.
 */
import type { EntityDelta, Id, TimeAdvance, WorldState } from '../../../types';
import type { CompletionEvidence, InferenceEngine } from '../../../runtime/engine';
import type { CommittedNarration } from '../../../runtime/committed-narration';

export const INSTRUCT_CANDIDATE_VERSION = 'instruct-narration-candidate-v1';

/** Chat template the weights were trained with. `auto` reads the engine's
 * model id; the renderer throws when it cannot decide instead of guessing. */
export type InstructTemplate = 'qwen2.5-instruct' | 'qwen3-instruct' | 'auto';

export type CandidateIssueKind =
  /** Fact alignment (re-exported from runtime/narration-alignment). */
  | 'actor_swap' | 'direction_reversed' | 'wrong_number' | 'task_claimed_without_fact'
  | 'movement_without_fact' | 'state_claim_without_fact' | 'wrong_time' | 'added_event' | 'wrong_person' | 'empty_narration'
  /** A committed change the prose never expressed. */
  | 'fact_omitted'
  /** Shape problems. */
  | 'too_short' | 'too_long' | 'truncated' | 'prompt_echo' | 'instruction_echo'
  | 'thinking_leaked' | 'not_prose' | 'empty_output'
  /** A registered name the projection did not license. */
  | 'unlicensed_entity'
  /** The point's own time advance was not narrated (empty-delta points). */
  | 'time_missing'
  /** No committed packet was supplied: the draft was not fact-graded. */
  | 'facts_unverified'
  /** Continuity. */
  | 'echo_prior'
  /** The draft repeats the same clause several times (small-model loop). */
  | 'loop_repeated'
  /** First-person narration outside dialogue (the scene is third person). */
  | 'first_person_narrator'
  /** Transport / retry evidence. Never accepted. */
  | 'cancelled' | 'timeout' | 'engine_error' | 'deadline_exceeded'
  /** A licensed event verb (the player's own action / settled result) was
   * allowed against the runtime grader; kept as evidence, not a failure. */
  | 'licensed_event';

export interface CandidateIssue {
  kind: CandidateIssueKind;
  severity: 'hard' | 'soft';
  attempt: number;
  detail: string;
  sentence?: string;
}

/** Caller-supplied scene material for callers that have no WorldState (the
 * lane-02 `BeatSceneContext` shape). It licenses names and description; it
 * never adds facts. */
export interface CandidateSceneContext {
  location?: string;
  placeNotes?: string[];
  present?: { name: string; note?: string }[];
  objects?: { name: string; note?: string }[];
  previousAction?: string;
}

export interface InstructCandidatePolicy {
  /** Whose scene this is. Defaults to the state's protagonist. */
  viewpointId?: Id;
  /** Lane-02 compatible alias ({id,name}); `viewpointId` wins when both exist. */
  viewpoint?: { id?: Id; name?: string } | null;
  template?: InstructTemplate;
  /** 'chat': use the engine's real chat turns when it exposes `chat()`
   * (system + user), otherwise send the same text through `complete()` and let
   * the GGUF template wrap it as one user turn.
   * 'raw': the candidate renders ChatML itself for a raw-completion engine.
   * 'auto' (default) picks 'chat' for the wllama backend, 'raw' otherwise. */
  promptMode?: 'chat' | 'raw' | 'auto';
  /** Display names of every character in the world (roster for swaps). */
  roster?: string[];
  locations?: string[];
  /** Already-true positions (bystanders who did not move this point). */
  knownPositions?: { name: string; location: string }[];
  /** Extra names the caller licenses (visible props). */
  visibleEntities?: string[];
  /** Event verbs the caller licenses even without a fact kind. */
  licensedEvents?: string[];
  /** Secrets that must not appear. */
  forbiddenKnowledge?: string[];
  /** Required time narration. Default true for elapsed>0. */
  requireTime?: boolean;
  minChars?: number;
  targetChars?: number;
  maxChars?: number;
  maxAttempts?: number;
  maxTokens?: number;
  maxTokensCeiling?: number;
  temperature?: number;
  retryTemperature?: number;
  seed?: number;
  timeoutMs?: number;
  deadlineMs?: number;
  /** Scene material used when no WorldState is supplied. */
  scene?: CandidateSceneContext | null;
  /** A short style sample. It is labelled style-only in the prompt; its facts
   * must not enter the scene. Off by default. */
  styleSample?: string | null;
  /** Optional prompt variant for A/B evidence. `plain` (default) uses the
   * shipped instruction; `scene-first` puts the material before the rules and
   * drops the numbered writing plan. Unknown values fall back to `plain`. */
  variant?: 'plain' | 'scene-first';
  /** System prompt override for experiments. The default is the shipped one. */
  systemPrompt?: string;
}

/** The settled point, in the shapes the controller already produces. */
export interface CandidateDelta {
  timeAdvance?: TimeAdvance | null;
  entityDeltas?: Record<Id, EntityDelta>;
}

export interface GenerateInstructCandidateArgs {
  engine: InferenceEngine;
  /** Point id for progress/evidence; parsed from `inputText` when omitted. */
  pointId?: Id;
  /** Read-only committed facts (optional: the projection supplies the scene). */
  committed?: CommittedNarration | null;
  /** The caller's serialized model input. Kept for compatibility and for
   * parsing a scene when no WorldState is passed. */
  inputText?: string;
  priorText?: string | null;
  signal?: AbortSignal;
  onProgress?: (state: CandidateProgress) => void;
  policy?: InstructCandidatePolicy;
  /** Settled after-state. Preferred source of the visible projection. */
  state?: WorldState | null;
  /** Settled before-state (only used for display deltas). */
  before?: WorldState | null;
  /** Settled delta for this point (positions/tasks/personality/sanity/items). */
  delta?: CandidateDelta | null;
  /** The player's committed action for this point. */
  playerInput?: string | null;
  /** Settled result lines (results task output). Licensed prior text. */
  settledResults?: string[];
  /** Recent accepted events for continuity. */
  recentEvents?: string[];
}

export interface CandidateProgress {
  pointId: Id | null;
  text: string;
  status: 'streaming' | 'accepted' | 'rejected' | 'cancelled' | 'failed';
  verified: boolean;
  elapsedMs: number;
  attempt: number;
}

export interface CandidateFact {
  id: string;
  kind: string;
  /** The plain sentence the prompt gives the model; immutable fact payload. */
  statement: string;
  /** Compiled from a committed fact, an item move, time, or appearance. */
  source: 'committed' | 'delta' | 'time' | 'item' | 'appearance';
  /** A must-say change vs. licensed detail. */
  mandatory: boolean;
  /** Display name of the changed entity, when it has one (item checks). */
  entity?: string;
  /** For item moves: the person now carrying it, when it is a character. */
  holder?: string;
  /** For moves shared by several actors: the origin and destination, so a
   * 「两人走进庭院」 sentence can be credited to each of them. */
  from?: string;
  to?: string;
}

export interface SceneCharacter {
  id: Id;
  name: string;
  viewpoint: boolean;
  appearance: string;
  personality: string;
  /** Items carried / worn (visible). */
  carrying: string[];
}

export interface ScenePosition {
  name: string;
  location: string;
  viewpoint: boolean;
}

export interface SceneItem {
  id: Id;
  name: string;
  appearance: string;
  placement: string;
}

export interface SceneProjection {
  viewpoint: { id: Id; name: string };
  /** Human time of the after-state, plus the advance. */
  time: string;
  advance: TimeAdvance | null;
  place: { id: Id; name: string; appearance: string; notes: string[] };
  characters: SceneCharacter[];
  positions: ScenePosition[];
  items: SceneItem[];
  facts: CandidateFact[];
  playerAction: string | null;
  priorExcerpt: string | null;
  recentEvents: string[];
  /** True when the projection came from a real WorldState. */
  fromState: boolean;
  /** Roster/licensing data the verifier needs but the prompt does not print. */
  licensing: {
    roster: string[];
    locations: string[];
    /** Every registered item name; not printed, used to reject an off-scene
     * prop the model pulls from pretraining or from another room. */
    items: string[];
    knownPositions: { name: string; location: string }[];
    visibleEntities: string[];
    licensedEvents: string[];
    forbiddenKnowledge: string[];
  };
}

export interface CandidateAttempt {
  attempt: number;
  prompt: string;
  promptChars: number;
  raw: string;
  cleaned: string;
  durationMs: number;
  firstTokenMs: number | null;
  finishReason: string | null;
  error: string | null;
  completion: CompletionEvidence | null;
  issues: CandidateIssue[];
  accepted: boolean;
  cancelled: boolean;
  timedOut: boolean;
}

export interface CandidateTimings {
  totalMs: number;
  attemptMs: number[];
  firstTokenMs: number | null;
  deadlineExceeded: boolean;
}

export interface GeneratedInstructCandidate {
  /** Accepted prose, or the best non-interrupted draft (never hidden). */
  text: string;
  accepted: boolean;
  rawAttempts: CandidateAttempt[];
  issues: CandidateIssue[];
  timings: CandidateTimings;
  strategyVersion: string;
  status: 'accepted' | 'rejected' | 'cancelled' | 'timeout' | 'error';
  /** The exact prompt of the last attempt (replay evidence). */
  prompt: string;
  projection: SceneProjection;
  /** Index into rawAttempts matching `text`, or null when empty. */
  attemptIndex: number | null;
  template: Exclude<InstructTemplate, 'auto'> | null;
}
