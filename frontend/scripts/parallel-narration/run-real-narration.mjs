// Real browser-model run for the committed-narration strategy.
//
// This is NOT a full baseline: it runs a small set of committed points through
// the actual page path (headless Edge + wllama + a real GGUF) and stores the
// exact prompt, raw completion, per-beat and per-attempt verdicts, retry
// guidance and wall time. The strategy code is the same module the page would
// import; the fact input is produced by the existing projectors/serializer.
//
// Local inference is an exclusive resource: acquire the lease first and
// release it afterwards (see .local/parallel-local-game/common.md).
//
//   node scripts/parallel-narration/run-real-narration.mjs \
//     [--model /models/qwen25-0.5b-narration-Q4_K_M.gguf] \
//     [--mode beats] [--set dev|unseen|continuation|all] \
//     [--out ../../../results/02-narration/real-model-evidence.json]
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
  maxTokens: Number(option('--max-tokens', '200')),
  maxAttempts: Number(option('--max-attempts', '2')),
  minChars: Number(option('--min-chars', '80')),
  // One or more arms measured in the same browser session (one model load).
  //   scene  — whole scene from lane 01's serialized input + writing contract
  //   prose  — whole scene rendered as the lane-08 reference closed-book turn
  //   beats  — one committed thing per call (lane 02 strategy)
  modes: (option('--modes', option('--mode', 'beats'))).split(',').map((value) => value.trim()).filter(Boolean),
  // scene mode only: which prompt shape the weights were trained on
  template: option('--template', 'legacy'),
  // The B-scene candidate was trained with a separate system turn. The page
  // engine always wraps a single user message, so a fair run needs an engine
  // that sends the system turn explicitly. This is probe tooling; the page
  // integration request is in results/quality/integration-02.json.
  system: option('--system', ''),
  inputWorktree: option('--input-worktree', 'D:/others/Jity/.local/parallel-local-game/worktrees/01-input'),
  scenarioFile: option('--scenario-file', ''),
  set: option('--set', 'dev'),
  instruction: option('--instruction', ''),
  gpu: process.argv.includes('--gpu'),
  // The comparison must run on the discrete adapter, not whatever Edge picks.
  // --require-vendor nvidia fails the run when the adapter is wrong instead of
  // producing numbers that look valid; empty string accepts any adapter.
  requireVendor: option('--require-vendor', process.argv.includes('--gpu') ? 'nvidia' : ''),
  // A model that never loads must fail within a bounded time instead of
  // hanging the queue.
  loadTimeoutMs: Number(option('--load-timeout-ms', '180000')),
  // With a scenario file, also run the built-in dev move + elapsed points on
  // the declared SHORT_STATE fixture: the product opening has no settled
  // change, so fact expression needs a point that does.
  withDev: process.argv.includes('--with-dev'),
};
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');
if (config.scenarioFile) {
  config.scenario = JSON.parse(readFileSync(config.scenarioFile, 'utf8'));
  const scenario = config.scenario;
  const missing = [];
  if (!scenario.inputText) missing.push('inputText');
  if (!scenario.committed?.facts) missing.push('committed.facts');
  if (!scenario.policy?.viewpoint?.name) missing.push('policy.viewpoint.name');
  if (!scenario.policy?.knownEntities?.length) missing.push('policy.knownEntities');
  if (missing.length) {
    console.error(`scenario file ${config.scenarioFile} is missing: ${missing.join(', ')}`);
    process.exit(2);
  }
  console.log(`[scenario] ${scenario.id}: inputChars=${scenario.inputText.length} `
    + `facts=${scenario.committed.facts.length} scene=${scenario.scene ? 'yes' : 'no'} `
    + `viewpoint=${scenario.viewpoint?.name ?? scenario.policy.viewpoint.name}`);
  if (process.argv.includes('--check-scenario')) process.exit(0);
}
const modelFile = resolve(config.modelDir, basename(config.model));
const evidence = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  strategy: null,
  config: {
    model: config.model, modelSha256: existsSync(modelFile) ? sha256(readFileSync(modelFile)) : null,
    modelBytes: existsSync(modelFile) ? statSync(modelFile).size : null,
    modes: config.modes, template: config.template, set: config.set,
    system: config.system || null,
    threads: config.numThreads, gpu: config.gpu, maxTokens: config.maxTokens,
    maxAttempts: config.maxAttempts, minChars: config.minChars,
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
  server: {
    host: '127.0.0.1', port: 0, hmr: false,
    fs: { strict: true, allow: [frontend, config.modelDir, config.inputWorktree] },
  },
  plugins: [{ name: 'narration-strategy-assets', configureServer: assetMiddleware }],
});
let browser;
try {
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({
    headless: true, channel: config.channel,
    // --force_high_performance_gpu is required for Edge to expose the NVIDIA
    // adapter; without it the run may quietly measure the integrated GPU.
    ...(config.gpu ? { args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu'] } : {}),
  });
  evidence.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  // wllama prints the ggml backend and adapter it actually used. Those lines
  // are the only proof that the weights ran on the requested adapter.
  const consoleLines = [];
  page.on('console', (message) => {
    const text = message.text();
    if (/ggml|webgpu|adapter|nvidia|vulkan/i.test(text)) consoleLines.push(text.slice(0, 300));
  });
  evidence.deviceProof = { requiredVendor: config.requireVendor || null, adapter: null, console: consoleLines };
  // Persist each finished arm from Node. Without this every result is lost if
  // the page crashes after the last arm; a run must be readable while it is
  // still going.
  const checkpoint = async (record) => {
    if (record.id === '__adapter') {
      evidence.deviceProof.adapter = record.adapter ?? null;
      const wanted = (config.requireVendor || '').toLowerCase();
      const adapter = record.adapter ?? {};
      // Chrome/Edge sometimes leave vendor empty but fill description. Match on
      // every field the browser exposes; only fail when nothing identifies the
      // adapter (then the proof is missing, so it is unverified, not "wrong").
      const identity = [adapter.vendor, adapter.architecture, adapter.device, adapter.description]
        .map((value) => String(value ?? '')).join(' ').toLowerCase();
      if (wanted && identity.trim() && !identity.includes(wanted)) {
        evidence.deviceProof.verdict = 'wrong_adapter';
        evidence.status = 'FAILED_ADAPTER';
        evidence.error = `required adapter vendor ${wanted}, got ${identity}`;
        save();
        throw new Error(evidence.error);
      }
      if (wanted && !identity.trim()) {
        evidence.deviceProof.verdict = 'adapter_unverified';
        console.warn('[adapter] browser exposed no adapter identity; backend target is unverified');
      } else {
        evidence.deviceProof.verdict = 'ok';
      }
      save();
      console.log(`[adapter] ${identity.trim() || 'identity unavailable'} verdict=${evidence.deviceProof.verdict}`);
      return;
    }
    evidence.runs = [...evidence.runs.filter((run) => run.id !== record.id), record];
    save();
    console.log(`[checkpoint] ${record.id} accepted=${record.accepted} chars=${record.chars}`);
  };
  await page.exposeFunction('__narrationCheckpoint', checkpoint);
  await page.goto(`http://127.0.0.1:${port}/__narration`);

  const result = await page.evaluate(async (config) => {
    if (!crossOriginIsolated) throw new Error('real narration run requires cross-origin isolation');
    const adapterInfo = await (async () => {
      if (!navigator.gpu) return { available: false, reason: 'navigator.gpu missing' };
      const adapter = await navigator.gpu.requestAdapter({ powerPreference: 'high-performance' });
      if (!adapter) return { available: false, reason: 'requestAdapter returned null' };
      const info = adapter.info ?? {};
      return {
        available: true,
        vendor: info.vendor ?? null, architecture: info.architecture ?? null,
        device: info.device ?? null, description: info.description ?? null,
      };
    })();
    if (window.__narrationCheckpoint) await window.__narrationCheckpoint({
      id: '__adapter', accepted: Boolean(adapterInfo.available), chars: 0, status: 'device',
      adapter: adapterInfo, attempts: [], beats: [], text: '',
    });
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const { createWllama } = await import('/src/lib/benchmark/wllama-loader.ts');
    const { IncompleteGenerationError } = await import('/src/lib/world-engine/runtime/engine.ts');
    const { generateCommittedNarration } = await import('/src/lib/world-engine/local/narration-generation/index.ts');
    const {
      renderTrainedRawPrompt, renderTrainedInstructUser, trainedSceneView, wrapChatml,
    } = await import('/src/lib/world-engine/local/narration-generation/trained-input.ts');
    const { projectCommittedNarration } = await import('/src/lib/world-engine/runtime/committed-narration.ts');
    const { legacyNarrationInput } = await import('/src/lib/world-engine/local/prompt.ts');
    const { SHORT_STATE } = await import('/src/lib/world-engine/runtime/b3-short-samples.ts');

    /** System-turn chat engine: the trained shape of the 0.5B scene candidate
     * (Qwen2.5 ChatML with a separate system message). */
    class ChatEngine {
      constructor(modelUrl, system, threads, gpu) {
        this.info = { backend: 'wllama-chat', modelId: null };
        this.modelUrl = modelUrl; this.system = system; this.threads = threads; this.gpu = gpu;
        this.instance = null; this.disposed = false;
      }
      async load() {
        const instance = await createWllama();
        const response = await fetch(this.modelUrl);
        if (!response.ok) throw new Error(`model fetch failed: ${response.status} ${this.modelUrl}`);
        const blob = await response.blob();
        await instance.loadModel([blob], {
          n_ctx: 4096, n_gpu_layers: this.gpu ? 99999 : 0, n_threads: this.threads,
        });
        if (this.disposed) { await instance.exit(); return; }
        this.instance = instance;
        this.info.modelId = this.modelUrl.split('/').pop() ?? this.modelUrl;
      }
      async complete(prompt, options = {}) {
        const instance = this.instance;
        if (!instance) throw new Error('chat engine is not loaded');
        if (options.signal?.aborted || this.disposed) throw new DOMException('Aborted', 'AbortError');
        const timeoutMs = options.timeoutMs ?? 120_000;
        const controller = new AbortController();
        const callerAbort = () => controller.abort();
        options.signal?.addEventListener('abort', callerAbort, { once: true });
        let timedOut = false;
        const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
        const started = performance.now();
        const evidence = { raw: '', finishReason: null, firstTokenMs: null, wallMs: 0 };
        try {
          const messages = [];
          if (this.system) messages.push({ role: 'system', content: this.system });
          messages.push({ role: 'user', content: prompt });
          await instance.createChatCompletion({
            messages,
            chat_template_kwargs: { enable_thinking: false },
            cache_prompt: true, stream: true,
            max_tokens: options.maxTokens ?? 256,
            temperature: options.temperature ?? 0,
            ...(options.seed !== undefined ? { seed: options.seed } : {}),
            ...(options.stop !== undefined ? { stop: options.stop } : {}),
            abortSignal: controller.signal,
            onData: (chunk) => {
              const choice = chunk.choices?.[0];
              const text = choice?.delta?.content ?? '';
              if (text && evidence.firstTokenMs === null) evidence.firstTokenMs = performance.now() - started;
              evidence.raw += text;
              if (choice?.finish_reason) evidence.finishReason = choice.finish_reason;
              if (chunk.usage) evidence.usage = chunk.usage;
              if (chunk.timings) evidence.timings = chunk.timings;
              options.onProgress?.({ raw: evidence.raw, elapsedMs: performance.now() - started });
            },
          });
          if (options.signal?.aborted || this.disposed) throw new DOMException('Aborted', 'AbortError');
          if (timedOut) throw new IncompleteGenerationError(evidence, 'generation deadline exceeded');
        } catch (error) {
          if (options.signal?.aborted || this.disposed) throw new DOMException('Aborted', 'AbortError');
          if (timedOut) {
            evidence.finishReason = 'timeout';
            throw new IncompleteGenerationError(evidence, 'generation deadline exceeded');
          }
          throw error;
        } finally {
          clearTimeout(timer);
          options.signal?.removeEventListener('abort', callerAbort);
          evidence.wallMs = performance.now() - started;
          options.onCompletion?.(evidence);
        }
        if (evidence.finishReason !== 'stop') throw new IncompleteGenerationError(evidence);
        return evidence.raw;
      }
      async dispose() {
        this.disposed = true;
        const instance = this.instance;
        this.instance = null;
        if (instance) await instance.exit();
      }
    }

    const engine = config.system
      ? new ChatEngine(config.model, config.system, config.numThreads, config.gpu)
      : new WllamaInferenceEngine({
        modelUrl: config.model, contextSize: 4096, numThreads: config.numThreads,
        ...(config.gpu ? { nGpuLayers: 99999 } : { nGpuLayers: 0 }),
      });
    const loadStarted = performance.now();
    // Bounded load: a stuck fetch/compile must not hold the queue forever.
    await Promise.race([
      engine.load(),
      new Promise((_, reject) => setTimeout(() => reject(new Error(`model load exceeded ${config.loadTimeoutMs} ms`)), config.loadTimeoutMs)),
    ]);
    const loadMs = performance.now() - loadStarted;

    const clone = (value) => JSON.parse(JSON.stringify(value));
    const position = (containerId) => ({ containerId, slotId: null, relativeTo: null });

    /** Scene material for the beat prompts: location description, who is
     * visible, visible objects. Read from the already-settled state. */
    const sceneFrom = (state, viewId) => {
      const view = state.characters[viewId];
      const containerId = view.position.containerId;
      const nameOf = (id) => state.initial.locations[id]?.name ?? state.initial.items[id]?.name
        ?? state.initial.characters[id]?.name ?? id;
      const notesOf = (entity, base) => [
        base,
        ...entity.appearanceChanges.filter((change) => change.supersedes.length === 0 && change.text).map((change) => change.text),
      ].filter(Boolean);
      const inPlace = Object.keys(state.characters).filter((id) => id !== viewId
        && state.characters[id].position.containerId === containerId);
      return {
        location: nameOf(containerId),
        placeNotes: notesOf(state.locations[containerId] ?? { appearanceChanges: [] },
          state.initial.locations[containerId]?.initialAppearance ?? ''),
        present: [viewId, ...inPlace].map((id) => ({
          name: state.initial.characters[id].name,
          note: notesOf(state.characters[id], state.initial.characters[id].initialAppearance)[0],
        })),
        objects: Object.keys(state.items)
          .filter((id) => state.items[id].position.containerId === containerId)
          .map((id) => ({
            name: state.initial.items[id].name,
            note: notesOf(state.items[id], state.initial.items[id].initialAppearance)[0],
          })),
      };
    };

    const entitiesOf = (state) => [
      ...Object.values(state.initial.characters).map((entity) => entity.name),
      ...Object.values(state.initial.locations).map((entity) => entity.name),
      ...Object.values(state.initial.items).map((entity) => entity.name),
    ];

    const read = (pointId, previousPointId, version, state, timeAdvance, entityDeltas) => ({
      pointId, previousPointId, version, stateDigest: pointId, state, timeAdvance, entityDeltas,
    });

    // ---- dev world: the short state used by the earlier probes -----------
    const rootState = clone(SHORT_STATE);
    const devReader = {
      root: read('root', null, 0, rootState, null, {}),
      move: (() => {
        const state = clone(rootState);
        state.characters.person_a.position = position('hall');
        state.time = { ...state.time, dateTime: '2026-10-27T09:00:01' };
        return read('point_1', 'root', 1, state,
          { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
          { person_a: { entityId: 'person_a', positionSet: position('hall') } });
      })(),
      elapsed: null,
    };
    devReader.elapsed = (() => {
      const state = clone(devReader.move.state);
      state.time = { ...state.time, dateTime: '2026-10-27T09:02:01' };
      return read('point_2', 'point_1', 2, state,
        { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } }, {});
    })();

    // ---- unseen world: different names, nested locations, task + item --
    const unseenTime = { calendar: 'gregorian', dateTime: '2026-11-02T20:10:00', instantOrdinal: 0 };
    const unseenTask = {
      id: 'task_ledger', ownerId: 'char_yu', parentTaskId: null,
      goal: '把账本送回二楼库房', status: 'pending',
    };
    const unseenState = {
      engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_unseen', protagonistId: 'char_yu',
      time: unseenTime,
      initial: {
        engineVersion: 'world-engine-v1', schemaVersion: 1, worldId: 'world_unseen', protagonistId: 'char_yu',
        initialTime: unseenTime,
        locations: {
          stairs: { id: 'stairs', name: '楼梯间', parentLocationId: null, initialAppearance: '水泥台阶，扶手冰凉。' },
          storeroom: { id: 'storeroom', name: '二楼库房', parentLocationId: 'stairs', initialAppearance: '一排樟木柜，灯管有一支在闪。' },
          landing: { id: 'landing', name: '二楼平台', parentLocationId: 'stairs', initialAppearance: '窗子关着，玻璃上有一层灰。' },
        },
        items: {
          ledger: {
            id: 'ledger', name: '账本', initialPosition: position('landing'),
            initialAppearance: '牛皮纸封面，边角卷起。',
          },
        },
        characters: {
          char_yu: {
            id: 'char_yu', name: '余晚', initialPosition: position('landing'),
            initialAppearance: '穿深绿外套。', initialPersonality: '寡言，做事慢',
            initialSanity: 8, tasks: { task_ledger: unseenTask },
          },
          char_luo: {
            id: 'char_luo', name: '罗青', initialPosition: position('storeroom'),
            initialAppearance: '袖子挽到手肘。', initialPersonality: '急性子，爱较真',
            initialSanity: 9, tasks: {},
          },
        },
      },
      locations: {
        stairs: { id: 'stairs', appearanceChanges: [] },
        storeroom: { id: 'storeroom', appearanceChanges: [] },
        landing: { id: 'landing', appearanceChanges: [] },
      },
      items: { ledger: { id: 'ledger', position: position('landing'), appearanceChanges: [] } },
      characters: {
        char_yu: {
          id: 'char_yu', position: position('landing'), appearanceChanges: [],
          personalityChanges: [], sanity: 8, tasks: { task_ledger: unseenTask },
        },
        char_luo: {
          id: 'char_luo', position: position('storeroom'), appearanceChanges: [],
          personalityChanges: [], sanity: 9, tasks: {},
        },
      },
    };
    const unseenRoot = read('u_root', null, 0, unseenState, null, {});
    // The committed-narration projector in this baseline refuses any change to
    // state.items / state.locations (only character state may move), so the
    // unseen point moves a character. Item moves are an upstream limitation,
    // recorded in the handoff, not something this probe can work around.
    const unseenMove = (() => {
      const state = clone(unseenState);
      state.characters.char_luo.position = position('landing');
      state.time = { ...state.time, dateTime: '2026-11-02T20:11:00' };
      return read('u_point_1', 'u_root', 1, state,
        { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
        { char_luo: { entityId: 'char_luo', positionSet: position('landing') } });
    })();

    const scenarios = [];
    if (config.scenario) {
      const s = config.scenario;
      scenarios.push({
        id: s.id, note: s.note ?? 'caller-supplied scenario',
        before: null, after: null,
        delta: { timeAdvance: s.time ?? null, entityDeltas: {} },
        time: s.time ?? null,
        committed: s.committed, inputText: s.inputText,
        view: s.viewpoint?.id ?? s.policy?.viewpoint?.id,
        policy: s.policy, scene: s.scene ?? null,
        continuation: false,
      });
    }
    const addDev = () => {
      scenarios.push({
        id: 'root-scene', before: null, after: devReader.root,
        delta: { timeAdvance: null, entityDeltas: {} }, time: null,
        note: 'No committed change: scene grounding only. Any new event/standing claim must be rejected.',
      });
      scenarios.push({
        id: 'move-direction', before: devReader.root, after: devReader.move,
        delta: { timeAdvance: devReader.move.timeAdvance, entityDeltas: devReader.move.entityDeltas },
        time: devReader.move.timeAdvance,
        note: 'Mandatory fact: 林川 move 走廊→门厅; POV 周宁 stays in 走廊.',
      });
      scenarios.push({
        id: 'elapsed-two-minutes', before: devReader.move, after: devReader.elapsed,
        delta: { timeAdvance: devReader.elapsed.timeAdvance, entityDeltas: {} },
        time: devReader.elapsed.timeAdvance,
        note: 'Empty delta plus elapsed 2 minutes: time must be narrated; no new change may be invented.',
      });
    };
    const addUnseen = () => {
      scenarios.push({
        id: 'unseen-item-move', before: unseenRoot, after: unseenMove,
        delta: { timeAdvance: unseenMove.timeAdvance, entityDeltas: unseenMove.entityDeltas },
        time: unseenMove.timeAdvance,
        note: 'Unseen world: 罗青 moves 二楼库房→二楼平台 in one minute; POV 余晚 stays on the landing.',
      });
    };
    const addContinuation = () => {
      scenarios.push({
        id: 'continuation-after-move', before: devReader.move, after: devReader.elapsed,
        delta: { timeAdvance: devReader.elapsed.timeAdvance, entityDeltas: {} },
        time: devReader.elapsed.timeAdvance, continuation: true,
        note: 'Second turn of the dev world: previous accepted prose is passed as priorText.',
      });
    };
    if (!config.scenario) {
      if (config.set === 'dev' || config.set === 'all') addDev();
      if (config.set === 'unseen' || config.set === 'all') addUnseen();
      if (config.set === 'continuation' || config.set === 'all') addContinuation();
    } else if (config.withDev) {
      // Only the two points that carry a settled change and a required time.
      addDev();
      const quietRoot = scenarios.findIndex((entry) => entry.id === 'root-scene');
      if (quietRoot >= 0) scenarios.splice(quietRoot, 1);
    }

    const runs = [];
    // Only a continuation scenario receives the previous scene. Reusing it
    // across unrelated worlds would compare prose that never shared context
    // and report a false echo.
    const priorFor = new Map();
    for (let index = 1; index < scenarios.length; index += 1) {
      const previous = scenarios[index - 1];
      if (scenarios[index].continuation) priorFor.set(scenarios[index].id, previous.text ?? null);
    }
    for (const scenario of scenarios) {
      const priorText = priorFor.get(scenario.id) ?? null;
      const committed = scenario.committed
        ?? projectCommittedNarration(scenario.after, scenario.before ?? null);
      const view = scenario.view ?? scenario.after.state.protagonistId;
      const inputText = scenario.inputText ?? await (async () => {
        if (config.modes.includes('beats') || config.template === 'legacy') {
          return legacyNarrationInput(scenario.before?.state ?? null, scenario.delta, scenario.after.state, view);
        }
        if (config.template === 'v2') {
          const input = await import(
            `/@fs/${config.inputWorktree}/frontend/src/lib/world-engine/local/narration-input/index.ts`
          );
          const built = input.buildNarrationInput({
            // Root point: no previous state exists; the settled after-state
            // is the snapshot, with the empty delta the root already has.
            before: scenario.before?.state ?? scenario.after.state,
            after: scenario.after.state,
            delta: scenario.delta.entityDeltas,
            timeAdvance: scenario.delta.timeAdvance,
            viewpointId: view,
          }, { model: 'result-v2', checkTokenizer: false });
          return built.rendered.text;
        }
        const trained = trainedSceneView({
          before: scenario.before?.state ?? null,
          after: scenario.after.state,
          delta: scenario.delta.entityDeltas,
          timeAdvance: scenario.delta.timeAdvance,
          viewpointId: view,
        });
        if (config.template === 'trained-instruct') {
          const system = config.instruction || '你是叙事引擎。根据给定的世界状态写出这一回合的小说正文。'
            + '只写已结算的事实，不新增人物、物品、事件、往事或承诺；对话用「」；直接输出正文，不写标题或说明。';
          return wrapChatml(system, renderTrainedInstructUser(trained));
        }
        return renderTrainedRawPrompt(trained);
      })();
      for (const mode of config.modes) {
      const streamed = [];
      let firstTextMs = null;
      let progressEvents = 0;
      const started = performance.now();
      const generated = await generateCommittedNarration({
        engine, committed, inputText, priorText,
        onProgress: (state) => {
          progressEvents += 1;
          if (firstTextMs === null && state.text.trim().length >= 20) firstTextMs = performance.now() - started;
          streamed.push({ status: state.status, chars: [...state.text].length, verified: state.verified });
        },
        policy: scenario.policy ? {
          ...scenario.policy,
          // CLI knobs win over the fixture's defaults so one command measures
          // the same input under an explicit decoder/length setting.
          maxTokens: config.maxTokens,
          minChars: config.minChars,
          mode: mode === 'beats' ? 'beats' : 'scene',
          ...(mode === 'prose' ? { promptShape: 'prose-facts' } : {}),
          scene: mode === 'beats' ? (scenario.scene ?? null) : (scenario.scene ?? null),
          time: scenario.time,
          ...(config.instruction ? { instruction: config.instruction } : {}),
        } : {
          mode: mode === 'beats' ? 'beats' : 'scene',
          ...(mode === 'prose' ? { promptShape: 'prose-facts' } : {}),
          scene: sceneFrom(scenario.after.state, view),
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
          knownEntities: entitiesOf(scenario.after.state),
          time: scenario.time,
          minChars: config.minChars, targetChars: 240,
          maxAttempts: config.maxAttempts, maxTokens: config.maxTokens, maxTokensCeiling: 700,
          beatAttempts: config.maxAttempts,
          temperature: 0.7, retryTemperature: 0.5, seed: 42,
          deadlineMs: 300_000, timeoutMs: 150_000,
          ...(config.instruction ? { instruction: config.instruction } : {}),
        },
      });
      const wallMs = performance.now() - started;
      scenario.text = generated.accepted ? generated.text : null;
      const record = {
        id: `${scenario.id}::${mode}`, mode, note: scenario.note,
        inputChars: inputText.length, inputText,
        accepted: generated.accepted, status: generated.status, strategyVersion: generated.strategyVersion,
        text: generated.text, chars: [...generated.text].length,
        wallMs, firstTextMs, timings: generated.timings, metrics: generated.metrics,
        ledger: {
          mandatory: generated.ledger.mandatory.map((fact) => ({ id: fact.id, kind: fact.kind })),
          optional: generated.ledger.optional.length,
          requireTime: generated.ledger.requireTime,
          licensedEntities: generated.ledger.licensedEntities,
          allowedEvents: generated.ledger.allowedEvents,
        },
        beats: (generated.beats ?? []).map((beat) => ({
          beatId: beat.beatId, kind: beat.kind, directive: beat.directive,
          text: beat.text, source: beat.source, attempts: beat.attempts,
          durationMs: beat.durationMs,
          issues: beat.issues.map((issue) => ({ kind: issue.kind, severity: issue.severity, detail: issue.detail, sentence: issue.sentence })),
          prompts: beat.prompts,
          raws: beat.raws,
        })),
        assembly: generated.assembly,
        // Same per-paragraph provenance lane 04's constrained candidate reports,
        // so one adapter can treat both candidates the same way.
        segments: generated.segments,
        beatCounts: generated.beatCounts,
        mixed: generated.mixed,
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
          repairedIssues: attempt.repairedIssues ?? null,
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
      // Per-arm checkpoint: raw prompt/text/attempts/timings/provenance land on
      // disk as soon as this arm finishes, not after the whole evaluate returns.
      if (typeof window !== 'undefined' && window.__narrationCheckpoint) {
        await window.__narrationCheckpoint(clone(record));
      }
      console.log(`[narration] ${scenario.id} [${mode}]: accepted=${generated.accepted} status=${generated.status} `
        + `chars=${record.chars} wallMs=${Math.round(wallMs)} attempts=${generated.rawAttempts.length} `
        + `beats=${(generated.beats ?? []).map((beat) => beat.source).join(',')}`);
      }
    }
    const info = engine.info;
    const diagnostics = engine.diagnostics;
    await engine.dispose();
    return { loadMs, info, diagnostics, runs };
  }, config);

  evidence.status = 'DONE';
  evidence.deviceProof.console = consoleLines.slice(-40);
  evidence.loadMs = result.loadMs;
  evidence.engine = { info: result.info, diagnostics: result.diagnostics };
  evidence.runs = result.runs.length ? result.runs : evidence.runs;
  evidence.strategy = evidence.runs[0]?.strategyVersion ?? null;
  save();
  const summary = result.runs.map((run) => ({
    id: run.id, accepted: run.accepted, status: run.status, chars: run.chars,
    attempts: run.attempts.length, beats: run.beats.map((beat) => beat.source),
    wallMs: Math.round(run.wallMs),
    hardIssues: run.attempts.map((attempt) => attempt.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind)),
  }));
  console.log(JSON.stringify({ out: config.out, model: config.model, loadMs: Math.round(result.loadMs), summary }, null, 2));
} catch (error) {
  // Never overwrite a more specific verdict (wrong adapter) with a generic one,
  // and keep whatever arms already reached their checkpoint.
  if (evidence.status !== 'FAILED_ADAPTER') evidence.status = 'FAILED';
  evidence.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  evidence.completedArms = evidence.runs.map((run) => run.id);
  save();
  throw error;
} finally {
  await browser?.close();
  await server.close();
}
