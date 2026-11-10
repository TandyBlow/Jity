/** Committed-narration strategy v1.
 *
 * Pipeline: fact license ledger → caller-serialized prompt (+ grounded repair
 * guidance on retry) → real engine call with real streaming → sentence-scoped
 * fact alignment + viewpoint/loop/length checks → bounded retry → truthful
 * display state and full evidence.
 *
 * What this module does NOT do: it does not serialize world state, does not
 * write state, does not replace a failed draft with a fixed answer, and does
 * not claim a retry repaired itself. `accepted: false` is a first-class result
 * with the rejected text and every issue attached.
 */
import {
  IncompleteGenerationError,
  type CompletionEvidence, type InferenceEngine,
} from '../../runtime/engine';
import type { CommittedNarration } from '../../runtime/committed-narration';
import { buildLedger } from './ledger';
import { buildRevisionGuidance } from './guidance';
import { composeNarrationPrompt } from './prompt';
import { verifyNarration } from './verify';
import {
  NARRATION_STRATEGY_VERSION,
  type GeneratedNarration, type GenerateCommittedNarrationInput, type NarrationAttempt,
  type NarrationDisplayState, type NarrationIssue, type NarrationLedger, type NarrationPolicy,
} from './types';

export * from './types';
export { buildLedger } from './ledger';
export { buildRevisionGuidance } from './guidance';
export { composeNarrationPrompt, insertBeforeBody } from './prompt';
export { verifyNarration } from './verify';

const nowMs = (): number => performance.now();
const charsOf = (text: string): number => [...text].length;
const clampInt = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, Math.round(Number.isFinite(value) ? value : min)));
const hardCount = (issues: readonly NarrationIssue[]): number => issues.filter((issue) => issue.severity === 'hard').length;

/** DOMException is not an `Error` subclass in every browser, so name matching
 * is the portable cancellation check. The wllama adapter rejects with a
 * DOMException named AbortError. */
function isAbortLike(error: unknown): boolean {
  return typeof error === 'object' && error !== null
    && (error as { name?: unknown }).name === 'AbortError';
}

/** Remove wrappers a small model likes to add. This is text cleanup, not a
 * state serializer: every fact still comes from the model's own prose and is
 * verified afterwards. */
export function sanitizeNarration(raw: string): string {
  const body = raw.includes('【正文】') ? raw.split('【正文】').pop() ?? raw : raw;
  return body
    .replace(/```[\s\S]*?```/gu, '')
    .replace(/```/gu, '')
    .replace(/^\s*(正文|叙事|输出)[:：]\s*/u, '')
    .replace(/【[^】]{1,12}】/gu, '')
    .replace(/\*\*/gu, '')
    .replace(/^#{1,6}\s*/gmu, '')
    .replace(/※/gu, '\n\n')
    .replace(/\n{3,}/gu, '\n\n')
    .trim();
}

interface RunAttemptArgs {
  engine: InferenceEngine;
  prompt: string;
  attempt: number;
  committed: CommittedNarration;
  ledger: NarrationLedger;
  policy: NarrationPolicy;
  priorText: string | null;
  maxTokens: number;
  temperature: number;
  remainingMs: number;
  guidance: string;
  signal?: AbortSignal;
  onProgress?: (state: NarrationDisplayState) => void;
}

interface RunAttemptResult {
  attempt: NarrationAttempt;
  display: NarrationDisplayState;
  /** Our own end-to-end timer fired during this attempt. */
  deadlineHit: boolean;
}

async function runAttempt(args: RunAttemptArgs): Promise<RunAttemptResult> {
  const started = nowMs();
  const controller = new AbortController();
  const external = args.signal;
  const forwardAbort = () => controller.abort();
  if (external?.aborted) controller.abort();
  else external?.addEventListener('abort', forwardAbort, { once: true });
  let deadlineHit = false;
  const remainingBudget = Math.max(1, Math.floor(args.remainingMs));
  // The engine gets its own per-call budget, capped by what is left of the
  // end-to-end deadline. Our timer below always covers the whole remainder, so
  // the two timers cannot outlive the reported total time.
  const callBudget = Math.max(1, Math.min(args.policy.timeoutMs ?? 150_000, remainingBudget));
  const timer = setTimeout(() => { deadlineHit = true; controller.abort(); }, remainingBudget);

  let raw = '';
  let finishReason: string | null = null;
  let firstTokenMs: number | null = null;
  let completion: CompletionEvidence | null = null;
  let error: string | null = null;
  let cancelled = false;
  let timedOut = false;
  let progressEvents = 0;

  try {
    const returned = await args.engine.complete(args.prompt, {
      maxTokens: args.maxTokens,
      temperature: args.temperature,
      ...(args.policy.seed !== undefined ? { seed: args.policy.seed } : {}),
      ...(args.policy.stop !== undefined ? { stop: args.policy.stop } : {}),
      signal: controller.signal,
      timeoutMs: callBudget,
      onProgress: (progress) => {
        progressEvents += 1;
        raw = progress.raw;
        args.onProgress?.({
          status: 'streaming', attempt: args.attempt, text: raw, verified: false,
          elapsedMs: nowMs() - started,
        });
      },
      onCompletion: (evidence) => {
        completion = evidence;
        if (evidence.raw) raw = evidence.raw;
        finishReason = evidence.finishReason;
        firstTokenMs = evidence.firstTokenMs;
      },
    });
    if (returned) raw = returned;
    if (finishReason === null) finishReason = 'stop';
  } catch (caught) {
    if (caught instanceof IncompleteGenerationError) {
      completion = caught.completion;
      if (caught.completion.raw) raw = caught.completion.raw;
      finishReason = caught.completion.finishReason;
      firstTokenMs = caught.completion.firstTokenMs;
      if (finishReason === 'timeout') timedOut = true;
      else error = caught.message;
    } else if (isAbortLike(caught)) {
      error = 'aborted';
      if (external?.aborted) cancelled = true;
      else if (deadlineHit) timedOut = true;
      else cancelled = true;
    } else {
      error = caught instanceof Error ? `${caught.name}: ${caught.message}` : String(caught);
    }
  } finally {
    clearTimeout(timer);
    external?.removeEventListener('abort', forwardAbort);
  }

  const cleaned = sanitizeNarration(raw);
  const issueList: NarrationIssue[] = [];
  if (cancelled) issueList.push({ kind: 'cancelled', severity: 'hard', attempt: args.attempt, detail: error ?? 'aborted' });
  if (timedOut) issueList.push({ kind: 'timeout', severity: 'hard', attempt: args.attempt, detail: 'generation deadline exceeded' });
  const verified = verifyNarration({
    text: cleaned, finishReason, committed: args.committed, ledger: args.ledger,
    policy: args.policy, priorText: args.priorText, attempt: args.attempt,
    promptEchoMarkers: promptEchoMarkers(args.prompt, args.policy, args.guidance),
  });
  issueList.push(...verified.issues);
  if (error && !completion && !cancelled && !timedOut) {
    issueList.push({ kind: 'engine_error', severity: 'hard', attempt: args.attempt, detail: error });
  }
  const accepted = !cancelled && !timedOut && !error && issueList.every((issue) => issue.severity !== 'hard');
  const durationMs = nowMs() - started;
  const attempt: NarrationAttempt = {
    attempt: args.attempt,
    prompt: args.prompt,
    promptChars: args.prompt.length,
    raw,
    cleaned,
    finishReason,
    error,
    durationMs,
    firstTokenMs,
    completion,
    alignment: verified.alignment,
    issues: issueList,
    metrics: verified.metrics,
    accepted,
    cancelled,
    timedOut,
    progressEvents,
  };
  const display: NarrationDisplayState = accepted
    ? { status: 'accepted', attempt: args.attempt, text: cleaned, verified: true, elapsedMs: durationMs }
    : cancelled
      ? { status: 'cancelled', attempt: args.attempt, text: cleaned, verified: false, elapsedMs: durationMs }
      : timedOut || (error !== null && !cleaned)
        ? { status: 'failed', attempt: args.attempt, text: cleaned, verified: false, elapsedMs: durationMs, issues: issueList }
        : { status: 'rejected', attempt: args.attempt, text: cleaned, verified: false, elapsedMs: durationMs, issues: issueList };
  args.onProgress?.(display);
  return { attempt, display, deadlineHit };
}

/** Instruction fragments that must never end up in the prose. The guidance
 * header and draft header are fixed; guidance content lines and the task
 * instruction's opening words are checked because a small instruct model
 * sometimes copies the task line instead of writing the scene. */
function promptEchoMarkers(prompt: string, policy: NarrationPolicy, guidance: string): string[] {
  const markers = ['【本次写作要求】', '【上一稿】', '【修订要求】'];
  for (const line of guidance.split('\n').slice(1)) {
    const trimmed = line.trim();
    if (trimmed.length >= 8) markers.push(trimmed.slice(0, 12));
  }
  const instruction = policy.instruction?.trim();
  if (instruction && prompt.includes(instruction)) markers.push(instruction.slice(0, 16));
  return markers;
}

function pickBest(attempts: readonly NarrationAttempt[]): NarrationAttempt | null {
  return attempts.reduce<NarrationAttempt | null>((best, candidate) => {
    if (!best) return candidate;
    const bestHard = hardCount(best.issues);
    const candidateHard = hardCount(candidate.issues);
    if (candidateHard !== bestHard) return candidateHard < bestHard ? candidate : best;
    return charsOf(candidate.cleaned) >= charsOf(best.cleaned) ? candidate : best;
  }, null);
}


export async function generateCommittedNarration(input: GenerateCommittedNarrationInput): Promise<GeneratedNarration> {
  if (!input.inputText.trim()) throw new Error('narration_input_empty: caller serialization produced no model input');
  const policy = input.policy ?? {};
  const callStarted = nowMs();
  const priorText = input.priorText ?? null;
  const ledger = buildLedger(input.committed, input.inputText, priorText, policy);
  const maxAttempts = clampInt(policy.maxAttempts ?? 2, 1, 4);
  const startTokens = clampInt(policy.maxTokens ?? 420, 64, 4096);
  const ceiling = clampInt(policy.maxTokensCeiling ?? 1200, startTokens, 8192);
  const deadlineMs = Math.max(1, policy.deadlineMs ?? 300_000);

  const attempts: NarrationAttempt[] = [];
  let guidance = '';
  let previousDraft: string | null = null;
  let maxTokens = startTokens;
  // A holder keeps TypeScript from assuming the closure assignment never ran.
  const progress: { last: NarrationDisplayState | null } = { last: null };
  let deadlineExceeded = false;

  const emit = (state: NarrationDisplayState): void => {
    progress.last = state;
    input.onProgress?.(state);
  };

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (input.signal?.aborted) break;
    const remaining = deadlineMs - (nowMs() - callStarted);
    if (remaining <= 0) { deadlineExceeded = true; break; }
    const prompt = composeNarrationPrompt({
      inputText: input.inputText,
      attempt,
      guidance,
      previousDraft,
      instruction: policy.instruction ?? null,
    }, policy);
    const result = await runAttempt({
      engine: input.engine,
      prompt,
      attempt,
      committed: input.committed,
      ledger,
      policy,
      priorText,
      maxTokens,
      temperature: attempt === 0 ? (policy.temperature ?? 0.7) : (policy.retryTemperature ?? 0.55),
      remainingMs: remaining,
      guidance,
      signal: input.signal,
      onProgress: emit,
    });
    attempts.push(result.attempt);
    if (result.deadlineHit || result.attempt.timedOut) deadlineExceeded = true;
    if (result.attempt.accepted || result.attempt.cancelled || result.attempt.timedOut) break;
    const hardIssues = result.attempt.issues.filter((issue) => issue.severity === 'hard');
    guidance = buildRevisionGuidance(hardIssues, ledger, policy);
    if (policy.revisionMode === 'revise' && result.attempt.cleaned) previousDraft = result.attempt.cleaned;
    if (hardIssues.some((issue) => issue.kind === 'truncated')) {
      maxTokens = Math.min(ceiling, Math.max(maxTokens + 160, Math.round(maxTokens * 1.5)));
    }
    if (nowMs() - callStarted >= deadlineMs) { deadlineExceeded = true; break; }
  }

  const acceptedAttempt = attempts.find((attempt) => attempt.accepted) ?? null;
  const completed = attempts.filter((attempt) => !attempt.cancelled && !attempt.timedOut);
  const best = acceptedAttempt ?? pickBest(completed);
  const cancelledAttempt = attempts.find((attempt) => attempt.cancelled) ?? null;
  const timeoutAttempt = attempts.find((attempt) => attempt.timedOut) ?? null;

  let status: GeneratedNarration['status'];
  if (acceptedAttempt) status = 'accepted';
  else if (cancelledAttempt || input.signal?.aborted) status = 'cancelled';
  else if (timeoutAttempt || deadlineExceeded) status = 'timeout';
  else if (!attempts.length) status = 'cancelled';
  else if (attempts.every((attempt) => attempt.error !== null && !attempt.cleaned)) status = 'error';
  else status = 'rejected';

  const selected = status === 'cancelled' ? cancelledAttempt : status === 'timeout' ? timeoutAttempt : best;
  const issues = selected?.issues ?? (status === 'cancelled'
    ? [{ kind: 'cancelled', severity: 'hard', attempt: 0, detail: 'cancelled before any attempt' } as NarrationIssue]
    : status === 'timeout'
      ? [{ kind: 'timeout', severity: 'hard', attempt: 0, detail: 'deadline exceeded before any attempt' } as NarrationIssue]
      : []);
  const text = selected?.cleaned ?? '';
  const metrics = selected?.metrics ?? null;
  const attemptIndex = selected ? attempts.indexOf(selected) : null;
  const totalMs = nowMs() - callStarted;
  const displayStatus: NarrationDisplayState['status'] = status === 'accepted' ? 'accepted'
    : status === 'cancelled' ? 'cancelled'
      : status === 'rejected' ? 'rejected' : 'failed';

  // The final display must match the returned text. Attempt-end displays are
  // already emitted; re-emit only when the chosen draft/status changed.
  if (!progress.last || progress.last.status !== displayStatus || progress.last.text !== text) {
    emit(displayStatus === 'accepted'
      ? { status: 'accepted', attempt: attemptIndex ?? 0, text, verified: true, elapsedMs: totalMs }
      : displayStatus === 'cancelled'
        ? { status: 'cancelled', attempt: attemptIndex ?? 0, text, verified: false, elapsedMs: totalMs }
        : displayStatus === 'rejected'
          ? { status: 'rejected', attempt: attemptIndex ?? 0, text, verified: false, elapsedMs: totalMs, issues }
          : { status: 'failed', attempt: attemptIndex ?? 0, text, verified: false, elapsedMs: totalMs, issues });
  }

  const attemptMs = attempts.map((attempt) => attempt.durationMs);
  return {
    text,
    rawAttempts: attempts,
    accepted: status === 'accepted',
    issues,
    timings: {
      totalMs,
      attemptMs,
      attemptsMs: attemptMs.reduce((sum, value) => sum + value, 0),
      firstTokenMs: attempts.map((attempt) => attempt.firstTokenMs).filter((value): value is number => value !== null)
        .sort((a, b) => a - b)[0] ?? null,
      deadlineExceeded,
    },
    strategyVersion: NARRATION_STRATEGY_VERSION,
    status,
    ledger,
    metrics,
    attemptIndex,
    display: progress.last as NarrationDisplayState,
  };
}
