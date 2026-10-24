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
