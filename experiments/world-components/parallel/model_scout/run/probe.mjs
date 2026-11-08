// Minimal browser run of MNN-Pocket-0.3B (GGUF) without WebGPU.
//
// What it does, end to end:
//  1. starts a local HTTP server (COOP/COEP so SharedArrayBuffer survives) that
//     serves this worktree's wllama bundle, the wllama wasm and the GGUF file
//     from the local model cache;
//  2. launches Edge headless through Playwright with GPU/WebGPU disabled;
//  3. in the page, deletes navigator.gpu, loads the GGUF through wllama
//     (WASM CPU, n_gpu_layers = 0) and runs the registered fixed prompt twice
//     with temperature 0 and seed 42;
//  4. records load time, memory samples, first-token latency, decode speed,
//     finish reason, raw text, and every console/page/request error.
//
// The output is one JSON file. Nothing is graded here: this run answers
// "does it load and generate in this browser", not "is the text good".
//
//   node run/probe.mjs --model ../../../.local/models/MNN-Pocket-0.3B-Instruct-Q4_1.gguf \
//       --out evidence/probe-Q4_1.json
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { cpus, freemem, totalmem } from 'node:os';
import { createReadStream, readFileSync, statSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { dirname, extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const experimentRoot = resolve(here, '..');
const frontend = resolve(experimentRoot, '../../../../frontend');
// Playwright is installed under frontend/node_modules; resolve it from there so
// this script can live in the experiment folder without its own package.json.
const { chromium } = createRequire(resolve(frontend, 'package.json'))('@playwright/test');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const git = (...args) => spawnSync('git', ['-c', 'safe.directory=*', '-C', experimentRoot, ...args], { encoding: 'utf8' }).stdout.trim();

const config = {
  model: resolve(option('--model', '')),
  prompt: resolve(option('--prompt', resolve(experimentRoot, 'inputs/nv-move-1.prompt.txt'))),
  out: resolve(option('--out', resolve(experimentRoot, 'evidence/probe.json'))),
  nCtx: Number(option('--n-ctx', '2048')),
  threads: Number(option('--threads', '4')),
  maxTokens: Number(option('--max-tokens', '96')),
  temperature: Number(option('--temperature', '0')),
  seed: Number(option('--seed', '42')),
  runs: Number(option('--runs', '2')),
  channel: option('--channel', 'msedge'),
  // Extra chat-template arguments, e.g. '{"enable_thinking":false}' for Qwen3
  // controls. Empty means "send none".
  chatKwargs: option('--chat-kwargs', ''),
  timeoutMs: Number(option('--timeout-ms', '600000')),
};
const promptText = readFileSync(config.prompt, 'utf8');
const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
const assets = {
  bundle: resolve(wllamaRoot, 'index.min.js'),
  wasm: resolve(wllamaRoot, 'wasm/wllama.wasm'),
};

const report = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  config: { ...config, modelBytes: statSync(config.model).size, modelSha256: sha256(readFileSync(config.model)) },
  prompt: { file: config.prompt, chars: promptText.length, sha256: sha256(Buffer.from(promptText, 'utf8')), text: promptText },
  assets: { bundleSha256: sha256(readFileSync(assets.bundle)), wasmSha256: sha256(readFileSync(assets.wasm)),
    wllamaVersion: JSON.parse(readFileSync(resolve(frontend, 'node_modules/@wllama/wllama/package.json'), 'utf8')).version },
  source: { head: git('rev-parse', 'HEAD'), branch: git('rev-parse', '--abbrev-ref', 'HEAD'), status: git('status', '--short') },
  device: { platform: process.platform, arch: process.arch, cpu: cpus()[0]?.model, logicalCpus: cpus().length,
    totalMemGB: +(totalmem() / 2 ** 30).toFixed(1), freeMemGB: +(freemem() / 2 ** 30).toFixed(1), node: process.version },
  console: [], pageErrors: [], requestFailures: [],
};
const save = () => writeFileSync(config.out, JSON.stringify(report, null, 2) + '\n');
save();

const MIME = { '.js': 'text/javascript', '.wasm': 'application/wasm', '.gguf': 'application/octet-stream', '.html': 'text/html; charset=utf-8' };
const isolate = (response) => {
  response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  response.setHeader('Cross-Origin-Resource-Policy', 'same-origin');
};
const serveFile = (request, response, file, download) => {
  const size = statSync(file).size;
  const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.range ?? '');
  if (range) {
    const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2] || 0));
    const end = range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
    response.writeHead(206, { 'Content-Range': `bytes ${start}-${end}/${size}`, 'Accept-Ranges': 'bytes',
      'Content-Length': end - start + 1, 'Content-Type': MIME[extname(file)] ?? 'application/octet-stream' });
    createReadStream(file, { start, end }).pipe(response);
    return;
  }
  response.writeHead(200, { 'Content-Length': size, 'Accept-Ranges': 'bytes',
    'Content-Type': MIME[extname(file)] ?? 'application/octet-stream', ...(download ? { 'Content-Disposition': 'attachment' } : {}) });
  createReadStream(file).pipe(response);
};

const server = createServer((request, response) => {
  isolate(response);
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname === '/') {
    response.writeHead(200, { 'Content-Type': MIME['.html'], 'Cache-Control': 'no-store' });
    response.end('<!doctype html><meta charset="utf-8"><title>model scout probe</title><body>probe page</body>');
    return;
  }
  if (url.pathname === '/wllama/index.min.js') return serveFile(request, response, assets.bundle);
  if (url.pathname === '/wasm/wllama.wasm') return serveFile(request, response, assets.wasm);
  if (url.pathname === '/model.gguf') return serveFile(request, response, config.model, true);
  if (url.pathname === '/favicon.ico') return response.writeHead(204).end();
  response.writeHead(404).end();
});

let browser;
try {
  await new Promise((done) => server.listen(0, '127.0.0.1', done));
  const origin = `http://127.0.0.1:${server.address().port}`;
  report.server = { origin };

  const cpuLoad = spawnSync('powershell', ['-NoProfile', '-Command',
    '(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average'], { encoding: 'utf8' }).stdout.trim();
  report.device.cpuLoadPercentAtStart = Number(cpuLoad) || null;
  browser = await chromium.launch({ headless: true, channel: config.channel,
    args: ['--disable-gpu', '--disable-features=WebGPU,Vulkan', '--js-flags=--expose-gc'] });
  report.browser = { version: browser.version(), channel: config.channel };
  const page = await browser.newPage();
  page.setDefaultTimeout(config.timeoutMs);
  page.on('console', (message) => report.console.push({ at: new Date().toISOString(), type: message.type(), text: message.text() }));
  page.on('pageerror', (error) => report.pageErrors.push({ at: new Date().toISOString(), message: error.message, stack: error.stack ?? null }));
  page.on('requestfailed', (request) => report.requestFailures.push({ at: new Date().toISOString(), url: request.url(),
    failure: request.failure()?.errorText ?? null }));
  // WebGPU must not be reachable from the page: deleting navigator.gpu before any
  // script runs proves the run below cannot have used it.
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'gpu', { configurable: true, get: () => undefined });
  });
  await page.goto(origin, { waitUntil: 'load' });
  report.environment = await page.evaluate(() => ({
    href: location.href, crossOriginIsolated: globalThis.crossOriginIsolated === true,
    gpuVisible: 'gpu' in navigator && navigator.gpu !== undefined,
  }));

  const result = await page.evaluate(async ({ config, promptText }) => {
    const memory = async () => {
      const started = performance.now();
      if (typeof performance.measureUserAgentSpecificMemory !== 'function') return { error: 'measureUserAgentSpecificMemory unavailable' };
      try {
        const sample = await performance.measureUserAgentSpecificMemory();
        return { ts: Date.now(), ms: Math.round(performance.now() - started), totalMB: +(sample.bytes / 2 ** 20).toFixed(1),
          breakdown: sample.breakdown.map((item) => ({ bytesMB: +(item.bytes / 2 ** 20).toFixed(1), types: item.types })) };
      } catch (error) {
        return { error: String(error) };
      }
    };
    const heap = () => performance.memory ? { usedMB: +(performance.memory.usedJSHeapSize / 2 ** 20).toFixed(1),
      totalMB: +(performance.memory.totalJSHeapSize / 2 ** 20).toFixed(1), limitMB: +(performance.memory.jsHeapSizeLimit / 2 ** 20).toFixed(1) } : null;

    const environment = {
      userAgent: navigator.userAgent, crossOriginIsolated: globalThis.crossOriginIsolated === true,
      sharedArrayBuffer: typeof SharedArrayBuffer === 'function', hardwareConcurrency: navigator.hardwareConcurrency,
      deviceMemoryGB: navigator.deviceMemory ?? null, gpuVisible: 'gpu' in navigator && navigator.gpu !== undefined,
      webgpuProbe: (() => { try { return typeof navigator.gpu?.requestAdapter === 'function'; } catch { return false; } })(),
    };

    const memorySamples = { beforeLoad: { wall: await memory(), heap: heap() } };
    const libs = await import(new URL('/wllama/index.min.js', location.origin).href);
    const libllamaVersion = libs.Wllama.getLibllamaVersion();
    const logs = [];
    const wllama = new libs.Wllama({ default: '/wasm/wllama.wasm' },
      { logger: Object.fromEntries(['log', 'debug', 'info', 'warn', 'error', 'trace']
        .map((level) => [level, (...args) => logs.push([level, args.map((arg) => typeof arg === 'string' ? arg : JSON.stringify(arg)).join(' ')])])) });
    const webgpuSupported = (() => { try { return wllama.isSupportWebGPU(); } catch { return null; } })();

    const progress = [];
    const progressCallback = ({ loaded, total }) => progress.push({ loaded, total, ms: Math.round(performance.now() - loadStarted) });
    const loadStarted = performance.now();
    await wllama.loadModelFromUrl('/model.gguf', { n_ctx: config.nCtx, n_threads: config.threads, n_gpu_layers: 0,
      seed: config.seed, log_level: 2, warmup: false, progressCallback });
    const loadMs = Math.round(performance.now() - loadStarted);
    memorySamples.afterLoad = { wall: await memory(), heap: heap() };

    let modelMetadata = null;
    try { modelMetadata = wllama.getModelMetadata(); } catch (error) { modelMetadata = { error: String(error) }; }
    const topology = { multithread: wllama.isMultithread(), numThreads: wllama.getNumThreads(),
      encoderDecoder: wllama.isEncoderDecoderArchitecture(), addBos: wllama.mustAddBosToken(), addEos: wllama.mustAddEosToken() };
    const chatTemplate = (() => { try { return wllama.getChatTemplate(); } catch { return null; } })();

    const runs = [];
    for (let index = 0; index < config.runs; index += 1) {
      const chunks = [];
      const started = performance.now();
      let firstTokenMs = null;
      await wllama.createChatCompletion({
        messages: [{ role: 'user', content: promptText }], stream: true,
        max_tokens: config.maxTokens, temperature: config.temperature, seed: config.seed,
        cache_prompt: false, return_progress: true,
        ...(config.chatKwargs ? { chat_template_kwargs: JSON.parse(config.chatKwargs) } : {}),
        onData: (chunk) => {
          const choice = chunk.choices?.[0];
          const text = choice?.delta?.content ?? '';
          if (text && firstTokenMs === null) firstTokenMs = Math.round(performance.now() - started);
          chunks.push({ ms: Math.round(performance.now() - started), text, finishReason: choice?.finish_reason ?? null,
            usage: chunk.usage ?? null, timings: chunk.timings ?? null });
        },
      });
      const wallMs = Math.round(performance.now() - started);
      const text = chunks.map((chunk) => chunk.text).join('');
      const usage = [...chunks].reverse().find((chunk) => chunk.usage)?.usage ?? null;
      const timings = [...chunks].reverse().find((chunk) => chunk.timings)?.timings ?? null;
      const finishReason = [...chunks].reverse().find((chunk) => chunk.finishReason)?.finishReason ?? null;
      const decoded = usage?.completion_tokens ?? null;
      runs.push({ index, firstTokenMs, wallMs, finishReason, usage, timings, text, chunkCount: chunks.length,
        promptTokens: timings?.prompt_n ?? null, prefillMs: timings ? +timings.prompt_ms.toFixed(0) : null,
        prefillTokensPerSec: timings ? +timings.prompt_per_second.toFixed(2) : null,
        predictedTokens: timings?.predicted_n ?? decoded, decodeMs: timings ? +timings.predicted_ms.toFixed(0) : null,
        decodeTokensPerSec: timings ? +timings.predicted_per_second.toFixed(2)
          : decoded && firstTokenMs !== null ? +(decoded / ((wallMs - firstTokenMs) / 1000)).toFixed(2) : null,
        chunks });
      memorySamples[`afterRun${index + 1}`] = { wall: await memory(), heap: heap() };
    }

    await wllama.exit();
    return { environment, libllamaVersion, webgpuSupported, topology, chatTemplate, modelMetadata,
      loadMs, progress, memorySamples, runs, logs: logs.slice(0, 400) };
  }, { config, promptText });

  Object.assign(report, result);
  report.status = 'COMPLETED';
  report.completedAt = new Date().toISOString();
} catch (error) {
  report.status = 'FAILED';
  report.error = { message: String(error), stack: error?.stack ?? null };
} finally {
  if (browser) await browser.close();
  await new Promise((done) => server.close(done));
  report.cleanup = { browserClosed: true, serverClosed: true };
  save();
  console.log(`${report.status} -> ${config.out}`);
}
