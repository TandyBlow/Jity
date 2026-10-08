/** Shared types for the local-inference benchmark harness. */

export type EnvironmentInfo = {
  userAgent: string;
  platform: string;
  hardwareConcurrency: number | null;
  deviceMemoryGB: number | null;
  crossOriginIsolated: boolean;
  webgpuExposed: boolean;
  wasmSimd: boolean;
  wasmThreadsPossible: boolean;
  collectedAt: string;
};

export type LoadParamsSnapshot = {
  n_ctx: number;
  n_batch: number;
  n_ubatch: number;
  n_threads: number | null;
};

/** Values readable only after a model is loaded (from wllama itself). */
export type RuntimeInfo = {
  sourceLabel: string;
  sourceBytes: number | null;
  multithread: boolean;
  numThreads: number;
  nCtx: number;
  nCtxTrain: number;
  nVocab: number;
  nEmbd: number;
  nLayer: number;
  libllamaVersion: string;
  generalMeta: Record<string, string>;
  /** The parameters the context was actually created with. */
  loadParams: LoadParamsSnapshot;
};

export type HeapSample = { usedMB: number | null; totalMB: number | null };

/**
 * Full-page memory sample. `preciseMB` comes from
 * performance.measureUserAgentSpecificMemory (crossOriginIsolated Chrome
 * only) and covers JS + WebAssembly heaps; the JS-heap-only fields are the
 * fallback.
 */
export type MemorySample = HeapSample & {
  preciseMB?: number | null;
  breakdownMB?: Record<string, number>;
};

export type RunKind = "load" | "prefill" | "decode" | "accept" | "abort" | "exit" | "memory";

export type AbortOutcome = "cancelled" | "completed_early" | "context_overflow" | "error";

export type RunRecord = {
  id: string;
  kind: RunKind;
  label: string;
  startedAt: string;
  wallMs: number;
  /** The suite this run belongs to; load/exit/memory checkpoints have none. */
  suiteId?: string;
  /** Requested档位; the measured token counts live on the fields below. */
  nominalTotalTokens?: number;
  nominalMemoryTokens?: number;
  /** llama.cpp timings, straight from the completion response. */
  promptTokens?: number;
  cachedTokens?: number;
  promptMs?: number;
  promptPerSecond?: number;
  predictedTokens?: number;
  predictedMs?: number;
  predictedPerSecond?: number;
  maxTokens?: number;
  seed?: number;
  /** Abort-test fields. */
  abortAfterMs?: number;
  stopLatencyMs?: number;
  /** Stream callbacks are not exactly tokens; chars are counted from text. */
  streamedChunks?: number;
  generatedChars?: number;
  abortOutcome?: AbortOutcome;
  abortPhase?: "prefill" | "decode" | "unknown";
  cancelledByUser?: boolean;
  completedNormally?: boolean;
  /** Accept-run verdict: the full call finished within the 4s target. */
  withinTarget?: boolean;
  heap?: HeapSample;
  memory?: MemorySample;
  error?: string;
};

export type BenchmarkConfig = {
  totalTokens: number[];
  memoryTokens: number[];
  decodeTokens: number;
  prefillRepeats: number;
  decodeRepeats: number;
  nCtx: number;
  nBatch: number;
  nUbatch: number;
  /** null = let wllama pick (hardwareConcurrency). */
  nThreads: number | null;
  /** Extra chat-completion对照 row after the raw-completion matrix. */
  chatReference: boolean;
  /** Real full-call 4s acceptance runs, one per档位 combo. */
  acceptEnabled: boolean;
  acceptOutputTokens: number;
};

export const DEFAULT_CONFIG: BenchmarkConfig = {
  totalTokens: [512, 1024, 2048],
  memoryTokens: [256, 512, 1024],
  decodeTokens: 128,
  prefillRepeats: 2,
  decodeRepeats: 1,
  nCtx: 4096,
  nBatch: 2048,
  nUbatch: 512,
  nThreads: null,
  chatReference: true,
  acceptEnabled: false,
  acceptOutputTokens: 512,
};

/** One executed suite. Config and model identity are snapshotted at start. */
export type SuiteRecord = {
  id: string;
  label: string;
  startedAt: string;
  finishedAt?: string;
  config: BenchmarkConfig;
  modelLabel: string | null;
  runs: RunRecord[];
};

export type ExportPayload = {
  environment: EnvironmentInfo;
  /** Persists after unload; replaced only by the next successful load. */
  model: RuntimeInfo | null;
  suites: SuiteRecord[];
  exportedAt: string;
};

/** Invalid档位 combos (memory injection must be smaller than the total). */
export function validCombos(config: BenchmarkConfig): Array<{
  total: number;
  memory: number;
}> {
  const combos: Array<{ total: number; memory: number }> = [];
  for (const total of config.totalTokens) {
    for (const memory of config.memoryTokens) {
      if (memory < total) combos.push({ total, memory });
    }
  }
  return combos;
}
