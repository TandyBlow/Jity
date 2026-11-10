// Real-device runtime probe for the wllama adapter, the inference queue and
// the stage-timing evidence. It is NOT a benchmark of game quality: it loads
// the actual GGUF in a real browser, streams real tokens, aborts a real
// generation, trips the deadline, and measures what the device actually did.
//
//   node scripts/parallel-runtime/measure-wllama.mjs --out ../.local/parallel-runtime/measure.json
//
// The model is served read-only from the shared models directory (default
// D:/others/Jity/frontend/public/models); nothing is copied into this tree.
// Acquire the self-service inference lease before running:
//   python .local/parallel-local-game/resource_lease.py acquire --lane 08-runtime --purpose "..."
// and release it in a finally block afterwards.
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const hasFlag = (flag) => process.argv.includes(flag);
const config = {
  modelFile: option('--model', 'Qwen3-0.6B-Q4_K_M.gguf'),
  modelsDir: resolve(option('--models', 'D:/others/Jity/frontend/public/models')),
  contextSize: Number(option('--context', '2048')),
  numThreads: Number(option('--threads', '4')),
  maxTokens: Number(option('--max-tokens', '48')),
  shortTimeoutMs: Number(option('--short-timeout-ms', '60000')),
  deadlineMs: Number(option('--deadline-ms', '250')),
  abortGraceMs: Number(option('--abort-grace-ms', '2500')),
  channel: option('--channel', 'msedge'),
  out: resolve(frontend, option('--out', '../.local/parallel-runtime/measure.json')),
};
const modelUrl = `/models/${config.modelFile}`;
const modelPath = resolve(config.modelsDir, config.modelFile);
if (!existsSync(modelPath)) throw new Error(`model not found: ${modelPath} (pass --models)`);
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const sourceFiles = [
  'frontend/src/lib/world-engine/runtime/wllama-engine.ts',
  'frontend/src/lib/world-engine/runtime/inference-queue.ts',
  'frontend/src/lib/world-engine/runtime/engine.ts',
  'frontend/src/lib/world-engine/local/runtime-diagnostics/types.ts',
  'frontend/src/lib/world-engine/local/runtime-diagnostics/recorder.ts',
  'frontend/src/lib/world-engine/local/runtime-diagnostics/stage-timer.ts',
  'frontend/src/lib/world-engine/local/runtime-diagnostics/index.ts',
  'frontend/scripts/parallel-runtime/measure-wllama.mjs',
];
const git = async (args) => {
  try {
    const { execFileSync } = await import('node:child_process');
    return execFileSync('git', ['-c', `safe.directory=${resolve(frontend, '..').replaceAll('\\', '/')}`, '-C', resolve(frontend, '..'), ...args], { encoding: 'utf8' }).trim();
  } catch {
    return '';
  }
};
const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
const report = {
  status: 'IN_PROGRESS',
  lane: process.env.JITY_PI_LANE ?? '08-runtime',
  startedAt: new Date().toISOString(),
  config,
  source: { head: await git(['rev-parse', 'HEAD']), status: await git(['status', '--short']),
    sha256: Object.fromEntries(sourceFiles.map((file) => [file, sha256(readFileSync(resolve(frontend, '..', file)))])),
    node: process.version },
  assets: {
    modelPath, modelBytes: statSync(modelPath).size, modelSha256: sha256(readFileSync(modelPath)),
    wllamaBundleSha256: sha256(readFileSync(resolve(wllamaRoot, 'index.min.js'))),
    wllamaWasmSha256: sha256(readFileSync(resolve(wllamaRoot, 'wasm/wllama.wasm'))),
    wllamaVersion: JSON.parse(readFileSync(resolve(frontend, 'node_modules/@wllama/wllama/package.json'), 'utf8')).version,
  },
};
const save = () => {
  mkdirSync(dirname(config.out), { recursive: true });
  const temp = `${config.out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(report, null, 2)}\n`);
  renameSync(temp, config.out);
};
save();

function sendFile(res, file, type) {
  if (!existsSync(file)) {
    res.statusCode = 404;
    res.end(`missing ${basename(file)}`);
    return;
  }
  const stat = statSync(file);
  res.setHeader('Content-Type', type);
  res.setHeader('Content-Length', stat.size);
  res.setHeader('Cache-Control', 'no-store');
  createReadStream(file).pipe(res);
}

const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/parallel-runtime-vite',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{ name: 'parallel-runtime', configureServer(vite) {
    vite.middlewares.use((req, res, next) => {
      res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
      res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
      const pathname = new URL(req.url ?? '/', 'http://127.0.0.1').pathname;
      if (pathname === '/__runtime') {
        res.setHeader('Content-Type', 'text/html');
        res.end('<!doctype html><meta charset="utf-8"><title>runtime probe</title><body>runtime probe</body>');
        return;
      }
      if (pathname === '/wllama/index.min.js') return sendFile(res, resolve(wllamaRoot, 'index.min.js'), 'text/javascript');
      if (pathname === '/wasm/wllama.wasm') return sendFile(res, resolve(wllamaRoot, 'wasm/wllama.wasm'), 'application/wasm');
      if (pathname.startsWith('/models/')) {
        // basename only: the probe never needs subdirectories, and this keeps
        // the shared models directory read-only and unreachable elsewhere.
        return sendFile(res, resolve(config.modelsDir, basename(decodeURIComponent(pathname))), 'application/octet-stream');
      }
      next();
    });
  } }],
});

let browser;
try {
  await server.listen();
  report.serverPort = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel, args: ['--enable-unsafe-webgpu'] });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.goto(`http://127.0.0.1:${report.serverPort}/__runtime`);
  const result = await page.evaluate(async (config) => {
    const startedAt = performance.now();
    const probe = { crossOriginIsolated: globalThis.crossOriginIsolated, hardwareConcurrency: navigator.hardwareConcurrency,
      userAgent: navigator.userAgent, startedAt, timings: {}, attempts: {}, samples: [], abort: null, deadline: null, dispose: null,
      errors: [] };
    let adapter = null;
    try { adapter = await navigator.gpu?.requestAdapter?.() ?? null; } catch (error) { probe.errors.push(`webgpu adapter: ${String(error)}`); }
    probe.webgpu = !!adapter;
    const modules = {
      engine: await import('/src/lib/world-engine/runtime/wllama-engine.ts'),
      diagnostics: await import('/src/lib/world-engine/local/runtime-diagnostics/index.ts'),
      queue: await import('/src/lib/world-engine/runtime/inference-queue.ts'),
      engineTypes: await import('/src/lib/world-engine/runtime/engine.ts'),
    };
    const diagnostics = new modules.diagnostics.RuntimeDiagnostics({ limit: 256 });
    const timer = new modules.diagnostics.StageTimer();
    const make = async (gpuLayers) => {
      const engine = new modules.engine.WllamaInferenceEngine({ modelUrl: config.modelUrl, contextSize: config.contextSize,
        numThreads: config.numThreads, nGpuLayers: gpuLayers, abortGraceMs: config.abortGraceMs, onEvidence: diagnostics.record });
      const started = performance.now();
      await engine.load();
      return { engine, loadMs: performance.now() - started, runtime: engine.runtime };
    };
    let engine;
    try {
      const attempt = await make(99999);
      engine = attempt.engine;
      probe.attempts.gpu = { ok: true, loadMs: attempt.loadMs, runtime: attempt.runtime };
    } catch (error) {
      probe.attempts.gpu = { ok: false, error: `${error?.name}: ${error?.message}`, elapsedMs: performance.now() - startedAt };
      const attempt = await make(0);
      engine = attempt.engine;
      probe.attempts.cpu = { ok: true, loadMs: attempt.loadMs, runtime: attempt.runtime };
    }
    const duplicateStarted = performance.now();
    await engine.load();
    probe.timings.duplicateLoadMs = performance.now() - duplicateStarted;
    probe.topology = engine.diagnostics;

    const prompt = '你是中文跑酷冒险的叙述者。只用三句话描写雨夜巷口的一次追逐，不要解释，不要列点。';
    const longPrompt = '你是中文跑酷冒险的叙述者。详细描写雨夜巷口的一次追逐：至少分成四段，写清人物的动作、环境的声音和主角的呼吸变化。不要解释，不要列点。';
    const run = async (label, text, options) => {
      let completion = null;
      const started = performance.now();
      const progressAt = [];
      const value = await engine.complete(text, { ...options, timeoutMs: options.timeoutMs ?? config.shortTimeoutMs,
        onProgress: (progress) => { progressAt.push(progress.elapsedMs); timer.tick(); },
        onCompletion: (evidence) => { completion = evidence; } });
      const wallMs = performance.now() - started;
      return { label, ok: true, wallMs, chars: value.length, firstProgressMs: progressAt[0] ?? null, completion };
    };

    // Two identical prompts: the second reports prompt-cache reuse.
    probe.samples.push(await run('cache-warm-1', prompt, { maxTokens: config.maxTokens, temperature: 0, seed: 42, cachePrompt: true }));
    probe.samples.push(await run('cache-warm-2', prompt, { maxTokens: config.maxTokens, temperature: 0, seed: 42, cachePrompt: true }));

    // Real abort as soon as readable text starts; then immediately reuse the
    // engine, which shows whether a cancellation left the model unusable.
    {
      const controller = new AbortController();
      let completion = null;
      let abortAt = null;
      let firstProgressAt = null;
      const started = performance.now();
      try {
        await engine.complete(longPrompt, { maxTokens: 512, temperature: 0.7, seed: 7, cachePrompt: true,
          timeoutMs: 120000, signal: controller.signal,
          onProgress: (progress) => {
            timer.tick();
            if (firstProgressAt === null) firstProgressAt = performance.now();
            if (abortAt === null && progress.raw.trim().length > 0) {
              abortAt = performance.now();
              controller.abort();
            }
          },
          onCompletion: (evidence) => { completion = evidence; },
        });
        probe.abort = { settledWithValue: true, wallMs: performance.now() - started, abortAt, firstProgressAt, completion };
      } catch (error) {
        probe.abort = { settledWithValue: false, name: error?.name, message: error?.message,
          abortToSettleMs: abortAt === null ? null : performance.now() - abortAt,
          wallMs: performance.now() - started, abortAt, firstProgressAt, completion };
      }
      try {
        probe.samples.push(await run('after-abort', prompt, { maxTokens: config.maxTokens, temperature: 0, seed: 42, cachePrompt: true }));
      } catch (error) {
        probe.errors.push(`after-abort: ${error?.name}: ${error?.message}`);
        if (!engine.runtime.loaded) {
          const reload = await make(engine.runtime.gpuLayers);
          engine = reload.engine;
          probe.timings.reloadAfterAbortMs = reload.loadMs;
          probe.samples.push(await run('after-abort-reload', prompt, { maxTokens: config.maxTokens, temperature: 0, seed: 42, cachePrompt: true }));
        }
      }
    }

    // The deadline path: abort a long generation after 250 ms and observe
    // whether the native cancel settles or the worker had to be terminated.
    {
      let completion = null;
      const started = performance.now();
      try {
        await engine.complete(longPrompt, { maxTokens: 512, temperature: 0, seed: 7, cachePrompt: false,
          timeoutMs: config.deadlineMs, onCompletion: (evidence) => { completion = evidence; } });
        probe.deadline = { settledWithValue: true, wallMs: performance.now() - started, completion };
      } catch (error) {
        probe.deadline = { settledWithValue: false, name: error?.name, message: error?.message,
          wallMs: performance.now() - started, completion };
      }
      probe.deadline.runtimeAfter = engine.runtime;
      if (!engine.runtime.loaded) {
        const reload = await make(engine.runtime.gpuLayers);
        engine = reload.engine;
        probe.timings.reloadAfterDeadlineMs = reload.loadMs;
      }
      try {
        probe.samples.push(await run('after-deadline', prompt, { maxTokens: config.maxTokens, temperature: 0, seed: 42, cachePrompt: false }));
      } catch (error) {
        probe.errors.push(`after-deadline: ${error?.name}: ${error?.message}`);
      }
    }

    // Queue evidence through the same engine, using a shared recorder.
    const queue = new modules.queue.SerialInferenceQueue(diagnostics.record);
    const queued = queue.run({ label: 'queued-after-probe', start: () => engine.complete(prompt, {
      maxTokens: 16, temperature: 0, seed: 42, cachePrompt: false, timeoutMs: config.shortTimeoutMs }) });
    probe.queue = { result: (await queued).value.length, stats: queue.stats };
    queue.dispose();

    const disposeStarted = performance.now();
    await engine.dispose();
    const firstDisposeMs = performance.now() - disposeStarted;
    const secondStarted = performance.now();
    await engine.dispose();
    probe.dispose = { firstDisposeMs, secondDisposeMs: performance.now() - secondStarted,
      terminal: !engine.runtime.loaded && engine.info.modelId === null };
    probe.timings.totalMs = performance.now() - startedAt;
    probe.timer = timer.snapshot();
    probe.diagnostics = diagnostics.snapshot();
    return probe;
  }, { ...config, modelUrl });
  report.result = result;
  report.status = 'COMPLETED';
  report.finishedAt = new Date().toISOString();
  save();
  const summary = result.diagnostics.summary;
  console.log(JSON.stringify({
    status: report.status,
    gpu: result.attempts.gpu?.ok ?? false,
    loadMs: result.attempts.gpu?.loadMs ?? result.attempts.cpu?.loadMs,
    duplicateLoadMs: result.timings.duplicateLoadMs,
    firstReadable: summary.generations.firstReadable,
    wall: summary.generations.wall,
    abort: result.abort && { settled: result.abort.settledWithValue, name: result.abort.name, abortToSettleMs: result.abort.abortToSettleMs,
      hardStopped: result.abort.completion?.hardStopped, stoppedMs: result.abort.completion?.stoppedMs },
    deadline: result.deadline && { name: result.deadline.name, hardStopped: result.deadline.completion?.hardStopped,
      stoppedMs: result.deadline.completion?.stoppedMs, runtimeAfter: result.deadline.runtimeAfter },
    cancels: summary.cancellations,
    queue: summary.queue,
    errors: result.errors,
  }, null, 2));
} catch (error) {
  report.status = 'FAILED';
  report.error = error instanceof Error ? `${error.name}: ${error.message}\n${error.stack}` : String(error);
  save();
  throw error;
} finally {
  if (browser) await browser.close();
  await server.close();
  report.cleanup = { browserClosed: true, serverClosed: true };
  save();
}
