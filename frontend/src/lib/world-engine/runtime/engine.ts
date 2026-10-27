/** Engine-agnostic inference surface for the B2 browser runtime. The queue,
 * the model port and every test depend on this interface, never on wllama:
 * cancellation is part of the contract — an adapter MUST forward the signal
 * to its underlying mechanism so a cancelled call stops consuming device
 * compute instead of only being ignored. */

export interface EngineInfo {
  backend: string;
  /** Model identity once loaded; null before load. */
  modelId: string | null;
}

export interface CompleteOptions {
  signal?: AbortSignal;
  maxTokens?: number;
  temperature?: number;
  seed?: number;
  stop?: string[];
  timeoutMs?: number;
  /** Optional generation grammar; the task codec still validates the result. */
  jsonSchema?: unknown;
  /** Streaming evidence, including the partial text if generation is cancelled. */
  onProgress?: (progress: { raw: string; elapsedMs: number }) => void;
  onCompletion?: (completion: CompletionEvidence) => void;
}

export interface CompletionEvidence {
  raw: string;
  finishReason: string | null;
  firstTokenMs: number | null;
  wallMs: number;
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number; prompt_tokens_details?: { cached_tokens: number } };
  timings?: { prompt_ms: number; predicted_ms: number; cache_n: number; prompt_n: number; predicted_n: number };
}

/** A truncated or interrupted answer must never become a state candidate,
 * even if its prefix happens to be parseable JSON. Keep the paid evidence. */
export class IncompleteGenerationError extends Error {
  readonly name = 'IncompleteGenerationError';
  constructor(readonly completion: CompletionEvidence, reason = `generation ended with ${completion.finishReason ?? 'no finish reason'}`) {
    super(reason);
  }
}

export interface InferenceEngine {
  readonly info: EngineInfo;
  /** Idempotent: repeated calls await the same load. */
  load(options?: { signal?: AbortSignal; modelUrl?: string }): Promise<void>;
  complete(prompt: string, options?: CompleteOptions): Promise<string>;
  dispose(): Promise<void>;
}

/** The canonical rejection for a cancelled inference call. The queue and
 * every adapter reject with this shape so callers can match on name alone. */
export function abortError(): Error {
  return new DOMException('Aborted', 'AbortError');
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}
