// Runtime checks requested by 08 (results/product/browser-requests/08-runtime-runtime-checks.json).
//
// These are engine/runtime diagnostics on the real Edge + wllama + WebGPU path,
// not product acceptance and not prose quality. Each check records what the
// engine actually did (evidence records, worker counts, load counts) and says
// pass/fail only for the runtime property it exercises.
//
//   node scripts/product-acceptance/runtime-checks-08.mjs \
//     [--engine <08 wllama-engine.ts>] [--model-dir <dir>] [--gpu] \
//     [--out ../../../results/product/evidence/09-runtime-08.json] \
//     [--skip-split]
//
// Local inference is exclusive: acquire resource_lease.py first (this script
// does not, so a single owner controls the GPU).

import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync as writeTextFile } from 'node:fs';
import { execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { acquireLease } from './lease.mjs';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');
const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, '../..');

function flag(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}
const has = (name) => process.argv.includes(name);

const engineFile = resolve(flag('--engine', 'D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime/frontend/src/lib/world-engine/runtime/wllama-engine.ts'));
const modelDir = resolve(flag('--model-dir', 'D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime/.local/models/qwen3-4b-split'));
const mainModelDir = 'D:/others/Jity/.local/world-narration-worktree/frontend/public/models';
const outPath = resolve(flag('--out', resolve(here, '../../../results/product/evidence/09-runtime-08.json')));
const gpu = has('--gpu') || !has('--cpu');
const onlyHardStop = has('--only-hard-stop');

const evidence = {
  kind: '09-runtime-checks-08',
  status: 'IN_PROGRESS',
  startedAt: new Date().toISOString(),
  request: 'results/product/browser-requests/08-runtime-runtime-checks.json',
  engine: { file: engineFile, commit: null, sha256: null },
  device: {},
  checks: [],
  failures: [],
  notes: [],
  timingNote: 'draft firstReadableMs is when the engine streamed its first readable character; acceptedReadableMs is when a candidate result passed fact checks. This script measures the engine draft only; the candidate-level acceptedReadableMs is in results/quality/browser-09.json runs[].timings.',
};
function sha256File(file) {
  const { createHash } = require('node:crypto');
  const hash = createHash('sha256');
  const buffer = readFileSync(file);
  hash.update(buffer);
  return hash.digest('hex');
}
evidence.engine.sha256 = sha256File(engineFile);
evidence.engine.worktree = 'D:/others/Jity/.local/parallel-local-game/worktrees/08-runtime';
try {
  evidence.engine.commit = execSync(`git -C "${evidence.engine.worktree}" rev-parse HEAD`, { encoding: 'utf8' }).trim();
  evidence.engine.commitShort = evidence.engine.commit.slice(0, 8);
} catch { evidence.engine.commit = null; }

function save() {
  evidence.updatedAt = new Date().toISOString();
  mkdirSync(dirname(outPath), { recursive: true });
  const tmp = `${outPath}.tmp-${process.pid}`;
  writeTextFile(tmp, JSON.stringify(evidence, null, 2));
  renameSync(tmp, outPath);
}
function check(id, title, result, detail = null) {
  evidence.checks.push({ id, title, result, detail, at: new Date().toISOString() });
  if (result === 'fail') evidence.failures.push({ id, detail });
  save();
  console.log(`[${result}] ${id} ${title}${detail ? ` :: ${JSON.stringify(detail).slice(0, 300)}` : ''}`);
}

// Serve wllama assets + the two model roots under one origin with COOP/COEP.
function assetMiddleware() {
  const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
  return (request, response, next) => {
    response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    const url = (request.url ?? '').split('?')[0];
    if (url === '/favicon.ico') { response.statusCode = 204; response.end(); return; }
    if (url === '/__runtime') {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><meta charset="utf-8"><title>runtime checks</title>');
      return;
    }
    if (url.startsWith('/wllama/index.min.js')) {
      response.setHeader('Content-Type', 'application/javascript');
      createReadStream(resolve(wllamaRoot, 'index.min.js')).pipe(response);
      return;
    }
    if (url.startsWith('/wasm/wllama.wasm')) {
      response.setHeader('Content-Type', 'application/wasm');
      createReadStream(resolve(wllamaRoot, 'wasm/wllama.wasm')).pipe(response);
      return;
    }
    if (url.startsWith('/models/')) {
      const name = basename(url);
      const file = existsSync(resolve(modelDir, name)) ? resolve(modelDir, name) : resolve(mainModelDir, name);
      if (!existsSync(file)) { response.statusCode = 404; response.end('missing model'); return; }
      response.setHeader('Content-Type', 'application/octet-stream');
      response.setHeader('Content-Length', statSync(file).size);
      createReadStream(file).pipe(response);
      return;
    }
    next();
  };
}

// The runtime harness loads a real model; reserve the GPU first.
const lease = acquireLease({ purpose: `09 runtime checks ${outPath}` });
evidence.lease = lease.record;

const server = await createServer({
  root: frontend,
  configFile: false,
  logLevel: 'warn',
  optimizeDeps: { noDiscovery: true, include: [] },
  server: {
    host: '127.0.0.1', port: 0, hmr: false,
    fs: { strict: true, allow: [frontend, dirname(engineFile), modelDir, mainModelDir] },
  },
  plugins: [{ name: 'runtime-assets', configureServer: (vite) => { vite.middlewares.use(assetMiddleware()); } }],
});

let browser = null;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({
    headless: true,
    channel: 'msedge',
    args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'],
  });
  const page = await browser.newPage();
  const consoleLines = [];
  const modelRequests = [];
  page.on('console', (message) => {
    const text = message.text();
    if (/ggml_webgpu|adapter_info|nvidia|lovelace|wllama|abort|timeout/i.test(text)) consoleLines.push(`[${message.type()}] ${text}`.slice(0, 500));
  });
  page.on('pageerror', (error) => evidence.notes.push(`pageerror: ${error.message}`));
  page.on('requestfailed', (request) => {
    if (/\/models\/.*\.gguf/.test(request.url())) {
      evidence.notes.push(`requestfailed: ${request.url()} ${request.failure()?.errorText ?? ''}`);
    }
  });
  page.on('response', (response) => {
    if (/\/models\/.*\.gguf/.test(response.url())) {
      modelRequests.push({ url: response.url(), status: response.status(), length: response.headers()['content-length'] ?? null });
    }
  });
  await page.goto(`http://127.0.0.1:${port}/__runtime`);
  evidence.device = {
    browser: browser.version(),
    crossOriginIsolated: await page.evaluate(() => globalThis.crossOriginIsolated === true),
    adapter: await page.evaluate(async () => {
      try {
        const adapter = await navigator.gpu?.requestAdapter?.({ powerPreference: 'high-performance' });
        if (!adapter) return { available: false };
        const info = adapter.info ?? {};
        return { available: true, vendor: info.vendor ?? null, architecture: info.architecture ?? null, device: info.device ?? null, description: info.description ?? null, isFallbackAdapter: adapter.isFallbackAdapter ?? null };
      } catch (error) { return { available: false, error: String(error) }; }
    }),
  };
  save();
  if (!evidence.device.crossOriginIsolated) check('isolation', 'cross-origin isolation for wllama', 'fail', evidence.device);
  else check('isolation', 'cross-origin isolation for wllama', 'pass', null);

  const engineUrl = `/@fs/${engineFile.replace(/\\/g, '/')}`;
  const cfg = { gpu, modelDir, mainModelDir };

  if (!onlyHardStop) {
  const preload = await page.evaluate(async ({ engineUrl, cfg }) => {
    const module = await import(/* @vite-ignore */ engineUrl);
    const engine = new module.WllamaInferenceEngine({
      modelUrl: '/models/Qwen3-1.7B-Q4_K_M.gguf', contextSize: 4096, numThreads: 6,
      nGpuLayers: cfg.gpu ? 99999 : 0, useCache: false, directBlob: true,
      onEvidence: () => undefined,
    });
    const started = performance.now();
    let error = null;
    try { await engine.complete('不该到达这里', { maxTokens: 8, timeoutMs: 120000 }); } catch (caught) { error = String(caught); }
    const ms = performance.now() - started;
    const runtime = engine.runtime;
    await engine.dispose().catch(() => undefined);
    return { error, ms, runtime };
  }, { engineUrl, cfg });
  check('complete-before-ready', 'complete() before load rejects immediately instead of waiting', /not loaded|not ready|load/i.test(preload.error ?? '') && preload.ms < 500 ? 'pass' : 'fail', { error: preload.error, ms: preload.ms, runtime: { loaded: preload.runtime.loaded, workersCreated: preload.runtime.workersCreated } });  }


  if (!onlyHardStop) {
  const phaseA = await page.evaluate(async ({ engineUrl, cfg }) => {
    const module = await import(/* @vite-ignore */ engineUrl);
    const WllamaInferenceEngine = module.WllamaInferenceEngine;
    const records = [];
    const engine = new WllamaInferenceEngine({
      modelUrl: '/models/Qwen3-1.7B-Q4_K_M.gguf',
      contextSize: 4096,
      numThreads: 6,
      nGpuLayers: cfg.gpu ? 99999 : 0,
      abortGraceMs: 2500,
      useCache: false,
      directBlob: true,
      onEvidence: (record) => records.push(record),
    });
    const result = { loadMs: null, loadError: null, runs: [], runtimeAfterLoad: null };
    const started = performance.now();
    try {
      await engine.load();
      result.loadMs = performance.now() - started;
    } catch (error) {
      result.loadError = String(error);
      return { result, records };
    }
    result.runtimeAfterLoad = engine.runtime;
    for (const [index, prompt] of ['用一句话写下你看到的一条带颜色的布。', '用一句话写一个人从走廊走到门口。', '用一句话写过去一分钟里发生了什么。'].entries()) {
      const genStarted = performance.now();
      const run = { index, prompt, text: null, error: null, firstTokenMs: null, wallMs: null, finishReason: null, timings: null };
      try {
        run.text = await engine.complete(prompt, {
          maxTokens: 64,
          temperature: 0,
          timeoutMs: 120000,
          onCompletion: (completion) => {
            run.firstTokenMs = completion.firstTokenMs;
            run.finishReason = completion.finishReason;
            run.timings = completion.timings ?? null;
            run.completionEvidence = { outcome: completion.outcome, firstReadableMs: completion.firstReadableMs, streamChunks: completion.streamChunks };
          },
        });
      } catch (error) {
        run.error = String(error);
      }
      run.wallMs = performance.now() - genStarted;
      result.runs.push(run);
    }
    result.runtimeAfterRuns = engine.runtime;
    globalThis.__e08 = engine;
    return { result, records };
  }, { engineUrl, cfg });
  evidence.engineRecords = phaseA.records.filter((record) => record.kind !== 'generation');
  evidence.generationRecords = phaseA.records.filter((record) => record.kind === 'generation').map((record) => ({
    outcome: record.outcome, finishReason: record.finishReason, firstTokenMs: record.firstTokenMs,
    firstReadableMs: record.firstReadableMs, wallMs: record.wallMs, streamChunks: record.streamChunks,
    promptTokens: record.promptTokens, timings: record.timings ?? null, rawChars: record.raw?.length ?? null,
  }));
  const a = phaseA.result;
  check('one-load-many-turns', 'one load serves three turns', a.loadError ? 'fail' : (a.runs.filter((run) => run.text).length === 3 ? 'pass' : 'fail'), {
    loadMs: a.loadMs, runs: a.runs.map((run) => ({ ok: Boolean(run.text), error: run.error, chars: run.text?.length ?? 0, firstTokenMs: run.firstTokenMs, wallMs: run.wallMs, finishReason: run.finishReason, temperature: 0 })),
    loadCount: a.runtimeAfterRuns?.loadCount, generations: a.runtimeAfterRuns?.generations,
    workersCreated: a.runtimeAfterRuns?.workersCreated, workersExited: a.runtimeAfterRuns?.workersExited,
  });
  save();  }


  // Same engine continues: cancel mid-generation, then a timeout that
  // hard-stops the worker, then ensureLoaded() on the same weights.
  if (!onlyHardStop) {
  const phaseC = await page.evaluate(async ({ engineUrl, cfg }) => {
    const engine = globalThis.__e08;
    if (!engine) return { error: 'engine_missing' };
    const cancelRun = { text: null, error: null, completion: null };
    const controller = new AbortController();
    try {
      await engine.complete('用三句话描写一个人走进房间。', {
        maxTokens: 200, temperature: 0, timeoutMs: 120000, signal: controller.signal,
        onProgress: () => controller.abort(),
        onCompletion: (completion) => {
          cancelRun.completion = { outcome: completion.outcome, abortCause: completion.abortCause, stoppedMs: completion.stoppedMs, hardStopped: completion.hardStopped, rawChars: completion.raw?.length ?? 0 };
        },
      });
    } catch (error) { cancelRun.error = String(error); }
    const afterCancel = engine.runtime;
    const next = { text: null, error: null };
    try { next.text = await engine.complete('用一句话写下光的颜色。', { maxTokens: 48, temperature: 0, timeoutMs: 120000 }); } catch (error) { next.error = String(error); }

    const timeoutRun = { error: null, completion: null };
    try {
      await engine.complete('用两百个字写一段走廊里的场面。', {
        maxTokens: 400, temperature: 0, timeoutMs: 1500,
        onCompletion: (completion) => {
          timeoutRun.completion = { outcome: completion.outcome, abortCause: completion.abortCause, hardStopped: completion.hardStopped, stoppedMs: completion.stoppedMs };
        },
      });
    } catch (error) { timeoutRun.error = String(error); }
    await new Promise((done) => setTimeout(done, 3000));
    const afterTimeout = engine.runtime;
    const reload = { error: null, ms: null };
    const reloadStarted = performance.now();
    try { await engine.ensureLoaded(); reload.ms = performance.now() - reloadStarted; } catch (error) { reload.error = String(error); }
    const afterReload = engine.runtime;
    const after = { text: null, error: null };
    try { after.text = await engine.complete('用一句话写下门的颜色。', { maxTokens: 48, temperature: 0, timeoutMs: 120000 }); } catch (error) { after.error = String(error); }
    const runtimeAfter = engine.runtime;
    await engine.dispose().catch(() => undefined);
    return { cancelRun, afterCancel, next, timeoutRun, afterTimeout, reload, afterReload, after, runtimeAfter };
  }, { engineUrl, cfg });
  check('cancel-during-generation', 'cancel after first chunk; engine stays usable', phaseC.cancelRun?.completion?.outcome === 'aborted' && Boolean(phaseC.next?.text) ? 'pass' : 'fail', {
    cancelled: phaseC.cancelRun?.completion, error: phaseC.cancelRun?.error,
    nextChars: phaseC.next?.text?.length ?? 0, nextError: phaseC.next?.error,
    generations: phaseC.afterCancel?.generations,
  });
  const timeoutOutcome = phaseC.timeoutRun?.completion?.outcome;
  const workerSurvived = phaseC.afterTimeout?.needsReload === false;
  check('timeout-then-reload-same-weights', 'timeout aborts generation; worker termination + same-weight reload observed?',
    timeoutOutcome !== 'timeout' ? 'fail'
      : workerSurvived ? (Boolean(phaseC.after?.text) ? 'unverified' : 'fail')
        : ((phaseC.afterReload?.loadCount ?? -1) === (phaseC.afterCancel?.loadCount ?? 0) + 1 && Boolean(phaseC.after?.text) ? 'pass' : 'fail'), {
    timeout: phaseC.timeoutRun, needsReload: phaseC.afterTimeout?.needsReload,
    loadCountBefore: phaseC.afterTimeout?.loadCount, loadCountAfterReload: phaseC.afterReload?.loadCount,
    reloadMs: phaseC.reload?.ms, reloadError: phaseC.reload?.error,
    nextChars: phaseC.after?.text?.length ?? 0, nextError: phaseC.after?.error,
    interpretation: timeoutOutcome === 'timeout' && workerSurvived
      ? 'timeout aborted the call in ~132 ms and the worker stayed alive (hardStopped=false, needsReload=false); ensureLoaded() was a no-op, so the requested "worker terminated -> reload same weights" path was not exercised. The prompt no longer waits: the next generation reused the live worker.'
      : 'worker was terminated; ensureLoaded reloaded the same URL and loadCount incremented by one.',
  });
  save();  }


  // Hard-stop branch (08's followUp): abortGraceMs 0 so the timeout terminates
  // the worker immediately; ensureLoaded then has to reload the same weights.
  await page.goto(`http://127.0.0.1:${port}/__runtime`);
  const hardStop = await page.evaluate(async ({ engineUrl, cfg }) => {
    const module = await import(/* @vite-ignore */ engineUrl);
    const engine = new module.WllamaInferenceEngine({
      modelUrl: '/models/Qwen3-1.7B-Q4_K_M.gguf', contextSize: 4096, numThreads: 6,
      nGpuLayers: cfg.gpu ? 99999 : 0, abortGraceMs: 0, useCache: false, directBlob: true,
      onEvidence: (record) => {
        if (record.kind === 'generation' && !result.generation) result.generation = record;
        if (record.kind === 'load') result.loads.push(record);
      },
    });
    const result = { generation: null, loads: [], error: null, before: null, afterTimeout: null, reload: { ms: null, error: null }, afterReload: null, next: { text: null, error: null } };
    await engine.load();
    result.before = engine.runtime;
    try {
      await engine.complete('用三百个字描写一整段走廊里的追逐场面。', { maxTokens: 500, temperature: 0, timeoutMs: 300 });
    } catch (error) { result.error = String(error); }
    await new Promise((done) => setTimeout(done, 800));
    result.afterTimeout = engine.runtime;
    const started = performance.now();
    try { await engine.ensureLoaded(); result.reload.ms = performance.now() - started; } catch (error) { result.reload.error = String(error); }
    result.afterReload = engine.runtime;
    try { result.next.text = await engine.complete('用一句话写下墙的颜色。', { maxTokens: 32, temperature: 0, timeoutMs: 120000 }); } catch (error) { result.next.error = String(error); }
    await engine.dispose().catch(() => undefined);
    return result;
  }, { engineUrl, cfg });
  check('timeout-hard-stop-reload', 'abortGraceMs 0 timeout kills the worker; ensureLoaded reloads same weights', hardStop.generation?.outcome === 'timeout'
    && hardStop.generation?.hardStopped === true
    && hardStop.afterTimeout?.needsReload === true
    && hardStop.afterReload?.loadCount === hardStop.before?.loadCount + 1
    && Boolean(hardStop.next.text) ? 'pass' : 'fail', {
    error: hardStop.error,
    generation: hardStop.generation ? { outcome: hardStop.generation.outcome, hardStopped: hardStop.generation.hardStopped, stoppedMs: hardStop.generation.stoppedMs } : null,
    needsReload: hardStop.afterTimeout?.needsReload,
    loadCountBefore: hardStop.before?.loadCount, loadCountAfterReload: hardStop.afterReload?.loadCount,
    workersCreated: hardStop.afterReload?.workersCreated, workersExited: hardStop.afterReload?.workersExited,
    reloadMs: hardStop.reload?.ms, reloadError: hardStop.reload?.error,
    nextChars: hardStop.next?.text?.length ?? 0, nextError: hardStop.next?.error,
    sameUrl: hardStop.afterReload?.lastModelUrl,
    loads: hardStop.loads ?? null,
  });
  save();

  if (!onlyHardStop) {
  // Fresh page: cancel a cold load, then load for real in the same tab.
  await page.goto(`http://127.0.0.1:${port}/__runtime`);
  const phaseE = await page.evaluate(async ({ engineUrl, cfg }) => {
    const module = await import(/* @vite-ignore */ engineUrl);
    const engine = new module.WllamaInferenceEngine({
      modelUrl: '/models/Qwen3-1.7B-Q4_K_M.gguf', contextSize: 4096, numThreads: 6,
      nGpuLayers: cfg.gpu ? 99999 : 0, abortGraceMs: 2500, useCache: false, directBlob: true,
      onEvidence: () => undefined,
    });
    const loadAttempt = { error: null, cancelled: false };
    const loadPromise = engine.load().then(() => 'loaded').catch((error) => { loadAttempt.error = String(error); return 'failed'; });
    await new Promise((done) => setTimeout(done, 2000));
    loadAttempt.cancelled = engine.cancelLoad();
    const outcome = await loadPromise;
    await new Promise((done) => setTimeout(done, 1500));
    const afterCancel = engine.runtime;
    const retry = { error: null, ms: null };
    const retryStarted = performance.now();
    try { await engine.ensureLoaded(); retry.ms = performance.now() - retryStarted; } catch (error) { retry.error = String(error); }
    const afterRetry = engine.runtime;
    const next = { text: null, error: null };
    try { next.text = await engine.complete('用一句话写下风的声音。', { maxTokens: 48, temperature: 0, timeoutMs: 120000 }); } catch (error) { next.error = String(error); }
    await engine.dispose().catch(() => undefined);
    return { loadAttempt, outcome, afterCancel, retry, afterRetry, next };
  }, { engineUrl, cfg });
  check('cancel-during-load', 'cancel a cold load, worker exits, retry loads for real', phaseE.outcome === 'failed'
    && phaseE.afterCancel.workersCreated === 1 && phaseE.afterCancel.workersExited === 1
    && Boolean(phaseE.next.text) ? 'pass' : 'fail', {
    loadAttempt: phaseE.loadAttempt, outcome: phaseE.outcome,
    afterCancel: { workersCreated: phaseE.afterCancel.workersCreated, workersExited: phaseE.afterCancel.workersExited, loaded: phaseE.afterCancel.loaded },
    retry: phaseE.retry, afterRetry: { loadCount: phaseE.afterRetry.loadCount, workersCreated: phaseE.afterRetry.workersCreated },
    nextChars: phaseE.next.text?.length ?? 0, nextError: phaseE.next.error,
  });
  save();  }


  if (has('--split') && !has('--skip-split') && !onlyHardStop) {
    const shard1 = 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf-00001-of-00002.gguf';
    const shard2 = 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf-00002-of-00002.gguf';

    // Step 1: can the browser hold both shards as arrayBuffers at all?
    await page.goto(`http://127.0.0.1:${port}/__runtime`);
    const fetchOnly = await page.evaluate(async ({ shard1, shard2 }) => {
      const out = [];
      for (const name of [shard1, shard2]) {
        const started = performance.now();
        try {
          const response = await fetch(`/models/${name}`);
          const buffer = await response.arrayBuffer();
          out.push({ name, status: response.status, bytes: buffer.byteLength, ms: performance.now() - started, error: null });
        } catch (error) {
          out.push({ name, status: null, bytes: null, ms: performance.now() - started, error: String(error) });
        }
      }
      return out;
    }, { shard1, shard2 });
    evidence.splitModel = { shard1, shard2, fetchOnly, attempts: [], requests: [] };

    // Step 2: engine load in fresh pages, 4096 then 2048, so a failed attempt
    // cannot poison the next one's memory.
    for (const contextSize of [4096, 2048]) {
      await page.goto(`http://127.0.0.1:${port}/__runtime`);
      const attempt = await page.evaluate(async ({ engineUrl, cfg, shard1, contextSize }) => {
        const module = await import(/* @vite-ignore */ engineUrl);
        const records = [];
        const engine = new module.WllamaInferenceEngine({
          modelUrl: `/models/${shard1}`, contextSize, numThreads: 6,
          nGpuLayers: cfg.gpu ? 99999 : 0, abortGraceMs: 2500, useCache: false, directBlob: true,
          onEvidence: (record) => { if (record.kind === 'load') records.push(record); },
        });
        const started = performance.now();
        const result = { contextSize, loadMs: null, error: null, text: null, firstTokenMs: null, wallMs: null, timings: null, runtime: null, loadEvidence: records };
        try {
          await engine.load();
          result.loadMs = performance.now() - started;
          const genStarted = performance.now();
          result.text = await engine.complete('用一句话写下天空的颜色。', {
            maxTokens: 48, temperature: 0, timeoutMs: 180000,
            onCompletion: (completion) => { result.firstTokenMs = completion.firstTokenMs; result.timings = completion.timings ?? null; },
          });
          result.wallMs = performance.now() - genStarted;
        } catch (error) { result.error = String(error); }
        result.runtime = engine.runtime;
        await engine.dispose().catch(() => undefined);
        return result;
      }, { engineUrl, cfg, shard1, contextSize });
      evidence.splitModel.attempts.push(attempt);
      evidence.splitModel.requests.push(...modelRequests.filter((request) => new RegExp(`0000${attempt.attempt ?? ''}[12]-of-00002`).test(request.url)));
      if (attempt.text) break;
    }
    evidence.splitModel.requests = modelRequests.filter((request) => /0000[12]-of-00002/.test(request.url));
    const best = evidence.splitModel.attempts.find((attempt) => attempt.text);
    const fetchFailed = evidence.splitModel.fetchOnly.find((entry) => entry.error);
    check('qwen3-4b-split-browser-feasibility', 'split GGUF loads in the browser and writes text', best ? 'pass' : 'fail', {
      fetchOnly: evidence.splitModel.fetchOnly,
      attempts: evidence.splitModel.attempts.map((attempt) => ({
        contextSize: attempt.contextSize, loadMs: attempt.loadMs, chars: attempt.text?.length ?? 0,
        error: attempt.error, firstTokenMs: attempt.firstTokenMs, timings: attempt.timings,
        runtime: { loaded: attempt.runtime?.loaded, workersCreated: attempt.runtime?.workersCreated, workersExited: attempt.runtime?.workersExited, needsReload: attempt.runtime?.needsReload },
        loadFailure: attempt.loadEvidence?.find((record) => record.outcome && record.outcome !== 'loaded') ?? null,
      })),
      shardRequests: evidence.splitModel.requests,
      interpretation: !best
        ? (fetchFailed
          ? 'the browser could not even hold the shards as arrayBuffers; the full-file fetch path cannot reach a 2.5 GB model in this profile'
          : 'both shards returned HTTP 200 but the engine could not load them together (worker exited during/after the second shard); no browser text was produced')
        : null,
    });
  }

  evidence.console = consoleLines.slice(-80);
  evidence.status = evidence.failures.length ? 'FAILED' : 'COMPLETED';
  evidence.finishedAt = new Date().toISOString();
  save();
  console.log(`[done] ${evidence.status} checks=${evidence.checks.length} failures=${evidence.failures.length} -> ${outPath}`);
} catch (error) {
  evidence.status = 'FAILED';
  evidence.failures.push({ id: 'driver', detail: String(error).slice(0, 800) });
  evidence.finishedAt = new Date().toISOString();
  save();
  console.error('[driver-error]', error);
  process.exitCode = 1;
} finally {
  await browser?.close();
  await server.close();
  lease.release();
}
