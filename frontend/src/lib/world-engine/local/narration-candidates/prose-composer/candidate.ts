/** `generateCandidate`-compatible entry for route C.
 *
 * The call shape matches lane 02's `generateCommittedNarration` so lane 06 can
 * swap implementations without a second game protocol. This candidate does not
 * call an inference engine: lane 04's skeleton already contains the facts, and
 * the composer owns language. When only `committed` facts exist, the adapter
 * builds a sparse skeleton and says so in `issues`.
 *
 * `onProgress` is emitted exactly once at the end with the finished text. It is
 * a program, not a model stream; pretending to stream partial prose would
 * misreport the work.
 */

import { composeProse, PROSE_STRATEGY_VERSION } from './compose';
import { sceneFromCommitted, sceneFromGrounding, type CommittedLike, type SceneGroundingLike } from './from-committed';
import type { ComposedProse, ProseIssue, ProseScene } from './types';

export const CANDIDATE_STRATEGY_VERSION = PROSE_STRATEGY_VERSION;

export interface CandidateProgress {
  text: string;
  status: 'complete' | 'failed';
  verified: boolean;
  elapsedMs: number;
}

export interface CandidatePolicy {
  /** Lane 04's fact skeleton. Preferred over `committed`. */
  scene?: ProseScene;
  /** Override for the composer's own floor. */
  minChars?: number;
  seed?: number;
  /** When only committed facts exist, identify the viewpoint. */
  viewpoint?: { id?: string; name: string } | null;
  /** Everything the player has already read this session, when the caller has
   * it. Static scene texture found here is not restated. */
  avoidText?: string | null;
  [key: string]: unknown;
}

export interface GenerateCandidateArgs {
  /** Accepted for signature compatibility; the composer needs no model. */
  engine?: unknown;
  /** Lane 02's fact packet, used only when `policy.scene` is absent. May carry
   * the settled `state`/`beforeState` reads the shared driver attaches. */
  committed?: CommittedLike;
  /** The same settled read, offered at the top level by the shared driver. */
  state?: CommittedLike['state'];
  beforeState?: CommittedLike['beforeState'];
  /** The driver also offers the settled delta separately. */
  delta?: { timeAdvance?: CommittedLike['timeAdvance'] } | null;
  inputText?: string;
  priorText?: string | null;
  signal?: AbortSignal;
  onProgress?: (progress: CandidateProgress) => void;
  policy?: CandidatePolicy;
}

export interface CandidateIssue {
  kind: string;
  severity: 'hard' | 'soft';
  detail: string;
  sentence?: string;
}

/** The fields lane 02 reads from one attempt. The program composer has no
 * prompt or model stream, but it reports the same slot so a caller can keep
 * one loop for both strategies. */
export interface CandidateAttempt {
  attempt: number;
  prompt: string;
  promptChars: number;
  raw: string;
  cleaned: string;
  finishReason: string | null;
  error: string | null;
  durationMs: number;
  firstTokenMs: number | null;
  completion: null;
  alignment: null;
  issues: CandidateIssue[];
  metrics: null;
  accepted: boolean;
  cancelled: boolean;
  timedOut: boolean;
}

export type CandidateStatus = 'accepted' | 'rejected' | 'cancelled' | 'error';

export type CandidateTimings = ComposedProse['timings'] & {
  attemptMs: number[];
  attemptsMs: number;
  firstTokenMs: number | null;
  deadlineExceeded: boolean;
};

export interface CandidateResult {
  text: string;
  accepted: boolean;
  rawAttempts: CandidateAttempt[];
  attemptIndex: number | null;
  status: CandidateStatus;
  issues: CandidateIssue[];
  timings: CandidateTimings;
  strategyVersion: string;
  strategy: 'prose-composer';
  /** Full composer result for callers that want the per-beat ledger. */
  composed: ComposedProse;
  /** Present when the adapter had to build a skeleton from bare facts. */
  sparse: boolean;
  display: {
    status: 'accepted' | 'rejected' | 'cancelled' | 'failed';
    attempt: number;
    text: string;
    verified: boolean;
    elapsedMs: number;
    issues?: CandidateIssue[];
  };
}

function abortIssue(): ProseIssue {
  return { kind: 'beat_unrendered', severity: 'hard', detail: 'cancelled before composition' };
}

function attemptFor(composed: ComposedProse, issues: CandidateIssue[], elapsedMs: number): CandidateAttempt {
  return {
    attempt: 1,
    prompt: '',
    promptChars: 0,
    raw: composed.text,
    cleaned: composed.text,
    finishReason: 'stop',
    error: null,
    durationMs: elapsedMs,
    firstTokenMs: null,
    completion: null,
    alignment: null,
    issues,
    metrics: null,
    accepted: composed.accepted,
    cancelled: false,
    timedOut: false,
  };
}

function timingsFor(composed: ComposedProse['timings'], elapsedMs: number): CandidateTimings {
  return {
    ...composed,
    attemptMs: [elapsedMs],
    attemptsMs: elapsedMs,
    firstTokenMs: null,
    deadlineExceeded: false,
  };
}

export function generateCandidate(args: GenerateCandidateArgs): CandidateResult {
  const started = typeof performance !== 'undefined' ? performance.now() : Date.now();
  const policy = args.policy ?? {};
  const provided = policy.scene as unknown;
  const isProseScene = Boolean(provided && typeof provided === 'object' && 'protagonistId' in provided);
  const isGrounding = Boolean(provided && typeof provided === 'object'
    && 'location' in provided && 'present' in provided
    && typeof (provided as { location?: unknown }).location === 'string');
  let scene: ProseScene | null = isProseScene ? provided as ProseScene : null;
  let sparse = false;
  const issues: CandidateIssue[] = [];

  if (!scene && args.committed) {
    const adapted = isGrounding
      ? sceneFromGrounding(provided as SceneGroundingLike, args.committed, {
        viewpoint: policy.viewpoint ?? null,
        priorText: args.priorText ?? null,
        avoidText: policy.avoidText ?? null,
        seed: policy.seed,
        minChars: policy.minChars,
        state: args.state ?? args.committed.state ?? null,
        delta: args.delta ?? null,
        timeAdvance: args.committed.timeAdvance ?? args.delta?.timeAdvance ?? null,
      })
      : sceneFromCommitted(args.committed, {
      viewpoint: policy.viewpoint ?? null,
      priorText: args.priorText ?? null,
      avoidText: policy.avoidText ?? null,
      seed: policy.seed,
      minChars: policy.minChars,
      state: args.state ?? args.committed.state ?? null,
      timeAdvance: args.committed.timeAdvance ?? args.delta?.timeAdvance ?? null,
      delta: args.delta ?? null,
    });
    scene = adapted.scene;
    sparse = adapted.sparse;
    if (sparse) {
      issues.push({
        kind: 'sparse_skeleton',
        severity: 'soft',
        detail: 'no scene skeleton was supplied; location appearance and dialogue are unavailable',
      });
    }
  }

  if (!scene) {
    const empty: ComposedProse = {
      text: '', paragraphs: [], opening: '', closing: '',
      strategyVersion: CANDIDATE_STRATEGY_VERSION, beats: [], derivedDialogue: [],
      issues: [{ kind: 'empty_scene', severity: 'hard', detail: 'generateCandidate requires policy.scene or committed facts' }],
      accepted: false,
      timings: { planMs: 0, composeMs: 0, verifyMs: 0, totalMs: 0 },
    };
    args.onProgress?.({ text: '', status: 'failed', verified: false, elapsedMs: 0 });
    const emptyIssues = empty.issues.map((issue) => ({ ...issue }));
    return {
      text: '', accepted: false, rawAttempts: [], attemptIndex: null, status: 'error',
      issues: emptyIssues, timings: timingsFor(empty.timings, 0),
      strategyVersion: CANDIDATE_STRATEGY_VERSION, strategy: 'prose-composer',
      composed: empty, sparse,
      display: { status: 'failed', attempt: 1, text: '', verified: false, elapsedMs: 0, issues: emptyIssues },
    };
  }

  if (args.signal?.aborted) {
    const empty: ComposedProse = {
      text: '', paragraphs: [], opening: '', closing: '',
      strategyVersion: CANDIDATE_STRATEGY_VERSION, beats: [], derivedDialogue: [],
      issues: [abortIssue()], accepted: false,
      timings: { planMs: 0, composeMs: 0, verifyMs: 0, totalMs: 0 },
    };
    const abortIssues = empty.issues.map((issue) => ({ ...issue }));
    return {
      text: '', accepted: false, rawAttempts: [], attemptIndex: null, status: 'cancelled',
      issues: abortIssues, timings: timingsFor(empty.timings, 0),
      strategyVersion: CANDIDATE_STRATEGY_VERSION, strategy: 'prose-composer',
      composed: empty, sparse,
      display: { status: 'cancelled', attempt: 1, text: '', verified: false, elapsedMs: 0 },
    };
  }

  if (args.priorText && !scene.priorText) scene = { ...scene, priorText: args.priorText };
  if (policy.avoidText && !scene.policy?.avoidText) {
    scene = { ...scene, policy: { ...(scene.policy ?? {}), avoidText: policy.avoidText } };
  }
  if (policy.minChars !== undefined) {
    scene = { ...scene, policy: { ...(scene.policy ?? {}), minChars: policy.minChars } };
  }
  if (policy.seed !== undefined && scene.seed === undefined) {
    scene = { ...scene, seed: policy.seed };
  }

  const composed = composeProse(scene);
  issues.push(...composed.issues.map((issue) => ({ ...issue })));
  const elapsedMs = (typeof performance !== 'undefined' ? performance.now() : Date.now()) - started;
  args.onProgress?.({
    text: composed.text,
    status: composed.accepted ? 'complete' : 'failed',
    verified: composed.accepted,
    elapsedMs,
  });
  const attempt = attemptFor(composed, issues, elapsedMs);
  const status: CandidateStatus = composed.accepted ? 'accepted' : 'rejected';
  return {
    text: composed.text,
    accepted: composed.accepted,
    rawAttempts: [attempt],
    attemptIndex: composed.text ? 0 : null,
    status,
    issues,
    timings: timingsFor(composed.timings, elapsedMs),
    strategyVersion: CANDIDATE_STRATEGY_VERSION,
    strategy: 'prose-composer',
    composed,
    sparse,
    display: {
      status: composed.accepted ? 'accepted' : 'rejected',
      attempt: 1,
      text: composed.text,
      verified: composed.accepted,
      elapsedMs,
      ...(composed.accepted ? {} : { issues }),
    },
  };
}
