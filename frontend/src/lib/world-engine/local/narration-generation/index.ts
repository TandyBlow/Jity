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
import { factPhrases, type CommittedNarration } from '../../runtime/committed-narration';
import { buildLedger } from './ledger';
import { buildRevisionGuidance } from './guidance';
import { composeNarrationPrompt } from './prompt';
import { renderProseFactsPrompt } from './scene-prompt';
import { senseViolations } from './licensed-sense';
import { actionViolations } from './licensed-action';
import { stripBeatLabel } from './beats';
import { beatFallbackSentence, buildBeatPrompt, planBeats, timeFallbackSentence } from './beats';
import { verifyNarration } from './verify';
import {
  NARRATION_STRATEGY_VERSION,
  type GeneratedNarration, type GenerateCommittedNarrationInput, type NarrationAttempt,
  type NarrationAssembly, type NarrationBeatEvidence, type NarrationDisplayState, type NarrationIssue,
  type NarrationLedger, type NarrationPolicy,
} from './types';

export * from './types';
export { buildLedger } from './ledger';
export { buildRevisionGuidance } from './guidance';
export { composeNarrationPrompt, insertBeforeBody, writingContract } from './prompt';
export {
  NARRATOR_SYSTEM_PROMPT, ownerOf, projectProseFacts, renderProseFactsPrompt, renderProseFactsUser,
} from './scene-prompt';
export { beatFallbackSentence, buildBeatPrompt, planBeats, timeFallbackSentence } from './beats';
export { verifyNarration } from './verify';
export {
  renderTrainedInstructUser, renderTrainedRawPrompt, trainedSceneView, wrapChatml,
  type TrainedSceneInput, type TrainedSceneView,
} from './trained-input';

const nowMs = (): number => performance.now();
/** Last non-empty sentence of a previously accepted scene. */
const firstSentence = (text: string): string | null => {
  const parts = text.split(/[。！？\n]+/u).map((part) => part.trim()).filter(Boolean);
  return parts.length ? parts[0] : null;
};

/** Last non-empty sentence of a previously accepted scene. */
const lastSentence = (text: string): string | null => {
  const parts = text.split(/[。！？\n]+/u).map((part) => part.trim()).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : null;
};
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
  /** Beat mode builds one small prompt per beat instead of the scene prompt. */
  buildPrompt?: (attempt: number, guidance: string) => string;
  /** Instruction fragments that must not appear in the prose. */
  echoMarkers?: string[];
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
    promptEchoMarkers: args.echoMarkers ?? promptEchoMarkers(args.prompt, args.policy, args.guidance),
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


const SENTENCE_SPLIT = /(?<=[。！？])/u;
const normalizeSentence = (text: string): string => text.replace(/[\s，。！？；：、「」『』“”"'…—\-·]/gu, '');

/** Drop duplicated sentences from an assembled scene, keeping the first
 * occurrence and the paragraph order. This is assembly, not rewriting: every
 * sentence that survives is one the model wrote or a committed fact sentence. */
export function dropDuplicateSentences(text: string): { text: string; dropped: string[] } {
  const dropped: string[] = [];
  const seen = new Set<string>();
  const paragraphs = text.split(/\n\s*\n/u).map((paragraph) => paragraph.trim()).filter(Boolean);
  const kept = paragraphs.map((paragraph) => paragraph.split(SENTENCE_SPLIT)
    .map((sentence) => sentence.trim())
    .filter(Boolean)
    .filter((sentence) => {
      const key = normalizeSentence(sentence);
      if (key.length < 4) return true;
      if (seen.has(key)) { dropped.push(sentence); return false; }
      seen.add(key);
      return true;
    })
    .join(''));
  return { text: kept.filter(Boolean).join('\n\n'), dropped };
}

/** Sentences that must not be removed from a scene: they are the only trace of
 * a settled change. Removal decisions are limited to endings that mention none
 * of these strings. */
function protectedStrings(committed: CommittedNarration): string[] {
  const out: string[] = [];
  for (const fact of committed.facts) {
    if (fact.kind === 'moved') out.push(fact.from, fact.to);
    else if (fact.kind === 'task_achieved') out.push(fact.goal);
    else if (fact.kind === 'personality_changed') out.push(fact.text);
    else if (fact.kind === 'sanity_changed') out.push(String(fact.from), String(fact.to));
    else if (fact.kind === 'at') out.push(fact.location);
  }
  return out.filter((value) => value && value.length >= 2);
}

const bigramSet = (text: string): Set<string> => {
  const clean = text.replace(/[\s，。！？；：、「」『』“”"'…—·,.!?]/gu, '');
  const out = new Set<string>();
  for (let index = 0; index + 1 < clean.length; index += 1) out.add(clean.slice(index, index + 2));
  return out;
};

const shareOf = (a: Set<string>, b: Set<string>): number => {
  if (!a.size || !b.size) return 0;
  let shared = 0;
  for (const gram of a) if (b.has(gram)) shared += 1;
  return shared / Math.min(a.size, b.size);
};

/** Cross-turn repetition, structurally: a scene that ends on (nearly) the same
 * sentence as the previous accepted scene is prose the player reads every
 * turn. The fix belongs to assembly, not to the fact checks: drop that closing
 * sentence when it carries no settled fact, and stop at two removals so the
 * scene cannot be hollowed out. Returns the text unchanged when the ending is
 * new, protected, or the remainder would fall under the length floor. */
export function trimEchoedEnding(
  text: string,
  priorText: string | null | undefined,
  options: { protect?: readonly string[]; minChars?: number } = {},
): { text: string; dropped: string[] } {
  const dropped: string[] = [];
  if (!priorText || !text.trim()) return { text, dropped };
  const protect = (options.protect ?? []).filter(Boolean);
  const floor = Math.max(20, options.minChars ?? 60);
  let current = text.trim();
  for (let round = 0; round < 2; round += 1) {
    const sentences = [...current.matchAll(/[^。！？\n]+[。！？]?/gu)].map((match) => match[0].trim()).filter(Boolean);
    if (sentences.length < 2) break;
    const last = sentences[sentences.length - 1];
    if (protect.some((value) => last.includes(value))) break;
    const priorTail = priorText.split(/[。！？\n]+/u).map((part) => part.trim()).filter(Boolean).slice(-2).join('');
    if (shareOf(bigramSet(last), bigramSet(priorTail)) < 0.6) break;
    const rest = sentences.slice(0, -1).join('').trim();
    if ([...rest].length < floor) break;
    dropped.push(last);
    current = rest;
  }
  return { text: current, dropped };
}

/** Issues for a scene that produced no text at all. */
function emptySceneIssues(cancelled: boolean, timedOut: boolean): NarrationIssue[] {
  if (cancelled) return [{ kind: 'cancelled', severity: 'hard', attempt: 0, detail: 'cancelled before any beat' }];
  if (timedOut) return [{ kind: 'timeout', severity: 'hard', attempt: 0, detail: 'deadline exceeded before any beat' }];
  return [{ kind: 'empty_narration', severity: 'hard', attempt: 0, detail: 'no beat produced text' }];
}

interface BeatRunResult {
  evidence: NarrationBeatEvidence;
  text: string;
  source: NarrationBeatEvidence['source'];
}

interface BeatArgs {
  input: GenerateCommittedNarrationInput;
  committed: CommittedNarration;
  ledger: NarrationLedger;
  policy: NarrationPolicy;
  startedAt: number;
  deadlineMs: number;
  onAttempt: (attempt: NarrationAttempt) => void;
  onStream: (beatText: string) => void;
}

/** Writes one beat with bounded repair, then falls back to the committed fact
 * sentence only when the beat carries a settled fact. A scene/atmosphere beat
 * that fails is skipped: inventing scenery is worse than a shorter scene. */
async function writeBeat(
  args: BeatArgs,
  beat: ReturnType<typeof planBeats>[number],
  written: readonly string[],
): Promise<BeatRunResult> {
  const { input, committed, ledger, policy, startedAt, deadlineMs } = args;
  const attemptBudget = clampInt(policy.beatAttempts ?? 2, 1, 3);
  const scopedPolicy: NarrationPolicy = {
    ...policy,
    mode: 'scene',
    minChars: 1,
    targetChars: 1,
    maxAttempts: 1,
    beatMaxChars: policy.beatMaxChars ?? 170,
  };
  const scopedLedger: NarrationLedger = {
    ...ledger,
    mandatory: beat.fact ? [beat.fact] : [],
    requireTime: beat.kind === 'time',
  };
  const prompts: string[] = [];
  const raws: string[] = [];
  const issues: NarrationIssue[] = [];
  let guidance = '';
  let attemptNumber = 0;
  const started = nowMs();
  for (let attempt = 0; attempt < attemptBudget; attempt += 1) {
    const remaining = deadlineMs - (nowMs() - startedAt);
    if (remaining <= 0 || input.signal?.aborted) break;
    const base = buildBeatPrompt({
      beat, ledger, policy, scene: policy.scene ?? null, written,
      priorTail: input.priorText ?? null,
    });
    const prompt = guidance
      ? `${base.replace(/正文：$/u, '')}\n【改写要求】${guidance}\n正文：`
      : base;
    prompts.push(prompt);
    // A scene/atmosphere beat is optional and must not eat the whole budget:
    // it is capped to a short paragraph and a short call, so a slow model
    // reaches the fact beats instead of stalling the point. Fact/time beats
    // keep the caller's full budget.
    const isSceneBeat = beat.kind === 'scene';
    // A quiet point has no fact beats to carry the scene, so the opening beat
    // IS the scene: a 90-token cap produced 81-character answers (rejected
    // against a 120-char floor). A mandatory scene beat gets the full budget;
    // an optional atmosphere beat stays short so it cannot eat the point.
    const beatTokens = isSceneBeat
      ? (beat.mandatory ? Math.min(policy.maxTokens ?? 160, 220) : Math.min(policy.maxTokens ?? 160, 90))
      : beat.kind === 'time' ? Math.min(policy.maxTokens ?? 160, 120) : (policy.maxTokens ?? 160);
    const beatRemaining = isSceneBeat ? Math.min(remaining, 45_000) : remaining;
    const result = await runAttempt({
      engine: input.engine,
      prompt,
      attempt: attemptNumber,
      committed,
      ledger: scopedLedger,
      policy: scopedPolicy,
      priorText: written.at(-1) ?? input.priorText ?? null,
      maxTokens: beatTokens,
      temperature: attempt === 0 ? (policy.temperature ?? 0.7) : (policy.retryTemperature ?? 0.5),
      remainingMs: beatRemaining,
      guidance,
      signal: input.signal,
      onProgress: (state) => {
        if (state.status === 'streaming') args.onStream(state.text);
      },
      echoMarkers: [
        '【要求】', '【这一件】', '你是中文小说作者',
        ...(beat.directive.length >= 12 ? [beat.directive.slice(0, 14)] : []),
      ],
    });
    args.onAttempt({ ...result.attempt, attempt: attemptNumber });
    attemptNumber += 1;
    raws.push(result.attempt.raw);
    issues.push(...result.attempt.issues.filter((issue) => issue.severity === 'hard'));
    const evidenceBase = {
      beatId: beat.id, kind: beat.kind, directive: beat.directive,
      attempts: attempt + 1, durationMs: nowMs() - started, prompts, raws,
    };
    if (result.attempt.accepted && result.attempt.cleaned) {
      // A beat label the model echoed («【环境】…») is an instruction, not
      // prose; the page would show it as text. Strip it before using the beat.
      const body = stripBeatLabel(result.attempt.cleaned);
      const invented = senseViolations(body, input.inputText, {
        movedNames: input.committed.facts.filter((fact) => fact.kind === 'moved').map((fact) => fact.name),
      });
      if (invented.length) {
        // Same narrow rule as the whole-scene path: an invented sound or smell
        // fails the beat instead of reaching the page as narration.
        const detail = invented.map((item) => `${item.noun}（${item.sentence}）`).join('；');
        issues.push({ kind: 'unlicensed_sense', severity: 'hard', attempt: attempt + 1, detail, sentence: invented[0].sentence });
        return {
          evidence: { ...evidenceBase, text: body, source: 'skipped', issues: [...issues, { kind: 'unlicensed_sense', severity: 'hard', attempt: attempt + 1, detail, sentence: invented[0].sentence }] },
          text: '',
          source: 'skipped',
        };
      }
      return {
        evidence: { ...evidenceBase, text: body, source: 'model', issues: [...issues] },
        text: body,
        source: 'model',
      };
    }
    if (result.attempt.cancelled || result.attempt.timedOut) {
      return {
        evidence: { ...evidenceBase, text: '', source: 'skipped', issues: result.attempt.issues },
        text: '',
        source: 'skipped',
      };
    }
    guidance = buildRevisionGuidance(
      result.attempt.issues.filter((issue) => issue.severity === 'hard'), scopedLedger, scopedPolicy,
    );
  }
  if (beat.kind === 'fact' && beat.fact) {
    const text = beatFallbackSentence(beat);
    return {
      evidence: {
        beatId: beat.id, kind: beat.kind, directive: beat.directive, text,
        source: 'fallback', attempts: attemptNumber, durationMs: nowMs() - started, issues, prompts, raws,
      },
      text,
      source: 'fallback',
    };
  }
  if (beat.kind === 'time' && ledger.time) {
    const text = timeFallbackSentence(ledger.time.duration, input.priorText ?? null);
    return {
      evidence: {
        beatId: beat.id, kind: beat.kind, directive: beat.directive, text,
        source: 'fallback', attempts: attemptNumber, durationMs: nowMs() - started, issues, prompts, raws,
      },
      text,
      source: 'fallback',
    };
  }
  return {
    evidence: {
      beatId: beat.id, kind: beat.kind, directive: beat.directive, text: '',
      source: 'skipped', attempts: attemptNumber, durationMs: nowMs() - started, issues, prompts, raws,
    },
    text: '',
    source: 'skipped',
  };
}

/** Beat-mode entry: plan → write each beat (streaming after every beat and
 * inside every beat) → assemble → final scene check with program-side dedupe
 * and fact-sentence completion. */
async function generateBeatNarration(
  input: GenerateCommittedNarrationInput,
  ledger: NarrationLedger,
  policy: NarrationPolicy,
  startedAt: number,
  deadlineMs: number,
  priorText: string | null,
): Promise<GeneratedNarration> {
  const beats = planBeats({ committed: input.committed, ledger, policy, scene: policy.scene ?? null });
  const attempts: NarrationAttempt[] = [];
  const evidence: NarrationBeatEvidence[] = [];
  const written: string[] = [];
  let deadlineExceeded = false;
  let cancelled = false;
  let attemptCount = 0;
  let lastDisplay: NarrationDisplayState | null = null;
  const assembly: NarrationAssembly = { droppedSentences: [], appendedSentences: [] };

  const emit = (current: string, status: NarrationDisplayState['status'] = 'streaming', issues?: NarrationIssue[]): void => {
    const text = [...written, current].filter(Boolean).join('\n\n').trim();
    const elapsedMs = nowMs() - startedAt;
    const state: NarrationDisplayState = status === 'accepted'
      ? { status, attempt: attemptCount, text, verified: true, elapsedMs }
      : status === 'rejected' || status === 'failed'
        ? { status, attempt: attemptCount, text, verified: false, elapsedMs, issues: issues ?? [] }
        : status === 'cancelled'
          ? { status, attempt: attemptCount, text, verified: false, elapsedMs }
          : { status: 'streaming', attempt: attemptCount, text, verified: false, elapsedMs };
    lastDisplay = state;
    input.onProgress?.(state);
  };

  for (const beat of beats) {
    if (input.signal?.aborted) { cancelled = true; break; }
    if (nowMs() - startedAt >= deadlineMs) { deadlineExceeded = true; break; }
    const result = await writeBeat({
      input, committed: input.committed, ledger, policy, startedAt, deadlineMs,
      onAttempt: (attempt) => { attempts.push(attempt); attemptCount += 1; },
      onStream: (beatText) => emit(beatText),
    }, beat, written);
    evidence.push(result.evidence);
    if (result.text) written.push(result.text);
    emit('');
    if (input.signal?.aborted) { cancelled = true; break; }
  }

  let assembled = written.join('\n\n').trim();
  const deduped = dropDuplicateSentences(assembled);
  if (deduped.dropped.length) {
    assembly.droppedSentences.push(...deduped.dropped);
    assembled = deduped.text;
  }
  // A scene that ends on the same sentence as the previous turn reads as
  // repeated prose even when every fact is right. Assembly removes that
  // ending only when the sentence carries no settled fact.
  const trimmed = trimEchoedEnding(assembled, priorText, {
    protect: protectedStrings(input.committed),
    minChars: policy.minChars ?? 60,
  });
  if (trimmed.dropped.length) {
    assembly.droppedSentences.push(...trimmed.dropped);
    assembled = trimmed.text;
  }

  const finalPolicy: NarrationPolicy = { ...policy, minChars: policy.minChars ?? 60 };
  const runFinalVerify = (text: string) => verifyNarration({
    text, finishReason: 'stop', committed: input.committed, ledger, policy: finalPolicy,
    priorText, attempt: Math.max(0, attemptCount - 1), promptEchoMarkers: [],
  });
  let final = assembled ? runFinalVerify(assembled) : null;

  // A missing required time or a settled fact that no beat expressed is
  // completed with the committed sentence instead of hiding the gap.
  if (final) {
    const append: string[] = [];
    for (const issue of final.issues) {
      if (issue.severity !== 'hard') continue;
      if (issue.kind === 'time_missing' && ledger.time) {
        append.push(timeFallbackSentence(ledger.time.duration, priorText));
      }
      if (issue.kind === 'fact_omitted') {
        const fact = ledger.mandatory.find((entry) => !issue.detail || issue.detail.includes(factPhrases(entry)[0]));
        if (fact) {
          append.push(beatFallbackSentence({
            id: 'repair', kind: 'fact', fact, directive: '', anchors: [], licensed: [],
            fallback: 'fact-sentence', mandatory: true,
          }));
        }
      }
    }
    if (append.length) {
      assembly.appendedSentences.push(...append);
      assembled = `${assembled}\n\n${append.join('')}`.trim();
      final = runFinalVerify(assembled);
    }
  }

  const sceneIssues = final?.issues ?? emptySceneIssues(input.signal?.aborted === true, deadlineExceeded);
  const hardIssues = sceneIssues.filter((issue) => issue.severity === 'hard');
  const allFellBack = !cancelled && !deadlineExceeded && evidence.length > 0
    && evidence.every((entry) => entry.source !== 'model');
  if (allFellBack) {
    hardIssues.push({
      kind: 'all_beats_fell_back', severity: 'hard', attempt: Math.max(0, attemptCount - 1),
      detail: 'every beat used the committed fact sentence; no generated prose',
    });
    sceneIssues.push(hardIssues[hardIssues.length - 1]);
  }
  const accepted = !cancelled && !deadlineExceeded && hardIssues.length === 0 && assembled.length > 0;
  const status: GeneratedNarration['status'] = accepted ? 'accepted'
    : cancelled ? 'cancelled' : deadlineExceeded ? 'timeout' : 'rejected';
  const totalMs = nowMs() - startedAt;
  const displayStatus: NarrationDisplayState['status'] = accepted ? 'accepted'
    : status === 'cancelled' ? 'cancelled' : status === 'timeout' ? 'failed' : 'rejected';
  emit('', displayStatus, final?.issues ?? hardIssues);

  const attemptMs = attempts.map((attempt) => attempt.durationMs);
  return {
    text: assembled,
    rawAttempts: attempts,
    accepted,
    issues: sceneIssues,
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
    metrics: final?.metrics ?? null,
    attemptIndex: attempts.length ? Math.max(0, attemptCount - 1) : null,
    beats: evidence,
    assembly,
    segments: evidence.map((beat) => ({
      beatId: beat.beatId, kind: beat.kind, source: beat.source, text: beat.text,
    })),
    beatCounts: {
      model: evidence.filter((beat) => beat.source === 'model').length,
      fallback: evidence.filter((beat) => beat.source === 'fallback').length,
      skipped: evidence.filter((beat) => beat.source === 'skipped').length,
    },
    mixed: evidence.some((beat) => beat.source === 'model') && evidence.some((beat) => beat.source !== 'model'),
    display: lastDisplay ?? {
      status: displayStatus,
      attempt: Math.max(0, attemptCount - 1),
      text: assembled,
      verified: accepted,
      elapsedMs: totalMs,
      ...(displayStatus === 'rejected' || displayStatus === 'failed' ? { issues: final?.issues ?? hardIssues } : {}),
    } as NarrationDisplayState,
  };
}

/** Compatible entry named by QUALITY-TEAMS.md: same arguments, same return
 * shape as `generateCommittedNarration`. Kept as a thin alias so integrators
 * and candidate runners can use one name without a second implementation. */
export const generateCandidate = (
  input: GenerateCommittedNarrationInput,
): Promise<GeneratedNarration> => generateCommittedNarration(input);

/** Ask the model to rewrite ONE sentence that invented something.
 *
 * Whole-draft retries keep reproducing the same ambient detail or the same
 * habitual gesture, so this narrows the task to a single sentence. The caller
 * re-checks the spliced text with the same narrow rules and the full verifier;
 * a repaired sentence that still invents something is discarded. */
async function repairSentences(args: {
  engine: InferenceEngine;
  text: string;
  inputText: string;
  policy: NarrationPolicy;
  attempt: number;
  ledger: NarrationLedger;
  signal?: AbortSignal;
}): Promise<string | null> {
  let text = args.text;
  for (let round = 0; round < 3; round += 1) {
    const movedNames = args.ledger.mandatory.filter((fact) => fact.kind === 'moved').map((fact) => fact.name);
    const senses = senseViolations(text, args.inputText, { movedNames });
    const acts = senses.length ? [] : actionViolations(text, args.inputText);
    if (!senses.length && !acts.length) return text;
    const target = senses.length
      ? { sentence: senses[0].sentence, lines: [
        '下面这句里写了没有出现过的声音或气味：',
        `原句：${senses[0].sentence}`,
        '',
        '只重写这一句：删掉那个声音或气味，保留这句里其它已经发生的事，不要新增任何声音、气味、动作或人物。',
        '只输出重写后的这一句，不要解释。',
      ] }
      : { sentence: acts[0].sentence, lines: [
        '下面这句里写了没有发生的姿势或手上的动作：',
        `原句：${acts[0].sentence}`,
        '',
        `只重写这一句：删掉「${acts[0].word}」这个动作（${acts[0].object ? `以及摆弄${acts[0].object}的部分` : '如果它只是被这个人拿在手里'}），保留这句里其它已经发生的事，不要新增动作、人物或物品。`,
        '只输出重写后的这一句，不要解释。',
      ] };
    let answer = '';
    try {
      answer = (await args.engine.complete(target.lines.join(String.fromCharCode(10)), {
        maxTokens: 120,
        temperature: 0.3,
        ...(args.policy.seed !== undefined ? { seed: args.policy.seed } : {}),
        ...(args.signal ? { signal: args.signal } : {}),
        timeoutMs: 45_000,
      }) ?? '').trim();
    } catch {
      return null;
    }
    const clean = answer.split(new RegExp(String.fromCharCode(10) + '+', 'u'))[0]?.trim() ?? '';
    if (!clean || clean.length > 120) return null;
    const at = text.indexOf(target.sentence);
    if (at < 0) return null;
    const after = text.slice(at + target.sentence.length);
    const hasMark = /^[。！？!?]/u.test(after);
    const punct = hasMark ? after[0] : '。';
    const body = clean.replace(/[。！？!?]+$/u, '');
    const rest = hasMark ? after.slice(1) : after;
    text = text.slice(0, at) + body + punct + rest;
  }
  return text;
}

export async function generateCommittedNarration(input: GenerateCommittedNarrationInput): Promise<GeneratedNarration> {
  if (!input.inputText.trim()) throw new Error('narration_input_empty: caller serialization produced no model input');
  const policy = input.policy ?? {};
  const callStarted = nowMs();
  const priorText = input.priorText ?? null;
  const ledger = buildLedger(input.committed, input.inputText, priorText, policy);
  const mode = policy.mode ?? (policy.scene ? 'beats' : 'scene');
  const deadlineBudget = Math.max(1, policy.deadlineMs ?? 300_000);
  if (mode === 'beats') {
    return generateBeatNarration(input, ledger, policy, callStarted, deadlineBudget, priorText);
  }
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
    // The deployable instruct model was measured on a closed-book turn, not on
    // lane 01's state record. `prose-facts` renders the same committed packet
    // in that shape; `serialized` keeps the training shape for fine-tuned
    // checkpoints. Guidance and the previous draft are appended by the same
    // composer, so a repair never loses the licensed material.
    const baseInput = policy.promptShape === 'prose-facts'
      ? renderProseFactsPrompt({
        committed: input.committed,
        policy,
        scene: policy.scene ?? null,
        priorTail: priorText ? lastSentence(priorText) : null,
        priorOpen: priorText ? firstSentence(priorText) : null,
      })
      : input.inputText;
    const prompt = composeNarrationPrompt({
      inputText: baseInput,
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
    // A sound or smell with no settled source asserts something that did not
    // happen. The real runs invented wind, footsteps and the smell of exercise
    // rounds in texts the general gate accepted, so this narrow class is checked
    // here, before the retry decision, and the guidance names the sentence.
    // The check is independent of the other rules: a draft that is also too
    // short can still assert an invented sound, and the evidence must say so.
    if (result.attempt.cleaned) {
      const invented = senseViolations(result.attempt.cleaned, input.inputText, {
        movedNames: input.committed.facts.filter((fact) => fact.kind === 'moved').map((fact) => fact.name),
      });
      if (invented.length) {
        result.attempt.accepted = false;
        if (!result.attempt.issues.some((issue) => issue.kind === 'unlicensed_sense')) result.attempt.issues.push({
          kind: 'unlicensed_sense', severity: 'hard', attempt: result.attempt.attempt,
          detail: invented.map((item) => `${item.noun}（${item.sentence}）`).join('；'),
          sentence: invented[0].sentence,
        });
      }
      const acted = actionViolations(result.attempt.cleaned, input.inputText);
      if (acted.length) {
        result.attempt.accepted = false;
        if (!result.attempt.issues.some((issue) => issue.kind === 'unlicensed_action')) result.attempt.issues.push({
          kind: 'unlicensed_action', severity: 'hard', attempt: result.attempt.attempt,
          detail: acted.map((item) => `${item.word}${item.object ? `·${item.object}` : ''}（${item.sentence}）`).join('；'),
          sentence: acted[0].sentence,
        });
      }
    }
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

  // Sentence-level repair for the one class the whole-draft retry cannot fix:
  // a sound or smell with no settled source. Rewriting the whole scene again
  // reproduces the same ambient detail, so the caller asks for the offending
  // sentence only and splices it back. If that still invents a sense, the
  // draft stays rejected; nothing is presented as narration on a guess.
  for (const attempt of attempts) {
    const hard = (attempt.issues ?? []).filter((issue) => issue.severity === 'hard');
    // Only a draft whose sole hard problem is the invented sense is repaired;
    // any other hard issue means the sentence is not the thing to fix.
    if (attempt.accepted || !attempt.cleaned) continue;
    // Length is included: a draft can be short *and* invent something, and the
    // repair only touches the invented sentence. The full verifier still runs
    // on the repaired text, so a draft that stays too short is rejected.
    const repairable = hard.every((issue) => issue.kind === 'unlicensed_sense'
      || issue.kind === 'unlicensed_action' || issue.kind === 'too_short');
    if (!hard.length || !repairable) continue;
    const repaired = await repairSentences({
      engine: input.engine, text: attempt.cleaned, inputText: input.inputText,
      policy, attempt: attempt.attempt, ledger, signal: input.signal,
    });
    if (!repaired) continue;
    const still = senseViolations(repaired, input.inputText, {
      movedNames: input.committed.facts.filter((fact) => fact.kind === 'moved').map((fact) => fact.name),
    });
    if (still.length) continue;
    if (actionViolations(repaired, input.inputText).length) continue;
    const check = verifyNarration({
      text: repaired, finishReason: 'stop', committed: input.committed, ledger, policy,
      priorText, attempt: attempt.attempt, promptEchoMarkers: [],
    });
    if (check.issues.some((issue) => issue.severity === 'hard')) continue;
    attempt.repairedIssues = [...(attempt.issues ?? [])];
    attempt.cleaned = repaired;
    attempt.accepted = true;
    attempt.issues = [...check.issues];
    // One repaired draft is enough; later attempts are older drafts.
    break;
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
  // Scene mode has no assembly step, so the cross-turn echoed ending is
  // removed here. It is only applied when the trimmed text still passes the
  // same verification; otherwise the model's text is kept as written.
  let text = selected?.cleaned ?? '';
  const sceneAssembly: NarrationAssembly = { droppedSentences: [], appendedSentences: [] };
  if (acceptedAttempt && text && priorText) {
    const trimmed = trimEchoedEnding(text, priorText, {
      protect: protectedStrings(input.committed),
      minChars: policy.minChars ?? 60,
    });
    if (trimmed.dropped.length) {
      const recheck = verifyNarration({
        text: trimmed.text, finishReason: 'stop', committed: input.committed, ledger, policy,
        priorText, attempt: 0, promptEchoMarkers: [],
      });
      if (recheck.issues.every((issue) => issue.severity !== 'hard')) {
        text = trimmed.text;
        sceneAssembly.droppedSentences.push(...trimmed.dropped);
      }
    }
  }
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
    beats: [],
    assembly: sceneAssembly,
    // A whole-scene answer is one paragraph, written by the model when the
    // attempt was accepted; the program never fills part of it.
    segments: text ? [{ beatId: 'scene', kind: 'scene', source: status === 'accepted' ? 'model' : 'skipped', text }] : [],
    beatCounts: { model: status === 'accepted' ? 1 : 0, fallback: 0, skipped: status === 'accepted' ? 0 : 1 },
    mixed: false,
    display: progress.last as NarrationDisplayState,
  };
}
// ZZZ_MARKER
