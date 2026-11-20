/** Types shared by the shared browser candidate driver.
 *
 * A "candidate" is one team's narration generator: a browser-importable module
 * exporting `generateCandidate(args)`. The driver only supplies a real engine,
 * a real committed projection and the read-only policy; it never authors prose,
 * never edits world state and never grades quality. Its output is evidence:
 * the exact input, prompt, raw attempts, text and timing.
 */
import type { InferenceEngine } from '../../../runtime/engine';
import type { CommittedNarration } from '../../../runtime/committed-narration';
import type { Id, TimeAdvance, WorldState } from '../../../types';

/** A settled projection, read-only. `before: null` is the world root. */
export interface ScenarioProjection {
  before: WorldState | null;
  after: WorldState;
  timeAdvance: TimeAdvance | null;
  entityDeltas: Record<Id, import('../../../types').EntityDelta>;
  viewpoint: Id;
}

/** Scene grounding a candidate may use instead of re-deriving it from the
 * serialized state. Every field is copied from the settled `after` state. */
export interface SceneGrounding {
  location: string;
  placeNotes: string[];
  present: { id: Id; name: string; note: string }[];
  objects: { id: Id; name: string; note: string }[];
  inventory: { id: Id; name: string; note: string }[];
  exits: string[];
}

/** One runnable input. Built by `scenarios.ts` from a public sample or a real
 * settled projection; `inputText` is the product's serialized fact input. */
export interface CandidateScenario {
  id: string;
  label: string;
  note: string;
  /** Identity used in evidence: which world/point/version produced the input. */
  identity: {
    worldId: Id;
    pointId: Id;
    version: number;
    stateDigest: string;
    previousPointId: Id | null;
    viewpointId: Id;
    viewpointName: string;
    changeKinds: string[];
    timeAdvance: TimeAdvance | null;
  };
  before: WorldState | null;
  after: WorldState;
  delta: { timeAdvance: TimeAdvance | null; entityDeltas: Record<Id, import('../../../types').EntityDelta> };
  /** Adapter packet: same fact kinds as the committed projector, but it also
   * accepts slot positions (the real free-day world uses them). */
  committed: CommittedNarration;
  inputText: string;
  scene: SceneGrounding;
  policy: Record<string, unknown>;
  priorText: string | null;
  /** When set, this scenario reuses the accepted text of that scenario as
   * `priorText` (a real continuation, not an invented previous turn). */
  continuesFrom: string | null;
}

/** A candidate-owned model loader. Team A's runtime loads the checkpoint with
 * its real chat template; without this the shared loader's plain `complete()`
 * would silently use a fallback prompt and misrepresent the template. */
export interface EngineLoaderSpec {
  moduleUrl: string;
  exportName: string;
  /** Catalog id understood by the loader's `modelSpec(id)` when it has one. */
  modelId?: string;
  modelRoot?: string;
}

export interface CandidateSpec {
  /** Team-facing id, e.g. `02-narration`, `03-actions`. */
  id: string;
  owner: string;
  /** Browser path such as `/@fs/D:/.../index.ts`. */
  moduleUrl: string;
  exportName: string;
  /** Overrides the run-level model. */
  modelUrl?: string;
  maxTokens?: number;
  temperature?: number;
  /** Candidate-specific policies are not invented here; only the caller's
   * numeric knobs are forwarded. */
  notes?: string;
  loader?: EngineLoaderSpec | null;
}

export interface GeneratorTimings {
  totalMs?: number;
  attemptMs?: number[];
  attemptsMs?: number;
  firstTokenMs?: number | null;
  [key: string]: unknown;
}

/** The contract every candidate returns. Unknown extra fields are preserved. */
export interface CandidateResult {
  text: string;
  accepted: boolean;
  rawAttempts?: unknown[];
  issues?: unknown[];
  timings?: GeneratorTimings;
  strategyVersion?: string;
  [key: string]: unknown;
}

export interface ProgressEvent {
  status?: string;
  text?: string;
  verified?: boolean;
  elapsedMs?: number;
  [key: string]: unknown;
}

/** Arguments passed to `generateCandidate`. Compatible with 02's
 * `GenerateCommittedNarrationInput`; a candidate may ignore fields it does not
 * use, but must not mutate them. */
export interface GenerateCandidateArgs {
  engine: InferenceEngine;
  committed: CommittedNarration;
  /** The settled after state and its delta, same reads the packet came from. */
  state?: WorldState;
  before?: WorldState | null;
  delta?: { timeAdvance: TimeAdvance | null; entityDeltas: Record<Id, import('../../../types').EntityDelta> };
  inputText: string;
  priorText: string | null;
  onProgress?: (state: ProgressEvent) => void;
  policy: Record<string, unknown>;
  signal?: AbortSignal;
}

export type GenerateCandidate = (args: GenerateCandidateArgs) => Promise<CandidateResult>;

/** Attempt evidence normalized from the many shapes candidates use. The
 * driver never rewrites a candidate's own record; it keeps the original in
 * `source` and lifts the fields owners need to read a failure quickly. */
export interface AttemptEvidence {
  index: number;
  prompt: string | null;
  promptChars: number | null;
  raw: string | null;
  cleaned: string | null;
  finishReason: string | null;
  error: string | null;
  durationMs: number | null;
  firstTokenMs: number | null;
  accepted: boolean | null;
  issues: unknown[];
  source: unknown;
}

export interface RunEvidence {
  runId: string;
  candidateId: string;
  owner: string;
  moduleUrl: string;
  exportName: string;
  modelUrl: string;
  scenarioId: string;
  startedAt: string;
  wallMs: number;
  coldStart: boolean;
  loadMs: number | null;
  identity: CandidateScenario['identity'];
  input: {
    textChars: number;
    text: string;
    scene: SceneGrounding;
    policy: Record<string, unknown>;
    priorText: string | null;
    /** Where `priorText` came from: an accepted prior turn, prose the page
     * actually displayed (fallback), or none. */
    priorSource?: 'accepted' | 'displayed_fallback' | 'none' | null;
    /** Extra read-only fields attached to `committed` for state-projecting
     * candidates; the fact packet itself is unchanged. */
    committedExtras: string[];
  };
  /** What the candidate returned, after contract validation. */
  result: {
    text: string;
    chars: number;
    paragraphs: string[];
    firstParagraph: string;
    lastParagraph: string;
    accepted: boolean;
    status: string | null;
    strategyVersion: string | null;
    timings: GeneratorTimings | null;
    issues: unknown[];
    attempts: AttemptEvidence[];
    extraKeys: string[];
  };
  progress: {
    count: number;
    firstAtMs: number | null;
    lastAtMs: number | null;
    /** When the streamed text first held a readable segment (a paragraph
     * break or >= 80 visible chars). Null means the candidate never streamed a
     * readable segment, not that the first token was slow. */
    firstReadableAtMs: number | null;
    tail: ProgressEvent[];
  };
  /** Whether the shared engine still holds a loaded model after this run.
   * False means the candidate's own timeout hard-stopped the worker; the next
   * candidate must reload first. */
  engineAfter: { alive: boolean; modelId: string | null };
  contract: { ok: boolean; missing: string[]; notes: string[] };
  error: string | null;
}

export interface EngineEvidence {
  modelUrl: string;
  loadMs: number;
  info: { backend: string; modelId: string | null };
  diagnostics: { multithread: boolean; numThreads: number } | null;
  webgpuAvailable: boolean;
  gpuRequested: boolean;
  backendNote: string;
  /** Set when a candidate-owned loader produced the engine. */
  loader?: {
    moduleUrl: string;
    exportName: string;
    modelId: string | null;
    backend: string | null;
    fallback: unknown;
    attempts: unknown;
  } | null;
}
