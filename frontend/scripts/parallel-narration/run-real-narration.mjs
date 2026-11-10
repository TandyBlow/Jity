// Real browser-model run for the committed-narration strategy.
//
// This is NOT a full baseline: it runs three representative committed points
// through the actual page path (headless Edge + wllama + a real GGUF) and
// stores the exact prompt, raw completion, per-attempt verdict, retry guidance
// and wall time. The strategy code is the same module the page would import;
// the fact input is produced by the existing projectors/serializer, not by a
// second implementation.
//
// Local inference is an exclusive resource: acquire the lease first and
// release it afterwards (see .local/parallel-local-game/common.md).
//
//   node scripts/parallel-narration/run-real-narration.mjs \
//     [--model /models/qwen25-0.5b-narration-Q4_K_M.gguf] \
//     [--out ../../results/02-narration/real-model-evidence.json]
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { createServer } from 'vite';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');

const frontend = fileURLToPath(new URL('../..', import.meta.url));
const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const config = {
  // Git Bash on Windows rewrites a `/models/...` argv into a Windows path.
  // The browser needs a fetchable URL path, so normalize to /models/<name>.
  model: (() => {
    const value = option('--model', '/models/qwen25-0.5b-narration-Q4_K_M.gguf');
    return value.startsWith('/models/') ? value : `/models/${basename(value)}`;
  })(),
  out: resolve(frontend, option('--out', '../../../results/02-narration/real-model-evidence.json')),
  modelDir: process.env.MODEL_DIR ?? 'D:/others/Jity/.local/world-narration-worktree/frontend/public/models',
  channel: option('--channel', 'msedge'),
  numThreads: Number(option('--threads', '4')),
  maxTokens: Number(option('--max-tokens', '300')),
  maxAttempts: Number(option('--max-attempts', '2')),
  minChars: Number(option('--min-chars', '80')),
  instruction: option('--instruction', ''),
};
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const modelFile = resolve(config.modelDir, basename(config.model));
const evidence = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  strategy: null,
  config: {
    model: config.model, modelSha256: existsSync(modelFile) ? sha256(readFileSync(modelFile)) : null,
    modelBytes: existsSync(modelFile) ? statSync(modelFile).size : null,
    threads: config.numThreads, maxTokens: config.maxTokens, maxAttempts: config.maxAttempts, minChars: config.minChars,
    instruction: config.instruction || null,
    temperature: 0.7, retryTemperature: 0.5, seed: 42,
  },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length, platform: process.platform },
  git: (() => {
    try {
      const { execFileSync } = require('node:child_process');
      return execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
    } catch { return null; }
  })(),
  runs: [],
};
const save = () => {
  mkdirSync(dirname(config.out), { recursive: true });
  const temp = `${config.out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(evidence, null, 2)}\n`);
  renameSync(temp, config.out);
};

/** Serve wllama's wasm/bundle and the user-provided GGUF without copying
 * either into the repository. */
function assetMiddleware(vite) {
  const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
  const map = {
    '/wllama/index.min.js': { file: resolve(wllamaRoot, 'index.min.js'), type: 'application/javascript' },
    '/wasm/wllama.wasm': { file: resolve(wllamaRoot, 'wasm/wllama.wasm'), type: 'application/wasm' },
  };
  vite.middlewares.use((request, response, next) => {
    response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    const url = (request.url ?? '').split('?')[0];
    if (url === '/__narration') {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><title>narration strategy</title>');
      return;
    }
    if (url.startsWith('/models/')) {
      const file = resolve(config.modelDir, basename(url));
      if (!existsSync(file)) { response.statusCode = 404; response.end('missing model'); return; }
      response.setHeader('Content-Type', 'application/octet-stream');
      response.setHeader('Content-Length', statSync(file).size);
      createReadStream(file).pipe(response);
      return;
    }
    const asset = map[url];
    if (asset) {
      if (!existsSync(asset.file)) { response.statusCode = 404; response.end('missing asset'); return; }
      response.setHeader('Content-Type', asset.type);
      createReadStream(asset.file).pipe(response);
      return;
    }
    next();
  });
}

const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{ name: 'narration-strategy-assets', configureServer: assetMiddleware }],
});
let browser;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  evidence.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.goto(`http://127.0.0.1:${port}/__narration`);

  const result = await page.evaluate(async (config) => {
    if (!crossOriginIsolated) throw new Error('real narration run requires cross-origin isolation');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { generateCommittedNarration } = await import('/src/lib/world-engine/local/narration-generation/index.ts');
    const { projectCommittedNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
    const { legacyNarrationInput } = await import('/src/lib/world-engine/local/prompt.ts');
    const { SHORT_STATE } = await import('/src/lib/world-engine/runtime/b3-short-samples.ts');

    const engine = new WllamaInferenceEngine({
      modelUrl: config.model, contextSize: 4096, numThreads: config.numThreads,
    });
    const loadStarted = performance.now();
    await engine.load();
    const loadMs = performance.now() - loadStarted;

    const clone = (value) => JSON.parse(JSON.stringify(value));
    const position = (containerId) => ({ containerId, slotId: null, relativeTo: null });
    const rootState = clone(SHORT_STATE);
    const rootRead = {
      pointId: 'root', previousPointId: null, version: 0, stateDigest: 'root',
      state: rootState, timeAdvance: null, entityDeltas: {},
    };
    const movedState = clone(rootState);
    movedState.characters.person_a.position = position('hall');
    movedState.time = { ...movedState.time, dateTime: '2026-10-27T09:00:01' };
    const moveRead = {
      pointId: 'point_1', previousPointId: 'root', version: 1, stateDigest: 'point_1',
      state: movedState,
      timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
      entityDeltas: { person_a: { entityId: 'person_a', positionSet: position('hall') } },
    };
    const elapsedState = clone(movedState);
    elapsedState.time = { ...elapsedState.time, dateTime: '2026-10-27T09:02:01' };
    const elapsedRead = {
      pointId: 'point_2', previousPointId: 'point_1', version: 2, stateDigest: 'point_2',
      state: elapsedState,
      timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
      entityDeltas: {},
    };
    const scenarios = [
      {
        id: 'root-scene', before: null, after: rootRead,
        delta: { timeAdvance: null, entityDeltas: {} }, time: null,
        note: 'No committed change: scene grounding only. Any new event/standing claim must be rejected.',
      },
      {
        id: 'move-direction', before: rootRead, after: moveRead,
        delta: { timeAdvance: moveRead.timeAdvance, entityDeltas: moveRead.entityDeltas }, time: moveRead.timeAdvance,
        note: 'Mandatory fact: 林川 move 走廊→门厅; POV 周宁 stays in 走廊.',
      },
      {
        id: 'elapsed-two-minutes', before: moveRead, after: elapsedRead,
        delta: { timeAdvance: elapsedRead.timeAdvance, entityDeltas: {} }, time: elapsedRead.timeAdvance,
        note: 'Empty delta plus elapsed 2 minutes: time must be narrated; no new change may be invented.',
      },
    ];

    const runs = [];
    let priorText = null;
    for (const scenario of scenarios) {
      const committed = projectCommittedNarration(scenario.after, scenario.before);
      const view = scenario.after.state.protagonistId;
      const inputText = legacyNarrationInput(scenario.before?.state ?? null, scenario.delta, scenario.after.state, view);
      const streamed = [];
      let progressEvents = 0;
      const started = performance.now();
      const generated = await generateCommittedNarration({
        engine, committed, inputText, priorText,
        onProgress: (state) => {
          progressEvents += 1;
          streamed.push({ status: state.status, chars: [...state.text].length, verified: state.verified });
        },
        policy: {
          viewpoint: { id: view, name: scenario.after.state.initial.characters[view].name },
          roster: Object.values(scenario.after.state.initial.characters).map((entity) => entity.name),
          locations: Object.values(scenario.after.state.initial.locations).map((entity) => entity.name),
          knownPositions: Object.keys(scenario.after.state.characters)
            .filter((id) => id !== view)
            .map((id) => ({
              name: scenario.after.state.initial.characters[id].name,
              location: scenario.after.state.initial.locations[scenario.after.state.characters[id].position.containerId]?.name
                ?? scenario.after.state.characters[id].position.containerId,
            })),
          knownEntities: [
            ...Object.values(scenario.after.state.initial.characters).map((entity) => entity.name),
            ...Object.values(scenario.after.state.initial.locations).map((entity) => entity.name),
            ...Object.values(scenario.after.state.initial.items).map((entity) => entity.name),
          ],
          time: scenario.time,
          minChars: config.minChars, targetChars: 240,
          maxAttempts: config.maxAttempts, maxTokens: config.maxTokens, maxTokensCeiling: 700,
          temperature: 0.7, retryTemperature: 0.5, seed: 42,
          deadlineMs: 180_000, timeoutMs: 150_000,
          ...(config.instruction ? { instruction: config.instruction } : {}),
        },
      });
      const wallMs = performance.now() - started;
      if (generated.accepted) priorText = generated.text;
      const record = {
        id: scenario.id, note: scenario.note,
        inputChars: inputText.length, inputText,
        accepted: generated.accepted, status: generated.status, strategyVersion: generated.strategyVersion,
        text: generated.text, chars: [...generated.text].length,
        wallMs, timings: generated.timings, metrics: generated.metrics,
        ledger: {
          mandatory: generated.ledger.mandatory.map((fact) => ({ id: fact.id, kind: fact.kind })),
          optional: generated.ledger.optional.length,
          requireTime: generated.ledger.requireTime,
          licensedEntities: generated.ledger.licensedEntities,
          allowedEvents: generated.ledger.allowedEvents,
        },
        displayStatus: generated.display.status,
        progressEvents, streamedTail: streamed.slice(-6),
        attempts: generated.rawAttempts.map((attempt) => ({
          attempt: attempt.attempt, promptChars: attempt.promptChars, prompt: attempt.prompt,
          raw: attempt.raw, cleaned: attempt.cleaned,
          finishReason: attempt.finishReason, error: attempt.error,
          durationMs: attempt.durationMs, firstTokenMs: attempt.firstTokenMs,
          progressEvents: attempt.progressEvents, accepted: attempt.accepted,
          cancelled: attempt.cancelled, timedOut: attempt.timedOut,
          issues: attempt.issues,
          metrics: attempt.metrics,
          alignment: attempt.alignment ? {
            timeExpressed: attempt.alignment.timeExpressed,
            coverage: attempt.alignment.coverage,
            omissions: attempt.alignment.omissions,
            violations: attempt.alignment.violations,
            unverified: attempt.alignment.unverified,
            repetition: attempt.alignment.repetition,
          } : null,
        })),
      };
      runs.push(record);
      console.log(`[narration] ${scenario.id}: accepted=${generated.accepted} status=${generated.status} chars=${record.chars} wallMs=${Math.round(wallMs)} attempts=${generated.rawAttempts.length}`);
    }
    const info = engine.info;
    const diagnostics = engine.diagnostics;
    await engine.dispose();
    return { loadMs, info, diagnostics, runs };
  }, config);

  evidence.status = 'DONE';
  evidence.loadMs = result.loadMs;
  evidence.engine = { info: result.info, diagnostics: result.diagnostics };
  evidence.runs = result.runs;
  evidence.strategy = result.runs[0]?.strategyVersion ?? null;
  save();
  const summary = result.runs.map((run) => ({
    id: run.id, accepted: run.accepted, status: run.status, chars: run.chars,
    attempts: run.attempts.length,
    wallMs: Math.round(run.wallMs),
    hardIssues: run.attempts.map((attempt) => attempt.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind)),
  }));
  console.log(JSON.stringify({ out: config.out, model: config.model, loadMs: Math.round(result.loadMs), summary }, null, 2));
} catch (error) {
  evidence.status = 'FAILED';
  evidence.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  save();
  throw error;
} finally {
  await browser?.close();
  await server.close();
}
