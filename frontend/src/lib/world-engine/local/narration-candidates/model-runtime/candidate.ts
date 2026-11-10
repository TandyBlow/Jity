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
import { IncompleteGenerationError, type CompletionEvidence } from '../../../runtime/engine';
import { alignNarration } from '../../../runtime/narration-alignment';
import type { CommittedNarration } from '../../../runtime/committed-narration';
import {
  buildMessages, cleanNarration, describeCommitted, normalizeTime, renderFallbackPrompt, renderNarrationUser, ThinkingFilter,
} from './template';
import { modelSpecByFile } from './catalog';
import { mergePositions, projectProseFacts } from './facts';
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
  const projected = projectProseFacts(committed);
  const alignment = alignNarration(projected.packet, text, {
    time: normalizeTime(policy.time),
    roster: policy.roster,
    locations: policy.locations,
    knownPositions: mergePositions(policy.knownPositions, projected.positions),
    previousText: policy.priorText ?? null,
  });
  return {
    ok: alignment.violations.length === 0 && alignment.omissions.length === 0 && alignment.timeExpressed !== false,
    violations: alignment.violations,
    omissions: alignment.omissions,
    unverified: alignment.unverified,
    timeExpressed: alignment.timeExpressed,
    coverage: alignment.coverage,
    repetition: alignment.repetition,
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
  // The 1.7B model, shown the previous paragraph, copied it verbatim and then
  // appended the new event. The result is both a repetition and a standing
  // claim from the previous point; treat a large overlap as a hard failure so
  // the repair actually rewrites instead of pasting.
  if (verification.repetition !== null && verification.repetition >= 0.6) {
    issues.push({
      kind: 'repeats_previous',
      detail: `${Math.round(verification.repetition * 100)}% of the previous passage is repeated`,
      severity: 'hard',
    });
  }
  for (const sentence of verification.unverified) {
    issues.push({ kind: 'unverified_sentence', detail: sentence, severity: 'soft' });
  }
  // A scene asked for 240 chars that comes back at 100 is not the product's
  // "complete body text". The explicit policy wins; otherwise use 60% of the
  // target so a draft that stops after two sentences gets one bounded repair.
  const minChars = policy.minChars ?? (policy.targetChars ? Math.round(policy.targetChars * 0.6) : 0);
  if ([...text.replace(/\s+/g, '')].length < minChars) {
    issues.push({ kind: 'too_short', detail: `${[...text].length} chars < minChars ${minChars}`, severity: 'hard' });
  }
  return issues;
}

function repairNote(issues: CandidateIssue[], previousText: string): string {
  const hard = issues.filter((issue) => issue.severity === 'hard');
  if (hard.length === 0) return '';
  const lines = ['上一版正文没有通过核对。保留其中正确的部分，只修正下面这些点：'];
  for (const issue of hard.slice(0, 6)) {
    const label: Record<string, string> = {
      actor_swap: '人物写反了', direction_reversed: '方向写反了', wrong_number: '数字写错了',
      task_claimed_without_fact: '写了没有提交的任务', movement_without_fact: '写了没有提交的移动',
      state_claim_without_fact: '写了没有提交的状态', wrong_time: '时间写错了', added_event: '加了没有提交的事件',
      omitted_fact: '漏了必须写到的事实', time_not_narrated: '没有写经过的时间', too_short: '正文太短',
      empty_narration: '正文为空', truncated: '上一版在上限处被截断，请写得更短并收束',
      repeats_previous: '重复了上一段的原文，请只写这一点新发生的事',
      timeout: '生成超时', generation_failed: '生成失败',
    };
    lines.push(`- ${label[issue.kind] ?? issue.kind}：${issue.detail}`);
  }
  // Showing the draft stops the model from re-planning the whole scene (and
  // spending the same tokens twice); a length repair in particular needs
  // something to extend. The draft is the same model's text for this point.
  const draft = previousText.trim();
  if (draft) {
    const chars = [...draft];
    const clipped = chars.slice(0, 400).join('');
    lines.push(`上一版正文（在此基础上改写，不要另起一版）：
${clipped}${chars.length > 400 ? '…' : ''}`);
  }
  return lines.join('\n');
}

interface ModelCall {
  text: string;
  completion: CompletionEvidence | null;
  /** The model stopped at maxTokens; the text is real but cut off. */
  truncated: boolean;
  /** The engine's own deadline fired. Terminal: the adapter may have stopped
   * the worker, so another call would only fail with "engine is not loaded". */
  timedOut: boolean;
  /** Transport/engine failure that a second call cannot fix by prompting. */
  failed: boolean;
}

async function callModel(
  engine: ChatCapableEngine,
  spec: ModelSpec | undefined,
  userText: string,
  policy: CandidatePolicy,
  temperature: number,
  onChunk: (text: string) => void,
): Promise<ModelCall> {
  // A holder, not a local: the engine assigns it from a callback and TS's
  // control-flow analysis would otherwise narrow a local to null at return.
  const holder: { completion: CompletionEvidence | null } = { completion: null };
  const options = {
    maxTokens: maxTokensFor(policy),
    temperature,
    ...(policy.seed !== undefined ? { seed: policy.seed } : {}),
    timeoutMs: policy.timeoutMs ?? DEFAULT_TIMEOUT_MS,
    stop: spec?.template.stop,
    cachePrompt: true,
    onProgress: (progress: { raw: string; elapsedMs: number }) => onChunk(progress.raw),
    onCompletion: (evidence: CompletionEvidence) => { holder.completion = evidence; },
  };
  const invoke = async (): Promise<string> => {
    if (engine.chat && spec && !spec.rawCompletion) return engine.chat(buildMessages(spec, userText), options);
    const prompt = spec ? renderFallbackPrompt(spec, userText) : userText;
    return engine.complete(prompt, options);
  };
  try {
    return { text: await invoke(), completion: holder.completion, truncated: false, timedOut: false, failed: false };
  } catch (error) {
    if ((error as { name?: string })?.name === 'AbortError') throw error;
    // A length-capped answer is real text the player paid for. Keep it as a
    // non-accepted draft (the caller sees `truncated` and may show/replace it)
    // instead of losing the whole point; the next attempt asks for less.
    if (error instanceof IncompleteGenerationError || (error as { name?: string })?.name === 'IncompleteGenerationError') {
      const evidence = (error as IncompleteGenerationError).completion ?? holder.completion;
      return {
        text: evidence?.raw ?? '',
        completion: evidence ?? holder.completion,
        truncated: evidence?.finishReason !== 'timeout',
        timedOut: evidence?.finishReason === 'timeout',
        failed: false,
      };
    }
    // The engine is gone or rejected the call. Returning a result the page can
    // show beats throwing away the fact that the point produced nothing; 09's
    // shared driver records a thrown error as a contract failure with no text.
    return { text: holder.completion?.raw ?? '', completion: holder.completion, truncated: false, timedOut: false, failed: true };
  }
}

export async function generateCandidate(args: CandidateArgs, options: GenerateCandidateOptions = {}): Promise<CandidateResult> {
  const policy: CandidatePolicy = { ...(args.policy ?? {}) };
  // 09 passes the continuation text as `priorText`, outside `policy`. The
  // prompt AND the verification must see the same value: without it the
  // repetition check silently does nothing for the shared driver.
  if (args.priorText !== undefined) policy.priorText = args.priorText;
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
  let status: CandidateResult['status'] = 'rejected';
  let terminalError: string | null = null;

  const baseUser = policy.prompt?.trim()
    ? policy.prompt
    : renderNarrationUser(args.committed, args.inputText, policy);

  for (let index = 0; index < maxAttempts; index += 1) {
    if (args.signal?.aborted) throw new Error('aborted');
    const attemptStarted = performance.now();
    const repair = index > 0 && best ? repairNote(best.issues, best.text) : '';
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
    let failed = false;
    let timedOut = false;
    try {
      const result = await callModel(args.engine, spec, userText, policy, index === 0 ? temperature : REPAIR_TEMPERATURE, onChunk);
      const tail = filter.flush();
      if (tail) {
        if (firstReadableMs === null && tail.trim().length > 0) firstReadableMs = performance.now() - started;
      }
      text = cleanNarration(result.text || filter.text);
      completion = result.completion;
      truncated = result.truncated;
      failed = result.failed;
      timedOut = result.timedOut;
    } catch (error) {
      // Abort is the caller's decision, not a point failure: keep throwing so
      // the page can distinguish "player stopped" from "model failed".
      if (args.signal?.aborted || (error as { name?: string })?.name === 'AbortError') throw error;
      failed = true;
      terminalError = error instanceof Error ? error.message : String(error);
      text = cleanNarration(filter.text);
    }
    const verification = verifiedResult(args.committed, text, policy);
    const issues = issuesOf(verification, text, policy, truncated);
    if (timedOut) issues.unshift({ kind: 'timeout', detail: 'the engine deadline fired before the model finished', severity: 'hard' });
    if (failed) issues.unshift({ kind: 'generation_failed', detail: terminalError ?? 'the engine rejected the call', severity: 'hard' });
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
      status = 'accepted';
      break;
    }
    if (timedOut) { status = 'timeout'; break; }
    if (failed) { status = 'error'; break; }
    args.onProgress?.({ text, status: 'retry', verified: false, elapsedMs: performance.now() - started });
  }

  const issues = best?.issues ?? [];
  const accepted = Boolean(best && best.verification?.ok && !issues.some((issue) => issue.severity === 'hard'));
  if (status !== 'accepted' && status !== 'timeout' && status !== 'error') status = 'rejected';
  const result: CandidateResult = {
    text: best?.text ?? '',
    accepted,
    status,
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
