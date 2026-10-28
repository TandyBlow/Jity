// Real-model short run for the second narration batch (state alignment and
// natural expression). Same on-device stack as the rule-facts batch:
// real Edge headless, wllama with the frozen Qwen3-0.6B Q4_K_M asset,
// COOP/COEP, temperature 0 and a fixed seed so a rerun is comparable.
//
// Per sample and per attempt the script records the exact prompt, the raw
// completion, timings and the grader verdict. Adoption / regeneration /
// fallback are produced by the harness (runNarrationEvaluation), not counted
// here, so the archive and the page test share one implementation.
//
//   node scripts/run-narration-eval.mjs --out ../artifacts/narration-eval/run.json
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { cpus } from 'node:os';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const hasFlag = (flag) => process.argv.includes(flag);
const config = { model: '/models/Qwen3-0.6B-Q4_K_M.gguf', contextSize: 4096, numThreads: 4,
  channel: 'msedge', seed: 42, temperature: 0, maxTokens: 160, cachePrompt: false, timeoutMs: 120_000,
  requireTime: hasFlag('--require-time'), holdout: hasFlag('--holdout') };
const output = resolve(frontend, option('--out', '../.local/narration-eval.json'));
const files = ['frontend/scripts/run-narration-eval.mjs',
  ...['narration-alignment', 'narration-eval', 'narration-eval-samples', 'narration-eval-holdout', 'committed-narration', 'wllama-engine', 'engine']
    .map((name) => `frontend/src/lib/world-engine/runtime/${name}.ts`)];
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const git = (...args) => execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root, ...args], { encoding: 'utf8' }).trim();

const report = { status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), config,
  source: { head: git('rev-parse', 'HEAD'), status: git('status', '--short'),
    sha256: Object.fromEntries(files.map((file) => [file, sha(readFileSync(resolve(root, file)))])),
    contractDigest: JSON.parse(readFileSync(resolve(root, 'frontend/src/lib/world-engine/contract-digest.json'), 'utf8')) },
  assets: { modelSha256: sha(readFileSync(resolve(frontend, 'public/models/Qwen3-0.6B-Q4_K_M.gguf'))),
    bundleSha256: sha(readFileSync(resolve(frontend, 'public/wllama/index.min.js'))),
    wasmSha256: sha(readFileSync(resolve(frontend, 'public/wasm/wllama.wasm'))),
    packageVersion: JSON.parse(readFileSync(resolve(frontend, 'node_modules/@wllama/wllama/package.json'))).version },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length }, runs: [] };
const save = () => { mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();

const server = await createServer({ root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/narration-eval-vite',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{ name: 'narration-eval', configureServer(vite) { vite.middlewares.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    if (req.url !== '/__narration') return next();
    res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>Narration evaluation</title>');
  }); } }] });
let browser;
try {
  await server.listen();
  report.serverPort = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.goto(`http://127.0.0.1:${report.serverPort}/__narration`);
  const loaded = await page.evaluate(async (config) => {
    if (!crossOriginIsolated) throw new Error('narration eval requires cross-origin isolation');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const engine = new WllamaInferenceEngine({ modelUrl: config.model, contextSize: config.contextSize, numThreads: config.numThreads });
    const started = performance.now(); await engine.load();
    window.__narration = { engine };
    return { loadMs: performance.now() - started, topology: engine.diagnostics };
  }, config);
  report.loadMs = loaded.loadMs;
  report.topology = loaded.topology;
  assert.deepEqual(loaded.topology, { multithread: true, numThreads: 4 });
  save();

  for (const entry of ['nv-move-1', 'nv-task-pers-sanity-1', 'nv-multi-1', 'nv-task-only-1', 'nv-refused-1',
    'nv-empty-1', 'nv-cont-1', 'nv-cont-2', 'nv-cont-3', 'nv-multi-opposite-1',
    ...(config.holdout ? ['hv-move-1', 'hv-sanity-1', 'hv-task-pers-1', 'hv-refused-1', 'hv-empty-1', 'hv-multi-opposite-1'] : [])]) {
    if (report.runs.some((run) => run.sampleId === entry)) continue;
    console.log(`[narration] ${entry}`);
    const row = await page.evaluate(async ({ entry, config }) => {
      const { runNarrationEvaluation } = await import('/src/lib/world-engine/runtime/narration-eval.ts');
      const { NARRATION_EVAL_SAMPLES } = await import('/src/lib/world-engine/runtime/narration-eval-samples.ts');
      const { NARRATION_EVAL_HOLDOUT_SAMPLES } = await import('/src/lib/world-engine/runtime/narration-eval-holdout.ts');
      const engine = window.__narration.engine;
      const sample = [...NARRATION_EVAL_SAMPLES, ...NARRATION_EVAL_HOLDOUT_SAMPLES].find((item) => item.id === entry);
      const started = performance.now();
      const report = await runNarrationEvaluation({ samples: [sample], maxAttempts: 2, requireTime: config.requireTime, generator: {
        async generate(prompt, _sample, attempt) {
          let completion = null;
          const callStarted = performance.now();
          const text = await engine.complete(prompt, { maxTokens: config.maxTokens, temperature: config.temperature,
            seed: config.seed, cachePrompt: config.cachePrompt, timeoutMs: config.timeoutMs,
            onCompletion: (evidence) => { completion = evidence; } });
          return { text, ms: performance.now() - callStarted, completion };
        },
      } });
      const run = report.samples[0];
      return { ...run, wallMs: performance.now() - started,
        attempts: run.natural.attempts.map((attempt) => ({ ...attempt, completion: attempt.completion ?? null })) };
    }, { entry, config });
    report.runs.push(row);
    report.status = 'IN_PROGRESS'; save();
    console.log(`[narration] ${entry}: adopted=${row.natural.adopted} attempts=${row.natural.attempts.length} ` +
      `violations=${row.natural.final.violations.length} omissions=${row.natural.final.omissions.length}`);
  }
  // Cross-sample aggregation, computed here so the archive never relies on
  // hand-derived headline numbers (the 2026-10-28 review found one such error).
  const calls = report.runs.flatMap((run) => run.natural.attempts.map((attempt) => attempt.ms)).sort((a, b) => a - b);
  const promptTokens = report.runs.flatMap((run) => run.natural.attempts.map((attempt) => attempt.completion?.timings?.prompt_n))
    .filter((tokens) => typeof tokens === 'number').sort((a, b) => a - b);
  report.summary = {
    samples: report.runs.length,
    requireTime: config.requireTime,
    holdout: config.holdout,
    templateAccepted: report.runs.filter((run) => run.template.verdict.ok).length,
    mechanicalAccepted: report.runs.filter((run) => run.mechanical.verdict.ok).length,
    naturalAdopted: report.runs.filter((run) => run.natural.adopted).length,
    naturalFirstAttempt: report.runs.filter((run) => run.natural.attempts[0]?.verdict.ok).length,
    regenerated: report.runs.filter((run) => run.natural.attempts.length > 1).length,
    fellBack: report.runs.filter((run) => run.natural.fellBack).length,
    timeNarratedTemplate: report.runs.filter((run) => run.template.verdict.timeExpressed === true).length,
    timeNarratedMechanical: report.runs.filter((run) => run.mechanical.verdict.timeExpressed === true).length,
    timeNarratedNatural: report.runs.filter((run) => run.natural.final.timeExpressed === true).length,
    omittedFacts: report.runs.reduce((sum, run) => sum + run.natural.final.omissions.length, 0),
    violations: report.runs.reduce((sum, run) => sum + run.natural.final.violations.length, 0),
    unverifiedSentences: report.runs.reduce((sum, run) => sum + run.natural.final.unverified.length, 0),
    calls: calls.length,
    meanMs: calls.length ? Math.round(calls.reduce((a, b) => a + b, 0) / calls.length) : null,
    p50Ms: calls.length ? Math.round(calls[Math.floor(calls.length / 2)]) : null,
    minMs: calls[0] ?? null, maxMs: calls[calls.length - 1] ?? null,
    medianPromptTokens: promptTokens.length ? promptTokens[Math.floor(promptTokens.length / 2)] : null,
  };
  report.status = 'COMPLETED'; report.completedAt = new Date().toISOString(); save();
} catch (error) {
  report.status = 'INTERRUPTED'; report.error = String(error); save(); throw error;
} finally {
  if (browser) await browser.close();
  await server.close(); report.cleanup = { browserClosed: true, serverClosed: true }; save();
}
