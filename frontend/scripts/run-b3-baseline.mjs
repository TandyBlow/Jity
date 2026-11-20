// B3 on-device baseline runner: real Chromium + real wllama + the frozen
// B3_SAMPLES, through the SAME eval harness the unit tests exercise
// (encode → serial queue → engine → structured decode → floor judges).
// Model, context, sampling and samples are FIXED baseline configuration;
// raw outputs land in the report so prompt iteration has evidence.
// Child servers are local and stopped in finally.
//
// Run: node scripts/run-b3-baseline.mjs [--model /models/X.gguf] [--channel msedge] [--out artifacts/b3-baseline.json]
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(frontendRoot, '..');

const args = process.argv.slice(2);
const argValue = (name, fallback) => {
  const index = args.indexOf(name);
  return index !== -1 && args[index + 1] !== undefined ? args[index + 1] : fallback;
};
const CONFIG = {
  model: argValue('--model', '/models/Qwen3-0.6B-Q4_K_M.gguf'),
  contextSize: 4096,
  maxTokens: 1024,
  temperature: 0,
  seed: 42,
  channel: argValue('--channel', 'msedge'),
};
const OUTPUT = resolve(repoRoot, argValue('--out', 'artifacts/b3-baseline.json'));

const require = createRequire(resolve(frontendRoot, 'package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');

const server = await createServer({
  root: frontendRoot,
  configFile: false,
  logLevel: 'warn',
  server: { host: '127.0.0.1', port: 0, strictPort: false, hmr: false },
  // The frontend is a Next project — no Vite index.html exists. Serve a
  // minimal harness page at /__b3 (the H1 pattern); Vite still transforms
  // the /src/*.ts imports it pulls in.
  plugins: [{
    name: 'b3-baseline-page',
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        if (req.url !== '/__b3') return next();
        res.setHeader('Content-Type', 'text/html');
        res.end('<!doctype html><title>Jity B3 baseline</title>');
      });
    },
  }],
});
await server.listen();
const port = server.config.server.port ?? server.config.server.inferredPort;
const origin = `http://127.0.0.1:${port}`;
console.log(`[b3-baseline] vite at ${origin}; model ${CONFIG.model}; channel ${CONFIG.channel}`);

let browser;
try {
  browser = await chromium.launch({ headless: true, channel: CONFIG.channel });
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  page.on('console', (message) => {
    const text = message.text();
    // Forward ALL types: sample progress arrives via console.log from
    // onSample — error-only forwarding made a slow run indistinguishable
    // from a stalled one.
    if (message.type() === 'error') console.error('[console.error]', text);
    else console.log(`[page:${message.type()}]`, text);
  });
  // Checkpoint every sample: a killed long run keeps its paid evidence
  // (per-sample rows with raw text), not just the final report.
  const partialRows = [];
  await page.exposeFunction('checkpointRow', (rowJson) => {
    partialRows.push(JSON.parse(rowJson));
    mkdirSync(dirname(OUTPUT), { recursive: true });
    writeFileSync(OUTPUT, JSON.stringify({ status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), config: CONFIG, rows: partialRows }, null, 2) + '\n');
  });
  await page.goto(`${origin}/__b3`);

  const started = Date.now();
  const outcome = await page.evaluate(async ({ config }) => {
    const { B3_SAMPLES } = await import('/src/lib/world-engine/runtime/b3-samples.ts');
    const { runB3Evaluation, formatB3Summary } = await import('/src/lib/world-engine/runtime/b3-eval.ts');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { createWllama } = await import('/src/lib/benchmark/wllama-loader.ts');
    const engine = new WllamaInferenceEngine(
      { modelUrl: config.model, contextSize: config.contextSize },
      createWllama,
    );
    const report = await runB3Evaluation(engine, B3_SAMPLES, {
      portOptions: { maxTokens: config.maxTokens, temperature: config.temperature, seed: config.seed },
      onSample: (row, index, total) => {
        console.log(`[b3-baseline] sample ${index + 1}/${total} ${row.id}: ${row.failure ?? 'ok'}${row.timing ? ` (${Math.round(row.timing.runMs)}ms)` : ''}`);
        window.checkpointRow(JSON.stringify(row));
      },
    });
    return {
      engineInfo: { ...engine.info },
      summary: formatB3Summary(report),
      report,
    };
  }, { config: CONFIG });

  const payload = {
    // Execution semantics only: the eval ran end-to-end. Quality verdicts
    // live in the report's per-task rates, never in this field.
    status: 'COMPLETED',
    layer: 'local real-browser/wllama baseline; review pending',
    recordedAt: new Date().toISOString(),
    wallMs: Date.now() - started,
    config: CONFIG,
    browser: browser.version(),
    origin,
    engineInfo: outcome.engineInfo,
    summary: outcome.summary,
    report: outcome.report,
  };
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, JSON.stringify(payload, null, 2) + '\n');
  console.log(`[b3-baseline] ${outcome.summary}`);
  console.log(`[b3-baseline] wall ${Math.round(payload.wallMs / 1000)}s → ${OUTPUT}`);
} finally {
  if (browser) await browser.close();
  await server.close();
}
