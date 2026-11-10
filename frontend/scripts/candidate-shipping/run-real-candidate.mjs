// Real-model run of the SHIPPED narration candidate path.
//
// Loads the model in headless Edge through wllama, builds one settled point
// from the real product world (free-day) with the real state kernel, then runs
// the selection runner exactly as the patched page would:
//
//   createNarrationRunner({ engine, candidate: 'trained' })
//
// The evidence records: the projection (facts, input size), load time, every
// real streaming increment, the candidate's own verdict and the text it
// produced (accepted or rejected). A rejection is stored as a rejection — the
// script never promotes it to accepted prose.
//
// Local inference is an exclusive resource: acquire the lease first and release
// it afterwards (see .local/parallel-local-game/common.md).
//
//   node scripts/candidate-shipping/run-real-candidate.mjs \
//     --tree <patched tree> [--model /models/qwen25-1.5b-narr-Q4_K_M.gguf] \
//     [--out ../../../results/06-recovery/real-candidate.json] [--threads 4]
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { basename, dirname, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');

const here = fileURLToPath(new URL('.', import.meta.url));
const flag = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const tree = resolve(flag('--tree', 'D:/others/Jity/.local/parallel-local-game/scratch/shipping-06'));
const config = {
  model: (() => {
    const value = flag('--model', '/models/qwen25-1.5b-narr-Q4_K_M.gguf');
    return value.startsWith('/models/') ? value : `/models/${basename(value)}`;
  })(),
  out: resolve(flag('--out', resolve(here, '../../../results/06-recovery/real-candidate.json'))),
  modelDir: process.env.MODEL_DIR ?? 'D:/others/Jity/.local/world-narration-worktree/frontend/public/models',
  channel: flag('--channel', 'msedge'),
  threads: Number(flag('--threads', '4')),
  gpu: process.argv.includes('--gpu'),
  candidate: flag('--candidate', 'trained'),
  mode: flag('--mode', 'program'),
  maxTokens: Number(flag('--max-tokens', '240')),
  minChars: Number(flag('--min-chars', '60')),
  targetChars: Number(flag('--target-chars', '200')),
  timeoutMs: Number(flag('--timeout-ms', '120000')),
  deadlineMs: Number(flag('--deadline-ms', '420000')),
  projectionOnly: process.argv.includes('--projection-only'),
};
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
const modelFile = resolve(config.modelDir, basename(config.model));
const evidence = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  tree,
  candidate: config.candidate,
  config: {
    model: config.model,
    modelSha256: existsSync(modelFile) ? sha256(readFileSync(modelFile)) : null,
    modelBytes: existsSync(modelFile) ? statSync(modelFile).size : null,
    threads: config.threads, gpu: config.gpu, channel: config.channel,
  },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length, platform: process.platform },
  git: (() => {
    try {
      const { execFileSync } = require('node:child_process');
      return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: tree, encoding: 'utf8' }).trim();
    } catch { return null; }
  })(),
};
const save = () => {
  mkdirSync(dirname(config.out), { recursive: true });
  const temp = `${config.out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(evidence, null, 2)}\n`);
  renameSync(temp, config.out);
};
save();

function assetMiddleware(vite) {
  const wllamaRoot = resolve(tree, 'frontend/node_modules/@wllama/wllama/esm');
  const map = {
    '/wllama/index.min.js': { file: resolve(wllamaRoot, 'index.min.js'), type: 'application/javascript' },
    '/wasm/wllama.wasm': { file: resolve(wllamaRoot, 'wasm/wllama.wasm'), type: 'application/wasm' },
  };
  vite.middlewares.use((request, response, next) => {
    response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    const url = (request.url ?? '').split('?')[0];
    if (url === '/__shipping') {
      response.setHeader('Content-Type', 'text/html');
      response.end('<!doctype html><title>shipped narration candidate</title>');
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
  root: resolve(tree, 'frontend'), configFile: false, logLevel: 'warn',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{ name: 'shipping-assets', configureServer: assetMiddleware }],
});
let browser;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({
    headless: true, channel: config.channel,
    ...(config.gpu ? { args: ['--enable-unsafe-webgpu'] } : {}),
  });
  evidence.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') console.error('[console]', message.text());
  });
  await page.goto(`http://127.0.0.1:${port}/__shipping`);
  const result = await page.evaluate(async (config) => {
    if (!crossOriginIsolated) throw new Error('real run requires cross-origin isolation');
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { createNarrationRunner, prepareNarration } = await import('/src/lib/world-engine/local/narration-candidates/selection/index.ts');
    const { applyPoint } = await import('/src/lib/world-engine/local/state.ts');

    const world = await (await fetch('/worlds/dragon-raja-free-day.world.json')).json();
    const timeAdvance = { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } };
    const entityDeltas = {
      lu: { entityId: 'lu', positionSet: { containerId: 'shed', slotId: null, relativeTo: null } },
    };
    const after = applyPoint(world, {
      worldId: world.worldId, id: 'point_shipping_1', sequence: 1, kind: 'normal',
      previousPointId: 'point_root', roundId: 'round_shipping_1', advanceId: 'advance_shipping_1',
      trigger: 'player', linkedFromPointId: null, timeAdvance, entityDeltas,
    });
    const point = {
      pointId: 'point_shipping_1', before: world, delta: { timeAdvance, entityDeltas }, after,
      playerInput: '我沿器材棚的推拉门进去，先看领用台，再确认器材笼的挂锁是不是还扣着。',
      priorText: null,
    };
    const prepared = prepareNarration(point);
    const projection = {
      facts: prepared.facts.facts.map((fact) => ({ kind: fact.kind, id: fact.id, ...(fact.kind === 'moved' ? { from: fact.from, to: fact.to } : {}) })),
      mandatory: prepared.mandatoryFactIds,
      inputChars: prepared.inputText ? prepared.inputText.length : null,
      inputError: prepared.inputError,
      viewpoint: prepared.viewpointName,
      scene: {
        location: prepared.scene.location,
        present: (prepared.scene.present ?? []).map((person) => person.name),
        objects: (prepared.scene.objects ?? []).map((object) => object.name),
      },
    };

    if (config.projectionOnly) {
      return { selection: null, projection, loadMs: 0, totalMs: 0, progressEvents: 0, progressFirst: null, progressLast: null, run: null };
    }
    if (config.candidate === 'constrained' && config.mode === 'program') {
      // Program realizer: the engine must not be called at all.
      const dummy = {
        info: { backend: 'none', modelId: null },
        load: async () => undefined,
        complete: async () => { throw new Error('program mode must not call the engine'); },
        dispose: async () => undefined,
      };
      const runner = createNarrationRunner({ engine: dummy, candidate: 'constrained', constrainedMode: 'program', minChars: config.minChars });
      const started = performance.now();
      const run = await runner.generate(point, () => undefined);
      return {
        selection: runner.selection, projection, loadMs: 0, totalMs: Math.round(performance.now() - started),
        progressEvents: 0, progressFirst: null, progressLast: null,
        run: {
          kind: run.kind, candidateId: run.candidateId ?? null,
          reason: run.kind === 'fallback' ? run.reason : null,
          grade: run.kind === 'adopted' ? run.grade : null,
          text: run.kind === 'adopted' ? run.text : run.detail?.text ?? null,
          textChars: (run.kind === 'adopted' ? run.text : run.detail?.text ?? '').length,
          issues: run.kind === 'adopted' ? run.issues : run.detail?.issues ?? null,
          timings: run.kind === 'adopted' ? run.timings : null,
          detail: run.kind === 'fallback' ? run.detail ?? null : null,
        },
      };
    }
    const engine = new WllamaInferenceEngine({
      modelUrl: config.model, contextSize: 4096, numThreads: config.threads,
      ...(config.gpu ? { nGpuLayers: 99999 } : { nGpuLayers: 0 }),
    });
    const loadStarted = performance.now();
    await engine.load();
    const loadMs = performance.now() - loadStarted;

    const progress = [];
    const started = performance.now();
    const runner = createNarrationRunner({
      engine, candidate: config.candidate,
      temperature: 0.45, retryTemperature: 0.3,
      maxTokens: config.maxTokens, maxTokensCeiling: Math.max(420, config.maxTokens),
      timeoutMs: config.timeoutMs, deadlineMs: config.deadlineMs,
      minChars: config.minChars, targetChars: config.targetChars,
    });
    const run = await runner.generate(point, (state) => {
      progress.push({ chars: state.text.length, elapsedMs: Math.round(state.elapsedMs), verified: state.verified });
    });
    const totalMs = performance.now() - started;
    await engine.dispose();
    return {
      selection: runner.selection,
      projection,
      loadMs: Math.round(loadMs),
      totalMs: Math.round(totalMs),
      progressEvents: progress.length,
      progressFirst: progress[0] ?? null,
      progressLast: progress.at(-1) ?? null,
      run: {
        kind: run.kind,
        candidateId: run.candidateId ?? null,
        grade: run.kind === 'adopted' ? run.grade : null,
        reason: run.kind === 'fallback' ? run.reason : null,
        text: run.kind === 'adopted' ? run.text : run.detail?.text ?? null,
        textChars: (run.kind === 'adopted' ? run.text : run.detail?.text ?? '').length,
        issues: run.kind === 'adopted' ? run.issues : run.detail?.issues ?? null,
        timings: run.kind === 'adopted' ? run.timings : run.detail?.timings ?? null,
        beats: run.kind === 'fallback' ? run.detail?.candidate?.beats ?? null : null,
        assembly: run.kind === 'fallback' ? run.detail?.candidate?.assembly ?? null : null,
        strategyVersion: run.kind === 'adopted' ? run.strategyVersion : run.detail?.strategyVersion ?? null,
      },
    };
  }, {
    model: config.model, threads: config.threads, gpu: config.gpu, candidate: config.candidate,
    projectionOnly: config.projectionOnly, mode: config.mode,
    maxTokens: config.maxTokens, minChars: config.minChars, targetChars: config.targetChars,
    timeoutMs: config.timeoutMs, deadlineMs: config.deadlineMs,
  });
  evidence.status = config.projectionOnly ? 'PROJECTION_ONLY' : result.run.kind === 'adopted' ? 'ACCEPTED' : 'REJECTED';
  evidence.result = result;
} catch (error) {
  evidence.status = 'FAILED';
  evidence.error = error instanceof Error ? `${error.name}: ${error.message}\n${error.stack ?? ''}` : String(error);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await server.close();
  save();
}
console.log(JSON.stringify({
  status: evidence.status,
  candidate: evidence.candidate,
  selection: evidence.result?.selection,
  projection: evidence.result?.projection,
  loadMs: evidence.result?.loadMs,
  totalMs: evidence.result?.totalMs,
  progressEvents: evidence.result?.progressEvents,
  run: evidence.result?.run && {
    kind: evidence.result.run.kind, reason: evidence.result.run.reason,
    textChars: evidence.result.run.textChars, issues: evidence.result.run.issues,
    timings: evidence.result.run.timings,
  },
  out: config.out,
  error: evidence.error,
}, null, 2));
