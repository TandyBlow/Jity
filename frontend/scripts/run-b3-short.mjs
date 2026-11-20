// Six sequential real-browser probes through RuntimeWorldModelPort.
// Every partial output is checkpointed; a per-call abort and a browser
// watchdog bound the paid work. No full B3 run or backend is started.
import { createServer } from 'vite';
import { chromium } from '@playwright/test';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const argument = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index < 0 ? fallback : process.argv[index + 1];
};
const config = {
  model: argument('--model', '/models/Qwen3-0.6B-Q4_K_M.gguf'),
  channel: argument('--channel', 'msedge'), contextSize: 4096,
  numThreads: 4, temperature: 0, seed: 42, timeoutMs: 90_000,
  taskMaxTokens: { action: 80, updates: 192, narration: 128 },
};
const output = resolve(root, argument('--out', 'artifacts/b3-short/qwen3-0.6b.json'));
const ids = argument('--samples', '').split(',').filter(Boolean);
const sourceFiles = ['frontend/scripts/run-b3-short.mjs', ...['engine', 'wllama-engine', 'model-port', 'prompts',
  'structured-output', 'output-schema', 'b3-short-samples'].map((file) => `frontend/src/lib/world-engine/runtime/${file}.ts`)];
const hash = (file) => createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex');
const git = (...args) => execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root, ...args], { encoding: 'utf8' }).trim();
const report = { status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), config,
  source: { head: git('rev-parse', 'HEAD'), status: git('status', '--short'), sha256: Object.fromEntries(sourceFiles.map((file) => [file, hash(file)])) },
  assets: { modelSha256: hash(`frontend/public${config.model}`),
    bundleSha256: hash('frontend/public/wllama/index.min.js'), wasmSha256: hash('frontend/public/wasm/wllama.wasm'),
    packageVersion: JSON.parse(readFileSync(resolve(frontend, 'node_modules/@wllama/wllama/package.json'))).version },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length }, rows: [] };
const save = () => { mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();
const server = await createServer({ root: frontend, configFile: false, logLevel: 'warn',
  cacheDir: '../.local/b3-short-vite',
  server: { host: '127.0.0.1', port: 0, hmr: false, headers: {
    'Cross-Origin-Opener-Policy': 'same-origin', 'Cross-Origin-Embedder-Policy': 'require-corp',
  } },
  plugins: [{ name: 'b3-short-page', configureServer(vite) {
    vite.middlewares.use((req, res, next) => {
      // configureServer runs before Vite's own header middleware, so the
      // custom HTML response must set these itself as well.
      res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
      res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
      if (req.url !== '/__b3_short') return next();
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><title>B3 three-task short test</title>');
    });
  } }],
});
let browser;
let activeId = null;
try {
  await server.listen();
  const address = server.httpServer.address();
  const origin = `http://127.0.0.1:${address.port}`;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') console.error('[browser]', message.text());
  });
  let lastProgressSave = 0;
  await page.exposeFunction('saveB3Progress', (progress) => {
    if (progress.id !== activeId) return;
    if (Date.now() - lastProgressSave < 1500) return;
    lastProgressSave = Date.now();
    report.inFlight = progress;
    save();
  });
  await page.goto(`${origin}/__b3_short`);
  const setup = await page.evaluate(async ({ config, ids }) => {
    if (!crossOriginIsolated) throw new Error('Short-test page must be cross-origin isolated before loading the model');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { RuntimeWorldModelPort } = await import('/src/lib/world-engine/runtime/model-port.ts');
    const { B3_SHORT_SAMPLES, judgeShortSample } = await import('/src/lib/world-engine/runtime/b3-short-samples.ts');
    const { buildTaskPrompt } = await import('/src/lib/world-engine/runtime/prompts.ts');
    const { getLibllamaVersion } = await import('/src/lib/benchmark/wllama-loader.ts');
    const engine = new WllamaInferenceEngine({ modelUrl: config.model, contextSize: config.contextSize, numThreads: config.numThreads });
    const started = performance.now();
    await engine.load();
    const port = new RuntimeWorldModelPort(engine, undefined, { ...config,
      onProgress: (_task, _key, progress) => { window.saveB3Progress({ id: window.__b3.id, ...progress }); },
      onCompletion: (_task, _key, evidence) => { window.__b3.evidence = evidence; },
    });
    const samples = ids.length ? B3_SHORT_SAMPLES.filter((sample) => ids.includes(sample.id)) : B3_SHORT_SAMPLES;
    if (ids.some((id) => !samples.some((sample) => sample.id === id))) throw new Error('Unknown sample ID');
    window.__b3 = { engine, port, samples, judgeShortSample, buildTaskPrompt, evidence: null, id: null };
    return { loadMs: performance.now() - started, topology: engine.diagnostics,
      crossOriginIsolated, libllama: getLibllamaVersion(), samples: samples.map((sample) => sample.id) };
  }, { config, ids });
  Object.assign(report, setup);
  save();
  console.log(`[b3-short] loaded ${config.model}: ${JSON.stringify(setup.topology)}; ${setup.samples.length} samples`);
  for (const id of setup.samples) {
    activeId = id;
    report.inFlight = { id, raw: '', elapsedMs: 0 };
    lastProgressSave = 0;
    save();
    console.log(`[b3-short] start ${id}`);
    let watchdog;
    const row = await Promise.race([
      page.evaluate(async (id) => {
        const runtime = window.__b3;
        const sample = runtime.samples.find((sample) => sample.id === id);
        runtime.id = id;
        runtime.evidence = null;
        const start = performance.now();
        const base = { ...sample, prompt: runtime.buildTaskPrompt(sample.task, sample.key, sample.input) };
        try {
          const generation = await runtime.port.generateDetailed(sample.task, sample.key, sample.input);
          const semanticNote = runtime.judgeShortSample(id, generation.value);
          return { ...base, value: generation.value, timing: generation.timing, wallMs: performance.now() - start,
            completion: runtime.evidence, failure: semanticNote ? 'semantic' : null, semanticNote };
        } catch (error) {
          return { ...base, failure: error.name === 'StructuredOutputError' ? 'structure' : 'engine',
            error: `${error.name}: ${error.message}`, timing: error.timing ?? null, wallMs: performance.now() - start,
            completion: runtime.evidence, raw: error.raw ?? runtime.evidence?.raw ?? null };
        }
      }, id),
      new Promise((_resolve, reject) => { watchdog = setTimeout(() => reject(new Error(`Browser watchdog exceeded for ${id}`)), config.timeoutMs + 20_000); }),
    ]).finally(() => clearTimeout(watchdog));
    activeId = null;
    delete report.inFlight;
    report.rows.push(row);
    save();
    console.log(`[b3-short] ${id}: ${row.failure ?? 'ok'}, ${Math.round(row.wallMs)}ms, finish=${row.completion?.finishReason}`);
  }
  report.status = 'COMPLETED'; // execution, not a quality PASS
  report.completedAt = new Date().toISOString();
  save();
} catch (error) {
  report.status = 'INTERRUPTED';
  report.error = String(error);
  save();
  throw error;
} finally {
  if (browser) await browser.close();
  await server.close();
}
console.log(`[b3-short] saved ${output}`);
