/**
 * First real-model narration experiment (offline, read-only facts).
 *
 * One isolated world was created by scripts/narration-experiment-world.mjs with
 * real page commands. `reads.json` reconstructs each committed point from
 * world_points + world_state_checkpoints. This runner loads the frozen Qwen3
 * 0.6B GGUF in Edge/wllama, asks the model to narrate each point's fact packet
 * three times, and records: the exact prompt, raw text, timings/token counts,
 * the independent fact check, the alignment grader and the page's exact-clause
 * gate. It never writes the world and never changes the product default.
 *
 * Fallback cases are separate: timeout (real engine), empty output and a fact
 * check failure (injected), plus a semantically correct natural text that the
 * page's exact-clause gate rejects. Raw text is kept in every case.
 *
 *   node scripts/run-narration-model-r1.mjs \
 *     --reads ../artifacts/next-runs/narration-model-r1/reads.json \
 *     --out ../artifacts/next-runs/narration-model-r1/run.json --runs 3
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { cpus } from 'node:os';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from 'playwright';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const arg = (flag, fallback) => {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : fallback;
};
const readsPath = resolve(frontend, arg('--reads', '../artifacts/next-runs/narration-model-r1/reads.json'));
const outputPath = resolve(frontend, arg('--out', '../artifacts/next-runs/narration-model-r1/run.json'));
const runsPerPoint = Number(arg('--runs', '3'));
const onlyPoint = arg('--point', null);
const skipFallbacks = process.argv.includes('--skip-fallbacks');
const config = {
  model: arg('--model', '/models/Qwen3-0.6B-Q4_K_M.gguf'),
  contextSize: 4096,
  numThreads: Number(arg('--threads', '4')),
  channel: arg('--channel', 'msedge'),
  seed: Number(arg('--seed', '42')),
  temperature: Number(arg('--temperature', '0')),
  maxTokens: Number(arg('--max-tokens', '160')),
  cachePrompt: false,
  timeoutMs: Number(arg('--timeout-ms', '120000')),
  runsPerPoint,
};
const reads = JSON.parse(readFileSync(readsPath, 'utf8'));
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const sourceFiles = [
  'frontend/scripts/run-narration-model-r1.mjs',
  'frontend/scripts/narration-experiment-world.mjs',
  'frontend/src/lib/world-engine/runtime/narration-factcheck.ts',
  'frontend/src/lib/world-engine/runtime/narration-alignment.ts',
  'frontend/src/lib/world-engine/runtime/committed-narration.ts',
  'frontend/src/lib/world-engine/runtime/narration-eval.ts',
  'frontend/src/lib/world-engine/runtime/wllama-engine.ts',
  'frontend/src/lib/world-engine/runtime/engine.ts',
];
const modelPath = resolve(frontend, 'public/models/Qwen3-0.6B-Q4_K_M.gguf');
const report = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  config,
  input: { path: readsPath, sha256: sha(readFileSync(readsPath)), worldId: reads.worldId, points: reads.points.length },
  source: {
    head: execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    status: execFileSync('git', ['-C', root, 'status', '--short'], { encoding: 'utf8' }).trim(),
    sha256: Object.fromEntries(sourceFiles.map((file) => [file, sha(readFileSync(resolve(root, file)))])),
  },
  assets: {
    model: config.model,
    modelBytes: readFileSync(modelPath).length,
    modelSha256: sha(readFileSync(modelPath)),
    wllamaVersion: JSON.parse(readFileSync(resolve(frontend, 'node_modules/@wllama/wllama/package.json'), 'utf8')).version,
    bundleSha256: sha(readFileSync(resolve(frontend, 'public/wllama/index.min.js'))),
    wasmSha256: sha(readFileSync(resolve(frontend, 'public/wasm/wllama.wasm'))),
  },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length },
  setup: null,
  runs: [],
  fallbacks: null,
};
mkdirSync(dirname(outputPath), { recursive: true });
const save = () => writeFileSync(outputPath, JSON.stringify(report, null, 1) + '\n');
save();

const server = await createServer({
  root: frontend,
  configFile: false,
  logLevel: 'warn',
  cacheDir: '../.local/narration-model-r1-vite',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{
    name: 'narration-model-experiment',
    configureServer(vite) {
      vite.middlewares.use((req, res, next) => {
        res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
        res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
        if (req.url !== '/__narration-model') return next();
        res.setHeader('Content-Type', 'text/html');
        res.end('<!doctype html><title>Narration model experiment</title>');
      });
    },
  }],
});
let browser;
try {
  await server.listen();
  report.serverPort = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.goto(`http://127.0.0.1:${report.serverPort}/__narration-model`);
  report.browserVersion = await page.evaluate(() => navigator.userAgent);
  const setup = await page.evaluate(async ({ reads, config }) => {
    if (!crossOriginIsolated) throw new Error('model experiment requires cross-origin isolation');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { projectCommittedNarration, renderCommittedNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
    const { buildNaturalPrompt } = await import('/src/lib/world-engine/runtime/narration-eval.ts');
    const engine = new WllamaInferenceEngine({ modelUrl: config.model, contextSize: config.contextSize, numThreads: config.numThreads });
    const started = performance.now();
    await engine.load();
    const loadMs = performance.now() - started;
    const points = reads.points.map((point) => {
      const packet = projectCommittedNarration(point.after, point.before);
      const time = point.after.timeAdvance?.duration ?? null;
      return { label: point.label, pointId: point.pointId, sequence: point.sequence, packet, time,
        template: renderCommittedNarration(packet, { time }) };
    });
    for (const [index, point] of points.entries()) {
      const sample = {
        id: point.label, category: 'experiment', note: point.label, packet: point.packet, time: point.time,
        locations: reads.locations, roster: reads.roster, previousText: index ? points[index - 1].template : null,
        forbidden: [],
      };
      point.previousText = sample.previousText;
      point.prompt = buildNaturalPrompt(sample);
      point.facts = point.packet.facts.map((fact) => ({ id: fact.id, kind: fact.kind, name: fact.name }));
    }
    window.__experiment = { engine, points, reads, config };
    return {
      loadMs, topology: engine.diagnostics && engine.diagnostics,
      points: points.map((point) => ({ label: point.label, pointId: point.pointId, sequence: point.sequence,
        facts: point.facts, time: point.time, prompt: point.prompt, template: point.template,
        promptChars: point.prompt.length })),
    };
  }, { reads, config });
  report.setup = setup;
  assert.deepEqual(setup.topology, { multithread: true, numThreads: config.numThreads });
  save();

  const indexes = reads.points.map((_, index) => index)
    .filter((index) => onlyPoint === null || reads.points[index].label === onlyPoint || reads.points[index].pointId === onlyPoint);
  for (const index of indexes) {
    for (let run = 1; run <= runsPerPoint; run += 1) {
      console.log(`[model] ${reads.points[index].label} run ${run}/${runsPerPoint}`);
      const row = await page.evaluate(async ({ index, run, config }) => {
        const { engine, points, reads } = window.__experiment;
        const point = points[index];
        const { checkFacts } = await import('/src/lib/world-engine/runtime/narration-factcheck.ts');
        const { alignNarration } = await import('/src/lib/world-engine/runtime/narration-alignment.ts');
        const { selectFactNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
        let text = '', ms = 0, completion = null, error = null;
        const started = performance.now();
        try {
          text = await engine.complete(point.prompt, {
            maxTokens: config.maxTokens, temperature: config.temperature, seed: config.seed,
            cachePrompt: config.cachePrompt, timeoutMs: config.timeoutMs,
            onCompletion: (evidence) => { completion = evidence; },
          });
        } catch (cause) {
          error = {
            name: cause?.name ?? 'Error', message: String(cause?.message ?? cause),
            finishReason: cause?.completion?.finishReason ?? null,
            partial: cause?.completion?.raw ?? null,
          };
          text = cause?.completion?.raw ?? '';
        }
        ms = performance.now() - started;
        const factsCheck = checkFacts({ facts: point.packet.facts, time: point.time,
          locations: reads.locations, roster: reads.roster }, text);
        const alignment = alignNarration(point.packet, text, { time: point.time, locations: reads.locations,
          roster: reads.roster, previousText: point.previousText, requireTime: point.time !== null });
        const pageGate = selectFactNarration(point.packet, text, { time: point.time });
        return {
          pointId: point.pointId, label: point.label, sequence: point.sequence, run,
          text, ms, completion, error,
          factsCheck, alignment,
          pageGate: { accepted: pageGate.accepted, reason: pageGate.reason, text: pageGate.text },
        };
      }, { index, run, config });
      report.runs.push(row);
      save();
      console.log(`[model] ${row.label} run ${row.run}: chars=${row.text.length} ms=${Math.round(row.ms)} ` +
        `factsOk=${row.factsCheck.ok} alignOk=${row.alignment.ok} pageOk=${row.pageGate.accepted}` +
        (row.error ? ` error=${row.error.name}` : ''));
    }
  }

  // Fallback entry: same checks, but the caller gets the template when the model
  // fails. Every raw output is kept next to the fallback decision.
  if (!skipFallbacks) {
  const fallbackIndex = reads.points.findIndex((point) => point.label === 'task-personality-sanity');
  report.fallbacks = await page.evaluate(async ({ index, config }) => {
    const { engine, points, reads } = window.__experiment;
    const point = points[index];
    const { checkFacts } = await import('/src/lib/world-engine/runtime/narration-factcheck.ts');
    const { alignNarration } = await import('/src/lib/world-engine/runtime/narration-alignment.ts');
    const { selectFactNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
    const entry = async (generate) => {
      let raw = '';
      try {
        const result = await generate();
        raw = result?.text ?? '';
        if (!raw.trim()) return { adopted: false, reason: 'empty_output', raw, text: point.template };
        const factsCheck = checkFacts({ facts: point.packet.facts, time: point.time,
          locations: reads.locations, roster: reads.roster }, raw);
        const alignment = alignNarration(point.packet, raw, { time: point.time, locations: reads.locations,
          roster: reads.roster, previousText: point.previousText, requireTime: point.time !== null });
        if (!factsCheck.ok || !alignment.ok) {
          return { adopted: false, reason: 'fact_check_failed', raw, factsCheck, alignment, text: point.template };
        }
        return { adopted: true, reason: null, raw, factsCheck, alignment, text: raw };
      } catch (cause) {
        return { adopted: false, reason: `generation_error: ${cause?.name ?? 'Error'}: ${cause?.message ?? cause}`,
          raw: cause?.completion?.raw ?? '', partial: cause?.completion ?? null, text: point.template };
      }
    };
    const timeout = await entry(async () => ({ text: await engine.complete(point.prompt, {
      maxTokens: 8, temperature: 0, seed: 42, cachePrompt: false, timeoutMs: 1 }) }));
    const empty = await entry(async () => ({ text: '' }));
    const wrong = await entry(async () => ({ text: '林川完成了任务「完成压力试验」，精神值从10变为8。' }));
    const naturalText = '约一秒过去了。林川留在走廊，精神值仍是10。周宁还在走廊，完成了任务「完成压力试验」并变得「经历压力试验后更谨慎」，精神值从10降到8。';
    const natural = await entry(async () => ({ text: naturalText }));
    const naturalPageGate = selectFactNarration(point.packet, naturalText, { time: point.time });
    return { pointId: point.pointId, label: point.label, template: point.template, timeout, empty, wrong, natural,
      naturalPageGate: { accepted: naturalPageGate.accepted, reason: naturalPageGate.reason, text: naturalPageGate.text } };
  }, { index: fallbackIndex, config });
  save();
  }

  const completed = report.runs.filter((row) => !row.error && row.text.trim());
  const times = completed.map((row) => row.ms).sort((a, b) => a - b);
  const promptTokens = report.runs.map((row) => row.completion?.timings?.prompt_n).filter((value) => typeof value === 'number');
  const completionTokens = report.runs.map((row) => row.completion?.timings?.predicted_n).filter((value) => typeof value === 'number');
  const distinct = [...new Set(report.runs.map((row) => row.text))];
  report.summary = {
    points: report.setup.points.length,
    generations: report.runs.length,
    distinctOutputs: distinct.length,
    errors: report.runs.filter((row) => row.error).length,
    empty: report.runs.filter((row) => !row.text.trim()).length,
    factCheckPass: report.runs.filter((row) => row.factsCheck.ok).length,
    factCheckRate: report.runs.length ? report.runs.filter((row) => row.factsCheck.ok).length / report.runs.length : null,
    alignerPass: report.runs.filter((row) => row.alignment.ok).length,
    alignerRate: report.runs.length ? report.runs.filter((row) => row.alignment.ok).length / report.runs.length : null,
    pageGatePass: report.runs.filter((row) => row.pageGate.accepted).length,
    pageGateRate: report.runs.length ? report.runs.filter((row) => row.pageGate.accepted).length / report.runs.length : null,
    factProblemKinds: report.runs.flatMap((row) => row.factsCheck.problems.map((problem) => problem.kind))
      .reduce((counts, kind) => ({ ...counts, [kind]: (counts[kind] ?? 0) + 1 }), {}),
    alignerViolationKinds: report.runs.flatMap((row) => row.alignment.violations.map((violation) => violation.kind))
      .reduce((counts, kind) => ({ ...counts, [kind]: (counts[kind] ?? 0) + 1 }), {}),
    calls: times.length,
    meanMs: times.length ? Math.round(times.reduce((a, b) => a + b, 0) / times.length) : null,
    p50Ms: times.length ? Math.round(times[Math.floor(times.length / 2)]) : null,
    minMs: times[0] ?? null, maxMs: times[times.length - 1] ?? null,
    promptTokensTotal: promptTokens.reduce((a, b) => a + b, 0),
    completionTokensTotal: completionTokens.reduce((a, b) => a + b, 0),
    promptTokensMean: promptTokens.length ? Math.round(promptTokens.reduce((a, b) => a + b, 0) / promptTokens.length) : null,
    completionTokensMean: completionTokens.length ? Math.round(completionTokens.reduce((a, b) => a + b, 0) / completionTokens.length) : null,
    tokenCalls: promptTokens.length,
    distinctTexts: distinct,
  };
  report.status = 'COMPLETED';
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
  report.cleanup = { browserClosed: true, serverClosed: true };
  save();
}
