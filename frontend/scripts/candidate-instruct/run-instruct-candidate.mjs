// Real-model run for the A-route instruct narration candidate.
//
// Loads a native instruct GGUF (Qwen2.5-1.5B-Instruct / Qwen3-1.7B) in
// headless Edge through the same WllamaInferenceEngine the page uses, builds
// settled points from the shipped free-day world with the real kernel
// (`applyPoint`), projects the facts with the page's narrow derivation, and
// calls `generateCandidate` exactly as the page would.
//
// It records, per case: the exact prompt, every raw completion (including a
// rejected repair attempt), the cleaned prose, the verdict, the issue list,
// first-token / full time, and the model's own completion evidence (token
// counts, finish reason). The archive is evidence for human reading; the only
// asserted invariants are structural (codec/verdict consistency, no thinking
// text in accepted prose, rejected drafts labelled rejected).
//
//   python ../../.local/parallel-local-game/resource_lease.py acquire --lane 03-actions --purpose "instruct candidate run"
//   node scripts/candidate-instruct/run-instruct-candidate.mjs \
//        --assets D:/others/Jity/.local/world-narration-worktree/frontend/public \
//        --model /models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
//        --out ../artifacts/candidate-instruct/run-qwen25-1.5b.json
//   python ../../.local/parallel-local-game/resource_lease.py release --lane 03-actions
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { cpus } from 'node:os';
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import { chromium } from '@playwright/test';

const frontend = fileURLToPath(new URL('../../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const hasFlag = (flag) => process.argv.includes(flag);
const config = {
  model: option('--model', '/models/qwen2.5-1.5b-instruct-q4_k_m.gguf'),
  assets: resolve(option('--assets', resolve(frontend, 'public'))),
  contextSize: Number(option('--context', '4096')),
  numThreads: Number(option('--threads', '6')),
  channel: option('--channel', 'msedge'),
  seed: Number(option('--seed', '42')),
  temperature: Number(option('--temperature', '0.6')),
  retryTemperature: Number(option('--retry-temperature', '0.35')),
  timeoutMs: Number(option('--timeout', '180000')),
  maxTokens: Number(option('--max-tokens', '520')),
  maxAttempts: Number(option('--max-attempts', '2')),
  targetChars: Number(option('--target-chars', '220')),
  styleSample: option('--style-sample', ''),
  variant: option('--variant', 'plain'),
  loader: option('--loader', ''),
  gpu: hasFlag('--gpu'),
  dry: hasFlag('--dry'),
  only: option('--cases', '') ? option('--cases', '').split(',') : null,
};
const output = resolve(frontend, option('--out', '../.local/candidate-instruct.json'));
const sha = (bytes) => createHash('sha256').update(bytes).digest('hex');
const fileSha = (path) => sha(readFileSync(path));
const git = (...args) => execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root, ...args], { encoding: 'utf8' }).trim();
const assetPath = resolve(config.assets, config.model.replace(/^\//, ''));

// ── Cases ──────────────────────────────────────────────────────────────────
// Each case is a settled point: `patches` are applied with the real kernel,
// `delta` is the entity delta of that point. Names/rooms come from the
// shipped world, so the projection is the actual scene, not a fixture.
const CASES = [
  {
    id: 'S0-root-open',
    note: '开局点：没有任何结算变化，只有初始场景（自由一日服务巷，15:20）',
    playerInput: null,
    patches: [],
    time: null,
  },
  {
    id: 'S1-move-time',
    note: '主角从服务巷走到器材棚，时间 2 分钟；棚里有人和器材',
    playerInput: '我把护目镜推上去，朝器材棚走过去。',
    patches: [{ entityId: 'lu', containerId: 'shed', slotId: null }],
    time: { boundary: 'elapsed', duration: { amount: 2, unit: 'minute' } },
  },
  {
    id: 'S2-task-sanity',
    note: '诺诺修好短讯机（任务达成），精神值 58→60；两人都在服务巷',
    playerInput: '我看着她把电池按进短讯机。',
    patches: [],
    delta: {
      sanity: { nono: 60 },
      tasksAchieved: { nono: ['task_nono_battery'] },
      personality: { nono: [{ id: 'chg_nono_1', text: '说话时不再把注意力全压在短讯机上', supersedes: [] }] },
    },
    time: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
  },
  {
    id: 'S3-item-give',
    note: '诺诺把短讯机递给主角（物品换手），没有位置/任务事实',
    playerInput: '我伸手接过诺诺递来的短讯机。',
    patches: [{ entityId: 'radio_nono', containerId: 'lu', slotId: 'slot_body' }],
    time: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
  },
  {
    id: 'S4-empty-time',
    note: '空增量点：没有实体变化，只有 1 分钟时间推进',
    playerInput: '我靠着墙，听巷口的动静。',
    patches: [],
    time: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
  },
  {
    id: 'S5-continuity',
    note: '连续点：上一段为 S1 的正文，主角再从器材棚回到服务巷',
    playerInput: '我拎着护目镜，退回服务巷。',
    basePatches: [{ entityId: 'lu', containerId: 'shed', slotId: null }],
    patches: [{ entityId: 'lu', containerId: 'lane', slotId: 'slot_wall' }],
    time: { boundary: 'elapsed', duration: { amount: 1, unit: 'minute' } },
    priorFrom: 'S1-move-time',
  },
  {
    id: 'S6-two-actors',
    note: '两人同时移动：主角与诺诺一起进中央庭院，时间 3 分钟',
    playerInput: '我和诺诺沿着墙根走进庭院。',
    patches: [
      { entityId: 'lu', containerId: 'yard', slotId: null },
      { entityId: 'nono', containerId: 'yard', slotId: null },
    ],
    time: { boundary: 'elapsed', duration: { amount: 3, unit: 'minute' } },
  },
];

const selected = config.only ? CASES.filter((entry) => config.only.includes(entry.id)) : CASES;
const report = {
  status: 'RUNNING',
  recordedAt: new Date().toISOString(),
  candidate: 'instruct-narration-candidate',
  model: config.model,
  config: {
    contextSize: config.contextSize, numThreads: config.numThreads,
    temperature: config.temperature, retryTemperature: config.retryTemperature,
    maxTokens: config.maxTokens, maxAttempts: config.maxAttempts, targetChars: config.targetChars,
    seed: config.seed, styleSample: config.styleSample || null,
  },
  source: {
    head: git('rev-parse', 'HEAD'),
    status: git('status', '--porcelain'),
    sha256: {},
  },
  assets: {
    model: config.model,
    modelSha256: existsSync(assetPath) ? fileSha(assetPath) : null,
    modelBytes: existsSync(assetPath) ? statSync(assetPath).size : null,
    wllamaSha256: existsSync(resolve(config.assets, 'wllama/index.min.js')) ? fileSha(resolve(config.assets, 'wllama/index.min.js')) : null,
    wasmSha256: existsSync(resolve(config.assets, 'wasm/wllama.wasm')) ? fileSha(resolve(config.assets, 'wasm/wllama.wasm')) : null,
  },
  device: { cpu: cpus()[0]?.model, logicalCpus: cpus().length },
  cases: selected.map(({ id, note }) => ({ id, note })),
  runs: [],
};
for (const file of [
  'src/lib/world-engine/local/narration-candidates/instruct/index.ts',
  'src/lib/world-engine/local/narration-candidates/instruct/projection.ts',
  'src/lib/world-engine/local/narration-candidates/instruct/prompt.ts',
  'src/lib/world-engine/local/narration-candidates/instruct/verify.ts',
  'src/lib/world-engine/local/narration-candidates/instruct/facts.ts',
  'src/lib/world-engine/local/narration-candidates/instruct/template.ts',
  'src/lib/world-engine/local/narration-candidates/instruct/clean.ts',
  'src/lib/world-engine/local/state.ts',
  'src/lib/world-engine/local/prompt.ts',
  'src/lib/world-engine/runtime/narration-alignment.ts',
  'src/lib/world-engine/runtime/committed-narration.ts',
]) report.source.sha256[file] = fileSha(resolve(frontend, file));
const save = () => { mkdirSync(dirname(output), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();

function assetMiddleware(vite) {
  vite.middlewares.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    const url = (req.url ?? '').split('?')[0];
    if (url === '/__candidate') {
      res.setHeader('Content-Type', 'text/html');
      res.end('<!doctype html><meta charset="utf-8"><title>Instruct candidate</title><body></body>');
      return;
    }
    const asset = /^\/(models|wllama|wasm)\//.exec(url);
    if (!asset) { next(); return; }
    const file = resolve(config.assets, url.slice(1));
    if (!existsSync(file)) { next(); return; }
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript'
      : file.endsWith('.wasm') ? 'application/wasm' : 'application/octet-stream');
    res.setHeader('Content-Length', statSync(file).size);
    createReadStream(file).pipe(res);
  });
}

/** Build a settled point in the browser context and return the plain case
 * data (state before/after, delta, packet) — the module does the projection. */
const buildCaseSource = String.raw`
  async (entry, priorText) => {
    const { buildInitialState, applyPoint } = await import('/src/lib/world-engine/local/state.ts');
    const { projectFacts } = await import('/src/lib/world-engine/local/narration-candidates/instruct/facts.ts');
    const world = await (await fetch('/worlds/dragon-raja-free-day.world.json')).json();
    const initial = buildInitialState({ ...world.initial, worldId: world.worldId });
    const move = (state, patches) => {
      const next = structuredClone(state);
      for (const patch of patches ?? []) {
        const entity = next.characters[patch.entityId] ?? next.items[patch.entityId];
        entity.position = { containerId: patch.containerId, slotId: patch.slotId ?? null, relativeTo: null };
      }
      return next;
    };
    const before = move(initial, entry.basePatches);
    const target = move(before, entry.patches);
    const entityDeltas = {};
    for (const [id, entity] of Object.entries(target.characters)) {
      const previous = before.characters[id];
      if (JSON.stringify(previous.position) !== JSON.stringify(entity.position)) {
        entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), positionSet: entity.position };
      }
      if (entry.delta?.sanity?.[id] !== undefined) {
        entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), sanitySet: entry.delta.sanity[id] };
      }
      if (entry.delta?.tasksAchieved?.[id]?.length) {
        entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), tasksAchieved: entry.delta.tasksAchieved[id] };
      }
      if (entry.delta?.personality?.[id]?.length) {
        entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), personalityChanges: entry.delta.personality[id] };
      }
    }
    for (const [id, entity] of Object.entries(target.items)) {
      const previous = before.items[id];
      if (JSON.stringify(previous.position) !== JSON.stringify(entity.position)) {
        entityDeltas[id] = { ...(entityDeltas[id] ?? { entityId: id }), positionSet: entity.position };
      }
    }
    const timeAdvance = entry.time;
    const point = {
      worldId: initial.worldId, id: 'point_case', sequence: 1, kind: 'normal', previousPointId: 'root',
      roundId: 'round_case', advanceId: 'advance_case', trigger: 'player', linkedFromPointId: null,
      timeAdvance: timeAdvance ?? { boundary: 'instant', duration: { amount: 0, unit: 'second' } },
      entityDeltas,
    };
    const after = applyPoint(target, point);
    const packet = projectFacts(before, { timeAdvance, entityDeltas }, after);
    return {
      state: after, before, delta: { timeAdvance, entityDeltas }, committed: packet,
      playerInput: entry.playerInput, priorText: priorText ?? null,
      room: after.initial.locations[after.characters[after.protagonistId].position.containerId]?.name,
      entities: Object.keys(entityDeltas),
    };
  }
`;

let browser;
let server;
try {
  server = await createServer({ root: frontend, configFile: false, logLevel: 'warn',
    cacheDir: '../.local/candidate-instruct-vite', server: { host: '127.0.0.1', port: 0, hmr: false, fs: { allow: [frontend, resolve(frontend, '../..')] } },
    plugins: [{ name: 'candidate-instruct', configureServer: assetMiddleware }] });
  await server.listen();
  const port = server.httpServer.address().port;
  browser = await chromium.launch({ headless: true, channel: config.channel });
  report.browser = browser.version();
  const page = await browser.newPage();
  page.on('pageerror', (error) => console.error('[pageerror]', error.message));
  await page.goto(`http://127.0.0.1:${port}/__candidate`);

  if (config.dry) {
    const rows = [];
    for (const entry of selected) {
      const built = await page.evaluate(new Function('entry', `return (${buildCaseSource})(entry, null);`), entry);
      const preview = await page.evaluate(async ({ built, config }) => {
        const mod = await import('/src/lib/world-engine/local/narration-candidates/instruct/index.ts');
        const fake = { info: { backend: 'fake', modelId: 'dry' }, load: async () => {}, dispose: async () => {},
          complete: async (prompt) => { fake.lastPrompt = prompt; return ''; }, lastPrompt: '' };
        const result = await mod.generateCandidate({
          engine: fake, committed: built.committed, state: built.state, before: built.before, delta: built.delta,
          playerInput: built.playerInput, policy: { template: 'qwen2.5-instruct', promptMode: 'raw', targetChars: config.targetChars, maxAttempts: 1 },
        });
        return { prompt: result.prompt, promptChars: result.prompt.length, projection: {
          place: result.projection.place.name, time: result.projection.time,
          characters: result.projection.characters.map((c) => c.name), items: result.projection.items.map((i) => i.name),
          facts: result.projection.facts.map((f) => f.statement),
        } };
      }, { built, config });
      rows.push({ caseId: entry.id, note: entry.note, ...preview });
      console.log(`[candidate] dry ${entry.id}: ${preview.promptChars} chars, ${preview.projection.facts.length} facts`);
    }
    report.dryRuns = rows;
    if (config.loader) {
      report.loaderCheck = await page.evaluate(async (config) => {
        const url = '/@fs/' + config.loader.replaceAll(String.fromCharCode(92), '/');
        const loader = await import(/* @vite-ignore */ url);
        const file = config.model.split('/').pop() ?? '';
        const spec = loader.modelSpecByFile(file);
        return { exports: Object.keys(loader).sort(), spec: spec.id, file: spec.gguf };
      }, config);
      console.log(`[candidate] loader check: ${report.loaderCheck.spec} (${report.loaderCheck.file})`);
    }
    report.status = 'DRY';
    save();
  } else {
    const loaded = await page.evaluate(async (config) => {
      if (!crossOriginIsolated) throw new Error('candidate run requires cross-origin isolation');
      if (config.loader) {
        // Product parity: 08's loader builds the engine with the checkpoint's
        // real chat template and exposes chat(messages). Read-only import.
        const url = '/@fs/' + config.loader.replaceAll(String.fromCharCode(92), '/');
        const loader = await import(/* @vite-ignore */ url);
        const file = config.model.split('/').pop() ?? '';
        const spec = loader.modelSpecByFile(file);
        const loaded = await loader.loadCandidateModel(spec, {
          modelRoot: '/models', preferGpu: config.gpu, forceCpu: !config.gpu,
          contextSize: config.contextSize, numThreads: config.numThreads,
        });
        window.__candidate = { engine: loaded.engine };
        return {
          loadMs: Math.round(loaded.loadMs), topology: null, info: loaded.engine.info,
          loader: { backend: loaded.backend, fallback: loaded.fallback, spec: spec.id,
            attempts: loaded.attempts?.map((entry) => ({ backend: entry.backend, ok: entry.ok, loadMs: Math.round(entry.loadMs ?? 0), error: entry.error ?? null })) },
        };
      }
      const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
      const engine = new WllamaInferenceEngine({ modelUrl: config.model, contextSize: config.contextSize, numThreads: config.numThreads, directBlob: true });
      const started = performance.now();
      await engine.load();
      window.__candidate = { engine };
      return { loadMs: Math.round(performance.now() - started), topology: engine.diagnostics, info: engine.info, loader: null };
    }, config);
    report.loadMs = loaded.loadMs;
    report.topology = loaded.topology;
    report.engineInfo = loaded.info;
    report.loader = loaded.loader;
    save();
    console.log(`[candidate] model loaded in ${loaded.loadMs}ms (${JSON.stringify(loaded.topology)})`);

    const texts = new Map();
    for (const entry of selected) {
      const priorText = entry.priorFrom ? texts.get(entry.priorFrom) ?? null : null;
      const built = await page.evaluate(new Function('payload', `return (${buildCaseSource})(payload.entry, payload.priorText);`), { entry, priorText });
      console.log(`[candidate] ${entry.id} room=${built.room} entities=${built.entities.join(',')}`);
      const row = await page.evaluate(async ({ built, config }) => {
        const mod = await import('/src/lib/world-engine/local/narration-candidates/instruct/index.ts');
        const started = performance.now();
        const progress = [];
        const result = await mod.generateCandidate({
          engine: window.__candidate.engine,
          pointId: 'point_case',
          committed: built.committed,
          state: built.state,
          before: built.before,
          delta: built.delta,
          playerInput: built.playerInput,
          priorText: built.priorText,
          policy: {
            template: 'qwen2.5-instruct', targetChars: config.targetChars,
            maxAttempts: config.maxAttempts, maxTokens: config.maxTokens,
            temperature: config.temperature, retryTemperature: config.retryTemperature,
            seed: config.seed, timeoutMs: config.timeoutMs,
            variant: config.variant === 'scene-first' ? 'scene-first' : 'plain',
            ...(config.styleSample ? { styleSample: config.styleSample } : {}),
          },
          onProgress: (state) => progress.push({ status: state.status, chars: state.text.length, elapsedMs: Math.round(state.elapsedMs) }),
        });
        return {
          wallMs: Math.round(performance.now() - started),
          accepted: result.accepted, status: result.status, text: result.text,
          template: result.template, strategyVersion: result.strategyVersion,
          timings: result.timings, issues: result.issues,
          attempts: result.rawAttempts.map((attempt) => ({
            attempt: attempt.attempt, durationMs: Math.round(attempt.durationMs),
            firstTokenMs: attempt.firstTokenMs === null ? null : Math.round(attempt.firstTokenMs),
            raw: attempt.raw, cleaned: attempt.cleaned, accepted: attempt.accepted,
            finishReason: attempt.finishReason, error: attempt.error,
            issues: attempt.issues,
          })),
          projection: {
            viewpoint: result.projection.viewpoint.name, place: result.projection.place.name,
            time: result.projection.time, characters: result.projection.characters.map((c) => c.name),
            items: result.projection.items.map((i) => i.name),
            facts: result.projection.facts.map((f) => ({ kind: f.kind, statement: f.statement, mandatory: f.mandatory })),
            playerAction: result.projection.playerAction,
          },
          progressTail: progress.slice(-3),
          progressEvents: progress.length,
        };
      }, { built, config });
      report.runs.push({ caseId: entry.id, note: entry.note, playerInput: entry.playerInput, time: entry.time, ...row });
      if (row.accepted) texts.set(entry.id, row.text);
      save();
      const hard = row.issues.filter((issue) => issue.severity === 'hard').map((issue) => issue.kind);
      console.log(`[candidate] ${entry.id}: ${row.accepted ? 'ACCEPTED' : 'REJECTED'} ${row.text.length} chars `
        + `${row.wallMs}ms attempts=${row.attempts.length} hard=${hard.join(',') || '-'}`);
      for (const attempt of row.attempts) console.log(`    #${attempt.attempt} ${attempt.durationMs}ms first=${attempt.firstTokenMs}ms: ${attempt.raw.slice(0, 200).replace(/\n/g, ' ')}`);
    }

    // Structural invariants only; semantic quality is for human reading.
    for (const run of report.runs) {
      assert.ok(run.attempts.length >= 1, `${run.caseId}: no model call`);
      assert.ok(run.attempts.length <= config.maxAttempts, `${run.caseId}: exceeded max attempts`);
      if (run.accepted) {
        assert.ok(!/<think>|Thinking Process|思考过程/.test(run.text), `${run.caseId}: thinking leaked into accepted prose`);
        assert.ok(run.text.length > 0, `${run.caseId}: accepted with empty text`);
      } else {
        assert.ok(run.issues.some((issue) => issue.severity === 'hard'), `${run.caseId}: rejected without a hard issue`);
      }
      for (const attempt of run.attempts) {
        assert.ok(attempt.raw !== undefined, `${run.caseId}: raw evidence missing`);
      }
    }
    const all = report.runs.flatMap((run) => run.attempts);
    const times = all.map((attempt) => attempt.durationMs).sort((a, b) => a - b);
    const firsts = all.map((attempt) => attempt.firstTokenMs).filter((value) => typeof value === 'number').sort((a, b) => a - b);
    report.summary = {
      cases: report.runs.length,
      calls: all.length,
      accepted: report.runs.filter((run) => run.accepted).length,
      meanCallMs: times.length ? Math.round(times.reduce((sum, value) => sum + value, 0) / times.length) : null,
      p50CallMs: times.length ? times[Math.floor(times.length / 2)] : null,
      maxCallMs: times.length ? times[times.length - 1] : null,
      p50FirstTokenMs: firsts.length ? firsts[Math.floor(firsts.length / 2)] : null,
      issueCounts: all.flatMap((attempt) => attempt.issues).reduce((counts, issue) => {
        counts[issue.kind] = (counts[issue.kind] ?? 0) + 1; return counts;
      }, {}),
    };
    report.status = 'COMPLETED';
  }
  report.completedAt = new Date().toISOString();
  save();
  console.log(`[candidate] done: ${report.runs.length} cases, archive ${output}`);
} catch (error) {
  report.status = 'INTERRUPTED';
  report.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  save();
  throw error;
} finally {
  if (browser) await browser.close();
  if (server) await server.close();
  report.cleanup = { browserClosed: Boolean(browser), serverClosed: Boolean(server) };
  save();
}
