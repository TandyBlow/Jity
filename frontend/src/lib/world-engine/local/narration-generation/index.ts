/** Committed-narration strategy: settled facts -> prompts -> raw model prose.
 *
 * The runtime does not inspect, refuse, rewrite or replace non-empty model prose
 * (NARRATION-RAW-OUTPUT-20261111). This module builds the prompt from the
 * committed facts and the caller's serialized input, makes the model call(s),
 * and returns the model's own text. Per-beat mode keeps the beat plan as display
 * boundaries only: each beat's answer is joined in order, never edited.
 *
 * There is no verification, no repair, no sentence pruning, no dedupe and no
 * program fallback here. An empty model answer is not prose; it stays empty.
 */
import {
  IncompleteGenerationError,
  type CompletionEvidence, type InferenceEngine,
} from '../../runtime/engine';
import type { CommittedNarration } from '../../runtime/committed-narration';
import { buildLedger } from './ledger';
import { composeNarrationPrompt } from './prompt';
import { renderProseFactsPrompt } from './scene-prompt';
import { buildBeatPrompt, planBeats } from './beats';
import {
  NARRATION_STRATEGY_VERSION,
  type GeneratedNarration, type GenerateCommittedNarrationInput, type NarrationAttempt,
  type NarrationBeatEvidence, type NarrationDisplayState, type NarrationIssue,
  type NarrationLedger, type NarrationPolicy, type NarrationSegment,
} from './types';

export * from './types';
export { buildLedger } from './ledger';
export { composeNarrationPrompt, insertBeforeBody, writingContract } from './prompt';
export {
  NARRATOR_SYSTEM_PROMPT, ownerOf, projectProseFacts, renderProseFactsPrompt, renderProseFactsUser,
} from './scene-prompt';
export { beatFallbackSentence, buildBeatPrompt, planBeats, timeFallbackSentence } from './beats';
export {
  renderTrainedInstructUser, renderTrainedRawPrompt, trainedSceneView, wrapChatml,
  type TrainedSceneInput, type TrainedSceneView,
} from './trained-input';

const nowMs = (): number => performance.now();

/** Protocol framing only: the 【正文】 marker and chat-template tokens are not
 * story content. Nothing else is removed. */
export function sanitizeNarration(raw: string): string {
  const marker = String.fromCharCode(0x3010) + '正文' + String.fromCharCode(0x3011);
  let text = raw.includes(marker) ? raw.split(marker).pop() ?? raw : raw;
  for (const token of ['<|im_end|>', '<|im_start|>', '<|endoftext|>']) {
    text = text.split(token).join('');
  }
  return text;
}

interface CallResult {
  raw: string;
  finishReason: string;
  firstTokenMs: number | null;
  ms: number;
  error: string | null;
}

async function callModel(
  engine: InferenceEngine,
  prompt: string,
  options: {
    maxTokens: number;
    temperature: number;
    timeoutMs: number;
    signal?: AbortSignal;
    stop?: string[];
    onProgress?: (raw: string, elapsedMs: number) => void;
    startedAt: number;
  },
): Promise<CallResult> {
  const started = nowMs();
  let raw = '';
  let finishReason = 'stop';
  let firstTokenMs: number | null = null;
  let error: string | null = null;
  try {
    const returned = await engine.complete(prompt, {
      maxTokens: options.maxTokens,
      temperature: options.temperature,
      timeoutMs: options.timeoutMs,
      ...(options.signal ? { signal: options.signal } : {}),
      ...(options.stop ? { stop: options.stop } : {}),
      onProgress: (progress) => {
        raw = progress.raw;
        options.onProgress?.(raw, nowMs() - options.startedAt);
      },
      onCompletion: (evidence: CompletionEvidence) => {
        if (evidence.raw) raw = evidence.raw;
        finishReason = evidence.finishReason ?? 'stop';
        firstTokenMs = evidence.firstTokenMs ?? null;
      },
    });
    if (typeof returned === 'string' && returned) raw = returned;
  } catch (caught) {
    if (caught instanceof IncompleteGenerationError) {
      // The engine still produced text; it is the content, not an error to
      // rewrite around.
      raw = caught.completion.raw;
      finishReason = caught.completion.finishReason ?? 'length';
      firstTokenMs = caught.completion.firstTokenMs ?? null;
    } else {
      error = caught instanceof Error ? `${caught.name}: ${caught.message}` : String(caught);
    }
  }
  return { raw, finishReason, firstTokenMs, ms: nowMs() - started, error };
}

type DisplayStatus = 'streaming' | 'accepted' | 'failed' | 'cancelled';

function display(text: string, status: DisplayStatus, attempt: number, elapsedMs: number): NarrationDisplayState {
  if (status === 'accepted') return { status, attempt, text, verified: true, elapsedMs };
  if (status === 'failed') return { status, attempt, text, verified: false, elapsedMs, issues: [] };
  if (status === 'cancelled') return { status, attempt, text, verified: false, elapsedMs };
  return { status, attempt, text, verified: false, elapsedMs };
}

/** One scene: the whole narration in a single model call. */
async function sceneNarration(
  input: GenerateCommittedNarrationInput,
  ledger: NarrationLedger,
  policy: NarrationPolicy,
  startedAt: number,
): Promise<GeneratedNarration> {
  const prose = policy.promptShape === 'prose-facts'
    ? renderProseFactsPrompt({ committed: input.committed, policy, scene: policy.scene ?? null })
    : composeNarrationPrompt({
      inputText: input.inputText, attempt: 0, guidance: '', previousDraft: null, instruction: null,
    }, policy);
  const attempt = await callModel(input.engine, prose, {
    maxTokens: policy.maxTokens ?? 480,
    temperature: policy.temperature ?? 0.6,
    timeoutMs: policy.timeoutMs ?? 150_000,
    ...(input.signal ? { signal: input.signal } : {}),
    ...(policy.stop ? { stop: policy.stop } : {}),
    startedAt,
    onProgress: (raw, elapsedMs) => {
      if (raw.trim()) input.onProgress?.(display(raw, 'streaming', 1, elapsedMs));
    },
  });
  const text = sanitizeNarration(attempt.raw);
  const attempts: NarrationAttempt[] = [{
    raw: attempt.raw,
    text,
    score: 0,
    issues: [],
    ms: attempt.ms,
    finishReason: attempt.finishReason,
    ...(attempt.error ? { error: attempt.error } : {}),
  } as NarrationAttempt];
  const status: GeneratedNarration['status'] = input.signal?.aborted ? 'cancelled'
    : attempt.error && !text.trim() ? 'error'
      : text.trim() ? 'accepted' : 'empty';
  const state = display(text, status === 'accepted' ? 'accepted' : status === 'cancelled' ? 'cancelled' : 'failed', 1, nowMs() - startedAt);
  if (text.trim()) input.onProgress?.(state);
  const segments: NarrationSegment[] = text.trim()
    ? [{ id: 'scene', kind: 'scene', source: 'model', text }]
    : [];
  return {
    text,
    rawAttempts: attempts,
    accepted: status === 'accepted' && text.trim().length > 0,
    issues: [],
    timings: {
      totalMs: nowMs() - startedAt,
      attemptMs: [attempt.ms],
      firstTokenMs: attempt.firstTokenMs,
      promptChars: prose.length,
      firstTextMs: text.trim() ? attempt.firstTokenMs : null,
      attempts: [{ attempt: 1, ms: attempt.ms, firstTokenMs: attempt.firstTokenMs, outcome: attempt.error ? 'error' : 'completed' }],
    },
    strategyVersion: NARRATION_STRATEGY_VERSION,
    status,
    ledger,
    metrics: null,
    attemptIndex: text.trim() ? 0 : null,
    beats: [],
    assembly: { droppedSentences: [], appendedSentences: [] },
    segments,
    beatCounts: { model: segments.length, fallback: 0, skipped: 0 },
    mixed: false,
    display: state,
  };
}

/** Beats: one model call per planned beat; answers joined as written. */
async function beatNarration(
  input: GenerateCommittedNarrationInput,
  ledger: NarrationLedger,
  policy: NarrationPolicy,
  startedAt: number,
): Promise<GeneratedNarration> {
  const beats = planBeats({ committed: input.committed, ledger, policy, scene: policy.scene ?? null });
  const evidence: NarrationBeatEvidence[] = [];
  const attempts: NarrationAttempt[] = [];
  const segments: NarrationSegment[] = [];
  const texts: string[] = [];
  let deadlineMs = startedAt + Math.max(5_000, policy.timeoutMs ?? 180_000);
  if (policy.deadlineMs) deadlineMs = Math.min(deadlineMs, startedAt + policy.deadlineMs);

  for (const beat of beats) {
    if (input.signal?.aborted) break;
    const remaining = deadlineMs - nowMs();
    if (remaining <= 2_000) break;
    const prompt = buildBeatPrompt({
      beat, ledger, policy, scene: policy.scene ?? null, written: [],
    });
    const result = await callModel(input.engine, prompt, {
      maxTokens: policy.beatMaxChars ? Math.max(240, policy.beatMaxChars) : policy.maxTokens ?? 480,
      temperature: policy.temperature ?? 0.6,
      timeoutMs: Math.min(policy.timeoutMs ?? 90_000, remaining - 1_000),
      ...(input.signal ? { signal: input.signal } : {}),
      ...(policy.stop ? { stop: policy.stop } : {}),
      startedAt,
      onProgress: (raw, elapsedMs) => {
        const current = [...texts, sanitizeNarration(raw)].filter((part) => part.trim()).join('\n\n');
        if (current.trim()) input.onProgress?.(display(current, 'streaming', evidence.length + 1, elapsedMs));
      },
    });
    const text = sanitizeNarration(result.raw);
    attempts.push({
      raw: result.raw,
      text,
      score: 0,
      issues: [],
      ms: result.ms,
      finishReason: result.finishReason,
      ...(result.error ? { error: result.error } : {}),
    } as NarrationAttempt);
    evidence.push({
      beatId: beat.id,
      kind: beat.kind,
      factId: beat.fact?.id ?? null,
      attempts: 1,
      issues: [],
      text,
      prompt,
      raw: result.raw,
      ms: result.ms,
    });
    if (text.trim()) {
      texts.push(text);
      segments.push({ id: beat.id, kind: beat.kind, source: 'model', text });
    }
  }

  const text = texts.join('\n\n');
  const cancelled = input.signal?.aborted === true;
  const errored = !text.trim() && attempts.length > 0 && attempts.every((attempt) => attempt.error);
  const status: GeneratedNarration['status'] = cancelled ? 'cancelled' : errored ? 'error' : text.trim() ? 'accepted' : 'empty';
  const state = display(text, status === 'accepted' ? 'accepted' : status === 'cancelled' ? 'cancelled' : 'failed', attempts.length, nowMs() - startedAt);
  if (text.trim()) input.onProgress?.(state);
  const issues: NarrationIssue[] = [];
  return {
    text,
    rawAttempts: attempts,
    accepted: status === 'accepted' && text.trim().length > 0,
    issues,
    timings: {
      totalMs: nowMs() - startedAt,
      attemptMs: attempts.map((attempt) => attempt.ms ?? attempt.durationMs ?? 0),
      firstTokenMs: attempts.find((attempt) => (attempt.text ?? '').trim())?.firstTokenMs ?? null,
      promptChars: attempts.reduce((sum, attempt) => sum + (typeof attempt.promptChars === 'number' ? attempt.promptChars : 0), 0),
      firstTextMs: text.trim() ? attempts.find((attempt) => (attempt.text ?? '').trim())?.firstTokenMs ?? null : null,
      attempts: attempts.map((attempt, index) => ({
        attempt: index + 1, ms: attempt.ms ?? attempt.durationMs ?? 0, firstTokenMs: attempt.firstTokenMs ?? null,
        outcome: attempt.error ? 'error' : 'completed',
      })),
    },
    strategyVersion: NARRATION_STRATEGY_VERSION,
    status,
    ledger,
    metrics: null,
    attemptIndex: text.trim() ? 0 : null,
    beats: evidence,
    assembly: { droppedSentences: [], appendedSentences: [] },
    segments,
    beatCounts: { model: segments.length, fallback: 0, skipped: 0 },
    mixed: false,
    display: state,
  };
}

export async function generateCommittedNarration(input: GenerateCommittedNarrationInput): Promise<GeneratedNarration> {
  const startedAt = nowMs();
  const policy = input.policy ?? {};
  const ledger = buildLedger(input.committed, input.inputText, policy);
  return policy.mode === 'scene'
    ? sceneNarration(input, ledger, policy, startedAt)
    : beatNarration(input, ledger, policy, startedAt);
}

/** Compatible entry named by QUALITY-TEAMS.md: same arguments, same return
 * shape as `generateCommittedNarration`. */
export const generateCandidate = (
  input: GenerateCommittedNarrationInput,
): Promise<GeneratedNarration> => generateCommittedNarration(input);
