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
//   `--only` / `--skip-tasks` are iteration switches; the canonical report is
//   the default full run (both scenes + task probes) and records its scope.
// Failures are deliverable evidence: a scene whose model candidates fail is
// recorded as failed — never replaced by scripted candidates and passed off
// as model success. A setup failure aborts; a scene failure is kept and the
// other scene still runs.
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, createWriteStream, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer as createNetServer } from 'node:net';
import { createServer } from 'vite';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const a = resolve(root, option('--server-checkout', '.local/world-server-worktree'));
const output = resolve(root, option('--out', 'artifacts/world-chain/b3-baseline.json'));
const dbSnapshotOption = option('--db-snapshot', 'artifacts/world-chain/b3-run-db');
const scope = { tasks: !process.argv.includes('--skip-tasks'), scenes: option('--only', 'both') };
if (!['action', 'chain', 'both'].includes(scope.scenes)) throw new Error(`--only expects action|chain|both, got ${scope.scenes}`);
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
  scope, modelLoad: null, modelConfig: {
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
                || (change.supersedes !== undefined && !Array.isArray(change.supersedes))) return { calls, error: `invalid ${key} item` };
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

    // 各任务端口。来源标记：program（pointPlan/time——不在 B3 模型化范围）。
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
        `- tasksAchieved：数组，元素必须是状态中已有的任务 id\n` +
        `- subtasksAdded：数组，元素 {"id":"draft_1","ownerId":"<角色id>","parentTaskId":null,"goal":"<新任务>","status":"pending"}\n` +
        `- personalityChanges：数组，元素 {"id":"draft_1","text":"<个性变化>","supersedes":[]}\n` +
        `- sanitySet：0 到 100 的整数，只写最终值（不要函数、字符串或表达式）\n` +
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
          const prompt = `你是文字冒险游戏的行动裁判。所有文本必须使用简体中文。\n${view}\n玩家输入原文：${input.advance?.inputText ?? '(无)'}\n` +
            `行动者：${actorName}（id=${input.actor}）。输入状态：${consumed ? '该输入已被消费' : '待处理'}\n` +
            `规则：输入状态是“该输入已被消费”时，必须输出 {"kind":"skip","text":""}，不得输出 act。\n` +
            `行动描述不超过 40 字，必须是第三人称、以${actorName}为主语，不得引入状态中未列出的角色或物品。\n` +
            `只输出 JSON：{"kind":"act","text":"<行动描述>"} 或 {"kind":"skip","text":""}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { kind: { type: 'string', enum: ['act', 'skip'] }, text: { type: 'string' } }, required: ['kind', 'text'] }, 128);
          if (out.kind === 'act' && !out.text) throw new Error('b3 action act with empty text');
          return out.kind === 'skip' ? { kind: 'skip' } : { kind: 'act', text: out.text };
        }
        if (task === 'targets') {
          const sourceName = nameOf(state, input.sourceId);
          const prompt = `你是目标判定器。所有文本必须使用简体中文。\n${view}\n行动（发起者 ${sourceName}，id=${input.sourceId}）：${input.actionText}\n` +
            `判断该行动是否指向场上另一名角色。只输出角色 id，不要输出名字、物品或地点。\n` +
            `不要指向本组中已经行动过的角色。不指向任何角色则输出空数组。\n` +
            `只输出 JSON：{"targets":["<被指向角色的id>"]} 或 {"targets":[]}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { targets: { type: 'array', items: { type: 'string' } } }, required: ['targets'] }, 64);
          if (!Array.isArray(out.targets)) throw new Error('b3 targets without array');
          const roster = new Set(Object.keys(state?.characters ?? {}));
          const backfills = [];
          out.targets = out.targets.filter((target) => {
            if (roster.has(target)) return true;
            backfills.push({ kind: 'target_dropped_not_in_roster', value: target });
            return false;
          });
          b3.calls[b3.calls.length - 1].backfills = backfills;
          return { targets: out.targets };
        }
        if (task === 'reaction') {
          const sourceName = nameOf(state, input.sourceId);
          const memberName = nameOf(state, input.memberId);
          const prompt = `你是反应描写器。所有文本必须使用简体中文。\n${view}\n发起者 ${sourceName} 的行动：${input.sourceActionText}\n` +
            `${memberName} 已被卷入（判定已准入）。写一句 ${memberName} 的第三人称反应行动，不超过 30 字；只写反应动作，不写结果或心理。\n` +
            `只输出 JSON：{"text":"<反应行动>"}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] }, 96);
          if (!out.text) throw new Error('b3 reaction with empty text');
          return out.text;
        }
        if (task === 'results') {
          const memberLines = input.members.map((member) => {
            return `- id=${member.memberId}（${nameOf(state, member.memberId)}）：${member.actionText}`;
          }).join('\n');
          const prompt = `你是结果判定器。所有文本必须使用简体中文。\n${view}\n本组冻结行动：\n${memberLines}\n` +
            `为每个成员写一句第三人称结算结果，只描述这些行动的直接后果，不新增未发生的事件。\n` +
            `只输出 JSON 对象，必须恰好包含这些键：${input.members.map((member) => `"${member.memberId}"`).join(', ')}`;
          const schema = { type: 'object', properties: Object.fromEntries(input.members.map((member) => [member.memberId, { type: 'string' }])),
            required: input.members.map((member) => member.memberId) };
          const out = await b3.complete(task, key, prompt, schema, 128);
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
            `判断规则：如果状态中所有任务都已达成（未完成数=0），本轮结束后交还玩家；如果仍有未完成任务，继续推进。\n` +
            `继续时 candidateCharacterIds 只能使用状态中列出的角色 id，至少一个；nextRoundId 写占位符即可（程序会回填永久身份）。\n` +
            `只输出 JSON：\n{"kind":"continue","candidateCharacterIds":["<角色id>",...],"nextRoundId":"pending","cancelReason":null}\n或\n{"kind":"handback","cancelReason":null}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { kind: { type: 'string', enum: ['continue', 'handback'] },
              candidateCharacterIds: { type: 'array', items: { type: 'string' } }, nextRoundId: { type: 'string' },
              cancelReason: { type: ['null', 'string'] } }, required: ['kind'] }, 96);
          const backfills = [];
          out.cancelReason = null;
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
            // 永久 ID 归程序：nextRoundId 一律回填为程序预分配的候选身份
            const nextRoundId = H.programNextRoundIds.shift();
            if (!nextRoundId) throw new Error('b3 next round id budget exhausted');
            if (out.nextRoundId !== nextRoundId) {
              backfills.push({ kind: 'next_round_id_backfilled', modelValue: out.nextRoundId ?? null, programValue: nextRoundId });
              out.nextRoundId = nextRoundId;
            }
          }
          b3.calls[b3.calls.length - 1].backfills = backfills;
          b3.calls[b3.calls.length - 1].context = { pending: pending.length };
          return out;
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

  if (scope.tasks) {
  // ---- task-level probes ----
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
        probes.push({ id: probe.id, task: probe.task, focus: probe.focus, input: probe.input, output: outcome, failure,
          ms: Math.round(performance.now() - started),
          call: H.b3.calls[H.b3.calls.length - 1] ?? null });
      };

      // 1) 角色归属 + 已消费输入（action）
      await run({ id: 'action_pending', task: 'action', focus: 'pending input yields an action proposal',
        input: { actor: protagonist, advance: baseAdvance({ inputText: '走到走廊' }), workingState: structuredClone(state) } });
      await run({ id: 'action_consumed', task: 'action', focus: 'consumed input must be skipped',
        input: { actor: protagonist, advance: baseAdvance({ intentStatus: 'consumed' }), workingState: structuredClone(state) } });
      await run({ id: 'action_nonactor', task: 'action', focus: 'role attribution: another actor for the same input',
        input: { actor: other, advance: baseAdvance({ inputText: '上下打量四周' }), workingState: structuredClone(state) } });

      // 2) 目标判定（targets）
      await run({ id: 'targets_directed', task: 'targets', focus: 'action naming another character yields that target',
        input: { sourceId: protagonist, actionText: `${protagonistName} 推开门厅深处的重门，示意 ${otherName} 到门边一起撑住。`, workingState: structuredClone(state) } });
      await run({ id: 'targets_solo', task: 'targets', focus: 'solo action yields no targets',
        input: { sourceId: protagonist, actionText: `${protagonistName} 独自检查了走廊的墙壁。`, workingState: structuredClone(state) } });

      // 2b) 反应（reaction）：被卷入者的第三人称反应行动
      await run({ id: 'reaction_joint', task: 'reaction', focus: 'admitted member gets a reaction action',
        input: { sourceId: protagonist, sourceActionText: `${protagonistName} 示意 ${otherName} 一起撑住重门。`, memberId: other,
          rollId: 'probe_roll', workingState: structuredClone(state) } });

      // 3) 共同结果（results）：必须覆盖全部成员
      await run({ id: 'results_joint', task: 'results', focus: 'joint results must cover every member',
        input: { groupId: 'group_probe', members: [
          { memberId: protagonist, actionText: `${protagonistName} 推开门示意同伴一起撑住。`, rollRefs: [] },
          { memberId: other, actionText: `${otherName} 上前与同伴一起撑住重门。`, rollRefs: [] }],
          workingState: structuredClone(state) } });

      // 4) 更新阶段依赖（updates）：merged + 分阶段（后序阶段读前序应用后的状态）
      const results = { [protagonist]: `${protagonistName} 完成了压力试验，精神受到冲击。`, [other]: `${otherName} 在一旁见证了整个过程。` };
      await run({ id: 'updates_merged', task: 'updates', focus: 'merged updates produce legal stage candidates',
        input: { groupId: 'group_probe', mode: 'group', results, workingState: structuredClone(state) } });
      // 分阶段：第一阶段 tasks → 程序应用 → 第二阶段 sanity 读应用后的状态
      let taskStage = null;
      let taskStageFailure = null;
      try { taskStage = await H.b3Port.generate('updates', 'probe#tasks',
        { groupId: 'group_probe', mode: 'group', stage: 'tasks', results, workingState: structuredClone(state) }); }
      catch (error) { taskStageFailure = String(error?.message ?? error); }
      probes.push({ id: 'updates_stage_tasks', task: 'updates', focus: 'tasks stage candidates', input: { stage: 'tasks' },
        output: taskStage, failure: taskStageFailure, ms: 0, call: H.b3.calls[H.b3.calls.length - 1] ?? null });
      // 程序应用第一阶段（与控制器 mergeUpdatesStages 同构的最小应用：任务达成 + 新增子任务）
      const applied = structuredClone(state);
      const taskStageCalls = Array.isArray(taskStage) ? taskStage : taskStage ? [taskStage] : [];
      for (const call of taskStageCalls) {
        for (const [entity, delta] of Object.entries(call.changes ?? {})) {
          for (const taskId of delta.tasksAchieved ?? []) if (applied.characters[entity]?.tasks?.[taskId]) applied.characters[entity].tasks[taskId].status = 'achieved';
          for (const task of delta.subtasksAdded ?? []) {
            if (applied.characters[entity]?.tasks && task?.id) applied.characters[entity].tasks[task.id] = task;
          }
        }
      }
      await run({ id: 'updates_stage_sanity', task: 'updates', focus: 'sanity stage reads the applied post-tasks state',
        input: { groupId: 'group_probe', mode: 'group', stage: 'sanity', results, workingState: applied } });

      // 5) 继续条件（continuation）：continue 与 handback 两个变体
      const roundChanges = [{ pointId: 'point_probe', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } },
        entityDeltas: {} }];
      H.programNextRoundIds = ['round_probe_next', 'round_probe_next_2'];
      await run({ id: 'continuation_more', task: 'continuation', focus: 'unfinished round continues',
        input: { round: { roundId: 'round_probe', trigger: 'player', order: roster, cursor: 0, actedIds: [], visitedIds: [], conclusion: null },
          head: H.head, workingState: structuredClone(state), roundChanges } });
      const doneState = structuredClone(state);
      for (const actor of Object.values(doneState.characters)) for (const task of Object.values(actor.tasks)) task.status = 'achieved';
      await run({ id: 'continuation_done', task: 'continuation', focus: 'everything achieved hands back',
        input: { round: { roundId: 'round_probe', trigger: 'player', order: roster, cursor: roster.length, actedIds: roster, visitedIds: roster, conclusion: null },
          head: H.head, workingState: doneState, roundChanges } });

      // ---- judgments: structure vs semantics, counted separately ----
      const judge = (probe) => {
        const { id, output: out, failure } = probe;
        const call = probe.call;
        if (failure || out == null) {
          if (call?.output != null && call?.validationError) {
            return { id, structure: true, semantics: false, why: call.validationError, note: 'parsed but semantically invalid' };
          }
          return { id, structure: false, semantics: false, why: failure ?? 'no output' };
        }
        const ok = (cond, why) => ({ id, structure: cond, semantics: cond, why: cond ? null : why });
        switch (id) {
          case 'action_pending': {
            if (out.kind !== 'act' && out.kind !== 'skip') return ok(false, `illegal kind ${out.kind}`);
            if (out.kind === 'act' && (typeof out.text !== 'string' || !out.text.trim())) return ok(false, 'act without text');
            if (out.kind === 'act' && H.looksLikeGoal(out.text)) return { id, structure: true, semantics: false, why: `goal/plan is not an action: ${out.text}` };
            return { id, structure: true, semantics: true, why: null, note: out.kind === 'act' ? `act: ${out.text}` : 'skip' };
          }
          case 'action_consumed':
            return out.kind === 'skip' ? { id, structure: true, semantics: true, why: null }
              : { id, structure: true, semantics: false, why: `consumed input produced ${out.kind}` };
          case 'action_nonactor': {
            if (out.kind !== 'act' && out.kind !== 'skip') return ok(false, `illegal kind ${out.kind}`);
            if (out.kind === 'act' && H.looksLikeGoal(out.text)) return { id, structure: true, semantics: false, why: `goal/plan is not an action: ${out.text}` };
            return { id, structure: true, semantics: true, why: null, note: out.kind === 'act' ? `act: ${out.text}` : 'skip' };
          }
          case 'targets_directed':
            if (!Array.isArray(out.targets)) return ok(false, 'no targets array');
            return out.targets.includes(other) ? { id, structure: true, semantics: true, why: null, note: `targets=${JSON.stringify(out.targets)}` }
              : { id, structure: true, semantics: false, why: `expected ${other} in ${JSON.stringify(out.targets)}` };
          case 'targets_solo':
            if (!Array.isArray(out.targets)) return ok(false, 'no targets array');
            return out.targets.length === 0 ? { id, structure: true, semantics: true, why: null, note: 'no targets' }
              : { id, structure: true, semantics: false, why: `expected empty, got ${JSON.stringify(out.targets)}` };
          case 'reaction_joint': {
            if (typeof out !== 'string' || !out.trim()) return ok(false, 'reaction is empty');
            if (/精神值|理智|生命值|任务(达成|完成)|状态|属性/.test(out)) return { id, structure: true, semantics: false, why: `reaction claims a state change: ${out}` };
            return { id, structure: true, semantics: true, why: null, note: out };
          }
          case 'results_joint': {
            const keys = Object.keys(out);
            const want = [protagonist, other].sort().join(',');
            return keys.sort().join(',') === want && keys.every((key) => typeof out[key] === 'string' && out[key].trim())
              ? { id, structure: true, semantics: true, why: null, note: JSON.stringify(out) }
              : ok(false, `results keys ${keys} != [${protagonist},${other}] or empty text`);
          }
          case 'updates_merged':
          case 'updates_stage_tasks':
          case 'updates_stage_sanity': {
            const expected = id === 'updates_merged' ? null : id === 'updates_stage_tasks' ? 'tasks' : 'sanity';
            const audit = H.auditUpdates(out, expected, new Set(roster), H.taskOwnersOf(state));
            return audit.error ? { id, structure: true, semantics: false, why: audit.error }
              : { id, structure: true, semantics: true, why: null, note: `${audit.calls.length} call(s): ${audit.calls.map((call) => call.stage).join(',')}` };
          }
          case 'continuation_more': {
            if (out.kind !== 'continue' && out.kind !== 'handback') return ok(false, `illegal kind ${out.kind}`);
            if (out.kind !== 'continue') return { id, structure: true, semantics: false, why: 'unfinished round handed back' };
            const backfills = call?.backfills ?? [];
            const candidateBad = backfills.some((entry) => entry.kind === 'candidate_dropped_not_in_roster' || entry.kind === 'candidates_backfilled_roster');
            return candidateBad ? { id, structure: true, semantics: false, why: `invalid candidateCharacterIds: ${JSON.stringify(backfills)}` }
              : { id, structure: true, semantics: true, why: null, note: 'continue' };
          }
          case 'continuation_done': {
            if (out.kind !== 'continue' && out.kind !== 'handback') return ok(false, `illegal kind ${out.kind}`);
            return out.kind === 'handback' ? { id, structure: true, semantics: true, why: null, note: 'handback' }
              : { id, structure: true, semantics: false, why: 'finished round continued' };
          }
          default:
            return ok(false, 'unknown probe');
        }
      };
      const judged = probes.map(judge);
      const structurePass = judged.filter((entry) => entry.structure).length;
      const semanticsPass = judged.filter((entry) => entry.semantics).length;
      return {
        probes: probes.map((probe, index) => ({ ...probe, judgment: judged[index], call: probe.call ? {
          task: probe.call.task, key: probe.call.key, at: probe.call.at, prompt: probe.call.prompt, promptChars: probe.call.promptChars,
          raw: probe.call.raw, output: probe.call.output, parseError: probe.call.parseError, validationError: probe.call.validationError ?? null,
          error: probe.call.error ?? null, errorName: probe.call.errorName ?? null, ms: probe.call.ms,
          completion: probe.call.completion ?? null, backfills: probe.call.backfills ?? [], source: probe.call.source ?? 'model' } : null })),
        rates: { probes: judged.length, structurePass, structureRate: Number((structurePass / judged.length).toFixed(3)),
          semanticsPass, semanticsRate: Number((semanticsPass / judged.length).toFixed(3)),
          totalModelMs: probes.reduce((sum, probe) => sum + (probe.call?.ms ?? 0), 0) },
      };
    });
    report.status = 'PASS_TASKS'; save();
    console.log(`[world-b3] tasks: ${report.tasks.rates.structurePass}/${report.tasks.rates.probes} structure, ` +
      `${report.tasks.rates.semanticsPass}/${report.tasks.rates.probes} semantics, ${report.tasks.rates.totalModelMs}ms model time`);
  } catch (error) { harnessError(error, 'task probes'); }
  } else { report.tasks = { skipped: true, reason: '--skip-tasks iteration run' }; save(); }

  if (scope.scenes !== 'chain') {
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
      const semanticErrors = [];
      for (const call of modelTasks) {
        if (call.error) semanticErrors.push({ task: call.task, error: call.error });
        if (call.validationError) semanticErrors.push({ task: call.task, error: call.validationError });
        if (call.task === 'action' && call.output?.kind === 'act' && H.looksLikeGoal(call.output.text)) {
          semanticErrors.push({ task: 'action', error: `goal/plan is not an action: ${call.output.text}` });
        }
        if (call.task === 'targets' && (call.backfills ?? []).some((entry) => entry.kind === 'target_dropped_not_in_roster')) {
          semanticErrors.push({ task: 'targets', error: 'target dropped: not in roster', backfills: call.backfills });
        }
        if (call.task === 'continuation') {
          if ((call.backfills ?? []).some((entry) => entry.kind === 'candidate_dropped_not_in_roster' || entry.kind === 'candidates_backfilled_roster')) {
            semanticErrors.push({ task: 'continuation', error: 'invalid candidateCharacterIds', backfills: call.backfills });
          }
          if (call.context?.pending === 0 && call.output?.kind === 'continue') semanticErrors.push({ task: 'continuation', error: 'all tasks achieved but continued' });
          if (call.context?.pending > 0 && call.output?.kind === 'handback') semanticErrors.push({ task: 'continuation', error: 'pending tasks handed back' });
        }
      }
      for (const entry of narration) if (entry.error) semanticErrors.push({ task: 'narration', error: entry.error });
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
      return { status: completed ? 'COMPLETED' : status, runError, cleanup, cleanupError, setupMs, walkMs, recovered, budget: driver.getMemory().budget,
        pointIds, scenePoints, finalState: { pointId: finalRead.pointId, version: finalRead.version, time: finalRead.state.time,
          characters: Object.fromEntries(Object.entries(finalRead.state.characters).map(([id, actor]) => [id, {
            position: actor.position, sanity: actor.sanity,
            tasks: Object.values(actor.tasks).map((task) => ({ id: task.id, goal: task.goal, status: task.status })),
            personality: [...(actor.personalityChanges ?? [])].filter((change) => change.active).map((change) => change.text) }])) },
        modelTasks: modelTasks.map((call) => ({ task: call.task, key: call.key, at: call.at, source: call.source ?? 'model',
          prompt: call.prompt, promptChars: call.promptChars, raw: call.raw, output: call.output, parseError: call.parseError ?? null,
          validationError: call.validationError ?? null, error: call.error ?? null, errorName: call.errorName ?? null,
          backfills: call.backfills ?? [], completion: call.completion ?? null, context: call.context ?? null, ms: call.ms })),
        narration, events, semanticErrors, narrationFallbacks, polishFallbacks,
        accepted: completed && semanticErrors.length === 0 && narrationFallbacks === 0 && polishFallbacks === 0,
        wire: H.wireCaptures.slice(wireMark), ops: H.opLog.slice(opMark) };
    });
    report.status = 'PASS_ACTION_SCENE'; save();
    console.log(`[world-b3] scene action: ${JSON.stringify(report.scenes.action.status)} walk=${report.scenes.action.walkMs}ms ` +
      `modelCalls=${report.scenes.action.modelTasks.length}`);
  } catch (error) {
    report.scenes.action = { status: 'FAILED', error: String(error?.stack ?? error), consoleTrail: consoleTrail.slice(-20) };
    save();
    console.error('[world-b3] scene action failed:', error);
  }
  }

  if (scope.scenes !== 'action') {
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
      const semanticErrors = [];
      for (const call of modelTasks) {
        if (call.error) semanticErrors.push({ task: call.task, error: call.error });
        if (call.validationError) semanticErrors.push({ task: call.task, error: call.validationError });
        if (call.task === 'action' && call.output?.kind === 'act' && H.looksLikeGoal(call.output.text)) {
          semanticErrors.push({ task: 'action', error: `goal/plan is not an action: ${call.output.text}` });
        }
        if (call.task === 'targets' && (call.backfills ?? []).some((entry) => entry.kind === 'target_dropped_not_in_roster')) {
          semanticErrors.push({ task: 'targets', error: 'target dropped: not in roster', backfills: call.backfills });
        }
        if (call.task === 'continuation') {
          if ((call.backfills ?? []).some((entry) => entry.kind === 'candidate_dropped_not_in_roster' || entry.kind === 'candidates_backfilled_roster')) {
            semanticErrors.push({ task: 'continuation', error: 'invalid candidateCharacterIds', backfills: call.backfills });
          }
          if (call.context?.pending === 0 && call.output?.kind === 'continue') semanticErrors.push({ task: 'continuation', error: 'all tasks achieved but continued' });
          if (call.context?.pending > 0 && call.output?.kind === 'handback') semanticErrors.push({ task: 'continuation', error: 'pending tasks handed back' });
        }
      }
      for (const entry of narration) if (entry.error) semanticErrors.push({ task: 'narration', error: entry.error });
      const narrationEvents = events.filter((event) => event.kind === 'narration');
      const narrationFallbacks = narrationEvents.filter((event) => !event.polished).length;
      const polishFallbacks = events.filter((event) => event.kind === 'polishFallback').length;
      return { status: completed ? 'COMPLETED' : status, runError, setupMs, walkMs, recovered, budget: driver.getMemory().budget,
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
        narration, events, semanticErrors, narrationFallbacks, polishFallbacks,
        accepted: completed && semanticErrors.length === 0 && narrationFallbacks === 0 && polishFallbacks === 0,
        wire: H.wireCaptures.slice(wireMark), ops: H.opLog.slice(opMark) };
    });
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
  const expectedScenes = scope.scenes === 'both' ? ['action', 'chain'] : [scope.scenes];
  const sceneFailures = expectedScenes.filter((name) => report.scenes[name]?.status !== 'COMPLETED');
  const semanticFailures = expectedScenes.filter((name) => report.scenes[name] && report.scenes[name].accepted === false);
  report.status = sceneFailures.length ? 'COMPLETED_WITH_FAILURES'
    : semanticFailures.length ? 'COMPLETED_WITH_SEMANTIC_FAILURES' : 'COMPLETED';
  report.summary = {
    scope,
    taskRates: report.tasks?.rates ?? null,
    scenes: Object.fromEntries(expectedScenes.map((name) => [name, report.scenes[name] ? {
      status: report.scenes[name].status, accepted: report.scenes[name].accepted ?? null,
      modelCalls: report.scenes[name].modelTasks?.length ?? null,
      semanticErrors: report.scenes[name].semanticErrors?.length ?? null,
      narrationFallbacks: report.scenes[name].narrationFallbacks ?? null } : null])),
    note: 'accepted=false means the protocol completed but settlement/narration semantics failed; see the scene evidence.',
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
