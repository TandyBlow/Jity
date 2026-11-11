/** C route: constrained narration candidate.
 *
 * The program reads the committed point (state + Δ), builds a read-only scene
 * skeleton and a beat plan (subject / direction / result / scene detail), then
 * asks a prose composer to write each beat. The composer may be a program
 * realizer, lane 07's composer, or a constrained small model. Every beat is
 * verified against the facts it was given; a failed beat is replaced by the
 * program realization of the SAME beat (never by a fact list), then the whole
 * text is verified again.
 *
 * This module never writes world state and never re-derives facts from prose.
 */
import type {
  EntityDelta, Id, Json, TimeAdvance, WorldState,
} from '../../../types';
import type { InferenceEngine } from '../../../runtime/engine';
import type { CommittedNarration, NarrationFact } from '../../../runtime/committed-narration';

/** One settled fact the narration may state. `mandatory` facts must appear in
 * the accepted text; optional facts are licensed scene material. */
export type SceneFact =
  | { id: string; kind: 'time'; mandatory: boolean; visibility: FactVisibility; advance: TimeAdvance }
  | {
    id: string; kind: 'move'; mandatory: boolean; visibility: FactVisibility;
    entityId: Id; name: string; entityKind: 'character' | 'item';
    fromId: Id; from: string; toId: Id; to: string;
    /** Relation to the viewpoint's location at the START and END of the point. */
    fromVisibility: 'in_view' | 'out_of_view'; toVisibility: 'in_view' | 'out_of_view';
    viewpoint: boolean;
  }
  | {
    id: string; kind: 'task_achieved'; mandatory: boolean; visibility: FactVisibility;
    ownerId: Id; name: string; taskId: Id; goal: string;
  }
  | {
    id: string; kind: 'subtask_added'; mandatory: boolean; visibility: FactVisibility;
    ownerId: Id; name: string; taskId: Id; parentTaskId: Id | null; parentGoal: string | null; goal: string;
  }
  | {
    id: string; kind: 'personality_changed'; mandatory: boolean; visibility: FactVisibility;
    ownerId: Id; name: string; changeId: Id; text: string; removed: boolean; supersededTexts: string[];
  }
  | {
    id: string; kind: 'sanity_changed'; mandatory: boolean; visibility: FactVisibility;
    ownerId: Id; name: string; from: number; to: number;
  }
  | {
    id: string; kind: 'appearance_changed'; mandatory: boolean; visibility: FactVisibility;
    entityId: Id; name: string; entityKind: 'character' | 'item' | 'location';
    changeId: Id; text: string | null; removed: boolean; supersededTexts: string[];
  }
  | {
    id: string; kind: 'at'; mandatory: boolean; visibility: FactVisibility;
    entityId: Id; name: string; locationId: Id; location: string;
  }
  | {
    id: string; kind: 'item_present'; mandatory: boolean; visibility: FactVisibility;
    itemId: Id; name: string; containerId: Id; container: string; note: string;
  }
  | {
    id: string; kind: 'item_discovered'; mandatory: boolean; visibility: FactVisibility;
    itemId: Id; name: string; containerId: Id; container: string; note: string;
  }
  /** The settlement's own result wording; narrated as one short paragraph. */
  | { id: string; kind: 'result'; mandatory: boolean; visibility: FactVisibility; text: string };

/** Whether the viewpoint could perceive the fact. Hidden facts are kept in the
 * skeleton for evidence but are not narrated by default (`R11/R12`: the prose
 * must not leak another room's business). */
export type FactVisibility = 'scene' | 'hidden';

export interface ScenePerson {
  id: Id;
  name: string;
  /** Already-settled appearance text (initial + active changes), single line. */
  note: string;
  /** True for the viewpoint. */
  viewpoint: boolean;
}

export interface SceneObject {
  id: Id;
  name: string;
  note: string;
}

export interface SceneSkeleton {
  anchor: {
    worldId: Id; pointId: Id; version: number; stateDigest: string; previousPointId: Id | null;
  };
  viewpoint: {
    id: Id; name: string; locationId: Id; location: string;
    note: string; personality: string; sanity: number;
  };
  time: TimeAdvance | null;
  place: { id: Id; name: string; note: string; parentName: string | null };
  present: ScenePerson[];
  objects: SceneObject[];
  /** All settled facts of the point, scene and hidden. */
  facts: SceneFact[];
  /** Every registered name in the world. Used to reject names the prose pulled
   * from pretraining instead of from this scene. */
  worldNames: { characters: string[]; locations: string[]; items: string[] };
  /** Names / places / items / quoted texts the prose may use. */
  licensed: {
    names: string[];
    locations: string[];
    items: string[];
    /** Descriptive text already present in the settled state. */
    details: string[];
    /** Frozen texts (task goals, personality changes) that may be quoted. */
    quotes: string[];
  };
  knowledge: SceneKnowledge;
  priorText: string | null;
  inputText: string | null;
  /** What the player declared this turn ("我沿着服务巷往里走…"). An instruction,
   * not a settled outcome: the beats may write it as done/tried, never as a
   * successful result (01's fact.action_omitted on every page turn). */
  previousAction?: string | null;
  resultsText: string | null;
  /** False when only the fact packet (no full state) was available. */
  hasSceneMaterial: boolean;
  /** True when the point has no settled entity change (time-only). */
  timeOnly: boolean;
}

/** Cross-turn knowledge the caller persists. Used only to avoid writing a
 * re-discovery ("第一次看见") of something the viewpoint already knows. */
export interface SceneKnowledge {
  discoveredItemIds: Id[];
  visitedLocationIds: Id[];
  metCharacterIds: Id[];
}

export interface BeatDirective {
  id: string;
  index: number;
  kind: 'open' | 'move' | 'event' | 'result' | 'scene' | 'close';
  subject: { id: Id; name: string; viewpoint: boolean } | null;
  /** Fact ids this beat must express. */
  factIds: string[];
  /** Detail strings this beat may use (already in `licensed.details`). */
  details: string[];
  /** Names the beat must contain (subject and/or destination). */
  mustMention: string[];
  /** Deterministic variation seed. */
  seed: number;
  minChars: number;
  maxChars: number;
}

export interface BeatPlan {
  beats: BeatDirective[];
  /** Facts that are not narrated because the viewpoint cannot perceive them. */
  hiddenFactIds: string[];
  /** Facts deliberately left optional (scene texture) in this plan. */
  optionalFactIds: string[];
}

export interface ComposeBeatRequest {
  beat: BeatDirective;
  scene: SceneSkeleton;
  /** Accepted text of all previous beats; null for the first beat. */
  prior: string | null;
}

export interface ComposeBeatOptions {
  signal?: AbortSignal;
  /** Real streaming delta for this beat (cumulative text). Program composers
   * MUST NOT call this: a finished string is not a stream. */
  onProgress?: (progress: { text: string; elapsedMs: number }) => void;
}

export interface ComposeBeatResult {
  text: string;
  /** Raw model output before cleanup, when a model wrote it. */
  raw?: string;
  source: 'program' | 'model' | 'external';
  ms?: number;
  attempts?: number;
}

/** Lane 07 (or any other composer) implements this. Duck-typed injection keeps
 * the two lanes independent: no cross-lane import is required. */
export type BeatComposer = (
  request: ComposeBeatRequest,
  options: ComposeBeatOptions,
) => Promise<ComposeBeatResult>;

export type CandidateIssueKind =
  | 'fact_missing' | 'fact_actor_swap' | 'fact_direction_reversed' | 'fact_wrong_number'
  | 'fact_time_wrong' | 'task_without_fact' | 'movement_without_fact'
  | 'unlicensed_entity' | 'unlicensed_event' | 'rediscovery_claim'
  | 'perspective_leak' | 'prompt_echo' | 'fact_list' | 'off_language' | 'empty_text' | 'too_short' | 'too_long'
  | 'repeated_sentence' | 'echo_prior' | 'opening_repeat' | 'engine_error' | 'cancelled'
  | 'beat_repaired' | 'beat_fallback' | 'sanity_direction_missing';

export interface CandidateIssue {
  kind: CandidateIssueKind;
  severity: 'hard' | 'soft';
  beatId: string | null;
  detail: string;
  sentence?: string;
}

export interface BeatEvidence {
  beatId: string;
  kind: BeatDirective['kind'];
  source: 'program' | 'model' | 'external' | 'fallback';
  text: string;
  prompt: string | null;
  raw: string | null;
  attempts: number;
  ms: number;
  issues: CandidateIssue[];
  /** Drafts that failed the beat gate before the accepted one. Kept so a mixed
   * turn shows what the model actually produced, not only the accepted text. */
  rejected?: { attempt: number; text: string; raw?: string; promptChars?: number; issues: CandidateIssue[] }[];
}

export interface CandidateTimings {
  totalMs: number;
  planMs: number;
  composeMs: number;
  verifyMs: number;
  beatsMs: number[];
  firstTextMs: number | null;
}

export interface CandidateProgress {
  text: string;
  status: 'streaming' | 'accepted' | 'repaired' | 'rejected';
  verified: boolean;
  elapsedMs: number;
  beatId: string | null;
}

/** Optional material the caller licenses beyond the settled state. Every entry
 * is a description that already exists in the world; it is never used to
 * invent an event. */
export interface SceneHints {
  placeNote?: string;
  presentNotes?: Record<Id, string>;
  objectNotes?: Record<Id, string>;
  /** One line for the previous point's action, used only as continuity tone. */
  previousAction?: string;
}

export interface ConstrainedPolicy {
  /** Driver-level knobs (the shared browser driver forwards these names). */
  maxTokens?: number;
  temperature?: number;
  /** Defaults to the world protagonist. */
  viewpointId?: Id;
  /** Read-only description overrides (all already settled). */
  scene?: SceneHints;
  knowledge?: Partial<SceneKnowledge>;
  /** Settlement result text for this point, if the caller has it. Used only as
   * extra licensed material for item/scene selection, never as a fact source. */
  resultsText?: string | null;
  /** Whether hidden (out-of-scene) facts may be narrated. Default false. */
  narrateHiddenDeltas?: boolean;
  /** 'program' never calls a model; 'model' uses the engine per beat;
   * 'auto' uses the engine only when the policy enables it. */
  mode?: 'program' | 'model' | 'auto';
  /** Lane 07's composer. Takes precedence over the built-in model writer. */
  composer?: BeatComposer;
  /** Whether `mode: 'model'` may call the engine. Default true. */
  enableModel?: boolean;
  model?: {
    maxTokensPerBeat?: number;
    temperature?: number;
    timeoutMs?: number;
    maxAttempts?: number;
    /** Extra instruction appended to every beat prompt (template adaptation). */
    instruction?: string | null;
    seed?: number;
  };
  /** 'direction' writes a felt change without the number; 'number' states the
   * committed values explicitly (the legacy alignment gate expects this). */
  sanityStyle?: 'direction' | 'number';
  minChars?: number;
  maxChars?: number;
  /** Deprecated: elapsed time may be omitted from prose. Incorrect durations
   * are still checked, even when an older caller sets this flag. */
  requireTime?: boolean;
  maxBeats?: number;
  /** Whole-turn wall budget for model writing (default 180000 ms). Once it is
   * spent, remaining beats are written by the program so the player still gets
   * a readable turn instead of a timeout. */
  turnTimeoutMs?: number;
  seed?: number;
  /** Strings the prose must not contain verbatim (hidden knowledge). */
  forbiddenKnowledge?: string[];
  /** Phrases used by previous accepted turns; the realizer avoids them. */
  avoidOpenings?: string[];
  /** Allow a constrained model to rewrite the final assembled text as one
   * scene. Off by default: per-beat writing is the verifiable unit. */
  polish?: boolean;
}

export interface GenerateCandidateInput {
  engine: InferenceEngine;
  /** Output of `projectConstrainedScene` (or a compatible packet). A packet
   * without `state` still produces prose from the fact list alone. */
  committed: CommittedScenePacket;
  /** Caller-serialized model input (lane 01 projection). Licensed material:
   * names inside it may appear in prose, and it is never re-parsed as state. */
  inputText?: string | null;
  priorText?: string | null;
  signal?: AbortSignal;
  onProgress?: (progress: CandidateProgress) => void;
  policy?: ConstrainedPolicy;
}

/** `CommittedNarration` plus the raw reads the C route needs for scene
 * material. The extra fields are optional so a facts-only packet still works. */
export interface CommittedScenePacket extends CommittedNarration {
  state?: WorldState;
  beforeState?: WorldState | null;
  timeAdvance?: TimeAdvance | null;
  entityDeltas?: Record<Id, EntityDelta>;
  /** Alternative serialized model input, when `inputText` is not passed. */
  inputText?: string | null;
  /** Alternative previous accepted text. */
  priorText?: string | null;
}

export interface CandidateVerification {
  ok: boolean;
  coverage: { factId: string; kind: SceneFact['kind']; expressed: boolean; mandatory: boolean }[];
  issues: CandidateIssue[];
  unverifiedSentences: string[];
  chars: number;
  hiddenFactIds: string[];
  repetition: number | null;
}

/** One assembled paragraph and who wrote it. Program paragraphs are an
 * explicit downgrade, not model prose; the page may label them per segment. */
export interface BeatSegment {
  beatId: string;
  kind: BeatDirective['kind'];
  source: BeatEvidence['source'];
  text: string;
}

export interface CandidateResult {
  text: string;
  accepted: boolean;
  /** Every beat, including repaired and fallback beats, with raw model output. */
  rawAttempts: BeatEvidence[];
  issues: CandidateIssue[];
  timings: CandidateTimings;
  strategyVersion: string;
  status: 'accepted' | 'rejected' | 'cancelled' | 'error';
  verification: CandidateVerification;
  skeleton: SceneSkeleton | null;
  plan: BeatPlan | null;
  /** Which composer wrote each beat, in order. */
  composers: string[];
  /** Assembled paragraphs with their writer, so a mixed turn is never shown as
   * wholly model-written. */
  segments: BeatSegment[];
  /** Beat provenance counts for one-line labelling. */
  beatCounts: { model: number; program: number; external: number; fallback: number };
  /** True when both a model/external writer and a program fallback wrote part of
   * this text. `accepted` alone never means the whole text is model prose. */
  mixed: boolean;
  /** Base fact packet for the legacy alignment gate (position/task/personality
   * facts only; sanity uses this route's direction rule). */
  basePacket: CommittedNarration | null;
  display: CandidateProgress;
}

export type { Json, NarrationFact };
