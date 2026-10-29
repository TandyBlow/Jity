// B3: real settlement-task port adaptation and the minimal semantic baseline
// (§798 stage 6). The wllama adapter's chat template, constrained decoding
// and timing fixes are already delivered — this batch asks whether the model
// can actually CARRY action / targets / reaction / results / six-stage
// updates / continuation, with identity allocation, dice, permanent IDs and
// state application staying program-owned.
//
//   tasks   task-level probes over a real world snapshot: role attribution,
//           consumed input, joint results, update-stage dependencies,
//           continuation conditions. Structure rate and semantic rate are
//           counted separately; raw failures and full call costs retained.
//   action  minimal real scene: one normal action point where the settlement
//           candidates come from the MODEL (not the rule authority).
//   chain   minimal real scene: joint settlement with real server d20, all
//           settlement tasks from the model.
//
//   node scripts/run-world-b3.mjs --out artifacts/world-chain/b3-baseline.json
//        [--server-checkout .local/world-server-worktree] [--python python]
//        [--db-snapshot artifacts/world-chain/b3-run-db]
//        [--only action|chain|both] [--skip-tasks]
//        [--rescore artifacts/world-chain/b3-baseline.json --out <new report>]
//   `--only` / `--skip-tasks` are iteration switches; the canonical report is
//   the default full run (both scenes + task probes) and records its scope.
// Failures are deliverable evidence: a scene whose model candidates fail is
// recorded as failed — never replaced by scripted candidates and passed off
// as model success. A setup failure aborts; a scene failure is kept and the
// other scene still runs.
//
// Scoring lives in ./b3-judges.mjs (Node, replayable over archived evidence).
// A verdict is pass | fail | review: `review` is an aspect the judge cannot
// decide automatically and is NEVER counted as passing. `--rescore <report>`
// re-scores an existing archive with the current judges.
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer as createNetServer } from 'node:net';
import { createServer } from 'vite';
import { buildContext, judgeProbe, judgeScene, runJudgeSelfTests, summarizeProbes } from './b3-judges.mjs';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const a = resolve(root, option('--server-checkout', '.local/world-server-worktree'));
const output = resolve(root, option('--out', 'artifacts/world-chain/b3-baseline.json'));
const dbSnapshotOption = option('--db-snapshot', 'artifacts/world-chain/b3-run-db');
const scope = { tasks: !process.argv.includes('--skip-tasks'), scenes: option('--only', 'both') };
if (!['action', 'chain', 'both', 'none'].includes(scope.scenes)) throw new Error(`--only expects action|chain|both|none, got ${scope.scenes}`);

// ---- re-score an existing archive with the current judges (no services) ----
//   node scripts/run-world-b3.mjs --rescore artifacts/world-chain/b3-baseline.json //        --out artifacts/world-chain/b3-rescore.json
// Old reports keep their raw prompts/outputs, so the same judge can be replayed
// over them. Verdicts that need evidence the archive never stored stay `review`.
const rescoreSource = option('--rescore', null);
if (rescoreSource) {
  const sourcePath = resolve(root, rescoreSource);
  if (sourcePath === output) throw new Error('--rescore must not overwrite its source; pass a different --out');
  const source = JSON.parse(readFileSync(sourcePath, 'utf8'));
  const worldState = source.bootstrap?.state?.state ?? source.bootstrap?.state;
  if (!worldState?.initial?.characters) throw new Error('rescore source has no saved world state');
  const context = buildContext(worldState);
  const probes = (source.tasks?.probes ?? []).map((probe) => ({ ...probe, judgment: judgeProbe(probe, context) }));
  const scenes = Object.fromEntries(Object.entries(source.scenes ?? {}).map(([name, scene]) => [name, {
    sourceStatus: scene.status,
    playerInput: scene.playerInput ?? null,
    modelTasks: (scene.modelTasks ?? []).length,
    judged: judgeScene(scene, context),
  }]));
  const selfTest = runJudgeSelfTests(context);
  const rescored = {
    kind: 'b3-rescore', judgeVersion: 2, recordedAt: new Date().toISOString(),
    source: { path: rescoreSource, recordedAt: source.recordedAt, status: source.status,
      browserHead: source.browserSource?.head ?? null, serverHead: source.serverSource?.head ?? null },
    contextFingerprint: { worldId: worldState.worldId, protagonist: context.protagonist, roster: context.roster, time: worldState.time },
    tasks: {
      rates: summarizeProbes(probes), judgeSelfTest: selfTest,
      probes: probes.map((probe) => ({ id: probe.id, task: probe.task, judgment: probe.judgment,
        failure: probe.failure ?? null, output: probe.output ?? probe.call?.output ?? null,
        call: probe.call ? { key: probe.call.key, raw: probe.call.raw, ms: probe.call.ms,
          backfills: probe.call.backfills ?? [], context: probe.call.context ?? null } : null })),
    },
    scenes,
    notes: [
      'Scoring only: no model call, no server, no new evidence.',
      'Old archives did not store result/reaction input context or continuation judgement fields; '
        + 'those aspects are `review`, never `pass`.',
      'The old action/continuation prompts encoded the superseded contract (consumed => skip every actor; '
        + 'incomplete tasks => continue); the new verdicts judge the outputs against the design contract.',
    ],
  };
  rescored.status = selfTest.failed > 0 ? 'JUDGE_SELF_TEST_FAILED' : 'RESCORED';
  writeFileSync(output, JSON.stringify(rescored, null, 2) + '\n');
  console.log(`[world-b3] rescored ${rescoreSource} → ${output}`);
  console.log(`[world-b3] probes: structure ${rescored.tasks.rates.structurePass}/${rescored.tasks.rates.probes}, ` +
    `pass ${rescored.tasks.rates.semanticsPass}, fail ${rescored.tasks.rates.semanticsFail}, review ${rescored.tasks.rates.pendingReview}; ` +
    `self-test failures ${selfTest.failed}`);
  process.exit(0);
}
const privateDir = resolve(root, `.local/world-b3-${Date.now()}`);
mkdirSync(privateDir, { recursive: true });
const sources = ['frontend/scripts/run-world-b3.mjs', 'frontend/src/app/world/narration-polisher.ts',
  'frontend/src/app/world/world-defaults.ts',
  ...['runtime/rule-session', 'runtime/rule-facts', 'runtime/committed-narration', 'runtime/prompts', 'runtime/wllama-engine',
    'runtime/focused-input', 'runtime/narration-split', 'runtime/engine', 'types',
    'controller', 'schedule', 'http-transport', 'recovery'].map((name) => `frontend/src/lib/world-engine/${name}.ts`)];

const git = (checkout, ...args) => { try {
  return execFileSync('git', ['-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).replace(/\n+$/, '');
} catch { return null; } };
const walkServerFiles = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => entry.isDirectory()
  ? (entry.name === '__pycache__' ? [] : walkServerFiles(resolve(dir, entry.name))) : [resolve(dir, entry.name)]);
const serverAppRoot = resolve(a, 'backend', 'app').replaceAll('\\', '/');
const serverFiles = walkServerFiles(resolve(a, 'backend', 'app'))
  .map((file) => ({ path: `backend/app/${file.replaceAll('\\', '/').slice(serverAppRoot.length + 1)}`, file }));
const report = {
  status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), kind: 'b3-baseline',
  privateDir, browserSource: { head: git(root, 'rev-parse', 'HEAD'), status: git(root, 'status', '--short'),
    sha256: Object.fromEntries(sources.map((file) => [file, createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex')])) },
  serverSource: { head: git(a, 'rev-parse', 'HEAD'), status: git(a, 'status', '--short'),
    sha256: Object.fromEntries(serverFiles.map(({ path, file }) => [path, createHash('sha256').update(readFileSync(file)).digest('hex')])) },
  scope, judgeVersion: 2, modelLoad: null, modelConfig: {
    settlement: { model: '/models/Qwen3-0.6B-Q4_K_M.gguf', contextSize: 2048, temperature: 0, seed: 42,
      maxTokens: 'per task (64-384)', timeoutMs: 110_000, constrainedDecoding: 'json_schema strict' },
    narration: { model: null, contextSize: 2048, maxTokens: 96, temperature: [0, 0.7], timeoutMs: 110_000,
      path: 'narration-polisher + checkFactNarration (one regeneration, then template fallback)' } },
  tasks: null, scenes: {},
};
const save = () => { mkdirSync(resolve(output, '..'), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();

const trackedDirty = (status, pinned) => (status ?? '').split('\n').filter((line) => line && !line.startsWith('??'))
  .map((line) => line.slice(3).replaceAll('\\', '/')).filter((path) => pinned.some((item) => path === item || path.startsWith(`${item}/`)));
const dirtyPinned = { server: trackedDirty(report.serverSource.status, ['backend/app']), browser: trackedDirty(report.browserSource.status, sources) };
const allowDirty = { server: process.argv.includes('--allow-dirty-server'), browser: process.argv.includes('--allow-dirty-browser') };
if ((dirtyPinned.server.length && !allowDirty.server) || (dirtyPinned.browser.length && !allowDirty.browser)) {
  report.status = 'FAILED';
  report.error = `pinned source tree dirty: server=${JSON.stringify(dirtyPinned.server)}${allowDirty.server ? ' (allowed)' : ''} ` +
    `browser=${JSON.stringify(dirtyPinned.browser)}${allowDirty.browser ? ' (allowed)' : ''} — commit/stash first, ` +
    `or pass --allow-dirty-server / --allow-dirty-browser for the side being run`;
  save();
  console.error(`[world-b3] FAILED: ${report.error}`);
  process.exit(1);
}

async function freePort() {
  const probe = createNetServer();
  const port = await new Promise((done, fail) => {
    probe.once('error', fail);
    probe.listen(0, '127.0.0.1', () => done(probe.address().port));
  });
  await new Promise((done) => probe.close(done));
  return port;
}
const apiPort = await freePort();
const vitePort = await freePort();
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const viteOrigin = `http://127.0.0.1:${vitePort}`;

const startService = () => {
  const service = spawn(option('--python', 'python'), ['-X', 'utf8', '-m', 'uvicorn', 'app.world_app:create_persistent_world_app', '--factory',
    '--host', '127.0.0.1', '--port', String(apiPort)], { cwd: resolve(a, 'backend'),
    env: { ...process.env, WORLD_SQLITE_PATH: resolve(privateDir, 'world.db'), WORLD_ALLOWED_ORIGINS: viteOrigin },
    windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const log = createWriteStream(resolve(privateDir, 'server.log'), { flags: 'a' });
  service.stdout.pipe(log);
  service.stderr.pipe(log);
  return service;
};
let service = startService();
const waitReady = async () => {
  for (let attempt = 0; ; attempt++) {
    if (service.exitCode !== null) throw new Error('World HTTP service exited before readiness');
    try {
      const response = await fetch(`${apiOrigin}/openapi.json`, { signal: AbortSignal.timeout(8000) });
      if (response.ok) return;
    } catch { /* boot still running */ }
    if (attempt >= 40) throw new Error('World HTTP service readiness timeout');
    await new Promise((done) => setTimeout(done, 500));
  }
};

const vite = await createServer({ root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/world-chain-vite',
  server: { host: '127.0.0.1', port: vitePort, hmr: false },
  plugins: [{ name: 'world-b3', configureServer(vite) { vite.middlewares.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    if (req.url !== '/__chain') return next();
    res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>World B3 baseline</title>');
  }); } }] });
await vite.listen();
report.lifecycle = { apiOrigin, viteOrigin };
save();

const cleanup = () => {
  try { vite.close(); } catch {}
  try { service.kill(); } catch {}
};

let browser;
const consoleTrail = [];
try {
  await waitReady();
  report.lifecycle.serviceReady = true; save();

  const { chromium } = await import('@playwright/test');
  browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage();
  page.on('console', (message) => consoleTrail.push(message.text()));
  page.on('pageerror', (error) => consoleTrail.push(`[pageerror] ${error.message}`));
  await page.goto(`${viteOrigin}/__chain`, { waitUntil: 'domcontentloaded' });
  assert.equal(await page.evaluate(() => window.crossOriginIsolated), true, 'B3 baseline requires cross-origin isolation');
  report.modelLoad = await page.evaluate(async (modelUrl) => {
    // B3 uses its OWN engine instance (constrained decoding + plain chat
    // completions for settlement tasks); the narration polisher keeps its
    // own cached engine — both load the same model file.
    const { WllamaInferenceEngine } = await import('/src/lib/world-engine/runtime/wllama-engine.ts');
    const engine = new WllamaInferenceEngine({ modelUrl, contextSize: 2048 });
    const started = performance.now();
    await engine.load();
    window.__b3engine = engine;
    return { model: modelUrl, loadMs: Math.round(performance.now() - started) };
  }, '/models/Qwen3-0.6B-Q4_K_M.gguf');
  save();

  // ---- shared page-side harness: raw ops + B3 model port ----
  await page.evaluate(async ({ api: apiBase }) => {
    const [{ HttpWorldTransport }, { RuleWorldSession, narrateFromReads }, { ControllerDriver, initialMemory },
      { defaultInitialTemplate, WORLD_POLICY, DEFAULT_POLISH_MODEL }, { narrationPolisher }] = await Promise.all([
      import('/src/lib/world-engine/http-transport.ts'), import('/src/lib/world-engine/runtime/rule-session.ts'),
      import('/src/lib/world-engine/controller.ts'), import('/src/app/world/world-defaults.ts'),
      import('/src/app/world/narration-polisher.ts')]);

    const H = {
      apiBase, worldId: null, lease: null, revision: null, head: null, rawSeq: 0,
      opLog: [], wireCaptures: [], events: [], calls: [], reads: new Map(),
      completionEvidence: [], narrationAttempts: [], narrationLog: [], programPlans: [], programNextRoundIds: [],
      sessionOptions(holderId) {
        return { transport: H.transport, initial: defaultInitialTemplate(), policy: WORLD_POLICY, polish: H.polish,
          onEvent: (event) => H.events.push({ ...event, at: Date.now() }), holderId };
      },
    };
    window.__h = H;

    const LEASE_FREE = new Set(['create_world', 'list_points', 'get_state', 'get_context', 'preview_point']);
    const LEASE_OWN = new Set(['lease_acquire']);
    const PATH_POINT_OPS = new Set(['narration_get']);
    const NEEDS_HEAD = (operation) => operation.startsWith('checkpoint_') || operation === 'create_rolls'
      || operation === 'round_conclusion_cancel';
    H.rawOp = async (operation, payload = {}, opts = {}) => {
      const started = performance.now();
      const scope = PATH_POINT_OPS.has(operation) ? { worldId: H.worldId, pointId: payload.pointId }
        : H.worldId && operation !== 'create_world' ? { worldId: H.worldId } : {};
      const body = operation === 'narration_get' ? {}
        : LEASE_FREE.has(operation) ? payload
        : { protocolVersion: 2, requestId: payload.requestId ?? `b3_raw_${++H.rawSeq}`, worldId: H.worldId,
            ...(LEASE_OWN.has(operation) ? {} : { leaseToken: H.lease?.leaseToken, fenceEpoch: H.lease?.fenceEpoch }),
            ...(NEEDS_HEAD(operation) ? { expectedPointId: H.head?.pointId, expectedVersion: H.head?.version,
              expectedCheckpointRevision: H.revision } : {}),
            ...payload };
      const response = await (opts.transport ?? H.http).execute(operation, body, scope);
      H.opLog.push({ op: operation, ms: Math.round(performance.now() - started), tag: opts.tag });
      H.captureEnvelope(response);
      if (operation === 'get_state') H.reads.set(response.data.pointId, structuredClone(response.data));
      return response.data ?? response;
    };
    H.captureEnvelope = (response) => {
      if (response.world) {
        H.worldId = response.world.worldId;
        H.head = response.world.head;
        if (response.world.lease) H.lease = { ...H.lease, ...response.world.lease };
      }
      const data = response.data;
      if (data?.lease?.leaseToken) H.lease = { ...H.lease, ...data.lease };
      if (data?.leaseToken) H.lease = { ...H.lease, leaseToken: data.leaseToken,
        fenceEpoch: data.fenceEpoch ?? H.lease?.fenceEpoch, expiresAtEpochMilli: data.expiresAtEpochMilli ?? H.lease?.expiresAtEpochMilli };
      if (response.control) H.revision = response.control.revision;
    };
    const capturingFetcher = async (input, init) => {
      const response = await fetch(input, init);
      if (response.status >= 400) H.wireCaptures.push({ url: String(input), body: String(init?.body ?? '').slice(0, 2000), status: response.status, response: (await response.clone().text()).slice(0, 2000) });
      return response;
    };
    H.http = new HttpWorldTransport(apiBase, capturingFetcher);
    H.control = async () => (await H.rawOp('get_context', { includeRecovery: false }, { tag: 'probe' })).control;
    H.snapshot = async () => {
      const read = await H.rawOp('get_state', {}, { tag: 'probe' });
      const protagonist = read.state.characters[read.state.protagonistId];
      return { version: read.version, headPointId: read.pointId, sanity: protagonist.sanity, location: protagonist.position.containerId };
    };
    H.ensureLease = async () => {
      if (H.lease?.leaseToken) return H.lease;
      await H.rawOp('lease_acquire', { holderId: 'b3_harness' }, { tag: 'setup' });
      if (!H.lease?.leaseToken) throw new Error('lease_acquire did not yield a lease');
      return H.lease;
    };

    // ---- B3 model port: constrained decoding, program identity backfill ----
    // 每任务的提示词/输出 schema/程序校验都在这里；身份（change/task/round id）
    // 由程序预分配并在输出校验时回填——模型只做语义判定。
    const nameOf = (state, id) => state?.initial?.characters?.[id]?.name
      ?? state?.initial?.items?.[id]?.name ?? state?.initial?.locations?.[id]?.name ?? id;
    const locationName = (state, id) => state?.initial?.locations?.[id]?.name ?? id;
    H.nameOf = nameOf;
    H.locationName = locationName;
    const looksLikeGoal = (text) => typeof text === 'string' && /需要|应该|打算|想要|愿意|必须|准备|试图/.test(text);
    H.looksLikeGoal = looksLikeGoal;
    const renderState = (state) => {
      if (!state) return '(状态不可用)';
      const lines = [`时间：${state.time.dateTime}`];
      for (const [id, actor] of Object.entries(state.characters)) {
        const tasks = Object.values(actor.tasks)
          .map((task) => `${task.goal}(${task.id},${task.status === 'achieved' ? '已达成' : '未完成'})`).join('；') || '无';
        lines.push(`角色 ${nameOf(state, id)}（id=${id}）：位于${locationName(state, actor.position.containerId)}，精神值${actor.sanity}。任务：${tasks}`);
      }
      const locations = Object.entries(state.locations ?? {}).map(([id]) => `${locationName(state, id)}(id=${id})`);
      if (locations.length) lines.push(`地点：${locations.join('、')}`);
      const items = Object.entries(state.items ?? {}).map(([id, item]) => `${nameOf(state, id)}（id=${id}，位于${locationName(state, item.position.containerId)}）`);
      if (items.length) lines.push(`物品：${items.join('、')}`);
      return lines.join('\n');
    };
    const b3 = {
      calls: [], // {task,key,prompt,promptChars,raw,output,ms,completion,backfills[],error}
      temperature: 0,
      async complete(task, key, prompt, schema, maxTokens) {
        const engine = window.__b3engine;
        const started = performance.now();
        let completion = null;
        const onCompletion = (evidence) => { completion = evidence; };
        let raw = null;
        let error = null;
        try {
          raw = await engine.complete(prompt, { maxTokens, temperature: b3.temperature, seed: 42, cachePrompt: true,
            timeoutMs: 110_000, onCompletion, jsonSchema: schema });
        } catch (caught) {
          error = caught;
          completion = caught?.completion ?? completion;
        }
        const ms = Math.round(performance.now() - started);
        let output = null;
        let parseError = null;
        if (!error) {
          try { output = JSON.parse(raw); } catch (caught) { parseError = String(caught); }
        }
        b3.calls.push({ task, key, at: Date.now(), prompt, promptChars: prompt.length, schema, maxTokens,
          raw: raw ?? completion?.raw ?? '', output, parseError, error: error ? String(error.message ?? error) : null,
          errorName: error?.name ?? null, ms, completion });
        if (error) throw error;
        if (parseError) throw new Error(`b3 ${task} output is not JSON: ${parseError} raw=${raw.slice(0, 200)}`);
        return output;
      },
    };
    H.b3 = b3;

    // ---- updates contract: the controller's canonical stages/fields ----
    const UPDATE_STAGES = ['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity'];
    const UPDATE_FIELDS = { position: ['positionSet'], appearance: ['appearanceChanges'], tasks: ['tasksAchieved'],
      subtasks: ['subtasksAdded'], personality: ['personalityChanges'], sanity: ['sanitySet'] };
    const isObject = (value) => value != null && typeof value === 'object' && !Array.isArray(value);
    const taskOwnersOf = (state) => {
      const owners = {};
      for (const [actorId, actor] of Object.entries(state?.characters ?? {})) for (const taskId of Object.keys(actor.tasks ?? {})) owners[taskId] = actorId;
      return owners;
    };
    H.taskOwnersOf = taskOwnersOf;
    const auditUpdates = (out, expectedStage, roster, taskOwners = {}) => {
      const calls = expectedStage ? (Array.isArray(out) ? null : isObject(out) ? [out] : null)
        : (Array.isArray(out) ? out : null);
      if (!calls) return { calls: null, error: expectedStage ? 'stage call must be one object' : 'merged updates must be an array' };
      const produced = {};
      for (const call of calls) {
        if (!isObject(call) || !isObject(call.changes)) continue;
        for (const [entity, delta] of Object.entries(call.changes)) {
          if (!isObject(delta)) continue;
          for (const task of delta.subtasksAdded ?? []) if (isObject(task) && typeof task.id === 'string') produced[task.id] = entity;
        }
      }
      let last = -1;
      for (const call of calls) {
        if (!isObject(call)) return { calls, error: 'update call must be an object' };
        const index = UPDATE_STAGES.indexOf(call.stage);
        if (index < 0) return { calls, error: `illegal stage ${call.stage}` };
        if (expectedStage && call.stage !== expectedStage) return { calls, error: `stage ${call.stage} != ${expectedStage}` };
        if (index <= last) return { calls, error: `out-of-order/duplicate stage ${call.stage}` };
        last = index;
        if (!isObject(call.changes)) return { calls, error: `changes of ${call.stage} must be an object` };
        const allowed = UPDATE_FIELDS[call.stage];
        for (const [entity, delta] of Object.entries(call.changes)) {
          if (roster && !roster.has(entity)) return { calls, error: `entity ${entity} not in roster` };
          if (!isObject(delta)) return { calls, error: `delta of ${entity} must be an object` };
          for (const key of Object.keys(delta)) {
            if (key === 'entityId') continue;
            if (!allowed.includes(key)) return { calls, error: `field ${key} not allowed in ${call.stage}` };
          }
          if (delta.positionSet !== undefined) {
            const position = delta.positionSet;
            if (!isObject(position) || typeof position.containerId !== 'string' || !position.containerId
              || (position.slotId != null && typeof position.slotId !== 'string')
              || (position.relativeTo != null && typeof position.relativeTo !== 'string')) return { calls, error: 'invalid positionSet' };
          }
          for (const key of ['appearanceChanges', 'personalityChanges']) {
            if (delta[key] === undefined) continue;
            if (!Array.isArray(delta[key])) return { calls, error: `${key} must be an array` };
            for (const change of delta[key]) {
              if (!isObject(change) || typeof change.id !== 'string' || !change.id
                || typeof change.text !== 'string' || !change.text
                || !Array.isArray(change.supersedes)) return { calls, error: `invalid ${key} item (supersedes must be an array)` };
            }
          }
          if (delta.tasksAchieved !== undefined) {
            if (!Array.isArray(delta.tasksAchieved) || delta.tasksAchieved.some((id) => typeof id !== 'string' || !id)) return { calls, error: 'tasksAchieved must be a string array' };
            for (const taskId of delta.tasksAchieved) {
              const owner = produced[taskId] ?? taskOwners[taskId];
              if (owner == null) return { calls, error: `tasksAchieved ${taskId} is not in the state or produced by this batch` };
              if (owner !== entity) return { calls, error: `task ${taskId} is owned by ${owner}, not ${entity}` };
            }
          }
          if (delta.subtasksAdded !== undefined) {
            if (!Array.isArray(delta.subtasksAdded)) return { calls, error: 'subtasksAdded must be an array' };
            for (const task of delta.subtasksAdded) {
              if (!isObject(task) || typeof task.id !== 'string' || !task.id || typeof task.goal !== 'string' || !task.goal
                || task.ownerId !== entity || (task.parentTaskId != null && typeof task.parentTaskId !== 'string')
                || task.status !== 'pending') return { calls, error: 'invalid subtasksAdded item' };
            }
          }
          if (delta.sanitySet !== undefined && !(Number.isInteger(delta.sanitySet) && delta.sanitySet >= 0 && delta.sanitySet <= 100)) {
            return { calls, error: 'sanitySet must be an integer in [0,100]' };
          }
        }
      }
      return { calls, error: null };
    };
    H.auditUpdates = auditUpdates;
    const allTasksAchieved = (state) => Object.values(state?.characters ?? {})
      .flatMap((actor) => Object.values(actor.tasks)).every((task) => task.status === 'achieved');

    // ---- stage-6 prompts (post-review contract) ------------------------
    // 契约职责来自设计 §6.1/§6.3/§7.1/§8.1：
    //   action  只有主角受玩家命令约束；consumed 只是「输入机会已处理」，
    //           其他人物仍按自己的任务与个性判断。
    //   results 输入含全组冻结行动与全部骰点判定；不得把未准入写成成功。
    //   updates 因果链：任务达成可单独成立，个性变化需有本批任务达成，
    //           理智变化需有本批个性变化。
    //   continuation 必须同时给出「大概率发生」与「与主角有关」，并给出拟行动
    //           与主角关联；这两个判断字段只是判断产物，wire 结论仍只保留
    //           kind/candidates/nextRoundId（§8.1：拟行动长文本不保存）。
    const updatesContract = (stage) => {
      const allowed = stage ? [stage] : UPDATE_STAGES;
      const fields = allowed.map((name) => `- ${name} 阶段只允许字段 ${UPDATE_FIELDS[name].join('/')}。`).join('\n');
      const exampleField = {
        position: '"positionSet":{"containerId":"<地点id>","slotId":null,"relativeTo":null}',
        appearance: '"appearanceChanges":[{"id":"draft_1","text":"<外貌变化>","supersedes":[]}]',
        tasks: '"tasksAchieved":["<状态中已有任务id>"]',
        subtasks: '"subtasksAdded":[{"id":"draft_1","ownerId":"<角色id>","parentTaskId":null,"goal":"<新任务>","status":"pending"}]',
        personality: '"personalityChanges":[{"id":"draft_1","text":"<个性变化>","supersedes":[]}]',
        sanity: '"sanitySet":<0-100整数>',
      };
      const example = stage ? `{"stage":"${stage}","changes":{"<角色id>":{${exampleField[stage]}}}}`
        : `[{"stage":"tasks","changes":{"<角色id>":{"tasksAchieved":["<状态中已有任务id>"]}}}]`;
      const shape = stage ? `只输出一个 JSON 对象（不要数组）：${example}`
        : `只输出 JSON 数组，按 position→appearance→tasks→subtasks→personality→sanity 顺序；只写实际发生变化的阶段：${example}`;
      return `字段契约：\n` +
        `- positionSet：{"containerId":"<地点id>","slotId":null,"relativeTo":null}\n` +
        `- appearanceChanges：数组，元素 {"id":"draft_1","text":"<外貌变化>","supersedes":[]}\n` +
        `- tasksAchieved：数组，元素必须是状态中已有的任务 id，且该任务属于同一个角色\n` +
        `- subtasksAdded：数组，元素 {"id":"draft_1","ownerId":"<角色id>","parentTaskId":null,"goal":"<新任务>","status":"pending"}\n` +
        `- personalityChanges：数组，元素 {"id":"draft_1","text":"<个性变化>","supersedes":[]}；只有本批有任务达成时才允许\n` +
        `- sanitySet：0 到 100 的整数，只写最终值；只有本批有该角色的个性变化时才允许\n` +
        `因果规则：任务达成可以单独出现（个性变化只是可能发生，不是必须）；没有新达成任务就不要写个性；没有个性变化就不要写理智。\n` +
        `${fields}\nchanges 的键只能是状态中列出的角色 id；不得嵌套 changes；不得输出契约外的字段。\n` +
        `示例：${example}\n${shape}\n无变化${stage ? `输出 {"stage":"${stage}","changes":{}}` : '输出 []'}。`;
    };
    const updatesSchema = (stage) => stage
      ? { type: 'object', properties: { stage: { type: 'string', enum: [stage] }, changes: { type: 'object' } }, required: ['stage', 'changes'] }
      : { type: 'array', items: { type: 'object', properties: { stage: { type: 'string' }, changes: { type: 'object' } }, required: ['stage', 'changes'] } };

    H.b3Port = {
      async generate(task, key, input) {
        if (task === 'pointPlan') {
          b3.calls.push({ task, key, at: Date.now(), source: 'program' });
          const plan = H.programPointPlan(key, input);
          b3.calls[b3.calls.length - 1].output = plan;
          return plan;
        }
        if (task === 'time') {
          b3.calls.push({ task, key, at: Date.now(), source: 'program' });
          return { boundary: 'instant', duration: { amount: 0, unit: 'second' } };
        }
        if (input == null) throw new Error(`b3 ${task} input is null (initial world creation is outside this harness)`);
        const state = input.workingState ?? null;
        const view = state ? renderState(state) : '(状态不可用)';
        if (task === 'action') {
          const actorName = nameOf(state, input.actor);
          const consumed = input.advance?.intentStatus !== 'pending';
          const inputText = input.advance?.inputText ?? null;
          const isProtagonist = input.actor === state?.protagonistId;
          const prompt = `你是文字冒险游戏的行动裁判。所有文本必须使用简体中文。\n${view}\n` +
            `玩家输入原文：${inputText ?? '(无)'}\n本次行动机会属于：${actorName}（id=${input.actor}）${isProtagonist ? '，他是主角' : '，他不是主角'}。\n` +
            `输入状态：${consumed ? '已消费（该输入机会已处理，输入只作为背景，不得再执行玩家命令）' : '待处理（玩家命令尚未执行成功）'}\n` +
            `规则：\n` +
            `- 只有主角的行动受玩家命令约束；主角不得把玩家命令当成已成功发生的事实。\n` +
            `- 输入已消费时，主角不得再次执行玩家命令；其他人物的行动只依据自己的任务、个性与处境判断。\n` +
            `- 输出一个具体的身体动作或发言（不超过 40 字，第三人称，以${actorName}为主语），不要写任务目标、计划、心理活动或状态数值。\n` +
            `- 不得引入状态中未列出的角色或物品。若不行动，输出 {"kind":"skip","text":""}。\n` +
            `只输出 JSON：{"kind":"act","text":"<行动描述>"} 或 {"kind":"skip","text":""}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { kind: { type: 'string', enum: ['act', 'skip'] }, text: { type: 'string' } }, required: ['kind', 'text'] }, 128);
          b3.calls[b3.calls.length - 1].context = { actor: input.actor, protagonist: state?.protagonistId, consumed, inputText, isProtagonist };
          if (out.kind === 'act' && !out.text) throw new Error('b3 action act with empty text');
          return out.kind === 'skip' ? { kind: 'skip' } : { kind: 'act', text: out.text };
        }
        if (task === 'targets') {
          const sourceName = nameOf(state, input.sourceId);
          const prompt = `你是目标判定器。所有文本必须使用简体中文。
${view}
行动（发起者 ${sourceName}，id=${input.sourceId}）：${input.actionText}
` +
            `判断该行动是否指向场上另一名角色。行动文本中出现的角色名字，按状态里的 id 输出；目标必须是状态里列出的其他角色。
` +
            `不要指向发起者自己，也不要指向已经行动过的角色。不指向任何角色就输出空数组。
` +
            `只输出 JSON：{"targets":[{"targetId":"<被指向角色的id>"}]} 或 {"targets":[]}`;
          // 产品 codec（structured-output.ts）的形状是 {targets:[{targetId}]}：
          // 模型只声明目标身份，触发键与骰点规则由程序分配。
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { targets: { type: 'array', items: {
              type: 'object', properties: { targetId: { type: 'string' } }, required: ['targetId'] } } },
            required: ['targets'] }, 96);
          if (!Array.isArray(out.targets)) throw new Error('b3 targets without array');
          const roster = new Set(Object.keys(state?.characters ?? {}));
          const backfills = [];
          const targetIds = out.targets.map((entry) => entry?.targetId).filter((target) => {
            if (typeof target === 'string' && target) return true;
            backfills.push({ kind: 'target_malformed', value: target ?? null });
            return false;
          });
          const kept = targetIds.filter((target) => {
            if (roster.has(target)) return true;
            backfills.push({ kind: 'target_dropped_not_in_roster', value: target });
            return false;
          });
          b3.calls[b3.calls.length - 1].backfills = backfills;
          // 自指/重复目标不是程序可修复的格式问题：记语义错误并停止，
          // 不静默改写模型的冻结目标集。
          if (kept.includes(input.sourceId)) {
            b3.calls[b3.calls.length - 1].validationError = 'target is the source itself';
            throw new Error(`b3 targets semantic: source targets itself (${input.sourceId})`);
          }
          if (new Set(kept).size !== kept.length) {
            b3.calls[b3.calls.length - 1].validationError = 'duplicate targets';
            throw new Error(`b3 targets semantic: duplicate targets ${JSON.stringify(kept)}`);
          }
          return { targets: kept.map((targetId) => ({ targetId })) };
        }
        if (task === 'reaction') {
          const sourceName = nameOf(state, input.sourceId);
          const memberName = nameOf(state, input.memberId);
          const prompt = `你是反应描写器。所有文本必须使用简体中文。\n${view}\n发起者 ${sourceName} 的行动：${input.sourceActionText}\n` +
            `${memberName} 已被卷入（判定已准入）。写一句 ${memberName} 的第三人称反应行动，不超过 30 字；\n` +
            `只写这个人的反应动作，不要重复发起者的行动，不要写结果、心理活动、精神值、理智或任务状态。\n` +
            `只输出 JSON：{"text":"<反应行动>"}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] }, 96);
          b3.calls[b3.calls.length - 1].context = { sourceActionText: input.sourceActionText, memberId: input.memberId };
          if (!out.text) throw new Error('b3 reaction with empty text');
          return out.text;
        }
        if (task === 'results') {
          const memberLines = input.members.map((member) => {
            const rolls = (member.rollRefs ?? []).map((roll) => `骰点 ${roll.result} / 阈值 11 → ${roll.admitted ? '准入' : '未准入'}`);
            return `- id=${member.memberId}（${nameOf(state, member.memberId)}）：${member.actionText}` +
              `；判定：${rolls.length ? rolls.join('；') : '无（单人行动，没有反应判定）'}`;
          }).join('\n');
          const prompt = `你是结果判定器。所有文本必须使用简体中文。\n${view}\n本组冻结行动与判定：\n${memberLines}\n` +
            `为每个成员写一句第三人称结算结果，只描述这些冻结行动的直接后果。\n` +
            `不得新增行动文本中没有的事件（撤退、受伤、耗尽等都不算直接后果）；判定为“未准入”的关系必须写成没有成功，判定为“准入”的不得写成失败。\n` +
            `只输出 JSON 对象，必须恰好包含这些键：${input.members.map((member) => `"${member.memberId}"`).join(', ')}`;
          const schema = { type: 'object', properties: Object.fromEntries(input.members.map((member) => [member.memberId, { type: 'string' }])),
            required: input.members.map((member) => member.memberId) };
          const out = await b3.complete(task, key, prompt, schema, 128);
          b3.calls[b3.calls.length - 1].context = { groupId: input.groupId,
            members: input.members.map((member) => ({ memberId: member.memberId, actionText: member.actionText, rollRefs: member.rollRefs ?? [] })) };
          const missing = input.members.map((member) => member.memberId).filter((id) => typeof out[id] !== 'string' || !out[id]);
          if (missing.length) throw new Error(`b3 results missing members: ${missing.join(',')}`);
          return Object.fromEntries(input.members.map((member) => [member.memberId, out[member.memberId]]));
        }
        if (task === 'updates') {
          const stage = input.stage ?? null;
          const context = input.mode === 'time_scan'
            ? '本点没有角色行动，时间已经推进；只根据时间与当前任务状态判断。'
            : `已确认结算结果：${JSON.stringify(input.results ?? {})}`;
          const prompt = `你是世界状态更新器。所有文本必须使用简体中文。\n${view}\n${context}\n` +
            `根据已发生的事实产出世界状态更新候选。${stage ? `只产出 stage="${stage}" 的更新。` : ''}\n` +
            `${updatesContract(stage)}`;
          const out = await b3.complete(task, key, prompt, updatesSchema(stage), 384);
          const audit = auditUpdates(out, stage, new Set(Object.keys(state?.characters ?? {})), taskOwnersOf(state));
          if (audit.error) {
            b3.calls[b3.calls.length - 1].validationError = audit.error;
            throw new Error(`b3 updates semantic: ${audit.error}`);
          }
          return out;
        }
        if (task === 'continuation') {
          const pending = Object.values(state?.characters ?? {}).flatMap((actor) => Object.values(actor.tasks))
            .filter((task) => task.status !== 'achieved');
          const prompt = `你是继续推进判断器。所有文本必须使用简体中文。\n${view}\n本轮已提交的变化：${JSON.stringify(input.roundChanges ?? [])}\n` +
            `当前轮：${JSON.stringify(input.round ?? {})}\n当前未完成任务数：${pending.length}\n` +
            `判断本 round 结束后是否继续自动推进。只有同时满足下面两条才 continue：\n` +
            `1) 后续有大概率会发生的行动：依据未完成任务、人物个性与处境判断，而不是只看“还有任务未完成”；\n` +
            `2) 该行动与主角有关：针对、涉及主角，或主角必然参与。\n` +
            `只满足其中一条，或两条都不满足，就 handback 交还玩家。\n` +
            `continue 时必须给出：candidateCharacterIds（至少一个、必须是状态中的角色 id）、plannedAction（拟发生的一句第三人称行动）、protagonistRelevance（一句说明该行动与${nameOf(state, state?.protagonistId)}的联系）。\n` +
            `handback 时 plannedAction 与 protagonistRelevance 输出空字符串。nextRoundId 写占位符 "pending"（程序会回填永久身份）。\n` +
            `只输出 JSON：\n{"kind":"continue","candidateCharacterIds":["<角色id>"],"nextRoundId":"pending","plannedAction":"<拟行动>","protagonistRelevance":"<与主角的联系>","cancelReason":null}\n或\n{"kind":"handback","plannedAction":"","protagonistRelevance":"","cancelReason":null}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { kind: { type: 'string', enum: ['continue', 'handback'] },
              candidateCharacterIds: { type: 'array', items: { type: 'string' } }, nextRoundId: { type: 'string' },
              plannedAction: { type: 'string' }, protagonistRelevance: { type: 'string' },
              cancelReason: { type: ['null', 'string'] } },
            required: ['kind', 'candidateCharacterIds', 'nextRoundId', 'plannedAction', 'protagonistRelevance'] }, 160);
          const record = b3.calls[b3.calls.length - 1];
          record.context = { pending: pending.length, prototype: 'two-condition' };
          const backfills = [];
          out.cancelReason = null;
          if (typeof out.plannedAction !== 'string') out.plannedAction = '';
          if (typeof out.protagonistRelevance !== 'string') out.protagonistRelevance = '';
          if (out.kind === 'continue') {
            const roster = new Set(Object.keys(state?.characters ?? {}));
            out.candidateCharacterIds = (out.candidateCharacterIds ?? []).filter((id) => {
              if (roster.has(id)) return true;
              backfills.push({ kind: 'candidate_dropped_not_in_roster', value: id });
              return false;
            });
            if (!out.candidateCharacterIds.length) {
              out.candidateCharacterIds = Object.keys(state?.characters ?? {});
              backfills.push({ kind: 'candidates_backfilled_roster' });
            }
            const nextRoundId = H.programNextRoundIds.shift();
            if (!nextRoundId) throw new Error('b3 next round id budget exhausted');
            if (out.nextRoundId !== nextRoundId) {
              backfills.push({ kind: 'next_round_id_backfilled', modelValue: out.nextRoundId ?? null, programValue: nextRoundId });
              out.nextRoundId = nextRoundId;
            }
          }
          record.backfills = backfills;
          // §8.1：拟行动长文本只属于判断，不进入 RoundConclusion。
          return out.kind === 'continue'
            ? { kind: 'continue', candidateCharacterIds: out.candidateCharacterIds, nextRoundId: out.nextRoundId }
            : { kind: 'handback' };
        }
        if (task === 'narration') {
          // 已交付的真实模型润色通路（与页面同一判分门）——来源 model
          const after = H.reads.get(key);
          if (!after) throw new Error('b3 narration_requires_saved_point_read');
          const before = after.previousPointId ? H.reads.get(after.previousPointId) ?? null : null;
          const attemptMark = H.narrationAttempts.length;
          const eventMark = H.events.length;
          const started = performance.now();
          try {
            const text = await H.narrateFromReads(after, before, H.polish, (event) => H.events.push({ ...event, at: Date.now() }));
            H.narrationLog.push({ task: 'narration', key, at: Date.now(), ms: Math.round(performance.now() - started), text,
              attempts: H.narrationAttempts.slice(attemptMark), events: H.events.slice(eventMark) });
            return text;
          } catch (error) {
            H.narrationLog.push({ task: 'narration', key, at: Date.now(), ms: Math.round(performance.now() - started), error: String(error?.message ?? error),
              attempts: H.narrationAttempts.slice(attemptMark), events: H.events.slice(eventMark) });
            throw error;
          }
        }
        throw new Error(`b3 port does not implement task ${task}`);
      },
    };

    // 程序侧 pointPlan：按轮消费预分配计划（B3 范围外，程序职责）
    H.programPointPlan = (roundId) => {
      const plan = H.programPlans.shift();
      if (!plan) throw new Error(`b3 point plan budget exhausted at round ${roundId}`);
      return plan;
    };

    // 叙事（已交付通路）：逐调用证据回调（实例级回调会被模块级缓存吞掉）
    H.narrateFromReads = narrateFromReads;
    H.narrationModel = DEFAULT_POLISH_MODEL;
    const basePolisher = await narrationPolisher(DEFAULT_POLISH_MODEL);
    H.polish = async (input, packet, focused, attempt) => {
      const started = performance.now();
      const evidenceBefore = H.completionEvidence.length;
      try {
        const text = await basePolisher(input, packet, focused, attempt, (item) => H.completionEvidence.push(item));
        H.narrationAttempts.push({ at: Date.now(), pointId: input?.pointId ?? null, attempt: attempt.index,
          ms: Math.round(performance.now() - started), text,
          facts: (focused?.facts ?? []).map((fact) => ({ id: fact.id, phrase: fact.allowedPhrases?.[0] ?? null })),
          completion: H.completionEvidence.slice(evidenceBefore) });
        return text;
      } catch (error) {
        H.narrationAttempts.push({ at: Date.now(), pointId: input?.pointId ?? null, attempt: attempt.index,
          ms: Math.round(performance.now() - started), error: String(error?.message ?? error),
          completion: H.completionEvidence.slice(evidenceBefore) });
        throw error;
      }
    };

    // 带记录的 tracked transport（场景用；commit 后不做 fold——B3 记录失败即交付）
    H.transport = { async execute(operation, request, scope, signal) {
      const started = performance.now();
      const response = await H.http.execute(operation, request, scope, signal);
      H.opLog.push({ op: operation, ms: Math.round(performance.now() - started) });
      H.captureEnvelope(response);
      if (operation === 'get_state') H.reads.set(response.data.pointId, structuredClone(response.data));
      return response;
    } };
    return { narrationModel: H.narrationModel };
  }, { api: apiOrigin });
  report.lifecycle.harnessReady = true;
  report.modelConfig.narration.model = (await page.evaluate(() => window.__h.narrationModel));
  save();

  const harnessError = (error, label) => {
    report.status = 'FAILED';
    report.error = `${label}: ${error?.stack ?? error}`;
    report.consoleTrail = consoleTrail.slice(-40);
    save();
    cleanup();
    try { browser?.close()?.catch(() => {}); } catch {}
    console.error(`[world-b3] FAILED at ${label}:`, error);
    process.exit(1);
  };

  // ---- bootstrap a real world and drive it with the RULE session to get a
  // realistic snapshot for the task probes (probes share the port code path
  // with the scenes — evaluation and production use the same functions). ----
  try {
    report.bootstrap = await page.evaluate(async () => {
      const H = window.__h;
      const { RuleWorldSession } = await import('/src/lib/world-engine/runtime/rule-session.ts');
      const session = RuleWorldSession.createNew(H.sessionOptions('b3_bootstrap'));
      const attach = await session.attach();
      if (attach.kind === 'error' || (attach.kind === 'stop' && attach.reason !== 'world_complete')) throw new Error(`bootstrap attach: ${JSON.stringify(attach)}`);
      for (const command of ['走到门厅', '完成压力试验']) {
        const terminal = await session.submit(command);
        if (terminal.kind !== 'stop' || terminal.reason !== 'world_complete') throw new Error(`bootstrap ${command}: ${JSON.stringify(terminal)}`);
      }
      return { worldId: H.worldId, state: await H.rawOp('get_state', {}, { tag: 'probe' }) };
    });
    save();
    console.log(`[world-b3] bootstrap: world=${report.bootstrap.worldId} version=${report.bootstrap.state.version}`);
  } catch (error) { harnessError(error, 'bootstrap'); }
  const judgeContext = () => buildContext(report.bootstrap.state.state);

  if (scope.tasks) {
  // ---- task-level probes (evidence only; Node judges score them) ----
  try {
    report.tasks = await page.evaluate(async () => {
      const H = window.__h;
      const stateRead = await H.rawOp('get_state', {}, { tag: 'probe' });
      const state = structuredClone(stateRead.state);
      const roster = Object.keys(state.characters);
      const protagonist = state.protagonistId;
      const other = roster.find((id) => id !== protagonist);
      const protagonistName = H.nameOf(state, protagonist);
      const otherName = H.nameOf(state, other);
      const baseAdvance = (overrides = {}) => ({ inputText: '走到走廊', intentStatus: 'pending', ...overrides });
      const probes = [];
      const run = async (probe) => {
        const started = performance.now();
        let outcome = null;
        let failure = null;
        try { outcome = await H.b3Port.generate(probe.task, probe.key ?? 'probe', structuredClone(probe.input)); }
        catch (error) { failure = String(error?.message ?? error); }
        const call = H.b3.calls[H.b3.calls.length - 1] ?? null;
        probes.push({ id: probe.id, task: probe.task, focus: probe.focus, input: probe.input,
          expect: probe.expect ?? null, output: outcome, failure,
          ms: Math.round(performance.now() - started), call: call ? {
            task: call.task, key: call.key, at: call.at, prompt: call.prompt, promptChars: call.promptChars,
            raw: call.raw, output: call.output, parseError: call.parseError ?? null,
            validationError: call.validationError ?? null, error: call.error ?? null, errorName: call.errorName ?? null,
            ms: call.ms, completion: call.completion ?? null, backfills: call.backfills ?? [],
            context: call.context ?? null, source: call.source ?? 'model' } : null });
        return outcome;
      };

      // 1) 行动判断：主角待处理 / 主角已消费 / 其他人物已消费
      await run({ id: 'action_pending', task: 'action', focus: 'pending input is judged for the protagonist',
        input: { actor: protagonist, advance: baseAdvance({ inputText: '走到走廊' }), workingState: structuredClone(state) } });
      await run({ id: 'action_consumed_protagonist', task: 'action',
        focus: 'consumed input: the protagonist must not re-execute the command',
        input: { actor: protagonist, advance: baseAdvance({ inputText: '走到走廊', intentStatus: 'consumed' }),
          workingState: structuredClone(state) } });
      await run({ id: 'action_consumed_npc', task: 'action',
        focus: 'consumed input is background only: other characters still judge from their tasks',
        expect: { advance: 'consumed' },
        input: { actor: other, advance: baseAdvance({ inputText: '走到走廊', intentStatus: 'consumed' }),
          workingState: structuredClone(state) } });

      // 2) 目标判定
      await run({ id: 'targets_directed', task: 'targets', focus: 'named target must be selected',
        expect: { directed: other },
        input: { sourceId: protagonist, actionText: `${protagonistName} 推开门厅深处的重门，示意 ${otherName} 到门边一起撑住。`, workingState: structuredClone(state) } });
      await run({ id: 'targets_solo', task: 'targets', focus: 'solo action yields no targets',
        expect: { solo: true },
        input: { sourceId: protagonist, actionText: `${protagonistName} 独自检查了走廊的墙壁。`, workingState: structuredClone(state) } });

      // 3) 反应
      await run({ id: 'reaction_joint', task: 'reaction', focus: 'admitted member writes its own reaction action',
        expect: { sourceActionText: `${protagonistName} 示意 ${otherName} 一起撑住重门。` },
        input: { sourceId: protagonist, sourceActionText: `${protagonistName} 示意 ${otherName} 一起撑住重门。`, memberId: other,
          rollId: 'probe_roll', workingState: structuredClone(state) } });

      // 4) 共同结果：无骰点 / 未准入骰点 / 准入骰点
      await run({ id: 'results_joint', task: 'results', focus: 'joint results must cover and attribute every member',
        input: { groupId: 'group_probe', members: [
          { memberId: protagonist, actionText: `${protagonistName} 推开门示意同伴一起撑住。`, rollRefs: [] },
          { memberId: other, actionText: `${otherName} 上前与同伴一起撑住重门。`, rollRefs: [] }],
          workingState: structuredClone(state) } });
      await run({ id: 'results_rejected_roll', task: 'results', focus: 'rejected roll must not be narrated as success',
        input: { groupId: 'group_probe_rejected', members: [
          { memberId: protagonist, actionText: `${protagonistName} 示意 ${otherName} 一起撑住重门。`, rollRefs: [] },
          { memberId: other, actionText: `${otherName} 被卷入重门。`,
            rollRefs: [{ sourceId: protagonist, targetId: other, triggerKey: 'probe_trigger', rollId: 'probe_roll_rejected',
              result: 8, eligible: true, admitted: false }] }],
          workingState: structuredClone(state) } });
      await run({ id: 'results_admitted_roll', task: 'results', focus: 'admitted roll must not be narrated as failure',
        input: { groupId: 'group_probe_admitted', members: [
          { memberId: protagonist, actionText: `${protagonistName} 示意 ${otherName} 一起撑住重门。`, rollRefs: [] },
          { memberId: other, actionText: `${otherName} 到门边一起撑住重门。`,
            rollRefs: [{ sourceId: protagonist, targetId: other, triggerKey: 'probe_trigger', rollId: 'probe_roll_admitted',
              result: 19, eligible: true, admitted: true }] }],
          workingState: structuredClone(state) } });

      // 5) 六阶段更新：合并调用 + 变化预期
      const results = { [protagonist]: `${protagonistName} 完成了压力试验。`, [other]: `${otherName} 在一旁见证，没有新的变化。` };
      await run({ id: 'updates_merged', task: 'updates', focus: 'merged updates: task-only change is legal and expected',
        expect: { expectTasks: { [protagonist]: ['task_pressure'] } },
        input: { groupId: 'group_probe', mode: 'group', results, workingState: structuredClone(state) } });
      await run({ id: 'updates_none_expected', task: 'updates', focus: 'no consequence and no task change yields no updates',
        expect: { forbidAnyChange: true },
        input: { groupId: 'group_probe_none', mode: 'group',
          results: { [protagonist]: `${protagonistName} 站着没有动。`, [other]: `${otherName} 站在一旁，没有新的变化。` },
          workingState: structuredClone(state) } });

      const taskStage = await run({ id: 'updates_stage_tasks', task: 'updates', focus: 'tasks stage returns one object',
        expect: { stage: 'tasks', expectTasks: { [protagonist]: ['task_pressure'] } },
        input: { groupId: 'group_probe', mode: 'group', stage: 'tasks', results, workingState: structuredClone(state) } });
      // 程序应用阶段 3（任务达成），供后续阶段读取
      const applied = structuredClone(state);
      const taskStageCalls = Array.isArray(taskStage) ? taskStage : taskStage ? [taskStage] : [];
      const appliedTasks = [];
      for (const call of taskStageCalls) {
        for (const [entity, delta] of Object.entries(call.changes ?? {})) {
          for (const taskId of delta.tasksAchieved ?? []) {
            if (applied.characters[entity]?.tasks?.[taskId]) { applied.characters[entity].tasks[taskId].status = 'achieved'; appliedTasks.push(`${entity}:${taskId}`); }
          }
          for (const task of delta.subtasksAdded ?? []) {
            if (applied.characters[entity]?.tasks && task?.id) { applied.characters[entity].tasks[task.id] = task; appliedTasks.push(`${entity}:${task.id}`); }
          }
        }
      }
      const personalityStage = await run({ id: 'updates_stage_personality', task: 'updates',
        focus: 'personality stage reads the applied tasks state',
        expect: { stage: 'personality' },
        input: { groupId: 'group_probe', mode: 'group', stage: 'personality', results, workingState: structuredClone(applied) } });
      // 程序应用阶段 5：模型给出合法个性变化就用模型的，否则注入带标签的夹具
      const withPersonality = structuredClone(applied);
      const personalityCalls = Array.isArray(personalityStage) ? personalityStage : personalityStage ? [personalityStage] : [];
      let personalityFixture = null;
      const appliedPersonalities = [];
      for (const call of personalityCalls) {
        for (const [entity, delta] of Object.entries(call.changes ?? {})) {
          for (const change of delta.personalityChanges ?? []) {
            if (!withPersonality.characters[entity] || !change?.id || !change?.text) continue;
            withPersonality.characters[entity].personalityChanges.push({ ...change, sourcePointId: 'probe_point', sourceSequence: 1, active: true });
            appliedPersonalities.push(`${entity}:${change.id}`);
          }
        }
      }
      if (!appliedPersonalities.length) {
        personalityFixture = { id: 'probe_change_fixture', text: '完成压力试验后更沉稳' };
        withPersonality.characters[protagonist].personalityChanges.push({ ...personalityFixture, supersedes: [],
          sourcePointId: 'probe_point', sourceSequence: 1, active: true });
        appliedPersonalities.push(`${protagonist}:${personalityFixture.id}`);
      }
      const sanityStage = await run({ id: 'updates_stage_sanity', task: 'updates',
        focus: 'sanity stage must recalculate the actor whose personality changed',
        expect: { stage: 'sanity', expectSanityFor: [protagonist] },
        input: { groupId: 'group_probe', mode: 'group', stage: 'sanity', results, workingState: structuredClone(withPersonality) } });

      // 6) 继续推进：§8.1 两条件
      const withTask = (actorId, task) => {
        const next = structuredClone(state);
        next.characters[actorId].tasks[task.id] = { id: task.id, ownerId: actorId, parentTaskId: null, goal: task.goal, status: 'pending' };
        return next;
      };
      const likelyState = withTask(other, { id: 'task_probe_block', goal: `拦下${protagonistName}，不让他离开` });
      const unrelatedState = withTask(other, { id: 'task_probe_inventory', goal: '独自清点走廊尽头的箱子' });
      const noDriverState = structuredClone(state);
      for (const actor of Object.values(noDriverState.characters)) for (const task of Object.values(actor.tasks)) task.status = 'achieved';
      const probeRound = (cursor, acted) => ({ roundId: 'round_probe', trigger: 'player', order: roster, cursor,
        actedIds: acted, visitedIds: acted, conclusion: null });
      const roundChanges = [{ pointId: 'point_probe', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } },
        entityDeltas: {} }];
      H.programNextRoundIds = ['round_probe_likely', 'round_probe_unrelated', 'round_probe_done'];
      await run({ id: 'continuation_likely_related', task: 'continuation',
        focus: 'a task that drives a likely action toward the protagonist justifies continue',
        expect: { continuation: 'continue-required', driver: other },
        input: { round: probeRound(roster.length, roster), head: H.head, workingState: likelyState, roundChanges } });
      await run({ id: 'continuation_unrelated', task: 'continuation',
        focus: 'a likely action with no protagonist relation hands back',
        expect: { continuation: 'handback-expected' },
        input: { round: probeRound(roster.length, roster), head: H.head, workingState: unrelatedState, roundChanges } });
      await run({ id: 'continuation_done', task: 'continuation',
        focus: 'no pending task and no stated driver hands back',
        expect: { continuation: 'handback-required' },
        input: { round: probeRound(roster.length, roster), head: H.head, workingState: noDriverState, roundChanges } });

      return { probes, stateFingerprint: { worldId: state.worldId, time: state.time, roster, protagonist } };
    });
    report.tasks.probes = report.tasks.probes.map((probe) => ({ ...probe, judgment: judgeProbe(probe, judgeContext()) }));
    report.tasks.rates = summarizeProbes(report.tasks.probes);
    report.tasks.judgeSelfTest = runJudgeSelfTests(judgeContext());
    report.judgeVersion = 2;
    save();
    console.log(`[world-b3] task probes recorded: ${report.tasks.probes.length} ` +
      `(structure ${report.tasks.rates.structurePass}/${report.tasks.rates.probes}, ` +
      `semantics pass ${report.tasks.rates.semanticsPass}, fail ${report.tasks.rates.semanticsFail}, ` +
      `review ${report.tasks.rates.pendingReview}; judge self-test failures ${report.tasks.judgeSelfTest.failed})`);
  } catch (error) { harnessError(error, 'task probes'); }
  } else { report.tasks = { skipped: true, reason: '--skip-tasks iteration run' }; save(); }

  if (scope.scenes !== 'chain' && scope.scenes !== 'none') {
  // ---- scene 1: normal action point, ALL settlement tasks from the model ----
  try {
    report.scenes.action = await page.evaluate(async () => {
      const H = window.__h;
      const { ControllerDriver, initialMemory } = await import('/src/lib/world-engine/controller.ts');
      const state = structuredClone((await H.rawOp('get_state', {}, { tag: 'probe' })).state);
      const roster = Object.keys(state.characters);
      const namespace = `b3_action_${Date.now().toString(36)}`;
      let sequence = 0;
      const next = () => `${namespace}_${++sequence}`;
      const api = async (operation, payload) => H.rawOp(operation, payload, { tag: 'setup' });
      const base = () => ({ requestId: next() });
      const callsMark = H.b3.calls.length;
      const narrationMark = H.narrationLog.length;
      const eventMark = H.events.length;
      const opMark = H.opLog.length;
      const wireMark = H.wireCaptures.length;
      const T_CHAIN = { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } };
      const T_AUTO = { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } };
      // 程序预分配：本轮首点 + 后续自动轮身份。首点必须是 normal；后续自动
      // 轮也用 normal（空点仍会逐个判断 actor）。自动轮没有玩家输入，action
      // 端口按 consumed 规则应全部 skip；模型若强行行动，场景按失败记录。
      const ids = await (async () => {
        const allocation = await api('allocate_ids', { ...base(), allocationKey: `${namespace}_ids`, slots: [
          { slotKey: 'point_1', kind: 'point' },
          ...Array.from({ length: 4 }, (_, index) => ({ slotKey: `round_auto${index + 1}`, kind: 'round' })),
          ...Array.from({ length: 4 }, (_, index) => ({ slotKey: `point_auto${index + 1}`, kind: 'point' }))] });
        return Object.fromEntries(allocation.allocations.map((entry) => [entry.slotKey, entry.id]));
      })();
      const pointIds = [ids.point_1, ...Array.from({ length: 4 }, (_, index) => ids[`point_auto${index + 1}`])];
      H.programPlans = [
        [{ pointId: ids.point_1, kind: 'normal', timeAdvance: T_CHAIN, actorIds: [...roster] }],
        ...Array.from({ length: 4 }, (_, index) => [{ pointId: ids[`point_auto${index + 1}`], kind: 'normal',
          timeAdvance: T_AUTO, actorIds: [...roster] }]),
      ];
      H.programNextRoundIds = Array.from({ length: 4 }, (_, index) => ids[`round_auto${index + 1}`]);
      if (!H.lease?.leaseToken) throw new Error('action scene requires the bootstrap lease');
      const memory = initialMemory(`${namespace}_driver`, 'b3_action_holder');
      memory.budget.max = 40; // 场景预算：只防无界继续推进，不替模型做语义判断
      const driver = new ControllerDriver({ transport: H.transport, model: H.b3Port }, memory);
      const setupStarted = performance.now();
      const recovered = await driver.recover(H.worldId, { leaseToken: H.lease.leaseToken, fenceEpoch: H.lease.fenceEpoch });
      if (recovered) throw new Error(`action recover: ${JSON.stringify(recovered)}`);
      // 失败即交付：driver 的 stop 状态原样记录，不换脚本候选
      driver.preparePlayerInput('走到走廊', roster, { allocationKey: `${namespace}_cmd1`, slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
        { slotKey: 'point', kind: 'point' }, ...roster.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' }))] },
        ['advance', 'input', 'round', 'point', ...roster.map((actor) => `group:${actor}`)]);
      const setupMs = Math.round(performance.now() - setupStarted);
      const started = performance.now();
      let status;
      let runError = null;
      try { status = await driver.run(80); } catch (error) { runError = String(error?.stack ?? error); status = { kind: 'error', detail: 'model port threw' }; }
      const walkMs = Math.round(performance.now() - started);
      const completed = !runError && (status === undefined || (status.kind === 'stop' && status.reason === 'world_complete'));
      const modelTasks = H.b3.calls.slice(callsMark);
      const narration = H.narrationLog.slice(narrationMark);
      const events = H.events.slice(eventMark);
      const finalRead = await H.rawOp('get_state', {}, { tag: 'probe' });
      const points = (await H.rawOp('list_points', { after: null, limit: 100 }, { tag: 'probe' })).points;
      const scenePointIds = new Set(pointIds);
      const scenePoints = points.filter((point) => scenePointIds.has(point.pointId))
        .map((point) => ({ pointId: point.pointId, kind: point.kind, roundId: point.roundId, version: point.version }));
      const narrationEvents = events.filter((event) => event.kind === 'narration');
      const narrationFallbacks = narrationEvents.filter((event) => !event.polished).length;
      const polishFallbacks = events.filter((event) => event.kind === 'polishFallback').length;
      let cleanup = null;
      let cleanupError = null;
      if (!completed) {
        try {
          const context = await H.rawOp('get_context', { includeRecovery: false }, { tag: 'cleanup' });
          const advanceId = context.world?.advance?.advanceId ?? null;
          const roundId = context.world?.activeRoundId ?? context.world?.round?.roundId ?? null;
          if (advanceId) {
            await api('round_conclusion_cancel', { ...base(), operation: 'cancel', advanceId, roundId, cancelReason: 'b3_action_scene_stopped' });
            cleanup = { canceledRound: roundId, advanceId };
          } else cleanup = { alreadyIdle: true };
        } catch (error) { cleanupError = String(error?.message ?? error); }
      }
      return { status: completed ? 'COMPLETED' : status, runError, cleanup, cleanupError, setupMs, walkMs,
        recovered, budget: driver.getMemory().budget, playerInput: '走到走廊',
        pointIds, scenePoints, finalState: { pointId: finalRead.pointId, version: finalRead.version, time: finalRead.state.time,
          characters: Object.fromEntries(Object.entries(finalRead.state.characters).map(([id, actor]) => [id, {
            position: actor.position, sanity: actor.sanity,
            tasks: Object.values(actor.tasks).map((task) => ({ id: task.id, goal: task.goal, status: task.status })),
            personality: [...(actor.personalityChanges ?? [])].filter((change) => change.active).map((change) => change.text) }])) },
        modelTasks: modelTasks.map((call) => ({ task: call.task, key: call.key, at: call.at, source: call.source ?? 'model',
          prompt: call.prompt, promptChars: call.promptChars, raw: call.raw, output: call.output, parseError: call.parseError ?? null,
          validationError: call.validationError ?? null, error: call.error ?? null, errorName: call.errorName ?? null,
          backfills: call.backfills ?? [], completion: call.completion ?? null, context: call.context ?? null, ms: call.ms })),
        narration, events, narrationFallbacks, polishFallbacks,
        wire: H.wireCaptures.slice(wireMark), ops: H.opLog.slice(opMark) };
    });
    report.scenes.action.judged = judgeScene(report.scenes.action, judgeContext());
    report.status = 'PASS_ACTION_SCENE'; save();
    console.log(`[world-b3] scene action: ${JSON.stringify(report.scenes.action.status)} walk=${report.scenes.action.walkMs}ms ` +
      `modelCalls=${report.scenes.action.modelTasks.length}`);
  } catch (error) {
    report.scenes.action = { status: 'FAILED', error: String(error?.stack ?? error), consoleTrail: consoleTrail.slice(-20) };
    save();
    console.error('[world-b3] scene action failed:', error);
  }
  }

  if (scope.scenes !== 'action' && scope.scenes !== 'none') {
  // ---- scene 2: joint settlement chain, real d20, all settlement tasks model ----
  try {
    report.scenes.chain = await page.evaluate(async () => {
      const H = window.__h;
      const { ControllerDriver, initialMemory } = await import('/src/lib/world-engine/controller.ts');
      const state = structuredClone((await H.rawOp('get_state', {}, { tag: 'probe' })).state);
      const roster = Object.keys(state.characters);
      const namespace = `b3_chain_${Date.now().toString(36)}`;
      let sequence = 0;
      const next = () => `${namespace}_${++sequence}`;
      const api = async (operation, payload) => H.rawOp(operation, payload, { tag: 'setup' });
      const base = () => ({ requestId: next() });
      const worldIdBefore = H.worldId;
      const setupStarted = performance.now();
      // 场景隔离：上一场景失败可能留下未提交点位；先读当前 advance 并整轮
      // cancel，保证链场景从可开局状态开始（取消本身不产生点）。
      const idleContext = await H.rawOp('get_context', { includeRecovery: false }, { tag: 'setup' });
      if (idleContext.world?.advance?.advanceId) {
        await api('round_conclusion_cancel', { ...base(), operation: 'cancel', advanceId: idleContext.world.advance.advanceId,
          roundId: idleContext.world.activeRoundId ?? idleContext.world.round?.roundId, cancelReason: 'previous_scene_left_round_open' });
      }
      // 未准入重试：同世界 cancel + 下一轮尝试（与 twenty v2 同款）
      const worldAttempts = [];
      const abandonedRounds = [];
      let ids = null;
      let admitted = false;
      let frozenOrder = roster;
      for (let attempt = 1; attempt <= 6 && !admitted; attempt++) {
        const allocation = await api('allocate_ids', { ...base(), allocationKey: `${namespace}_a${attempt}`, slots: [
          { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
          { slotKey: 'point_1', kind: 'point' }, { slotKey: 'group_1', kind: 'group' },
          { slotKey: 'trigger:ring', kind: 'trigger' },
          ...Array.from({ length: 4 }, (_, index) => ({ slotKey: `round_auto${index + 1}`, kind: 'round' })),
          ...Array.from({ length: 4 }, (_, index) => ({ slotKey: `point_auto${index + 1}`, kind: 'point' }))] });
        ids = Object.fromEntries(allocation.allocations.map((entry) => [entry.slotKey, entry.id]));
        const inputText = '推开门厅深处的重门，示意同伴到门边一起撑住。';
        await api('checkpoint_start_advance', { ...base(), operation: 'start_advance', advanceId: ids.advance, inputId: ids.input,
          roundId: ids.round, inputText, order: roster });
        frozenOrder = (await H.rawOp('get_context', { includeRecovery: false }, { tag: 'setup' })).world?.round?.order ?? roster;
        const initiator = frozenOrder[0];
        const reactor = frozenOrder[1] ?? frozenOrder[0];
        await api('checkpoint_begin_point', { ...base(), operation: 'begin_point', pointId: ids.point_1, kind: 'normal',
          timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } } });
        await api('checkpoint_discover_group', { ...base(), operation: 'discover_group', pointId: ids.point_1, groupId: ids.group_1,
          initiatorId: initiator, actionText: inputText, targetIds: null });
        await api('checkpoint_extend_group', { ...base(), operation: 'extend_group', pointId: ids.point_1, groupId: ids.group_1,
          sourceId: initiator, targets: [{ targetId: reactor, triggerKey: ids['trigger:ring'] }], admittedMember: null });
        const ringRoll = (await api('create_rolls', { ...base(), rolls: [{ advanceId: ids.advance, roundId: ids.round, groupId: ids.group_1,
          sourceId: initiator, targetId: reactor, triggerKey: ids['trigger:ring'],
          ruleVersion: 'reaction-d20-v1', target: 11 }] })).rolls[0];
        worldAttempts.push({ attempt, roundId: ids.round, initiator, reactor,
          roll: { admitted: ringRoll.admitted, rollId: ringRoll.rollId, result: ringRoll.result, eligible: ringRoll.eligible } });
        if (ringRoll.admitted) admitted = true;
        else {
          await api('round_conclusion_cancel', { ...base(), operation: 'cancel', advanceId: ids.advance,
            roundId: ids.round, cancelReason: `first_ring_roll_${ringRoll.result}_not_admitted` });
          abandonedRounds.push({ attempt, roundId: ids.round, rollResult: ringRoll.result });
        }
      }
      if (!admitted) return { status: 'NO_ADMISSION', worldAttempts, abandonedRounds };
      const setupMs = Math.round(performance.now() - setupStarted);
      // 驱动器接管：targets/reaction/(targets)/results/updates/commit/narration/continuation 全模型
      const callsBefore = H.b3.calls.length;
      const narrationMark = H.narrationLog.length;
      const eventMark = H.events.length;
      const opMark = H.opLog.length;
      const wireMark = H.wireCaptures.length;
      const T_AUTO = { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } };
      const pointIds = [ids.point_1, ...Array.from({ length: 4 }, (_, index) => ids[`point_auto${index + 1}`])];
      H.programPlans = Array.from({ length: 4 }, (_, index) => [{ pointId: ids[`point_auto${index + 1}`], kind: 'normal',
        timeAdvance: T_AUTO, actorIds: [...roster] }]);
      H.programNextRoundIds = Array.from({ length: 4 }, (_, index) => ids[`round_auto${index + 1}`]);
      const memory = initialMemory(`${namespace}_driver`, 'b3_chain_holder');
      memory.budget.max = 40;
      const driver = new ControllerDriver({ transport: H.transport, model: H.b3Port }, memory);
      const recovered = await driver.recover(H.worldId, { leaseToken: H.lease.leaseToken, fenceEpoch: H.lease.fenceEpoch });
      if (recovered) throw new Error(`chain recover: ${JSON.stringify(recovered)}`);
      const started = performance.now();
      let status;
      let runError = null;
      try { status = await driver.run(80); } catch (error) { runError = String(error?.stack ?? error); status = { kind: 'error', detail: 'model port threw' }; }
      const walkMs = Math.round(performance.now() - started);
      const completed = !runError && (status === undefined || (status.kind === 'stop' && status.reason === 'world_complete'));
      const modelTasks = H.b3.calls.slice(callsBefore);
      const narration = H.narrationLog.slice(narrationMark);
      const events = H.events.slice(eventMark);
      const finalRead = await H.rawOp('get_state', {}, { tag: 'probe' });
      const points = (await H.rawOp('list_points', { after: null, limit: 100 }, { tag: 'probe' })).points;
      const scenePointIds = new Set(pointIds);
      const scenePoints = points.filter((point) => scenePointIds.has(point.pointId))
        .map((point) => ({ pointId: point.pointId, kind: point.kind, roundId: point.roundId, version: point.version }));
      const narrationEvents = events.filter((event) => event.kind === 'narration');
      const narrationFallbacks = narrationEvents.filter((event) => !event.polished).length;
      const polishFallbacks = events.filter((event) => event.kind === 'polishFallback').length;
      return { status: completed ? 'COMPLETED' : status, runError, setupMs, walkMs, recovered, budget: driver.getMemory().budget,
        playerInput: '推开门厅深处的重门，示意同伴到门边一起撑住。',
        worldIdBefore, worldAttempts, abandonedRounds, pointIds, scenePoints,
        finalState: { pointId: finalRead.pointId, version: finalRead.version, time: finalRead.state.time,
          characters: Object.fromEntries(Object.entries(finalRead.state.characters).map(([id, actor]) => [id, {
            position: actor.position, sanity: actor.sanity,
            tasks: Object.values(actor.tasks).map((task) => ({ id: task.id, goal: task.goal, status: task.status })),
            personality: [...(actor.personalityChanges ?? [])].filter((change) => change.active).map((change) => change.text) }])) },
        modelTasks: modelTasks.map((call) => ({ task: call.task, key: call.key, at: call.at, source: call.source ?? 'model',
          prompt: call.prompt, promptChars: call.promptChars, raw: call.raw, output: call.output, parseError: call.parseError ?? null,
          validationError: call.validationError ?? null, error: call.error ?? null, errorName: call.errorName ?? null,
          backfills: call.backfills ?? [], completion: call.completion ?? null, context: call.context ?? null, ms: call.ms })),
        narration, events, narrationFallbacks, polishFallbacks,
        wire: H.wireCaptures.slice(wireMark), ops: H.opLog.slice(opMark) };
    });
    report.scenes.chain.judged = judgeScene(report.scenes.chain, judgeContext());
    report.status = 'PASS_CHAIN_SCENE'; save();
    console.log(`[world-b3] scene chain: ${JSON.stringify(report.scenes.chain.status)} walk=${report.scenes.chain.walkMs}ms ` +
      `modelCalls=${(report.scenes.chain.modelTasks ?? []).length}`);
  } catch (error) {
    report.scenes.chain = { status: 'FAILED', error: String(error?.stack ?? error), consoleTrail: consoleTrail.slice(-20) };
    save();
    console.error('[world-b3] scene chain failed:', error);
  }
  }

  // ---- final report ----
  if (!report.tasks) report.tasks = { skipped: true, reason: '--skip-tasks iteration run' };
  const expectedScenes = scope.scenes === 'both' ? ['action', 'chain'] : scope.scenes === 'none' ? [] : [scope.scenes];
  const sceneFailures = expectedScenes.filter((name) => report.scenes[name]?.status !== 'COMPLETED');
  const semanticFailures = expectedScenes.filter((name) => report.scenes[name] && report.scenes[name].judged?.accepted !== true);
  const selfTestFailed = report.tasks?.judgeSelfTest?.failed ?? 0;
  report.status = sceneFailures.length ? 'COMPLETED_WITH_FAILURES'
    : semanticFailures.length ? 'COMPLETED_WITH_SEMANTIC_FAILURES'
    : selfTestFailed > 0 ? 'JUDGE_SELF_TEST_FAILED' : 'COMPLETED';
  report.summary = {
    scope, judgeVersion: report.judgeVersion ?? null,
    taskRates: report.tasks?.rates ?? null,
    judgeSelfTest: report.tasks?.judgeSelfTest ? { cases: report.tasks.judgeSelfTest.cases.length, failed: report.tasks.judgeSelfTest.failed } : null,
    scenes: Object.fromEntries(expectedScenes.map((name) => [name, report.scenes[name] ? {
      status: report.scenes[name].status, accepted: report.scenes[name].judged?.accepted ?? null,
      modelCalls: report.scenes[name].judged?.modelCalls ?? null,
      programCalls: report.scenes[name].judged?.programCalls ?? null,
      semanticErrors: report.scenes[name].judged?.semanticErrors?.length ?? null,
      pendingReview: report.scenes[name].judged?.pendingReview?.length ?? null,
      narrationFallbacks: report.scenes[name].judged?.narrationFallbacks?.length ?? null } : null])),
    note: 'Model calls are counted by source; program-owned pointPlan/time calls are reported separately. '
      + 'accepted=false means the protocol completed but settlement/narration semantics failed or still need review; see the scene evidence.',
  };
  save();
  console.log(`[world-b3] ${report.status} → ${output}`);
  cleanup();
  await browser.close();
  try { service.kill(); } catch {}
  await new Promise((done) => {
    if (service.exitCode !== null) return done();
    const timer = setTimeout(done, 5000);
    service.once('exit', () => { clearTimeout(timer); done(); });
  });
  try { service.kill('SIGKILL'); } catch {}
  const dbSnapshotDir = resolve(root, dbSnapshotOption);
  mkdirSync(dbSnapshotDir, { recursive: true });
  report.retainedEvidence = { privateDir, dbSnapshot: dbSnapshotOption };
  for (const suffix of ['', '-wal', '-shm']) {
    const source = resolve(privateDir, `world.db${suffix}`);
    if (existsSync(source)) copyFileSync(source, resolve(dbSnapshotDir, `world.db${suffix}`));
  }
  if (existsSync(resolve(privateDir, 'server.log'))) copyFileSync(resolve(privateDir, 'server.log'), resolve(dbSnapshotDir, 'server.log'));
  save();
  console.log(`[world-b3] ${report.status} → ${output} (db+log retained in ${dbSnapshotOption})`);
  process.exit(0);
} catch (error) {
  report.status = 'FAILED';
  report.error = String(error?.stack ?? error);
  report.consoleTrail = consoleTrail.slice(-40);
  save();
  cleanup();
  try { if (browser) await browser.close(); } catch {}
  console.error('[world-b3] FAILED:', error);
  process.exit(1);
}
