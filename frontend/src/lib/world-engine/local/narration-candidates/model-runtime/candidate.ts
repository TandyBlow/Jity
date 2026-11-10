/** Reference A-route candidate over a real instruct checkpoint.
 *
 * 03 owns the product generation policy. This module is the model/runtime
 * half that 03 and 09 can call as-is: it takes the shared candidate args
 * (`{engine, committed, inputText, priorText, signal, onProgress, policy}`),
 * renders one committed point with the checkpoint's own template, streams
 * real chunks, and verifies the text against the committed facts with the
 * existing alignment grader. It is deliberately one call per point (plus one
 * bounded repair), because every intermediate model call counts against the
 * player's wait.
 *
 * The text is never replaced by a template when verification fails: the
 * caller receives `accepted: false` and the issues, so a page can show the
 * draft as unverified or fall back on its own terms.
 */
import { IncompleteGenerationError, isAbortError, type CompletionEvidence } from '../../../runtime/engine';
import { alignNarration } from '../../../runtime/narration-alignment';
import type { CommittedNarration } from '../../../runtime/committed-narration';
import {
  buildMessages, cleanNarration, describeCommitted, renderFallbackPrompt, renderNarrationUser, ThinkingFilter,
} from './template';
import { modelSpecByFile } from './catalog';
import type {
  CandidateArgs, CandidateAttempt, CandidateIssue, CandidatePolicy, CandidateResult, CandidateVerification,
  ChatCapableEngine, ModelSpec,
} from './types';

export const CANDIDATE_STRATEGY_VERSION = 'a-instruct-single-call-v1';

export interface GenerateCandidateOptions {
  /** Catalog identity for the evidence record; the engine is supplied by the
   * caller, so this is descriptive, never used to load anything. */
  spec?: ModelSpec;
}

function specFor(engine: ChatCapableEngine): ModelSpec | undefined {
  if (!engine.info.modelId) return undefined;
  try { return modelSpecByFile(engine.info.modelId); } catch { return undefined; }
}

const DEFAULT_MAX_TOKENS_CEILING = 700;
const DEFAULT_TARGET_CHARS = 240;
const DEFAULT_TIMEOUT_MS = 150_000;
const REPAIR_TEMPERATURE = 0.4;

function maxTokensFor(policy: CandidatePolicy): number {
  const ceiling = policy.maxTokensCeiling ?? DEFAULT_MAX_TOKENS_CEILING;
  if (policy.maxTokens !== undefined) return Math.min(policy.maxTokens, ceiling);
  const target = policy.targetChars ?? DEFAULT_TARGET_CHARS;
  // Chinese prose is roughly 1.3-1.6 characters per token on Qwen; give the
  // model room to finish a sentence but never an unbounded scene.
  return Math.min(ceiling, Math.max(96, Math.ceil(target * 1.6)));
}

function verifiedResult(
  committed: CommittedNarration,
  text: string,
  policy: CandidatePolicy,
): CandidateVerification {
  const alignment = alignNarration(committed, text, {
    time: policy.time ?? null,
    roster: policy.roster,
    locations: policy.locations,
    knownPositions: policy.knownPositions,
    previousText: policy.priorText ?? null,
  });
  return {
    ok: alignment.violations.length === 0 && alignment.omissions.length === 0 && alignment.timeExpressed !== false,
    violations: alignment.violations,
    omissions: alignment.omissions,
    unverified: alignment.unverified,
    timeExpressed: alignment.timeExpressed,
    coverage: alignment.coverage,
  };
}

function issuesOf(verification: CandidateVerification | null, text: string, policy: CandidatePolicy, truncated = false): CandidateIssue[] {
  const issues: CandidateIssue[] = [];
  if (truncated) issues.push({ kind: 'truncated', detail: 'generation hit maxTokens before the model finished', severity: 'hard' });
  if (!verification) return issues;
  for (const violation of verification.violations) {
    issues.push({ kind: violation.kind, detail: violation.detail, severity: 'hard' });
  }
  for (const omission of verification.omissions) {
    issues.push({ kind: 'omitted_fact', detail: omission, severity: 'hard' });
  }
  if (verification.timeExpressed === false) {
    issues.push({ kind: 'time_not_narrated', detail: 'the passage must state the elapsed time', severity: 'hard' });
  }
  for (const sentence of verification.unverified) {
    issues.push({ kind: 'unverified_sentence', detail: sentence, severity: 'soft' });
  }
  const minChars = policy.minChars ?? 0;
  if ([...text.replace(/\s+/g, '')].length < minChars) {
    issues.push({ kind: 'too_short', detail: `${[...text].length} chars < minChars ${minChars}`, severity: 'hard' });
  }
  return issues;
}

function repairNote(issues: CandidateIssue[]): string {
  const hard = issues.filter((issue) => issue.severity === 'hard');
  if (hard.length === 0) return '';
  const lines = ['上一版正文没有通过事实核对，请重写，只修正下面这些点：'];
  for (const issue of hard.slice(0, 6)) {
    const label: Record<string, string> = {
      actor_swap: '人物写反了', direction_reversed: '方向写反了', wrong_number: '数字写错了',
      task_claimed_without_fact: '写了没有提交的任务', movement_without_fact: '写了没有提交的移动',
      state_claim_without_fact: '写了没有提交的状态', wrong_time: '时间写错了', added_event: '加了没有提交的事件',
      omitted_fact: '漏了必须写到的事实', time_not_narrated: '没有写经过的时间', too_short: '正文太短',
      empty_narration: '正文为空', truncated: '上一版在上限处被截断，请写得更短并收束',
    };
    lines.push(`- ${label[issue.kind] ?? issue.kind}：${issue.detail}`);
  }
  return lines.join('\n');
}

interface ModelCall {
  text: string;
  completion: CompletionEvidence | null;
  /** The model stopped at maxTokens; the text is real but cut off. */
  truncated: boolean;
}

async function callModel(
  engine: ChatCapableEngine,
  spec: ModelSpec | undefined,
  userText: string,
  policy: CandidatePolicy,
  temperature: number,
  onChunk: (text: string) => void,
): Promise<ModelCall> {
  let completion: CompletionEvidence | null = null;
  const options = {
    maxTokens: maxTokensFor(policy),
    temperature,
    ...(policy.seed !== undefined ? { seed: policy.seed } : {}),
    timeoutMs: policy.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    stop: spec?.template.stop,
    cachePrompt: true,
    onProgress: (progress: { raw: string; elapsedMs: number }) => onChunk(progress.raw),
    onCompletion: (evidence: CompletionEvidence) => { completion = evidence; },
  };
  const invoke = async (): Promise<string> => {
    if (engine.chat && spec && !spec.rawCompletion) return engine.chat(buildMessages(spec, userText), options);
    const prompt = spec ? renderFallbackPrompt(spec, userText) : userText;
    return engine.complete(prompt, options);
  };
  try {
    return { text: await invoke(), completion, truncated: false };
  } catch (error) {
    // A length-capped answer is real text the player paid for. Keep it as a
    // non-accepted draft (the caller sees `truncated` and may show/replace it)
    // instead of losing the whole point; the next attempt asks for less.
    if (error instanceof IncompleteGenerationError || (error as { name?: string })?.name === 'IncompleteGenerationError') {
      const evidence = (error as IncompleteGenerationError).completion ?? completion;
      return { text: evidence?.raw ?? '', completion: evidence ?? completion, truncated: true };
    }
    throw error;
  }
}

export async function generateCandidate(args: CandidateArgs, options: GenerateCandidateOptions = {}): Promise<CandidateResult> {
  const policy = args.policy ?? {};
  // A shared driver (09) loads the engine itself and calls with no spec; the
  // catalog still identifies the checkpoint from info.modelId, so the model's
  // real template is used instead of a fused fallback prompt.
  const spec = options.spec ?? specFor(args.engine);
  const maxAttempts = Math.max(1, Math.min(policy.attempts ?? 2, 3));
  const temperature = policy.temperature ?? 0.7;
  const started = performance.now();
  const attempts: CandidateAttempt[] = [];
  const perAttemptMs: number[] = [];
  let firstProgressMs: number | null = null;
  let firstReadableMs: number | null = null;
  let lastVerification: CandidateVerification | null = null;
  let best: { text: string; verification: CandidateVerification | null; issues: CandidateIssue[] } | null = null;

  const baseUser = policy.prompt?.trim()
    ? policy.prompt
    : renderNarrationUser(args.committed, args.inputText, { ...policy, priorText: args.priorText ?? policy.priorText ?? null });

  for (let index = 0; index < maxAttempts; index += 1) {
    if (args.signal?.aborted) throw new Error('aborted');
    const attemptStarted = performance.now();
    const repair = index > 0 && best ? repairNote(best.issues) : '';
    const userText = repair ? `${baseUser}\n\n${repair}` : baseUser;
    let display = '';
    const filter = new ThinkingFilter();
    const onChunk = (raw: string) => {
      if (firstProgressMs === null) firstProgressMs = performance.now() - started;
      const added = filter.push(raw.slice(display.length));
      display = raw;
      if (!added) return;
      if (firstReadableMs === null && added.trim().length > 0) firstReadableMs = performance.now() - started;
      args.onProgress?.({ text: filter.text, status: 'streaming', verified: false, elapsedMs: performance.now() - started });
    };
    let text = '';
    let completion: CompletionEvidence | null = null;
    let truncated = false;
    try {
      const result = await callModel(args.engine, spec, userText, policy, index === 0 ? temperature : REPAIR_TEMPERATURE, onChunk);
      const tail = filter.flush();
      if (tail) {
        if (firstReadableMs === null && tail.trim().length > 0) firstReadableMs = performance.now() - started;
      }
      text = cleanNarration(result.text || filter.text);
      completion = result.completion;
      truncated = result.truncated;
    } catch (error) {
      if (args.signal?.aborted) throw error;
      perAttemptMs.push(performance.now() - attemptStarted);
      attempts.push({
        index, prompt: userText, promptChars: userText.length, text: '',
        completion: null, verification: null, accepted: false,
        issueKinds: ['generation_failed'], temperature: index === 0 ? temperature : REPAIR_TEMPERATURE,
      });
      throw error;
    }
    const verification = verifiedResult(args.committed, text, policy);
    const issues = issuesOf(verification, text, policy, truncated);
    const accepted = verification.ok && !issues.some((issue) => issue.severity === 'hard');
    const attemptMs = performance.now() - attemptStarted;
    perAttemptMs.push(attemptMs);
    attempts.push({
      index, prompt: userText, promptChars: userText.length, text, completion,
      verification, accepted, issueKinds: issues.map((issue) => issue.kind),
      temperature: index === 0 ? temperature : REPAIR_TEMPERATURE,
    });
    lastVerification = verification;
    if (!best || issues.filter((issue) => issue.severity === 'hard').length < best.issues.filter((issue) => issue.severity === 'hard').length) {
      best = { text, verification, issues };
    }
    if (accepted) {
      best = { text, verification, issues };
      break;
    }
    args.onProgress?.({ text, status: 'retry', verified: false, elapsedMs: performance.now() - started });
  }

  const issues = best?.issues ?? [];
  const accepted = Boolean(best && best.verification?.ok && !issues.some((issue) => issue.severity === 'hard'));
  const result: CandidateResult = {
    text: best?.text ?? '',
    accepted,
    rawAttempts: attempts,
    issues,
    timings: {
      loadMs: null,
      firstReadableMs,
      firstProgressMs,
      calls: attempts.length,
      totalMs: performance.now() - started,
      perAttemptMs,
    },
    strategyVersion: CANDIDATE_STRATEGY_VERSION,
    model: spec ? { id: spec.id, templateId: spec.template.id } : null,
    verification: best?.verification ?? lastVerification,
  };
  args.onProgress?.({ text: result.text, status: 'done', verified: accepted, elapsedMs: performance.now() - started });
  return result;
}

export { describeCommitted };
export type { CandidateArgs, CandidateResult };
