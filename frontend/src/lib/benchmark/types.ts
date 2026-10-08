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
};

export type HeapSample = { usedMB: number | null; totalMB: number | null };

export type RunKind = "load" | "prefill" | "decode" | "abort" | "exit";

export type RunRecord = {
  id: string;
  kind: RunKind;
  label: string;
  startedAt: string;
  wallMs: number;
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
  tokensBeforeAbort?: number;
  completedNormally?: boolean;
  heap?: HeapSample;
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
};

export type Suite = {
  environment: EnvironmentInfo;
  runtime: RuntimeInfo | null;
  config: BenchmarkConfig;
  runs: RunRecord[];
  finishedAt?: string;
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
