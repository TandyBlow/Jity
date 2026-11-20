// Narration-split rule-baseline runner: real Chromium (Edge headless) + the
// frozen NARRATION_SPLIT_SAMPLES through the four-stage pipeline
// (locate → select → organize → compose) — NO model calls at v0. Scoring is
// delegated to narration-split-eval.ts: sentence-scoped requiredFact checks
// (the frozen requirements, NOT free keyword presence) plus a residue-based
// fabrication check; the scorer's own counterexample self-test gates the
// report. Timings use 1 warmup + 5 measured repeats per sample (several
// stages are sub-millisecond — single-shot zeros are not statistics).
// Perspective and recent series narrations are threaded into the pipeline;
// report lands in artifacts/narration-split-baseline.json. Child servers are
// local and stopped in finally.
//
// Run: node scripts/run-narration-baseline.mjs [--channel msedge] [--out artifacts/narration-split-baseline.json]
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
const CONFIG = { channel: argValue('--channel', 'msedge'), repeats: 5 };
const OUTPUT = resolve(repoRoot, argValue('--out', 'artifacts/narration-split-baseline.json'));

const require = createRequire(resolve(frontendRoot, 'package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');

const server = await createServer({
  root: frontendRoot,
  configFile: false,
  logLevel: 'warn',
  server: { host: '127.0.0.1', port: 0, strictPort: false, hmr: false },
  plugins: [{
    name: 'narration-baseline-page',
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        if (req.url !== '/__ns') return next();
        res.setHeader('Content-Type', 'text/html');
        res.end('<!doctype html><title>Jity narration-split baseline</title>');
      });
    },
  }],
});
await server.listen();
const port = server.config.server.port ?? server.config.server.inferredPort;
const origin = `http://127.0.0.1:${port}`;
console.log(`[ns-baseline] vite at ${origin}; channel ${CONFIG.channel}`);

let browser;
try {
  browser = await chromium.launch({ headless: true, channel: CONFIG.channel });
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  page.on('console', (message) => {
    const text = message.text();
    // Forward ALL types: sample progress must stay visible — error-only
    // forwarding made runs indistinguishable from stalls.
    if (message.type() === 'error') console.error('[console.error]', text);
    else console.log(`[page:${message.type()}]`, text);
  });
  await page.goto(`${origin}/__ns`);

  const outcome = await page.evaluate(async (config) => {
    const { NARRATION_SPLIT_SAMPLES } = await import('/src/lib/world-engine/runtime/narration-split-samples.ts');
    const ns = await import('/src/lib/world-engine/runtime/narration-split.ts');
    const evalMod = await import('/src/lib/world-engine/runtime/narration-split-eval.ts');

    // The scorer must first survive its own counterexamples; otherwise the
    // whole report is void.
    const selfTest = evalMod.scorerSelfTest();
    for (const t of selfTest) console.log(`[ns-baseline] self-test ${t.pass ? 'PASS' : 'FAIL'}: ${t.name}`);
    if (selfTest.some((t) => !t.pass)) throw new Error('scorer self-test failed — report void');

    const median = (xs) => {
      const sorted = [...xs].sort((a, b) => a - b);
      return sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    };

    const rows = [];
    const seriesTexts = {};
    for (const sample of NARRATION_SPLIT_SAMPLES) {
      evalMod.assertFrozenRequirements(sample);
      const recent = sample.series ? (seriesTexts[sample.series] ?? []) : [];
      // Warmup (input gate + JIT/settle), then measured repeats.
      ns.runNarrationPipeline({ before: sample.before, delta: sample.delta, after: sample.after, timeAdvance: sample.timeAdvance, perspective: sample.perspective });
      const stageMs = { locate: [], select: [], organize: [], compose: [] };
      let text = '';
      for (let rep = 0; rep < config.repeats; rep++) {
        const t0 = performance.now();
        const located = ns.locateChanges(sample.before, sample.delta);
        const t1 = performance.now();
        const fragments = ns.selectContent(located, sample.before, sample.timeAdvance);
        const t2 = performance.now();
        const plan = ns.organizeExpression(fragments, { recentNarrations: recent, perspective: sample.perspective });
        const t3 = performance.now();
        const composed = ns.composeSentences(plan, sample.perspective);
        const t4 = performance.now();
        stageMs.locate.push(t1 - t0);
        stageMs.select.push(t2 - t1);
        stageMs.organize.push(t3 - t2);
        stageMs.compose.push(t4 - t3);
        text = composed;
      }
      const verdict = evalMod.evaluateNarration(sample, text, recent);
      if (sample.series) (seriesTexts[sample.series] ??= []).push(text);
      rows.push({
        id: sample.id, category: sample.category, series: sample.series ?? null,
        stageMs: Object.fromEntries(Object.entries(stageMs).map(([k, v]) => [k, median(v)])),
        text,
        factChecks: verdict.factChecks,
        omissions: verdict.omissions,
        fabricationFlags: verdict.fabricationFlags,
        repetition: verdict.repetition,
      });
      const facts = `${verdict.factChecks.filter((f) => f.pass).length}/${verdict.factChecks.length}`;
      console.log(`[ns-baseline] ${rows.length}/${NARRATION_SPLIT_SAMPLES.length} ${sample.id}: facts ${facts}, omissions ${verdict.omissions.length}, flags ${verdict.fabricationFlags.length}, ${median(rows[rows.length - 1].stageMs && [rows[rows.length - 1].stageMs.locate + rows[rows.length - 1].stageMs.select + rows[rows.length - 1].stageMs.organize + rows[rows.length - 1].stageMs.compose]) === 0 ? '~0' : 'ok'}`);
      console.log(`[ns-baseline]   text: ${text}`);
    }

    const allChecks = rows.flatMap((r) => r.factChecks);
    const omissions = rows.flatMap((r) => r.omissions.map((o) => `${r.id}: ${o}`));
    const stageSums = rows.map((r) => r.stageMs.locate + r.stageMs.select + r.stageMs.organize + r.stageMs.compose);
    const sorted = [...stageSums].sort((a, b) => a - b);
    const summary = {
      samples: rows.length,
      factCoverage: `${allChecks.filter((c) => c.pass).length}/${allChecks.length}`,
      omissions,
      fabricationFlags: rows.flatMap((r) => r.fabricationFlags.map((f) => `${r.id}: ${f}`)),
      repetitions: Object.fromEntries(rows.filter((r) => r.repetition != null).map((r) => [r.id, Math.round(r.repetition * 1000) / 1000])),
      totalMs: { medianBySample: stageSums.map((v) => Math.round(v * 1000) / 1000), p95: sorted[Math.min(sorted.length - 1, Math.floor(0.95 * sorted.length))] },
    };
    console.log(`[ns-baseline] facts ${summary.factCoverage}; omissions ${omissions.length}; flags ${summary.fabricationFlags.length}`);
    return { rows, summary, selfTest };
  }, CONFIG);

  const payload = {
    // Execution semantics only: the baseline ran end-to-end with a passing
    // scorer self-test. Quality verdicts live in summary/rows, never here.
    status: 'COMPLETED',
    layer: 'narration-split rule baseline (no model); scorer counterexample self-test gated; naturalness human-rated',
    recordedAt: new Date().toISOString(),
    config: CONFIG,
    browser: browser.version(),
    origin,
    scorerSelfTest: outcome.selfTest,
    summary: outcome.summary,
    rows: outcome.rows,
  };
  mkdirSync(dirname(OUTPUT), { recursive: true });
  writeFileSync(OUTPUT, JSON.stringify(payload, null, 2) + '\n');
  console.log(`[ns-baseline] done → ${OUTPUT}`);
} finally {
  if (browser) await browser.close();
  await server.close();
}
