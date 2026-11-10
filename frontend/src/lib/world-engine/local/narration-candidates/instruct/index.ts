/** A-route narration candidate: complete scene prose from a native instruct
 * model, graded against the committed point.
 *
 * One generation call per attempt (two attempts at most). The candidate never
 * writes state: it reads a settled point, asks the model for prose, cleans the
 * template artifacts, grades the draft with the runtime fact alignment and its
 * own scene checks, and returns every draft it paid for. A rejected draft is
 * returned as `accepted: false`; it is never relabelled as narration.
 *
 *   const result = await generateCandidate({
 *     engine, committed, inputText, priorText,
 *     state: after, before, delta, playerInput: lastCommand,
 *     policy: { targetChars: 260, maxAttempts: 2, template: 'qwen2.5-instruct' },
 *   });
 *   if (result.accepted) show(result.text); else showFailure(result);
 */
import { IncompleteGenerationError, isAbortError, type InferenceEngine } from '../../../runtime/engine';
import type { CompleteOptions } from '../../../runtime/engine';
import { cleanDraft, shapeIssues } from './clean';
import { buildProjection, pointIdOf } from './projection';
import { buildRepairPrompt, buildSceneUserPrompt, buildSystemPrompt } from './prompt';
import { renderPrompt, resolvePromptMode, resolveTemplate, stopSequences, type PromptMode, type ResolvedTemplate } from './template';
import type {
  CandidateAttempt, CandidateIssue, CandidateProgress, CandidateTimings,
  GenerateInstructCandidateArgs, GeneratedInstructCandidate, InstructCandidatePolicy, SceneProjection,
} from './types';
import { INSTRUCT_CANDIDATE_VERSION } from './types';
import { verifyDraft } from './verify';

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

/** Lane 08's adapter adds `chat()` next to the InferenceEngine contract so an
 * instruct checkpoint receives the caller's system turn. The shared interface
 * cannot carry it, so the candidate feature-detects it: with `chat()` the
 * system prompt is a real system turn; without it the same text goes through
 * `complete()` and the GGUF template wraps it as one user turn. */
interface ChatCapableEngine extends InferenceEngine {
  chat?: (messages: { role: 'system' | 'user' | 'assistant'; content: string }[], options?: CompleteOptions) => Promise<string>;
}

function defaultAttempts(policy: InstructCandidatePolicy): number {
  const value = policy.maxAttempts ?? 2;
  return Math.max(1, Math.min(2, value));
}

function attemptIssues(text: string, projection: SceneProjection, args: GenerateInstructCandidateArgs, attempt: number): CandidateIssue[] {
  const policy = args.policy ?? {};
  const shape = shapeIssues(text).map((entry) => ({ kind: entry.kind, severity: 'hard' as const, attempt, detail: entry.detail }));
  const verified = verifyDraft({
    text,
    projection,
    committed: args.committed ?? null,
    policy,
    previousText: args.priorText ?? null,
    licensedText: [args.playerInput ?? '', ...(args.settledResults ?? []), args.priorText ?? ''],
  });
  return [...shape, ...verified.issues.map((entry) => ({ ...entry, attempt }))];
}

function chooseBest(attempts: CandidateAttempt[]): CandidateAttempt | null {
  const usable = attempts.filter((attempt) => !attempt.cancelled && !attempt.timedOut && attempt.cleaned.trim());
  if (!usable.length) return null;
  const score = (attempt: CandidateAttempt) => attempt.issues.filter((entry) => entry.severity === 'hard').length;
  return usable.reduce((best, attempt) => (score(attempt) < score(best) ? attempt : best), usable[0]);
}

export async function generateCandidate(args: GenerateInstructCandidateArgs): Promise<GeneratedInstructCandidate> {
  const policy = args.policy ?? {};
  const template: ResolvedTemplate = resolveTemplate(policy.template, args.engine.info);
  const promptMode: PromptMode = resolvePromptMode(policy.promptMode, args.engine.info);
  const projection = buildProjection({
    state: args.state ?? null,
    before: args.before ?? null,
    delta: args.delta ?? null,
    committed: args.committed ?? null,
    policy,
    playerInput: args.playerInput ?? null,
    priorText: args.priorText ?? null,
    recentEvents: args.recentEvents ?? [],
    ...(args.inputText ? { inputText: args.inputText } : {}),
  });
  const pointId = args.pointId ?? pointIdOf(args.inputText);
  const attempts: CandidateAttempt[] = [];
  const attemptMs: number[] = [];
  const started = now();
  const deadlineMs = policy.deadlineMs ?? 180_000;
  const maxAttempts = defaultAttempts(policy);
  let deadlineExceeded = false;
  let cancelled = false;
  let timedOut = false;
  let lastPrompt = '';
  let previousText: string | null = null;
  let firstTokenMs: number | null = null;

  const system = buildSystemPrompt(policy);
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    if (now() - started > deadlineMs) { deadlineExceeded = true; break; }
    const user = attempt === 1 || !previousText
      ? buildSceneUserPrompt(projection, policy)
      : buildRepairPrompt({ projection, policy, previousText, issues: attempts[attempts.length - 1]?.issues ?? [] });
    const prompt = renderPrompt({ system, user }, template, promptMode);
    lastPrompt = prompt;
    const attemptStart = now();
    let attemptFirstToken: number | null = null;
    let raw = '';
    let finishReason: string | null = null;
    let error: string | null = null;
    let attemptCancelled = false;
    let attemptTimedOut = false;
    try {
      const options: CompleteOptions = {
        maxTokens: policy.maxTokens ?? 520,
        temperature: attempt === 1 ? (policy.temperature ?? 0.6) : (policy.retryTemperature ?? 0.35),
        seed: policy.seed ?? 42,
        stop: promptMode === 'raw' ? stopSequences(template) : undefined,
        timeoutMs: policy.timeoutMs ?? 120_000,
        ...(args.signal ? { signal: args.signal } : {}),
        onProgress: (progress) => {
          if (attemptFirstToken === null && progress.raw.trim()) attemptFirstToken = now() - attemptStart;
          const partial = cleanDraft(progress.raw).text;
          args.onProgress?.({
            pointId: pointId ?? null, text: partial, status: 'streaming', verified: false,
            elapsedMs: now() - started, attempt,
          });
        },
      };
      const chat = (args.engine as ChatCapableEngine).chat;
      raw = promptMode === 'chat' && typeof chat === 'function'
        ? await chat.call(args.engine, [{ role: 'system', content: system }, { role: 'user', content: user }], options)
        : await args.engine.complete(prompt, options);
    } catch (caught) {
      if (isAbortError(caught)) {
        attemptCancelled = true;
        cancelled = true;
      } else if (caught instanceof Error && /timeout|timed out/i.test(caught.message)) {
        attemptTimedOut = true;
        timedOut = true;
      } else if (caught instanceof IncompleteGenerationError) {
        // The adapter rejects a generation that stopped at the token cap (or
        // lost its finish reason) instead of returning a silent partial. The
        // paid text still has to be judged: keep it and let `truncated` drive
        // the repair, never relabel it as a transport error.
        raw = caught.completion.raw;
        finishReason = caught.completion.finishReason;
      } else {
        error = caught instanceof Error ? caught.message : String(caught);
      }
    }
    const durationMs = now() - attemptStart;
    attemptMs.push(durationMs);
    if (firstTokenMs === null && attemptFirstToken !== null) firstTokenMs = attemptFirstToken;
    const cleaned = cleanDraft(raw);
    const issues = raw && !attemptCancelled && !attemptTimedOut && !error
      ? attemptIssues(cleaned.text, projection, args, attempt)
        .concat(finishReason === 'length'
          ? [{ kind: 'truncated' as const, severity: 'hard' as const, attempt, detail: 'generation stopped at the token cap' }]
          : [])
      : [
        ...(attemptCancelled ? [{ kind: 'cancelled' as const, severity: 'hard' as const, attempt, detail: 'aborted' }] : []),
        ...(attemptTimedOut ? [{ kind: 'timeout' as const, severity: 'hard' as const, attempt, detail: 'engine timeout' }] : []),
        ...(error ? [{ kind: 'engine_error' as const, severity: 'hard' as const, attempt, detail: error }] : []),
      ];
    const accepted = !attemptCancelled && !attemptTimedOut && !error && !issues.some((entry) => entry.severity === 'hard');
    const record: CandidateAttempt = {
      attempt,
      prompt,
      promptChars: prompt.length,
      raw,
      cleaned: cleaned.text,
      durationMs,
      firstTokenMs: attemptFirstToken,
      finishReason,
      error,
      completion: null,
      issues,
      accepted,
      cancelled: attemptCancelled,
      timedOut: attemptTimedOut,
    };
    attempts.push(record);
    previousText = cleaned.text || previousText;
    if (accepted) break;
    if (attemptCancelled || attemptTimedOut || error) break;
  }

  const best = chooseBest(attempts);
  const text = best?.cleaned ?? '';
  const accepted = best?.accepted === true;
  const allIssues = attempts.flatMap((attempt) => attempt.issues);
  const totalMs = now() - started;
  const timings: CandidateTimings = {
    totalMs, attemptMs, firstTokenMs,
    deadlineExceeded: deadlineExceeded || totalMs > deadlineMs,
  };
  const status: GeneratedInstructCandidate['status'] = accepted ? 'accepted'
    : cancelled ? 'cancelled'
      : timedOut ? 'timeout'
        : text ? 'rejected' : 'error';
  const displayStatus: CandidateProgress['status'] = accepted ? 'accepted'
    : cancelled ? 'cancelled'
      : text ? 'rejected' : 'failed';
  const attemptIndex = best ? attempts.indexOf(best) : null;
  if (text) {
    args.onProgress?.({
      pointId: pointId ?? null, text, status: displayStatus, verified: accepted,
      elapsedMs: totalMs, attempt: best?.attempt ?? 0,
    });
  }
  return {
    text,
    accepted,
    rawAttempts: attempts,
    issues: allIssues,
    timings,
    strategyVersion: INSTRUCT_CANDIDATE_VERSION,
    status,
    prompt: lastPrompt,
    projection,
    attemptIndex,
    template,
  };
}

/** Bind an engine + defaults, keeping the `generateCandidate(args)` shape. */
export function createInstructCandidate(
  engine: InferenceEngine,
  defaults: Omit<GenerateInstructCandidateArgs, 'engine'> = {},
) {
  return (args: Omit<GenerateInstructCandidateArgs, 'engine'> = {}) => generateCandidate({ ...defaults, ...args, engine });
}

export type {
  CandidateProgress, CandidateIssue, CandidateAttempt, GeneratedInstructCandidate,
  GenerateInstructCandidateArgs, InstructCandidatePolicy, SceneProjection,
};
