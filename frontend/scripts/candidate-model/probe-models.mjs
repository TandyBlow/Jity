// Real-device probe for the A-group narration models.
//
// For each catalog model it (1) verifies the exact file hash/size on the host,
// (2) loads the GGUF in a real browser through the candidate loader (WebGPU
// first, CPU fallback recorded), (3) generates ONE real Chinese narration
// point from a frozen committed delta through the candidate module, and
// (4) records load, first readable text, per-call model timings, the model's
// actual text and the fact verdict. It is a model/runtime probe, not a
// quality benchmark: one shared input so the models are comparable, never a
// claim that the output passes product review.
//
//   node scripts/candidate-model/probe-models.mjs \
//     --model qwen2.5-1.5b-instruct-q4km --model qwen3-1.7b-q4km \
//     [--models-dir D:/others/Jity/frontend/public/models]... \
//     [--cpu-compare qwen2.5-1.5b-instruct-q4km] [--force-cpu] \
//     [--max-tokens 160] [--out ../.local/candidate-model/probe.json]
//
// Local inference is an exclusive resource: acquire the lease first and
// release it afterwards (see .local/parallel-local-game/common.md).
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { execFileSync } from 'node:child_process';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const repoRoot = resolve(frontend, '..');
const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const options = (flag) => process.argv.flatMap((value, index) => (value === flag && process.argv[index + 1] ? [process.argv[index + 1]] : []));
const hasFlag = (flag) => process.argv.includes(flag);

const config = {
  models: options('--model'),
  modelDirs: options('--models-dir').length > 0 ? options('--models-dir') : [
    'D:/others/Jity/.local/world-narration-worktree/frontend/public/models',
    'D:/others/Jity/frontend/public/models',
    'D:/others/Jity/.local/models',
  ],
  out: resolve(frontend, option('--out', '../.local/candidate-model/probe.json')),
  channel: option('--channel', 'msedge'),
  maxTokens: Number(option('--max-tokens', '160')),
  cpuCompare: option('--cpu-compare', ''),
  forceCpu: hasFlag('--force-cpu'),
  threads: Number(option('--threads', '0')),
  context: Number(option('--context', '0')),
};

if (config.models.length === 0) {
  console.error('pick at least one --model <catalog id>; ids are in src/lib/world-engine/local/narration-candidates/model-runtime/catalog.ts');
  process.exit(2);
}

const sha256File = (file) => new Promise((resolveHash, rejectHash) => {
  const hash = createHash('sha256');
  createReadStream(file).on('data', (chunk) => hash.update(chunk))
    .on('end', () => resolveHash(hash.digest('hex'))).on('error', rejectHash);
});

const git = (...args) => {
  try { return execFileSync('git', ['-c', `safe.directory=${repoRoot.replaceAll('\\', '/')}`, '-C', repoRoot, ...args], { encoding: 'utf8' }).trim(); }
  catch { return ''; }
};

const nvidiaMemory = () => {
  try {
    const raw = execFileSync('nvidia-smi', ['--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits'], { encoding: 'utf8' }).trim().split('\n')[0];
    const [mb, util] = raw.split(',').map((value) => Number(value.trim()));
    return { usedMiB: mb, utilization: util };
  } catch { return null; }
};

// Model files are read-only shared assets; nothing is copied into the repo.
const fileFor = (sources, model) => {
  for (const dir of config.modelDirs) {
    const file = resolve(dir, model.gguf);
    if (existsSync(file)) return file;
  }
  return null;
};

const catalogSource = readFileSync(resolve(frontend, 'src/lib/world-engine/local/narration-candidates/model-runtime/catalog.ts'), 'utf8');
const parseCatalog = () => {
  const entries = [];
  for (const block of catalogSource.split('{\n    id:').slice(1)) {
    const id = block.match(/^\s*'([^']+)'/)?.[1];
    const gguf = block.match(/gguf:\s*'([^']+)'/)?.[1];
    const sha256 = block.match(/sha256:\s*'([0-9a-f]{64})'/)?.[1];
    const bytes = Number(block.match(/bytes:\s*(\d+)/)?.[1]);
    const parametersB = Number(block.match(/parametersB:\s*([\d.]+)/)?.[1]);
    const templateId = block.match(/id:\s*'([^']+)',\n\s*systemMessage/)?.[1];
    if (id && gguf && sha256) entries.push({ id, gguf, sha256, bytes, parametersB, templateId });
  }
  return entries;
};
const catalog = parseCatalog();
const selected = config.models.map((id) => {
  const entry = catalog.find((item) => item.id === id);
  if (!entry) throw new Error(`model ${id} is not in the catalog (${catalog.map((item) => item.id).join(', ')})`);
  return entry;
});

const report = {
  status: 'IN_PROGRESS',
  lane: process.env.JITY_PI_LANE ?? '08-runtime',
  recordedAt: new Date().toISOString(),
  source: {
    head: git('rev-parse', 'HEAD'),
    status: git('status', '--short'),
    cameraFiles: [
      'frontend/src/lib/world-engine/local/narration-candidates/model-runtime/catalog.ts',
      'frontend/src/lib/world-engine/local/narration-candidates/model-runtime/backend.ts',
      'frontend/src/lib/world-engine/local/narration-candidates/model-runtime/candidate.ts',
      'frontend/src/lib/world-engine/local/narration-candidates/model-runtime/template.ts',
      'frontend/src/lib/world-engine/runtime/wllama-engine.ts',
      'frontend/scripts/candidate-model/probe-models.mjs',
    ].map((file) => ({ file, sha256: createHash('sha256').update(readFileSync(resolve(repoRoot, file))).digest('hex') })),
  },
  device: {
    cpu: cpus()[0]?.model, logicalCpus: cpus().length, platform: process.platform,
    totalMemoryBytes: (await import('node:os')).totalmem?.() ?? null,
    gpuAtStart: nvidiaMemory(),
  },
  config: { models: config.models, threads: config.threads || 'catalog default', context: config.context || 'catalog default', maxTokens: config.maxTokens, channel: config.channel, forceCpu: config.forceCpu },
  models: [],
};
const save = () => {
  mkdirSync(dirname(config.out), { recursive: true });
  const temp = `${config.out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(report, null, 2)}\n`);
  renameSync(temp, config.out);
};
save();

// Host-side asset verification: the browser loads exactly the hashed file.
for (const entry of selected) {
  const file = fileFor(config.modelDirs, entry);
  if (!file) { report.status = 'FAILED'; report.error = `model file missing for ${entry.id}: ${entry.gguf} in ${config.modelDirs.join(', ')}`; save(); throw new Error(report.error); }
  const bytes = statSync(file).size;
  const sha256 = await sha256File(file);
  const verified = bytes === entry.bytes && sha256 === entry.sha256;
  report.models.push({ id: entry.id, gguf: entry.gguf, file, bytes, sha256, catalogBytes: entry.bytes, catalogSha256: entry.sha256, verified });
  if (!verified) { report.status = 'FAILED'; report.error = `asset mismatch for ${entry.id}`; save(); throw new Error(report.error); }
  console.log(`[verify] ${entry.id} ${bytes} ${sha256.slice(0, 16)} ok`);
}

// Serve wllama + the selected GGUFs read-only.
const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
const findModelFile = (urlPath) => {
  const name = basename(decodeURIComponent(urlPath));
  for (const dir of config.modelDirs) {
    const file = resolve(dir, name);
    if (existsSync(file)) return file;
  }
  return null;
};
const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/candidate-model-vite',
  server: { host: '127.0.0.1', port: 0, hmr: false },
  plugins: [{ name: 'candidate-model-probe', configureServer(vite) {
    vite.middlewares.use((request, response, next) => {
      response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
      response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
      const url = (request.url ?? '').split('?')[0];
      if (url === '/__candidate-model') {
        response.setHeader('Content-Type', 'text/html');
        response.end('<!doctype html><meta charset="utf-8"><title>candidate model probe</title><body>probe</body>');
        return;
      }
      if (url === '/wllama/index.min.js') {
        response.setHeader('Content-Type', 'text/javascript');
        createReadStream(resolve(wllamaRoot, 'index.min.js')).pipe(response);
        return;
      }
      if (url === '/wasm/wllama.wasm') {
        response.setHeader('Content-Type', 'application/wasm');
        createReadStream(resolve(wllamaRoot, 'wasm/wllama.wasm')).pipe(response);
        return;
      }
      if (url.startsWith('/models/')) {
        const file = findModelFile(url);
        if (!file) { response.statusCode = 404; response.end('missing model'); return; }
        response.setHeader('Content-Type', 'application/octet-stream');
        response.setHeader('Content-Length', statSync(file).size);
        response.setHeader('Cache-Control', 'no-store');
        createReadStream(file).pipe(response);
        return;
      }
      next();
    });
  } }],
});

let browser;
const consoleLines = [];
try {
  await server.listen();
  report.serverPort = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel, args: ['--enable-unsafe-webgpu'] });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  page.on('console', (message) => {
    const text = message.text();
    if (/webgpu|ggml|backend|vulkan|cuda|adapter|offload/i.test(text)) consoleLines.push(`${message.type()}: ${text.slice(0, 400)}`);
  });
  await page.goto(`http://127.0.0.1:${report.serverPort}/__candidate-model`);

  const modelIds = selected.map((entry) => entry.id);
  const runConfig = { modelIds, maxTokens: config.maxTokens, forceCpu: config.forceCpu,
    threads: config.threads || null, context: config.context || null };
  const mmSampler = () => nvidiaMemory();
  for (const modelId of modelIds) {
    console.log(`[probe] ${modelId}`);
    let peak = mmSampler();
    const sampler = setInterval(() => {
      const sample = mmSampler();
      if (sample && (!peak || sample.usedMiB > peak.usedMiB)) peak = sample;
    }, 400);
    const result = await page.evaluate(async (config) => {
      const startedAt = performance.now();
      try {
      const { modelSpec } = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/catalog.ts');
      const { loadCandidateModel, webgpuAvailable } = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/backend.ts');
      const { generateCandidate } = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/candidate.ts');
      const { RuntimeDiagnostics } = await import('/src/lib/world-engine/local/runtime-diagnostics/index.ts');
      const { projectCommittedNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
      const { legacyNarrationInput } = await import('/src/lib/world-engine/local/prompt.ts');
      const { SHORT_STATE } = await import('/src/lib/world-engine/runtime/b3-short-samples.ts');
      const spec = modelSpec(config.modelId);
      const adapter = navigator.gpu ? await navigator.gpu.requestAdapter() : null;
      const adapterInfo = adapter?.info
        ? { vendor: adapter.info.vendor, architecture: adapter.info.architecture, device: adapter.info.device, description: adapter.info.description }
        : null;
      const diagnostics = new RuntimeDiagnostics({ limit: 128 });
      const loaded = await loadCandidateModel(spec, {
        preferGpu: !config.forceCpu,
        onEvidence: diagnostics.record,
        ...(config.threads ? { numThreads: config.threads } : {}),
        ...(config.context ? { contextSize: config.context } : {}),
      });
      // A frozen committed point (the dev world of the narration probes):
      // 林川 moves 走廊→门厅; POV 周宁 stays; two minutes pass.
      const clone = (value) => JSON.parse(JSON.stringify(value));
      const position = (containerId) => ({ containerId, slotId: null, relativeTo: null });
      const root = { pointId: 'root', previousPointId: null, version: 0, stateDigest: 'root', state: clone(SHORT_STATE), timeAdvance: null, entityDeltas: {} };
      const moved = clone(SHORT_STATE);
      moved.characters.person_a.position = position('hall');
      moved.time = { ...moved.time, dateTime: '2026-10-27T09:02:00' };
      const after = {
        pointId: 'point_1', previousPointId: 'root', version: 1, stateDigest: 'point_1', state: moved,
        timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
        entityDeltas: { person_a: { entityId: 'person_a', positionSet: position('hall') } },
      };
      const committed = projectCommittedNarration(after, root);
      const delta = { timeAdvance: after.timeAdvance, entityDeltas: after.entityDeltas };
      const inputText = legacyNarrationInput(root.state, delta, moved, 'person_c');
      const view = 'person_c';
      const sceneFrom = (state, viewId) => {
        const containerId = state.characters[viewId].position.containerId;
        const nameOf = (id) => state.initial.locations[id]?.name ?? state.initial.items[id]?.name ?? state.initial.characters[id]?.name ?? id;
        const notesOf = (entity, base) => [base, ...(entity.appearanceChanges ?? []).filter((change) => change.supersedes.length === 0 && change.text).map((change) => change.text)].filter(Boolean);
        const inPlace = Object.keys(state.characters).filter((id) => id !== viewId && state.characters[id].position.containerId === containerId);
        return {
          location: nameOf(containerId),
          placeNotes: notesOf(state.locations[containerId] ?? { appearanceChanges: [] }, state.initial.locations[containerId]?.initialAppearance ?? ''),
          present: [viewId, ...inPlace].map((id) => ({ name: state.initial.characters[id].name, note: notesOf(state.characters[id], state.initial.characters[id].initialAppearance)[0] })),
          objects: Object.keys(state.items).filter((id) => state.items[id].position.containerId === containerId)
            .map((id) => ({ name: state.initial.items[id].name, note: notesOf(state.items[id], state.initial.items[id].initialAppearance)[0] })),
        };
      };
      const progress = [];
      const generationStarted = performance.now();
      let generated;
      try {
        generated = await generateCandidate({
          engine: loaded.engine,
          committed,
          inputText,
          policy: {
            mode: 'beats',
            scene: sceneFrom(moved, view),
            viewpoint: { id: view, name: moved.initial.characters[view].name },
            roster: Object.values(moved.initial.characters).map((entity) => entity.name),
            locations: Object.values(moved.initial.locations).map((entity) => entity.name),
            knownPositions: Object.keys(moved.characters).filter((id) => id !== view).map((id) => ({
              name: moved.initial.characters[id].name,
              location: moved.initial.locations[moved.characters[id].position.containerId]?.name ?? moved.characters[id].position.containerId,
            })),
            knownEntities: [
              ...Object.values(moved.initial.characters).map((entity) => entity.name),
              ...Object.values(moved.initial.locations).map((entity) => entity.name),
              ...Object.values(moved.initial.items).map((entity) => entity.name),
            ],
            time: after.timeAdvance.duration,
            minChars: 60, targetChars: 200,
            maxTokens: config.maxTokens, maxTokensCeiling: config.maxTokens,
            temperature: 0.7, seed: 42, attempts: 2, timeoutMs: 150000,
          },
          onProgress: (state) => progress.push({ status: state.status, chars: [...state.text].length, verified: state.verified, elapsedMs: state.elapsedMs }),
        }, { spec });
      } finally {
        await loaded.engine.dispose();
      }
      const generationMs = performance.now() - generationStarted;
      const attempts = generated.rawAttempts.map((attempt) => ({
        index: attempt.index,
        temperature: attempt.temperature,
        promptChars: attempt.promptChars,
        text: attempt.text,
        accepted: attempt.accepted,
        issueKinds: attempt.issueKinds,
        completion: attempt.completion && {
          wallMs: attempt.completion.wallMs,
          firstTokenMs: attempt.completion.firstTokenMs,
          finishReason: attempt.completion.finishReason,
          promptTokens: attempt.completion.timings?.prompt_n ?? null,
          predictedTokens: attempt.completion.timings?.predicted_n ?? null,
          predictedMs: attempt.completion.timings?.predicted_ms ?? null,
        },
      }));
      return {
        modelId: config.modelId,
        webgpuAvailable: webgpuAvailable(),
        adapterInfo,
        backend: loaded.backend,
        fallback: loaded.fallback,
        attempts: loaded.attempts,
        loadMs: loaded.loadMs,
        generationMs,
        firstReadableMs: generated.timings.firstReadableMs,
        firstProgressMs: generated.timings.firstProgressMs,
        progressEvents: progress.length,
        firstProgress: progress[0] ?? null,
        lastProgress: progress.at(-1) ?? null,
        text: generated.text,
        accepted: generated.accepted,
        issues: generated.issues,
        verification: generated.verification,
        attemptsText: attempts,
        runtime: loaded.engine.runtime,
        loadEvidence: loaded.evidence,
        diagnostics: diagnostics.summary(),
        totalMs: performance.now() - startedAt,
      };
      } catch (error) {
        // One model failing must not throw away the models already measured.
        return { modelId: config.modelId, error: String(error?.message ?? error), stack: String(error?.stack ?? '') };
      }
    }, { ...runConfig, modelId });
    clearInterval(sampler);
    const peakAfter = mmSampler();
    const record = report.models.find((entry) => entry.id === modelId);
    record.result = result;
    record.memory = { before: report.device.gpuAtStart, peakMiB: peak?.usedMiB ?? null, after: peakAfter };
    report.memorySamples = [...(report.memorySamples ?? []), { modelId, peak: peak?.usedMiB ?? null, after: peakAfter }];
    save();
    if (result.error) {
      console.log(`[probe] ${modelId}: FAILED ${result.error}`);
      continue;
    }
    const tok = result.attemptsText[0]?.completion;
    const tps = tok?.predictedTokens && tok?.predictedMs ? (tok.predictedTokens / (tok.predictedMs / 1000)).toFixed(1) : null;
    console.log(`[probe] ${modelId}: backend=${result.backend} load=${Math.round(result.loadMs)}ms firstReadable=${Math.round(result.firstReadableMs ?? -1)}ms gen=${Math.round(result.generationMs)}ms tok/s=${tps} accepted=${result.accepted} chars=${[...result.text].length}`);
    if (result.text) console.log(`[probe] text: ${result.text}`);
  }

  if (config.cpuCompare) {
    console.log(`[cpu-compare] ${config.cpuCompare}`);
    const entry = report.models.find((item) => item.id === config.cpuCompare);
    if (!entry) throw new Error(`--cpu-compare ${config.cpuCompare} was not probed`);
    const sampler2 = setInterval(() => undefined, 1000);
    const result = await page.evaluate(async (config) => {
      const { modelSpec } = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/catalog.ts');
      const { loadCandidateModel } = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/backend.ts');
      const spec = modelSpec(config.modelId);
      const loaded = await loadCandidateModel(spec, { forceCpu: true });
      const started = performance.now();
      let completion = null;
      const text = await loaded.engine.chat([
        { role: 'system', content: '你是中文小说作者。只输出一段正文，不要解释。' },
        { role: 'user', content: '写一段雨夜巷口的追逐，约一百二十字。' },
      ], { maxTokens: config.maxTokens, temperature: 0, seed: 42, timeoutMs: 300000, cachePrompt: false,
        onCompletion: (evidence) => { completion = evidence; } });
      const wallMs = performance.now() - started;
      await loaded.engine.dispose();
      return { modelId: config.modelId, backend: loaded.backend, attempts: loaded.attempts, loadMs: loaded.loadMs, wallMs, text, completion };
    }, { modelId: config.cpuCompare, maxTokens: config.maxTokens });
    clearInterval(sampler2);
    report.cpuCompare = result;
    save();
    console.log(`[cpu-compare] ${config.cpuCompare}: load=${Math.round(result.loadMs)}ms gen=${Math.round(result.wallMs)}ms text=${JSON.stringify(result.text.slice(0, 80))}`);
  }

  report.status = 'COMPLETED';
  report.finishedAt = new Date().toISOString();
  report.consoleBackendLines = [...new Set(consoleLines)].slice(0, 80);
  save();
  console.log(JSON.stringify({ status: report.status, output: config.out, models: report.models.map((entry) => ({
    id: entry.id, backend: entry.result?.backend, loadMs: entry.result?.loadMs, firstReadableMs: entry.result?.firstReadableMs, accepted: entry.result?.accepted,
  })) }, null, 2));
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
