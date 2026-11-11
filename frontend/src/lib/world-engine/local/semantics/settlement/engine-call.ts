/** One JSON-producing model call with bounded retry and full evidence.
 * The retry is a validation retry, never a dice or state rerun. A second
 * invalid answer is returned as a failure; callers decide whether a
 * conservative no-change candidate is allowed. */
import type { InferenceEngine } from '../../../runtime/engine';
import type { ModelCallEvidence } from './types';
import { errorText, parseJsonValue } from './support';

export interface JsonCallOptions {
  maxTokens: number;
  temperature?: number;
  timeoutMs?: number;
  maxPromptChars?: number;
  maxAttempts?: number;
  jsonSchema?: unknown;
  /** Parse and structurally validate. Throwing triggers one feedback retry. */
  validate: (value: unknown) => void;
  /** Optional second-attempt instruction; defaults to a format-only reminder. */
  feedback?: string;
}

export interface JsonCallResult {
  value: unknown;
  raw: string;
  ms: number;
  calls: ModelCallEvidence[];
}

export class JsonCallError extends Error {
  readonly calls: ModelCallEvidence[];
  readonly raw: string;
  readonly ms: number;

  constructor(message: string, calls: ModelCallEvidence[]) {
    super(message);
    this.name = 'JsonCallError';
    this.calls = calls;
    this.raw = calls.map((call) => call.raw).filter(Boolean).join('\n---\n');
    this.ms = calls.reduce((sum, call) => sum + call.ms, 0);
  }
}

export async function callJson(
  engine: InferenceEngine,
  prompt: string,
  options: JsonCallOptions,
): Promise<JsonCallResult> {
  const maxAttempts = options.maxAttempts ?? 2;
  const maxPromptChars = options.maxPromptChars ?? 8000;
  if (prompt.length > maxPromptChars) {
    throw new JsonCallError(`context_capacity_exceeded: prompt=${prompt.length} max=${maxPromptChars}`, []);
  }
  const calls: ModelCallEvidence[] = [];
  let lastError = '';
  // A length-truncated answer needs a different retry, not the same request.
  let truncated = false;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    // A truncated answer is a capacity problem, not a format mistake: repeating
    // the same cap and the same request (3turn 9623 group_29: 49.9 s of output cut
    // at the limit, then a repair that dropped a member) fails again. The retry
    // asks for a shorter answer and keeps the caller's own correction.
    const retryNote = truncated
      ? '上一次输出因长度上限被截断：每条 reason 压到 20 字以内，facts 每人一句，不要解释，不要加代码块。'
      : '请只输出符合格式的 JSON，不要解释，不要加代码块。';
    const attemptPrompt = attempt === 1
      ? prompt
      : [prompt, '', `上一次输出无效：${lastError}`, retryNote, ...(options.feedback ? [options.feedback] : [])].join('\n');
    if (attemptPrompt.length > maxPromptChars) {
      throw new JsonCallError(`context_capacity_exceeded: retry prompt=${attemptPrompt.length} max=${maxPromptChars}`, calls);
    }
    const started = performance.now();
    try {
      const raw = await engine.complete(attemptPrompt, {
        maxTokens: options.maxTokens,
        temperature: attempt === 1 ? options.temperature ?? 0 : 0.2,
        timeoutMs: options.timeoutMs ?? 60_000,
        jsonSchema: options.jsonSchema,
      });
      const ms = performance.now() - started;
      try {
        const value = parseJsonValue(raw);
        options.validate(value);
        calls.push({ prompt: attemptPrompt, raw, ms, attempt });
        return { value, raw, ms: calls.reduce((sum, call) => sum + call.ms, 0), calls };
      } catch (error) {
        lastError = errorText(error);
        calls.push({ prompt: attemptPrompt, raw, ms, attempt, error: lastError });
      }
    } catch (error) {
      const ms = performance.now() - started;
      lastError = errorText(error);
      if (/ended with (?:length|no finish reason)/iu.test(lastError) || /IncompleteGenerationError/u.test(lastError)) {
        truncated = true;
      }
      calls.push({ prompt: attemptPrompt, raw: '', ms, attempt, error: lastError });
    }
  }
  throw new JsonCallError(`model_output_invalid: ${lastError}`, calls);
}

export function joinedRaw(calls: ModelCallEvidence[]): string {
  return calls.map((call) => call.raw).filter(Boolean).join('\n---\n');
}

export function joinedMs(calls: ModelCallEvidence[]): number {
  return calls.reduce((sum, call) => sum + call.ms, 0);
}
