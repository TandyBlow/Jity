/**
 * Benchmark runner. Wraps wllama calls and reads llama.cpp's own timings
 * (prompt_ms / predicted_ms) out of the completion response, so prefill and
 * decode are measured separately. Wall-clock times are recorded alongside,
 * because — unlike llama-bench — a browser call includes tokenization,
 * sampling and worker round-trips.
 *
 * The chars-per-token ratio is calibrated once (first prefill probe) and
 * shared by every later stage: prefill repeats, decode, accept runs and abort
 * tests all build prompts with the same ratio.
 */

import type { Wllama } from "@wllama/wllama";

import { sampleHeap, sampleMemory } from "./environment";
import { adjustCharRatio, buildPrompt } from "./prompts";
import type {
  BenchmarkConfig,
  RunRecord,
  RuntimeInfo,
} from "./types";
import { validCombos } from "./types";
import { getLibllamaVersion } from "./wllama-loader";

/** The per-component target from the trial plan, in ms. */
export const ACCEPT_TARGET_MS = 4000;

let runCounter = 0;
/**
 * Per-suite salt mixed into every prompt nonce: a second suite measuring the
 * same档位 must not replay the previous suite's KV cache (a full prefix hit
 * reports prefill as single-digit milliseconds).
 */
let suiteEpoch = 0;

function nonce(base: number): number {
  return base + suiteEpoch * 7919;
}

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
  /**
   * Registers the controller of the in-flight call so the UI's stop button
   * can cancel actual inference, not only skip the next stage.
   */
  onController?: (controller: AbortController) => void;
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

function isAbortError(error: unknown): boolean {
  const name = error instanceof Error ? error.name : "";
  return /abort/i.test(`${name} ${errorMessage(error)}`);
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
  return collectRuntimeInfo(wllama, label, sourceBytes, config);
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
  return collectRuntimeInfo(wllama, url, sourceBytes, config);
}

function collectRuntimeInfo(
  wllama: Wllama,
  sourceLabel: string,
  sourceBytes: number | null,
  config: BenchmarkConfig,
): RuntimeInfo {
  const metadata = wllama.getModelMetadata();
  const context = wllama.getLoadedContextInfo();
  const generalMeta: Record<string, string> = {};
  for (const [key, value] of Object.entries(metadata.meta ?? {})) {
    if (key.startsWith("general.")) generalMeta[key] = String(value);
  }
  const params = loadParams(config);
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
    loadParams: {
      n_ctx: params.n_ctx,
      n_batch: params.n_batch,
      n_ubatch: params.n_ubatch,
      n_threads: params.n_threads ?? null,
    },
  };
}

type CompletionTimings = {
  usage?: { prompt_tokens?: number; completion_tokens?: number };
  choices?: Array<{ finish_reason?: string | null }>;
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

/**
 * Prefix-cache hits make prefill look faster than a cold call, so anything
 * beyond a trivial hit is flagged on the record instead of passing silently.
 * With nonce-first prompts a clean run sits at 0.
 */
const CACHE_HIT_WARNING_TOKENS = 16;

function readTimings(response: CompletionTimings) {
  return {
    promptTokens: response.usage?.prompt_tokens,
    predictedTokens: response.usage?.completion_tokens,
    finishReason: response.choices?.[0]?.finish_reason ?? null,
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

type CompletionCall = {
  prompt: string;
  max_tokens: number;
  seed: number;
  temperature?: number;
};

/**
 * One timed completion wired to the UI's stop button. Returns null when the
 * call did not finish (user cancel or failure); the record carries why.
 */
async function runCompletion(
  wllama: Wllama,
  call: CompletionCall,
  hooks: RunnerHooks,
  record: RunRecord,
): Promise<CompletionTimings | null> {
  const controller = new AbortController();
  hooks.onController?.(controller);
  const started = performance.now();
  try {
    const response = (await wllama.createCompletion({
      prompt: call.prompt,
      max_tokens: call.max_tokens,
      temperature: call.temperature ?? 0,
      seed: call.seed,
      abortSignal: controller.signal,
    })) as CompletionTimings;
    record.wallMs = Math.round(performance.now() - started);
    Object.assign(record, readTimings(response));
    if ((record.cachedTokens ?? 0) > CACHE_HIT_WARNING_TOKENS && !record.error) {
      record.error = `缓存污染警告：前缀命中 ${record.cachedTokens} tok，prefill 被低估`;
    }
    return response as CompletionTimings;
  } catch (error) {
    record.wallMs = Math.round(performance.now() - started);
    if (isAbortError(error)) {
      record.cancelledByUser = true;
      record.error = "用户停止";
    } else {
      record.error = errorMessage(error);
    }
    return null;
  }
}

/**
 * Prefill + calibration for one档位 combo. The first repeat doubles as the
 * calibration probe; the runner returns the calibrated ratio so later stages
 * (decode, accept, abort) build prompts with the same configuration.
 */
async function runPrefillCombo(
  wllama: Wllama,
  total: number,
  memory: number,
  repeat: number,
  charRatio: number,
  hooks: RunnerHooks,
): Promise<number> {
  const runNonce = nonce(total * 10007 + memory * 101 + repeat);
  const prompt = buildPrompt({
    totalTokens: total,
    memoryTokens: memory,
    nonce: runNonce,
    charRatio,
  });
  const seed = 445 + repeat;
  const record = baseRecord("prefill", `${total} tok（记忆 ${memory}）· 第 ${repeat + 1} 遍`);
  record.nominalTotalTokens = total;
  record.nominalMemoryTokens = memory;
  record.seed = seed;

  await runCompletion(wllama, { prompt, max_tokens: 1, seed }, hooks, record);
  hooks.onRun(record);

  const measured = record.promptTokens ?? 0;
  return measured > 0 ? adjustCharRatio(charRatio, measured, total) : charRatio;
}

/** Returns the calibrated chars-per-token ratio for the whole suite. */
export async function runPrefillMatrix(
  wllama: Wllama,
  config: BenchmarkConfig,
  hooks: RunnerHooks,
): Promise<number> {
  suiteEpoch += 1;
  let charRatio = 1.0;
  for (const { total, memory } of validCombos(config)) {
    for (let repeat = 0; repeat < config.prefillRepeats; repeat += 1) {
      if (stopped(hooks)) return charRatio;
      charRatio = await runPrefillCombo(wllama, total, memory, repeat, charRatio, hooks);
    }
  }
  return charRatio;
}

/** Decode speed at the largest档位, using the suite's calibrated ratio. */
export async function runDecodeMatrix(
  wllama: Wllama,
  config: BenchmarkConfig,
  charRatio: number,
  hooks: RunnerHooks,
): Promise<void> {
  const combos = validCombos(config);
  const largest = combos[combos.length - 1];
  if (!largest) return;

  for (let repeat = 0; repeat < config.decodeRepeats; repeat += 1) {
    if (stopped(hooks)) return;
    const runNonce = nonce(largest.total * 70001 + largest.memory * 13 + repeat);
    const prompt = buildPrompt({
      totalTokens: largest.total,
      memoryTokens: largest.memory,
      nonce: runNonce,
      charRatio,
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
    await runCompletion(
      wllama,
      { prompt, max_tokens: config.decodeTokens, seed },
      hooks,
      record,
    );
    hooks.onRun(record);
  }

  if (config.chatReference) {
    if (stopped(hooks)) return;
    const chatNonce = nonce(largest.total * 70001 + 777);
    const prompt = buildPrompt({
      totalTokens: largest.total,
      memoryTokens: largest.memory,
      nonce: chatNonce,
      charRatio,
    });
    const record = baseRecord("decode", `chat 模板对照 · ${largest.total} tok 输入`);
    record.nominalTotalTokens = largest.total;
    record.nominalMemoryTokens = largest.memory;
    record.maxTokens = Math.min(config.decodeTokens, 64);
    record.seed = 424242;
    const controller = new AbortController();
    hooks.onController?.(controller);
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
        abortSignal: controller.signal,
      })) as CompletionTimings;
      record.wallMs = Math.round(performance.now() - started);
      Object.assign(record, readTimings(response));
      if ((record.cachedTokens ?? 0) > CACHE_HIT_WARNING_TOKENS && !record.error) {
        record.error = `缓存污染警告：前缀命中 ${record.cachedTokens} tok，prefill 被低估`;
      }
    } catch (error) {
      record.wallMs = Math.round(performance.now() - started);
      if (isAbortError(error)) {
        record.cancelledByUser = true;
        record.error = "用户停止";
      } else {
        record.error = errorMessage(error);
      }
    }
    hooks.onRun(record);
  }
}

/**
 * REAL 4-second acceptance: one full call per档位 combo (actual prefill +
 * `acceptOutputTokens` generated), judged on measured wall time — not an
 * extrapolation from rates.
 */
export async function runAcceptMatrix(
  wllama: Wllama,
  config: BenchmarkConfig,
  charRatio: number,
  hooks: RunnerHooks,
): Promise<void> {
  for (const { total, memory } of validCombos(config)) {
    if (stopped(hooks)) return;
    const runNonce = nonce(total * 30011 + memory * 7 + config.acceptOutputTokens);
    const prompt = buildPrompt({
      totalTokens: total,
      memoryTokens: memory,
      nonce: runNonce,
      charRatio,
    });
    const seed = 55501 + total;
    const record = baseRecord(
      "accept",
      `4 秒实测 · ${total} tok（记忆 ${memory}）+ 生成 ${config.acceptOutputTokens}`,
    );
    record.nominalTotalTokens = total;
    record.nominalMemoryTokens = memory;
    record.maxTokens = config.acceptOutputTokens;
    record.seed = seed;
    await runCompletion(
      wllama,
      { prompt, max_tokens: config.acceptOutputTokens, seed },
      hooks,
      record,
    );
    // A verdict requires the call to actually deliver the target load: a
    // generation that stops early (EOS after 1 token) must not count as
    // "within 4 seconds" for a 512-token workload.
    record.completedLoad =
      !record.error
      && ((record.predictedTokens ?? 0) >= config.acceptOutputTokens
        || record.finishReason === "length");
    record.withinTarget =
      record.error || !record.completedLoad ? undefined : record.wallMs <= ACCEPT_TARGET_MS;
    hooks.onRun(record);
  }
}

export type AbortPlan = {
  /** Short fuse — expected to land during input processing. */
  shortMs: number;
  /**
   * Measured-prefill + margin — expected to land during generation. Null
   * when no prefill reference exists (skipped).
   */
  decodeMs: number | null;
};

/**
 * Cancel mid-call, once per phase. Each attempt records its outcome class,
 * and a context-overflow failure writes the error text on the record (and
 * retries smaller) instead of vanishing into an internal flag.
 */
export async function runAbortTests(
  wllama: Wllama,
  config: BenchmarkConfig,
  charRatio: number,
  hooks: RunnerHooks,
  plan: AbortPlan,
): Promise<void> {
  if (stopped(hooks)) return;
  await runAbortOnce(wllama, config, charRatio, hooks, plan.shortMs, "输入处理阶段取消", 1);
  if (plan.decodeMs != null && !stopped(hooks)) {
    await runAbortOnce(wllama, config, charRatio, hooks, plan.decodeMs, "生成阶段取消", 2);
  }
}

async function runAbortOnce(
  wllama: Wllama,
  config: BenchmarkConfig,
  charRatio: number,
  hooks: RunnerHooks,
  abortAfterMs: number,
  phaseLabel: string,
  phaseSalt: number,
): Promise<void> {
  const combos = validCombos(config);
  const totals = combos.map((combo) => combo.total);
  const memories = combos.map((combo) => combo.memory);
  let nominalTotal = Math.min(...(totals.length ? totals : [512]));
  const nominalMemory = Math.min(64, ...(memories.length ? memories : [64]));
  const maxTokens = Math.max(config.decodeTokens, 256);
  const seed = 31337;

  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const prompt = buildPrompt({
      totalTokens: nominalTotal,
      memoryTokens: nominalMemory,
      // The phase salt keeps the second cancel test from replaying the
      // first one's input computation through the prefix cache.
      nonce: nonce(999983 + phaseSalt * 1009 + attempt),
      charRatio,
    });
    const record = baseRecord(
      "abort",
      `${phaseLabel} · ${abortAfterMs}ms${attempt > 1 ? `（缩小提示第 ${attempt - 1} 次）` : ""}`,
    );
    record.nominalTotalTokens = nominalTotal;
    record.nominalMemoryTokens = nominalMemory;
    record.maxTokens = maxTokens;
    record.abortAfterMs = abortAfterMs;
    record.seed = seed;

    const controller = new AbortController();
    hooks.onController?.(controller);
    let timerFired = false;
    let stopRequestedAt = 0;
    let streamedChunks = 0;
    let generatedChars = 0;
    const timer = window.setTimeout(() => {
      timerFired = true;
      stopRequestedAt = performance.now();
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
        onData: (chunk) => {
          streamedChunks += 1;
          generatedChars += [...(chunk.choices?.[0]?.text ?? "")].length;
        },
      });
      record.completedNormally = true;
      record.abortOutcome = "completed_early";
    } catch (error) {
      const message = errorMessage(error);
      if (/exceeds the available context/i.test(message)) {
        contextOverflow = true;
        record.abortOutcome = "context_overflow";
        record.error = message;
      } else if (isAbortError(error)) {
        record.abortOutcome = timerFired ? "cancelled" : "error";
        if (!timerFired) {
          // Aborted before the benchmark fuse: that was the stop button.
          record.cancelledByUser = true;
          record.error = "用户停止";
        }
      } else {
        record.abortOutcome = "error";
        record.error = message;
      }
    } finally {
      window.clearTimeout(timer);
    }
    record.wallMs = Math.round(performance.now() - started);
    record.streamedChunks = streamedChunks;
    record.generatedChars = generatedChars;
    record.abortPhase = generatedChars > 0
      ? "decode"
      : record.completedNormally
        ? "decode"
        : "prefill";
    record.stopLatencyMs = stopRequestedAt > 0
      ? Math.round(performance.now() - stopRequestedAt)
      : undefined;
    record.heap = sampleHeap();
    hooks.onRun(record);

    if (record.cancelledByUser) return;
    if (!contextOverflow) return;
    if (attempt < 3) {
      nominalTotal = Math.max(64, Math.floor(nominalTotal / 4));
      hooks.onStatus(`中断测试提示超出上下文，缩小到 ${nominalTotal} tok 重试`);
    }
  }
}

/** Full-page memory sample (JS + WASM when the precise API is available). */
export async function runMemoryCheckpoint(
  label: string,
  hooks: RunnerHooks,
): Promise<void> {
  const record = baseRecord("memory", label);
  record.memory = await sampleMemory();
  hooks.onRun(record);
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
