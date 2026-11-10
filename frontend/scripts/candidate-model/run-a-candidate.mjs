// Real-browser A-route run: one loaded model, several committed points.
//
// Loads a catalog checkpoint once, then runs the frozen dev/unseen points
// through a candidate entry (default: this tree's model-runtime reference
// candidate; --entry can point at 03's generation module once it exists).
// It stores the exact prompt, raw attempts, per-call timings, the alignment
// verdict and the final text so 03/09/06 can read the actual prose instead of
// a score.
//
//   node scripts/candidate-model/run-a-candidate.mjs \
//     --model qwen2.5-1.5b-instruct-q4km --set dev \
//     [--entry /src/lib/world-engine/local/narration-candidates/instruct/index.ts] \
//     [--export generateCandidate] \
//     [--target-chars 200] [--attempts 2] [--max-tokens 320] \
//     [--out ../../results/quality/a-run-1.5b.json]
//
// The inference lease must be held (see .local/parallel-local-game/common.md);
// this script does not acquire or release it.
import { createHash } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { cpus } from 'node:os';
import { execFileSync } from 'node:child_process';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';
import { sendGguf } from './gguf-server.mjs';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const repoRoot = resolve(frontend, '..');
const option = (flag, fallback) => (process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback);
const options = (flag) => process.argv.flatMap((value, index) => (value === flag && process.argv[index + 1] ? [process.argv[index + 1]] : []));
const config = {
  model: option('--model', 'qwen2.5-1.5b-instruct-q4km'),
  set: option('--set', 'dev'),
  only: option('--only', '').split(',').map((value) => value.trim()).filter(Boolean),
  entry: option('--entry', ''),
  exportName: option('--export', 'generateCandidate'),
  targetChars: Number(option('--target-chars', '220')),
  minChars: Number(option('--min-chars', '60')),
  attempts: Number(option('--attempts', '2')),
  maxTokens: Number(option('--max-tokens', '360')),
  temperature: Number(option('--temperature', '0.7')),
  seed: Number(option('--seed', '42')),
  channel: option('--channel', 'msedge'),
  threads: Number(option('--threads', '0')),
  context: Number(option('--context', '0')),
  forceCpu: process.argv.includes('--force-cpu'),
  lowPowerGpu: process.argv.includes('--low-power-gpu'),
  out: resolve(frontend, option('--out', '../../results/quality/a-candidate-run.json')),
  modelsDirs: options('--models-dir').length > 0 ? options('--models-dir') : [
    'D:/others/Jity/.local/world-narration-worktree/frontend/public/models',
    'D:/others/Jity/frontend/public/models',
    'D:/others/Jity/.local/models',
  ],
};
// An absolute path is converted here, not by the shell: Git Bash rewrites
// arguments that start with '/@fs/' into a Windows path (and mangles the drive
// colon), which made a 03 run fail before the model was even called.
const entryFile = config.entry && /^[A-Za-z]:[\/]/.test(config.entry) ? config.entry : '';
if (entryFile) config.entry = '/@fs/' + entryFile.split(String.fromCharCode(92)).join('/');
// A module in another worktree imports its own siblings; allow that tree's
// frontend root, not only the entry file's directory.
const entryRoot = (() => {
  if (!entryFile) return null;
  const normalized = entryFile.split(String.fromCharCode(92)).join('/');
  const at = normalized.lastIndexOf('/frontend/');
  return at > 0 ? normalized.slice(0, at + '/frontend'.length) : dirname(entryFile);
})();

const sha256File = (file) => new Promise((done, fail) => {
  const hash = createHash('sha256');
  createReadStream(file).on('data', (chunk) => hash.update(chunk)).on('end', () => done(hash.digest('hex'))).on('error', fail);
});
const nvidiaMemory = () => {
  try {
    const query = '--query-gpu=memory.used,utilization.gpu';
    const output = execFileSync('nvidia-smi', [query, '--format=csv,noheader,nounits'], { encoding: 'utf8' }).trim();
    const raw = output.split(String.fromCharCode(10))[0];
    const [usedMiB, utilization] = raw.split(',').map((value) => Number(value.trim()));
    return { usedMiB, utilization };
  } catch { return null; }
};
const git = (...args) => {
  try { return execFileSync('git', ['-c', `safe.directory=${repoRoot.replaceAll('\\', '/')}`, '-C', repoRoot, ...args], { encoding: 'utf8' }).trim(); }
  catch { return ''; }
};

// The checkout may use CRLF on Windows; parse the catalog as LF.
const catalogSource = readFileSync(resolve(frontend, 'src/lib/world-engine/local/narration-candidates/model-runtime/catalog.ts'), 'utf8').split(String.fromCharCode(13, 10)).join(String.fromCharCode(10));

const entry = (() => {
  for (const block of catalogSource.split('{\n    id:').slice(1)) {
    const id = block.match(/^\s*'([^']+)'/)?.[1];
    if (id !== config.model) continue;
    return {
      id,
      gguf: block.match(/gguf:\s*'([^']+)'/)?.[1],
      sha256: block.match(/sha256:\s*'([0-9a-f]{64})'/)?.[1],
      bytes: Number(block.match(/bytes:\s*(\d+)/)?.[1]),
    };
  }
  return null;
})();
if (!entry?.gguf) throw new Error(`model ${config.model} is not in the catalog`);
const modelFile = config.modelsDirs.map((dir) => resolve(dir, entry.gguf)).find((file) => existsSync(file));
if (!modelFile) throw new Error(`model file ${entry.gguf} not found in ${config.modelsDirs.join(', ')}`);
const modelBytes = statSync(modelFile).size;
const modelSha256 = await sha256File(modelFile);
if (modelBytes !== entry.bytes || modelSha256 !== entry.sha256) throw new Error(`model file does not match the catalog: ${modelFile}`);

const report = {
  status: 'IN_PROGRESS',
  lane: process.env.JITY_PI_LANE ?? '08-runtime',
  recordedAt: new Date().toISOString(),
  git: { head: git('rev-parse', 'HEAD'), status: git('status', '--short') },
  model: { id: entry.id, file: modelFile, bytes: modelBytes, sha256: modelSha256 },
  config: { set: config.set, entry: config.entry || 'model-runtime reference candidate', exportName: config.exportName,
    targetChars: config.targetChars, minChars: config.minChars, attempts: config.attempts, maxTokens: config.maxTokens,
    temperature: config.temperature, seed: config.seed, threads: config.threads || 'catalog default', context: config.context || 'catalog default', forceCpu: config.forceCpu },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length, platform: process.platform,
    gpuAtStart: nvidiaMemory() },
  points: [],
};
const save = () => {
  mkdirSync(dirname(config.out), { recursive: true });
  const temp = `${config.out}.tmp`;
  writeFileSync(temp, `${JSON.stringify(report, null, 2)}\n`);
  renameSync(temp, config.out);
};
save();

const wllamaRoot = resolve(frontend, 'node_modules/@wllama/wllama/esm');
const server = await createServer({
  root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/candidate-model-vite',
  server: {
    host: '127.0.0.1', port: 0, hmr: false,
    // --entry may live in another lane's worktree; Vite only serves the
    // project root unless the candidate directory is allowed explicitly.
    fs: { allow: [frontend, ...(entryRoot ? [entryRoot] : [])] },
  },
  plugins: [{ name: 'candidate-model-run', configureServer(vite) {
    vite.middlewares.use((request, response, next) => {
      response.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
      response.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
      const url = (request.url ?? '').split('?')[0];
      if (url === '/__candidate-run') {
        response.setHeader('Content-Type', 'text/html');
        response.end('<!doctype html><meta charset="utf-8"><title>candidate run</title><body>run</body>');
        return;
      }
      if (url === '/wllama/index.min.js') { response.setHeader('Content-Type', 'text/javascript'); createReadStream(resolve(wllamaRoot, 'index.min.js')).pipe(response); return; }
      if (url === '/wasm/wllama.wasm') { response.setHeader('Content-Type', 'application/wasm'); createReadStream(resolve(wllamaRoot, 'wasm/wllama.wasm')).pipe(response); return; }
      if (url.startsWith('/models/')) {
        const name = basename(decodeURIComponent(url));
        const file = config.modelsDirs.map((dir) => resolve(dir, name)).find((candidate) => existsSync(candidate));
        if (!file) { response.statusCode = 404; response.end('missing model'); return; }
        sendGguf(request, response, file);
        return;
      }
      next();
    });
  } }],
});

let browser;
try {
  await server.listen();
  report.serverPort = server.httpServer.address().port;
  // Chromium's GPU picker otherwise prefers the integrated adapter on a
// hybrid-graphics laptop. The switch asks for the discrete GPU; the
// adapter name is still recorded so a failed request is visible.
  const gpuArgs = config.lowPowerGpu ? ['--force_low_power_gpu'] : ['--force_high_performance_gpu'];
  browser = await chromium.launch({ headless: true, channel: config.channel, args: ['--enable-unsafe-webgpu', ...gpuArgs] });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  const consoleLines = [];
  page.on('console', (message) => {
    const text = message.text();
    if (/webgpu|ggml|backend|vulkan|cuda|adapter|offload/i.test(text)) consoleLines.push(`${message.type()}: ${text.slice(0, 400)}`);
    if (message.type() === 'error') console.error('[console.error]', text.slice(0, 300));
  });
  await page.goto(`http://127.0.0.1:${report.serverPort}/__candidate-run`);
  const loaded = await page.evaluate(async (config) => {
    if (!crossOriginIsolated) throw new Error('the candidate run requires cross-origin isolation');
    const { modelSpec } = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/catalog.ts');
    const { loadCandidateModel, webgpuAvailable } = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/backend.ts');
    const spec = modelSpec(config.model);
    const started = performance.now();
    const adapter = navigator.gpu ? await navigator.gpu.requestAdapter() : null;
    const adapterInfo = adapter?.info
      ? { vendor: adapter.info.vendor, architecture: adapter.info.architecture, device: adapter.info.device, description: adapter.info.description }
      : null;
    const result = await loadCandidateModel(spec, {
      preferGpu: !config.forceCpu,
      ...(config.threads ? { numThreads: config.threads } : {}),
      ...(config.context ? { contextSize: config.context } : {}),
    });
    window.__candidateRun = { engine: result.engine, spec };
    return { backend: result.backend, fallback: result.fallback, attempts: result.attempts, loadMs: performance.now() - started,
      webgpuAvailable: webgpuAvailable(), adapterInfo, runtime: result.engine.runtime };
  }, config);
  report.load = loaded;
  report.adapterInfo = loaded.adapterInfo ?? null;
  save();
  console.log(`[run] ${config.model} backend=${loaded.backend} load=${Math.round(loaded.loadMs)}ms`);

  const points = await page.evaluate(async (config) => {
    const { projectCommittedNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
    const { legacyNarrationInput } = await import('/src/lib/world-engine/local/prompt.ts');
    const { SHORT_STATE } = await import('/src/lib/world-engine/runtime/b3-short-samples.ts');
    const reference = await import('/src/lib/world-engine/local/narration-candidates/model-runtime/candidate.ts');
    const entryModule = config.entry ? await import(config.entry) : reference;
    const generate = entryModule[config.exportName];
    if (typeof generate !== 'function') throw new Error(`candidate entry ${config.entry || 'reference'} has no export ${config.exportName}`);
    const spec = window.__candidateRun.spec;
    const engine = window.__candidateRun.engine;
    const clone = (value) => JSON.parse(JSON.stringify(value));
    const position = (containerId) => ({ containerId, slotId: null, relativeTo: null });
    const read = (pointId, previousPointId, version, state, timeAdvance, entityDeltas) => ({
      pointId, previousPointId, version, stateDigest: pointId, state, timeAdvance, entityDeltas,
    });
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
    const policyFor = (state, view, time) => ({
      mode: 'beats', scene: sceneFrom(state, view), viewpoint: { id: view, name: state.initial.characters[view].name },
      roster: Object.values(state.initial.characters).map((entity) => entity.name),
      locations: Object.values(state.initial.locations).map((entity) => entity.name),
      knownPositions: Object.keys(state.characters).filter((id) => id !== view).map((id) => ({
        name: state.initial.characters[id].name,
        location: state.initial.locations[state.characters[id].position.containerId]?.name ?? state.characters[id].position.containerId,
      })),
      knownEntities: [
        ...Object.values(state.initial.characters).map((entity) => entity.name),
        ...Object.values(state.initial.locations).map((entity) => entity.name),
        ...Object.values(state.initial.items).map((entity) => entity.name),
      ],
      time, minChars: config.minChars, targetChars: config.targetChars,
      maxTokens: config.maxTokens, maxTokensCeiling: config.maxTokens,
      temperature: config.temperature, seed: config.seed, attempts: config.attempts, timeoutMs: 150000,
    });

    // ---- scenario fixtures (same worlds as the 02 narration probes) ----
    const schoolRoot = clone(SHORT_STATE);
    const schoolMove = clone(schoolRoot);
    schoolMove.characters.person_a.position = position('hall');
    schoolMove.time = { ...schoolMove.time, dateTime: '2026-10-27T09:00:01' };
    const schoolElapsed = clone(schoolMove);
    schoolElapsed.time = { ...schoolElapsed.time, dateTime: '2026-10-27T09:02:01' };
    const schoolRootRead = read('root', null, 0, schoolRoot, null, {});
    const schoolMoveRead = read('point_1', 'root', 1, schoolMove, { boundary: 'instant', duration: { amount: 2, unit: 'minute' } }, {
      person_a: { entityId: 'person_a', positionSet: position('hall') },
    });
    const schoolElapsedRead = read('point_2', 'point_1', 2, schoolElapsed, { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, {});

    const unseenTime = { calendar: 'gregorian', dateTime: '2026-11-02T20:10:00', instantOrdinal: 0 };
    const unseenTask = { id: 'task_ledger', ownerId: 'char_yu', parentTaskId: null, goal: '把账本送回二楼库房', status: 'pending' };
    const unseenState = {
      engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_unseen', protagonistId: 'char_yu', time: unseenTime,
      initial: {
        engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_unseen', protagonistId: 'char_yu', initialTime: unseenTime,
        locations: {
          stairs: { id: 'stairs', name: '楼梯间', parentLocationId: null, initialAppearance: '水泥台阶，扶手冰凉。' },
          storeroom: { id: 'storeroom', name: '二楼库房', parentLocationId: 'stairs', initialAppearance: '一排樟木柜，灯管有一支在闪。' },
          landing: { id: 'landing', name: '二楼平台', parentLocationId: 'stairs', initialAppearance: '窗子关着，玻璃上有一层灰。' },
        },
        items: { ledger: { id: 'ledger', name: '账本', initialPosition: position('landing'), initialAppearance: '牛皮纸封面，边角卷起。' } },
        characters: {
          char_yu: { id: 'char_yu', name: '余晚', initialPosition: position('landing'), initialAppearance: '穿深绿外套。', initialPersonality: '寡言，做事慢', initialSanity: 8, tasks: { task_ledger: unseenTask } },
          char_luo: { id: 'char_luo', name: '罗青', initialPosition: position('storeroom'), initialAppearance: '袖子挽到手肘。', initialPersonality: '急性子，爱较真', initialSanity: 9, tasks: {} },
        },
      },
      locations: {
        stairs: { id: 'stairs', appearanceChanges: [] },
        storeroom: { id: 'storeroom', appearanceChanges: [] },
        landing: { id: 'landing', appearanceChanges: [] },
      },
      items: { ledger: { id: 'ledger', position: position('landing'), appearanceChanges: [] } },
      characters: {
        char_yu: { id: 'char_yu', position: position('landing'), appearanceChanges: [], personalityChanges: [], sanity: 8, tasks: { task_ledger: unseenTask } },
        char_luo: { id: 'char_luo', position: position('storeroom'), appearanceChanges: [], personalityChanges: [], sanity: 9, tasks: {} },
      },
    };
    const unseenRootRead = read('u_root', null, 0, unseenState, null, {});
    const unseenMoveState = clone(unseenState);
    unseenMoveState.characters.char_luo.position = position('landing');
    unseenMoveState.time = { ...unseenMoveState.time, dateTime: '2026-11-02T20:11:00' };
    const unseenMoveRead = read('u_point_1', 'u_root', 1, unseenMoveState, { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } }, {
      char_luo: { entityId: 'char_luo', positionSet: position('landing') },
    });

    const scenarios = [];
    if (config.set === 'dev' || config.set === 'all') {
      scenarios.push({ id: 'root-scene', before: null, after: schoolRootRead, delta: { timeAdvance: null, entityDeltas: {} }, time: null });
      scenarios.push({ id: 'move-direction', before: schoolRootRead, after: schoolMoveRead, delta: { timeAdvance: schoolMoveRead.timeAdvance, entityDeltas: schoolMoveRead.entityDeltas }, time: schoolMoveRead.timeAdvance.duration });
    }
    if (config.set === 'unseen' || config.set === 'all') {
      scenarios.push({ id: 'unseen-move', before: unseenRootRead, after: unseenMoveRead, delta: { timeAdvance: unseenMoveRead.timeAdvance, entityDeltas: unseenMoveRead.entityDeltas }, time: unseenMoveRead.timeAdvance.duration });
    }
    if (config.set === 'continuation' || config.set === 'all' || config.set === 'dev') {
      scenarios.push({ id: 'continuation-elapsed', before: schoolMoveRead, after: schoolElapsedRead, delta: { timeAdvance: schoolElapsedRead.timeAdvance, entityDeltas: {} }, time: schoolElapsedRead.timeAdvance.duration, continuation: true });
    }

    const selected = config.only.length ? scenarios.filter((scenario) => config.only.includes(scenario.id)) : scenarios;
    const results = [];
    // Prior text is only for a real continuation of the same world. Reusing the
    // root passage for an independent point (or another world) made the model
    // paste stale positions; the shared driver only does this via continuesFrom.
    const acceptedByWorld = new Map();
    for (const scenario of selected) {
      const worldId = scenario.after.state.worldId;
      const priorText = scenario.continuation ? acceptedByWorld.get(worldId) ?? null : null;
      const view = scenario.after.state.protagonistId;
      const committed = projectCommittedNarration(scenario.after, scenario.before ?? null);
      const inputText = legacyNarrationInput(scenario.before?.state ?? null, scenario.delta, scenario.after.state, view);
      const progress = [];
      const started = performance.now();
      let result;
      try {
        result = await generate({
          engine, committed, inputText, priorText,
          // 03's instruct candidate builds its own projection from the settled
          // states; the reference candidate ignores these extras.
          state: scenario.after.state,
          before: scenario.before?.state ?? null,
          delta: scenario.delta,
          pointId: scenario.after.pointId,
          policy: { ...policyFor(scenario.after.state, view, scenario.time), ...(priorText ? { priorText } : {}) },
        }, { spec });
      } catch (error) {
        results.push({ id: scenario.id, error: `${error?.name}: ${error?.message}`, wallMs: performance.now() - started });
        continue;
      }
      const wallMs = performance.now() - started;
      if (result.accepted) acceptedByWorld.set(worldId, result.text);
      results.push({
        id: scenario.id,
        time: scenario.time,
        wallMs,
        firstReadableMs: result.timings?.firstReadableMs ?? null,
        accepted: result.accepted,
        text: result.text,
        issues: result.issues,
        verification: result.verification,
        attempts: (result.rawAttempts ?? result.attempts ?? []).map((attempt) => ({
          index: attempt.index, temperature: attempt.temperature, promptChars: attempt.promptChars,
          text: attempt.text, accepted: attempt.accepted, issueKinds: attempt.issueKinds,
          prompt: attempt.prompt,
          completion: attempt.completion && {
            wallMs: attempt.completion.wallMs, firstTokenMs: attempt.completion.firstTokenMs, finishReason: attempt.completion.finishReason,
            promptTokens: attempt.completion.timings?.prompt_n ?? null,
            predictedTokens: attempt.completion.timings?.predicted_n ?? null,
            predictedMs: attempt.completion.timings?.predicted_ms ?? null,
          },
        })),
        strategyVersion: result.strategyVersion,
        progressEvents: progress.length,
      });
    }
    return results;
  }, config);
  report.points = points;
  report.consoleBackendLines = [...new Set(consoleLines)].slice(0, 60);
  report.gpu = { before: report.device.gpuAtStart, after: nvidiaMemory(), note: 'host-side only; the WebGPU adapter name is in adapterInfo/consoleBackendLines' };
  await page.evaluate(async () => {
    await window.__candidateRun.engine.dispose();
    delete window.__candidateRun;
  });
  const completed = points.filter((point) => !point.error);
  const accepted = completed.filter((point) => point.accepted);
  report.summary = {
    points: completed.length,
    errors: points.length - completed.length,
    accepted: accepted.length,
    firstReadableMs: completed.map((point) => point.firstReadableMs).filter((value) => typeof value === 'number'),
    wallMs: completed.map((point) => point.wallMs),
  };
  report.status = 'COMPLETED';
  report.finishedAt = new Date().toISOString();
  save();
  for (const point of points) {
    console.log(`[point] ${point.id} accepted=${point.accepted} wall=${Math.round(point.wallMs)}ms firstReadable=${point.firstReadableMs === null ? 'n/a' : Math.round(point.firstReadableMs)}ms`);
    if (point.text) console.log(`[text] ${point.text}`);
    if (point.error) console.log(`[error] ${point.error}`);
    for (const issue of point.issues ?? []) if (issue.severity === 'hard') console.log(`[issue] ${issue.kind}: ${issue.detail}`);
  }
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
