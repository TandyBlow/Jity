/**
 * Benchmark runner. Wraps wllama calls and reads llama.cpp's own timings
 * (prompt_ms / predicted_ms) out of the completion response, so prefill and
 * decode are measured separately. Wall-clock times are recorded alongside,
 * because — unlike llama-bench — a browser call includes tokenization,
 * sampling and worker round-trips.
 */

import type { Wllama } from "@wllama/wllama";

import { sampleHeap } from "./environment";
import { adjustCharRatio, buildPrompt } from "./prompts";
import type { BenchmarkConfig, RunRecord, RuntimeInfo } from "./types";
import { validCombos } from "./types";
import { getLibllamaVersion } from "./wllama-loader";

let runCounter = 0;

function nextRunId(kind: string): string {
  runCounter += 1;
  return `${kind}-${runCounter}-${Date.now()}`;
}

function baseRecord(kind: RunRecord["kind"], label: string): RunRecord {
  return {
    id: nextRunId(kind),
    kind,
    label,
    startedAt: new Date().toISOString(),
    wallMs: 0,
    heap: sampleHeap(),
  };
}

export type RunnerHooks = {
  onStatus: (message: string) => void;
  onRun: (record: RunRecord) => void;
  /** Between-run escape hatch: the UI can cancel the remaining suite. */
  shouldStop?: () => boolean;
};

function stopped(hooks: RunnerHooks): boolean {
  return hooks.shouldStop?.() ?? false;
}

/** Load params shared by every scenario: CPU-only, explicit context sizes. */
export function loadParams(config: BenchmarkConfig) {
  return {
    n_ctx: config.nCtx,
    n_batch: config.nBatch,
    n_ubatch: config.nUbatch,
    n_gpu_layers: 0,
    warmup: false,
    ...(config.nThreads !== null ? { n_threads: config.nThreads } : {}),
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function runLoadFromBlobs(
  wllama: Wllama,
  blobs: Blob[],
  label: string,
  config: BenchmarkConfig,
  hooks: RunnerHooks,
): Promise<RuntimeInfo> {
  const record = baseRecord("load", label);
  const sourceBytes = blobs.reduce((sum, blob) => sum + blob.size, 0);
  const started = performance.now();
  try {
    await wllama.loadModel(blobs, loadParams(config));
  } catch (error) {
    record.wallMs = Math.round(performance.now() - started);
    record.error = errorMessage(error);
    hooks.onRun(record);
    throw error;
  }
  record.wallMs = Math.round(performance.now() - started);
  hooks.onRun(record);
  return collectRuntimeInfo(wllama, label, sourceBytes);
}

export async function runLoadFromUrl(
  wllama: Wllama,
  url: string,
  config: BenchmarkConfig,
  hooks: RunnerHooks,
): Promise<RuntimeInfo> {
  const record = baseRecord("load", `URL: ${url}`);
  let sourceBytes: number | null = null;
  const started = performance.now();
  try {
    await wllama.loadModelFromUrl(url, {
      ...loadParams(config),
      progressCallback: ({ loaded, total }: { loaded: number; total: number }) => {
        if (total > 0) sourceBytes = total;
        if (total > 0) {
          hooks.onStatus(
            `下载模型 ${(loaded / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB`,
          );
        }
      },
    });
  } catch (error) {
    record.wallMs = Math.round(performance.now() - started);
    record.error = errorMessage(error);
    hooks.onRun(record);
    throw error;
  }
  record.wallMs = Math.round(performance.now() - started);
  hooks.onRun(record);
  return collectRuntimeInfo(wllama, url, sourceBytes);
}

function collectRuntimeInfo(
  wllama: Wllama,
  sourceLabel: string,
  sourceBytes: number | null,
): RuntimeInfo {
  const metadata = wllama.getModelMetadata();
  const context = wllama.getLoadedContextInfo();
  const generalMeta: Record<string, string> = {};
  for (const [key, value] of Object.entries(metadata.meta ?? {})) {
    if (key.startsWith("general.")) generalMeta[key] = String(value);
  }
  return {
    sourceLabel,
    sourceBytes,
    multithread: wllama.isMultithread(),
    numThreads: wllama.getNumThreads(),
    nCtx: context.n_ctx,
    nCtxTrain: context.n_ctx_train,
    nVocab: metadata.hparams.nVocab,
    nEmbd: metadata.hparams.nEmbd,
    nLayer: metadata.hparams.nLayer,
    libllamaVersion: getLibllamaVersion(),
    generalMeta,
  };
}

type CompletionTimings = {
  usage?: { prompt_tokens?: number; completion_tokens?: number };
  timings?: {
    cache_n?: number;
    prompt_n?: number;
    prompt_ms?: number;
    prompt_per_second?: number;
    predicted_n?: number;
    predicted_ms?: number;
    predicted_per_second?: number;
  };
};

function readTimings(response: CompletionTimings) {
  return {
    promptTokens: response.usage?.prompt_tokens,
    predictedTokens: response.usage?.completion_tokens,
    cachedTokens: response.timings?.cache_n,
    promptMs: response.timings?.prompt_ms != null
      ? Math.round(response.timings.prompt_ms)
      : undefined,
    promptPerSecond: response.timings?.prompt_per_second,
    predictedMs: response.timings?.predicted_ms != null
      ? Math.round(response.timings.predicted_ms)
      : undefined,
    predictedPerSecond: response.timings?.predicted_per_second,
  };
}

/**
 * Prefill + calibration for one档位 combo. The first repeat doubles as the
 * calibration probe: its measured prompt_tokens recalibrates the
 * chars-per-token ratio for every later repeat. Probe rows are real prefill
 * measurements and are reported as such.
 */
async function runPrefillCombo(
  wllama: Wllama,
  total: number,
  memory: number,
  repeat: number,
  charRatio: number,
  hooks: RunnerHooks,
): Promise<number> {
  const nonce = total * 10007 + memory * 101 + repeat;
  const prompt = buildPrompt({
    totalTokens: total,
    memoryTokens: memory,
    nonce,
    charRatio,
  });
  const seed = 445 + repeat;
  const record = baseRecord("prefill", `${total} tok（记忆 ${memory}）· 第 ${repeat + 1} 遍`);
  record.nominalTotalTokens = total;
  record.nominalMemoryTokens = memory;
  record.seed = seed;

  const started = performance.now();
  try {
    const response = (await wllama.createCompletion({
      prompt,
      max_tokens: 1,
      temperature: 0,
      seed,
    })) as CompletionTimings;
    record.wallMs = Math.round(performance.now() - started);
    Object.assign(record, readTimings(response));
  } catch (error) {
    record.wallMs = Math.round(performance.now() - started);
    record.error = errorMessage(error);
    hooks.onRun(record);
    return charRatio;
  }
  hooks.onRun(record);

  const measured = record.promptTokens ?? 0;
  return measured > 0 ? adjustCharRatio(charRatio, measured, total) : charRatio;
}

export async function runPrefillMatrix(
  wllama: Wllama,
  config: BenchmarkConfig,
  hooks: RunnerHooks,
): Promise<void> {
  let charRatio = 1.0;
  for (const { total, memory } of validCombos(config)) {
    for (let repeat = 0; repeat < config.prefillRepeats; repeat += 1) {
      if (stopped(hooks)) return;
      charRatio = await runPrefillCombo(wllama, total, memory, repeat, charRatio, hooks);
    }
  }
}

/** Decode speed at the largest档位 — the binding constraint for narration. */
export async function runDecodeMatrix(
  wllama: Wllama,
  config: BenchmarkConfig,
  hooks: RunnerHooks,
): Promise<void> {
  const combos = validCombos(config);
  const largest = combos[combos.length - 1];
  if (!largest) return;

  for (let repeat = 0; repeat < config.decodeRepeats; repeat += 1) {
    if (stopped(hooks)) return;
    const nonce = largest.total * 70001 + largest.memory * 13 + repeat;
    const prompt = buildPrompt({
      totalTokens: largest.total,
      memoryTokens: largest.memory,
      nonce,
      charRatio: 1.0,
    });
    const seed = 9901 + repeat;
    const record = baseRecord(
      "decode",
      `${largest.total} tok 输入 · 生成 ${config.decodeTokens} token · 第 ${repeat + 1} 遍`,
    );
    record.nominalTotalTokens = largest.total;
    record.nominalMemoryTokens = largest.memory;
    record.maxTokens = config.decodeTokens;
    record.seed = seed;
    const started = performance.now();
    try {
      const response = (await wllama.createCompletion({
        prompt,
        max_tokens: config.decodeTokens,
        temperature: 0,
        seed,
      })) as CompletionTimings;
      record.wallMs = Math.round(performance.now() - started);
      Object.assign(record, readTimings(response));
    } catch (error) {
      record.wallMs = Math.round(performance.now() - started);
      record.error = errorMessage(error);
    }
    hooks.onRun(record);
  }

  if (config.chatReference) {
    if (stopped(hooks)) return;
    const nonce = largest.total * 70001 + 777;
    const prompt = buildPrompt({
      totalTokens: largest.total,
      memoryTokens: largest.memory,
      nonce,
      charRatio: 1.0,
    });
    const record = baseRecord("decode", `chat 模板对照 · ${largest.total} tok 输入`);
    record.nominalTotalTokens = largest.total;
    record.nominalMemoryTokens = largest.memory;
    record.maxTokens = Math.min(config.decodeTokens, 64);
    record.seed = 424242;
    const started = performance.now();
    try {
      const response = (await wllama.createChatCompletion({
        messages: [
          { role: "system", content: "你是桌面 RPG 的中文 GM。只输出剧情正文。" },
          { role: "user", content: prompt },
        ],
        max_tokens: record.maxTokens,
        temperature: 0,
        seed: record.seed,
        cache_prompt: false,
      })) as CompletionTimings;
      record.wallMs = Math.round(performance.now() - started);
      Object.assign(record, readTimings(response));
    } catch (error) {
      record.wallMs = Math.round(performance.now() - started);
      record.error = errorMessage(error);
    }
    hooks.onRun(record);
  }
}

/**
 * Abort mid-generation: measures how quickly the runtime actually stops after
 * abort() and how many tokens were streamed before the cancel landed. This
 * is the "取消推理" acceptance condition from the runtime筛选.
 *
 * The prompt starts at the smallest configured档位 and shrinks on context
 * overflow, because the tokenizer's real token count is only known after the
 * model rejects the request.
 */
export async function runAbortTest(
  wllama: Wllama,
  config: BenchmarkConfig,
  hooks: RunnerHooks,
  abortAfterMs: number,
): Promise<void> {
  if (stopped(hooks)) return;
  const combos = validCombos(config);
  const totals = combos.map((combo) => combo.total);
  const memories = combos.map((combo) => combo.memory);
  let nominalTotal = Math.min(...(totals.length ? totals : [512]));
  const nominalMemory = Math.min(64, ...(memories.length ? memories : [64]));
  const maxTokens = 512;
  const seed = 31337;

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const prompt = buildPrompt({
      totalTokens: nominalTotal,
      memoryTokens: nominalMemory,
      nonce: 999983 + attempt,
      charRatio: 0.5,
    });
    const record = baseRecord("abort", `中断测试 · ${abortAfterMs}ms 后取消${attempt > 1 ? `（缩小提示第 ${attempt - 1} 次）` : ""}`);
    record.nominalTotalTokens = nominalTotal;
    record.nominalMemoryTokens = nominalMemory;
    record.maxTokens = maxTokens;
    record.abortAfterMs = abortAfterMs;
    record.seed = seed;

    const controller = new AbortController();
    let tokensBeforeAbort = 0;
    let abortStartedAt = 0;
    const timer = window.setTimeout(() => {
      abortStartedAt = performance.now();
      controller.abort();
    }, abortAfterMs);

    const started = performance.now();
    let contextOverflow = false;
    try {
      await wllama.createCompletion({
        prompt,
        max_tokens: maxTokens,
        temperature: 0,
        seed,
        stream: true,
        abortSignal: controller.signal,
        onData: () => {
          tokensBeforeAbort += 1;
        },
      });
      record.completedNormally = true;
    } catch (error) {
      record.completedNormally = false;
      const message = errorMessage(error);
      const name = error instanceof Error ? error.name : "";
      if (/exceeds the available context/i.test(message)) {
        contextOverflow = true;
      } else if (!/abort/i.test(`${name} ${message}`)) {
        record.error = message;
      }
    } finally {
      window.clearTimeout(timer);
    }
    record.wallMs = Math.round(performance.now() - started);
    record.tokensBeforeAbort = tokensBeforeAbort;
    record.stopLatencyMs = abortStartedAt > 0
      ? Math.round(performance.now() - abortStartedAt)
      : undefined;
    record.heap = sampleHeap();
    hooks.onRun(record);

    if (!contextOverflow) return;
    if (attempt < 3) {
      nominalTotal = Math.max(64, Math.floor(nominalTotal / 4));
      hooks.onStatus(`中断测试提示超出上下文，缩小到 ${nominalTotal} tok 重试`);
    }
  }
}

/** Unload cost — informs the dynamic load/unload decision. */
export async function runExit(wllama: Wllama, hooks: RunnerHooks): Promise<void> {
  const record = baseRecord("exit", "卸载模型并释放内存");
  const started = performance.now();
  try {
    await wllama.exit();
  } catch (error) {
    record.error = errorMessage(error);
  }
  record.wallMs = Math.round(performance.now() - started);
  record.heap = sampleHeap();
  hooks.onRun(record);
}
