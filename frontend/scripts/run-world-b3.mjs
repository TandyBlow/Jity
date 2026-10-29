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
// Failures are deliverable evidence: a scene whose model candidates fail is
// recorded as failed — never replaced by scripted candidates and passed off
// as model success.
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
const privateDir = resolve(root, `.local/world-b3-${Date.now()}`);
mkdirSync(privateDir, { recursive: true });
const sources = ['frontend/scripts/run-world-b3.mjs', 'frontend/src/app/world/narration-polisher.ts',
  ...['runtime/rule-session', 'runtime/rule-facts', 'runtime/committed-narration', 'runtime/prompts', 'runtime/wllama-engine',
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
  modelLoad: null, tasks: null, scenes: {},
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
      sessionOptions(holderId) {
        return { transport: H.transport, initial: defaultInitialTemplate(), policy: WORLD_POLICY, polish: H.polish,
          onEvent: (event) => H.events.push({ ...event, at: Date.now() }), holderId };
      },
    };
    window.__h = H;

    const LEASE_FREE = new Set(['create_world', 'list_points', 'get_state', 'get_context', 'preview_point']);
    const LEASE_OWN = new Set(['lease_acquire']);
    const PATH_POINT_OPS = new Set(['narration_get']);
    const NEEDS_HEAD = (operation) => operation.startsWith('checkpoint_') || operation === 'create_rolls';
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
      if (response.status >= 400) H.wireCaptures.push({ url: String(input), body: String(init?.body ?? '').slice(0, 400), status: response.status, response: (await response.clone().text()).slice(0, 300) });
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
    const renderState = (state) => {
      const lines = [`时间：${state.time.dateTime}`];
      for (const [id, actor] of Object.entries(state.characters)) {
        const tasks = Object.values(actor.tasks)
          .map((task) => `${task.goal}(${task.id},${task.status === 'achieved' ? '已达成' : '未完成'})`).join('；') || '无';
        lines.push(`角色 ${actor.name}（id=${id}）：位于${state.locations[actor.position.containerId]?.name ?? actor.position.containerId}，精神值${actor.sanity}。任务：${tasks}`);
      }
      return lines.join('\n');
    };
    const b3 = {
      calls: [], // {task, key, promptChars, output, ms, completion, backfills[], schema}
      temperature: 0,
      async complete(task, key, prompt, schema, maxTokens) {
        const engine = window.__b3engine;
        const started = performance.now();
        let completion = null;
        const onCompletion = (evidence) => { completion = evidence; };
        const raw = await engine.complete(prompt, { maxTokens, temperature: b3.temperature, cachePrompt: true,
          timeoutMs: 110_000, onCompletion, jsonSchema: schema });
        const ms = Math.round(performance.now() - started);
        let output = null;
        let parseError = null;
        try { output = JSON.parse(raw); } catch (error) { parseError = String(error); }
        b3.calls.push({ task, key, at: Date.now(), promptChars: prompt.length, raw: raw.slice(0, 400), output, parseError, ms, completion });
        if (parseError) throw new Error(`b3 ${task} output is not JSON: ${parseError} raw=${raw.slice(0, 200)}`);
        return output;
      },
    };
    H.b3 = b3;

    // 各任务端口。来源标记：program（pointPlan/time——不在 B3 模型化范围）。
    H.b3Port = {
      async generate(task, key, input) {
        if (task === 'pointPlan') {
          b3.calls.push({ task, key, at: Date.now(), source: 'program' });
          return H.programPointPlan(key, input);
        }
        if (task === 'time') {
          b3.calls.push({ task, key, at: Date.now(), source: 'program' });
          return { boundary: 'instant', duration: { amount: 0, unit: 'second' } };
        }
        const state = input.workingState ?? null;
        const view = state ? renderState(state) : '(状态不可用)';
        if (task === 'action') {
          const actor = state?.characters?.[input.actor];
          const consumed = input.advance?.intentStatus !== 'pending';
          const prompt = `你是文字冒险游戏的行动裁判。\n${view}\n玩家输入原文：${input.advance?.inputText ?? '(无)'}\n` +
            `行动者：${actor?.name ?? input.actor}（id=${input.actor}）。输入状态：${consumed ? '该输入已被消费' : '待处理'}\n` +
            `该输入已被消费时必须跳过。行动描述不超过 40 字。只输出 JSON：{"kind":"act","text":"<以${actor?.name ?? input.actor}为主语的第三人称行动描述>"} 或 {"kind":"skip","text":""}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { kind: { type: 'string', enum: ['act', 'skip'] }, text: { type: 'string' } }, required: ['kind', 'text'] }, 128);
          if (out.kind === 'act' && !out.text) throw new Error('b3 action act with empty text');
          return out.kind === 'skip' ? { kind: 'skip' } : { kind: 'act', text: out.text };
        }
        if (task === 'targets') {
          const source = state?.characters?.[input.sourceId];
          const prompt = `你是目标判定器。\n${view}\n行动（发起者 ${source?.name ?? input.sourceId}，id=${input.sourceId}）：${input.actionText}\n` +
            `判断该行动是否指向场上另一角色。只输出 JSON：{"targets":["<被指向角色的id>"]}；不指向任何角色则输出 {"targets":[]}`;
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
          const source = state?.characters?.[input.sourceId];
          const member = state?.characters?.[input.memberId];
          const prompt = `你是反应描写器。\n${view}\n发起者 ${source?.name ?? input.sourceId} 的行动：${input.sourceActionText}\n` +
            `${member?.name ?? input.memberId} 已被卷入（判定已准入）。写一句 ${member?.name ?? input.memberId} 的第三人称反应行动，不超过 30 字。\n` +
            `只输出 JSON：{"text":"<反应行动>"}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] }, 96);
          if (!out.text) throw new Error('b3 reaction with empty text');
          return out.text;
        }
        if (task === 'results') {
          const memberLines = input.members.map((member) => {
            const actor = state?.characters?.[member.memberId];
            return `- id=${member.memberId}（${actor?.name ?? '?'}）：${member.actionText}`;
          }).join('\n');
          const prompt = `你是结果判定器。\n${view}\n本组冻结行动：\n${memberLines}\n` +
            `为每个成员写一句第三人称结算结果。只输出 JSON，必须恰好包含这些键：${input.members.map((member) => `"${member.memberId}"`).join(', ')}`;
          const schema = { type: 'object', properties: Object.fromEntries(input.members.map((member) => [member.memberId, { type: 'string' }])),
            required: input.members.map((member) => member.memberId) };
          const out = await b3.complete(task, key, prompt, schema, 128);
          const missing = input.members.map((member) => member.memberId).filter((id) => typeof out[id] !== 'string' || !out[id]);
          if (missing.length) throw new Error(`b3 results missing members: ${missing.join(',')}`);
          return Object.fromEntries(input.members.map((member) => [member.memberId, out[member.memberId]]));
        }
        if (task === 'updates') {
          const resultsJson = JSON.stringify(input.results ?? {});
          const stageNote = input.stage ? `只产出 stage="${input.stage}" 的更新。` : '数组每项的 stage 取以下之一：position/appearance/tasks/subtasks/personality/sanity。';
          const prompt = `你是世界状态更新器。\n${view}\n已确认结算结果：${resultsJson}\n` +
            `根据结果产出世界状态更新候选。${stageNote}\nchanges 的键只能是角色 id；任务引用只用状态里已列出的任务 id；` +
            `personality 变化含 id(自拟草稿 id)/text/supersedes([])；sanity 用 sanitySet 数值。\n` +
            `只输出 JSON：[{"stage":"...","changes":{"<角色id>":{...}}}]；无变化输出 []`;
          const out = await b3.complete(task, key, prompt, { type: 'array', items: { type: 'object', properties: { stage: { type: 'string' }, changes: { type: 'object' } }, required: ['stage', 'changes'] } }, 384);
          if (!Array.isArray(out)) throw new Error('b3 updates without array');
          const stages = new Set(['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity']);
          const roster = new Set(Object.keys(state?.characters ?? {}));
          for (const call of out) {
            if (!stages.has(call.stage)) throw new Error(`b3 updates illegal stage ${call.stage}`);
            for (const entity of Object.keys(call.changes)) {
              if (!roster.has(entity)) throw new Error(`b3 updates changes key ${entity} not in roster`);
            }
          }
          return out;
        }
        if (task === 'continuation') {
          const prompt = `你是继续推进判断器。\n${view}\n本轮已提交的变化：${JSON.stringify(input.roundChanges ?? [])}\n` +
            `当前轮：${JSON.stringify(input.round ?? {})}\n` +
            `判断本轮结束后游戏是否继续推进。只输出 JSON：\n{"kind":"continue","candidateCharacterIds":["<角色id>",...],"nextRoundId":"<沿用输入给出的候选身份>"}\n或\n{"kind":"handback","cancelReason":null}`;
          const out = await b3.complete(task, key, prompt,
            { type: 'object', properties: { kind: { type: 'string', enum: ['continue', 'handback'] },
              candidateCharacterIds: { type: 'array', items: { type: 'string' } }, nextRoundId: { type: 'string' },
              cancelReason: { type: ['null', 'string'] } }, required: ['kind'] }, 96);
          const backfills = [];
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
            if (out.nextRoundId !== H.programNextRoundId) {
              backfills.push({ kind: 'next_round_id_backfilled', modelValue: out.nextRoundId ?? null, programValue: H.programNextRoundId });
              out.nextRoundId = H.programNextRoundId;
            }
          }
          b3.calls[b3.calls.length - 1].backfills = backfills;
          return out;
        }
        if (task === 'narration') {
          // 已交付的真实模型润色通路（与页面同一判分门）——来源 model
          const after = H.reads.get(key);
          if (!after) throw new Error('b3 narration_requires_saved_point_read');
          const before = after.previousPointId ? H.reads.get(after.previousPointId) ?? null : null;
          return H.narrateFromReads(after, before, H.polish, (event) => H.events.push({ ...event, at: Date.now() }));
        }
        throw new Error(`b3 port does not implement task ${task}`);
      },
    };

    // 程序侧 pointPlan：单点计划（B3 范围外，程序职责）
    H.programPointPlan = (roundId, input) => H.programPlan ?? [{ pointId: H.programPointIds?.shift() ?? 'point_draft',
      kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } }, actorIds: [] }];

    // 叙事（已交付通路）
    H.narrateFromReads = narrateFromReads;
    (async () => {
      const basePolisher = await narrationPolisher(DEFAULT_POLISH_MODEL);
      H.polish = async (input2, packet, focused, attempt) => basePolisher(input2, packet, focused, attempt);
    })();

    // 带记录的 tracked transport（场景用；commit 后不做 fold——B3 记录失败即交付）
    H.transport = { async execute(operation, request, scope, signal) {
      const started = performance.now();
      const response = await H.http.execute(operation, request, scope, signal);
      H.opLog.push({ op: operation, ms: Math.round(performance.now() - started) });
      H.captureEnvelope(response);
      if (operation === 'get_state') H.reads.set(response.data.pointId, structuredClone(response.data));
      return response;
    } };
  }, { api: apiOrigin });
  report.lifecycle.harnessReady = true; save();

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

  // ---- task-level probes ----
  try {
    report.tasks = await page.evaluate(async () => {
      const H = window.__h;
      const stateRead = await H.rawOp('get_state', {}, { tag: 'probe' });
      const state = structuredClone(stateRead.state);
      const roster = Object.keys(state.characters);
      const protagonist = state.protagonistId;
      const other = roster.find((id) => id !== protagonist);
      const protagonistName = state.characters[protagonist].name;
      const otherName = state.characters[other].name;

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
      // 程序应用第一阶段（与控制器 mergeUpdatesStages 同构的最小应用：只动任务）
      const applied = structuredClone(state);
      for (const call of (Array.isArray(taskStage) ? taskStage : [])) {
        for (const [entity, delta] of Object.entries(call.changes ?? {})) {
          for (const taskId of delta.tasksAchieved ?? []) if (applied.characters[entity]?.tasks?.[taskId]) applied.characters[entity].tasks[taskId].status = 'achieved';
        }
      }
      await run({ id: 'updates_stage_sanity', task: 'updates', focus: 'sanity stage reads the applied post-tasks state',
        input: { groupId: 'group_probe', mode: 'group', stage: 'sanity', results, workingState: applied } });

      // 5) 继续条件（continuation）：continue 与 handback 两个变体
      const roundChanges = [{ pointId: 'point_probe', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } },
        entityDeltas: {} }];
      H.programNextRoundId = 'round_probe_next';
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
        if (failure || out == null) return { id, structure: false, semantics: false, why: failure ?? 'no output' };
        const ok = (cond, why) => ({ id, structure: cond, semantics: cond, why: cond ? null : why });
        switch (id) {
          case 'action_pending': {
            if (out.kind !== 'act' && out.kind !== 'skip') return ok(false, `illegal kind ${out.kind}`);
            if (out.kind === 'act' && typeof out.text !== 'string') return ok(false, 'act without text');
            return { id, structure: true, semantics: true, why: null, note: out.kind === 'act' ? `act: ${out.text}` : 'skip' };
          }
          case 'action_consumed':
            return out.kind === 'skip' ? { id, structure: true, semantics: true, why: null }
              : { id, structure: true, semantics: false, why: `consumed input produced ${out.kind}` };
          case 'action_nonactor': {
            if (out.kind !== 'act' && out.kind !== 'skip') return ok(false, `illegal kind ${out.kind}`);
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
          case 'results_joint': {
            const keys = Object.keys(out);
            const want = [protagonist, other].sort().join(',');
            return keys.sort().join(',') === want && keys.every((key) => typeof out[key] === 'string' && out[key])
              ? { id, structure: true, semantics: true, why: null } : ok(false, `results keys ${keys} != [${protagonist},${other}]`);
          }
          case 'updates_merged': {
            if (!Array.isArray(out)) return ok(false, 'not an array');
            const stages = new Set(['position', 'appearance', 'tasks', 'subtasks', 'personality', 'sanity']);
            for (const call of out) {
              if (!stages.has(call.stage)) return ok(false, `illegal stage ${call.stage}`);
              for (const entity of Object.keys(call.changes ?? {})) if (!roster.includes(entity)) return ok(false, `changes key ${entity} not in roster`);
            }
            return { id, structure: true, semantics: true, why: null, note: `${out.length} calls: ${out.map((call) => call.stage).join(',')}` };
          }
          case 'updates_stage_tasks':
            return Array.isArray(out) && out.every((call) => call.stage === 'tasks')
              ? { id, structure: true, semantics: true, why: null } : ok(false, 'stage!=tasks in tasks-stage call');
          case 'updates_stage_sanity':
            return Array.isArray(out) && out.every((call) => call.stage === 'sanity')
              ? { id, structure: true, semantics: true, why: null } : ok(false, 'stage!=sanity in sanity-stage call');
          case 'continuation_more':
            if (out.kind !== 'continue' && out.kind !== 'handback') return ok(false, `illegal kind ${out.kind}`);
            return out.kind === 'continue' ? { id, structure: true, semantics: true, why: null, note: 'continue' }
              : { id, structure: true, semantics: false, why: 'unfinished round handed back' };
          case 'continuation_done':
            if (out.kind !== 'continue' && out.kind !== 'handback') return ok(false, `illegal kind ${out.kind}`);
            return out.kind === 'handback' ? { id, structure: true, semantics: true, why: null, note: 'handback' }
              : { id, structure: true, semantics: false, why: 'finished round continued' };
          default:
            return ok(false, 'unknown probe');
        }
      };
      const judged = probes.map(judge);
      const structurePass = judged.filter((entry) => entry.structure).length;
      const semanticsPass = judged.filter((entry) => entry.semantics).length;
      return {
        probes: probes.map((probe, index) => ({ ...probe, judgment: judged[index], call: probe.call ? {
          task: probe.call.task, promptChars: probe.call.promptChars, raw: probe.call.raw, ms: probe.call.ms,
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
      // 根叙事引导 + 玩家输入的分配：point/advance/input/round/group 全部程序预分配
      const ids = await (async () => {
        const allocation = await api('allocate_ids', { ...base(), allocationKey: `${namespace}_ids`, slots: [
          { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
          { slotKey: 'point_1', kind: 'point' }, ...roster.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' })),
          { slotKey: 'change_draft', kind: 'change' }] });
        return Object.fromEntries(allocation.allocations.map((entry) => [entry.slotKey, entry.id]));
      })();
      H.programPlan = [{ pointId: ids.point_1, kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } }, actorIds: [...roster] }];
      H.programNextRoundId = 'round_b3_action_next'; // 不被消费（handback 预期）；仅作回填候选

      const driver = new ControllerDriver({ transport: H.transport, model: H.b3Port }, initialMemory(`${namespace}_driver`, 'b3_action_holder'));
      // 失败即交付：driver 的 stop 状态原样记录，不换脚本候选
      driver.preparePlayerInput('走到走廊', roster, { allocationKey: `${namespace}_cmd1`, slots: [
        { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
        { slotKey: 'point', kind: 'point' }, ...roster.map((actor) => ({ slotKey: `group:${actor}`, kind: 'group' }))] },
        ['advance', 'input', 'round', 'point', ...roster.map((actor) => `group:${actor}`)]);
      const started = performance.now();
      const status = await driver.run();
      const walkMs = Math.round(performance.now() - started);
      const completed = status === undefined || (status.kind === 'stop' && status.reason === 'world_complete');
      const modelTasks = H.b3.calls.slice();
      return { status: completed ? 'COMPLETED' : status, walkMs, wire: H.wireCaptures.slice(-4),
        modelTasks: modelTasks.map((call) => ({ task: call.task, key: call.key, ms: call.ms, promptChars: call.promptChars,
          raw: call.raw, output: call.output, backfills: call.backfills ?? [], completion: call.completion ?? null })),
        ops: H.opLog.length };
    });
    report.status = 'PASS_ACTION_SCENE'; save();
    console.log(`[world-b3] scene action: ${JSON.stringify(report.scenes.action.status)} walk=${report.scenes.action.walkMs}ms ` +
      `modelCalls=${report.scenes.action.modelTasks.length}`);
  } catch (error) { harnessError(error, 'scene action'); }

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
          { slotKey: 'successor', kind: 'point' }, { slotKey: 'round_2', kind: 'round' },
          { slotKey: 'point_auto', kind: 'point' }] });
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
      const setupMs = 0; // 与 walk 合并计；setup 时间计入总时长
      // 驱动器接管：targets/reaction/(targets)/results/updates/commit/narration/continuation 全模型
      const headBefore = H.head;
      H.programPlan = [
        { pointId: ids.successor, kind: 'instant', timeAdvance: { boundary: 'instant', duration: { amount: 0, unit: 'second' } }, actorIds: [] },
        { pointId: ids.point_auto, kind: 'normal', timeAdvance: { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } }, actorIds: [...roster] }];
      H.programNextRoundId = ids.round_2; // 回填候选=程序预分配的轮身份
      const driver = new ControllerDriver({ transport: H.transport, model: H.b3Port }, initialMemory(`${namespace}_driver`, 'b3_chain_holder'));
      await driver.recover(H.worldId, { leaseToken: H.lease.leaseToken, fenceEpoch: H.lease.fenceEpoch });
      const callsBefore = H.b3.calls.length;
      const started = performance.now();
      const status = await driver.run();
      const walkMs = Math.round(performance.now() - started);
      const completed = status === undefined || (status.kind === 'stop' && status.reason === 'world_complete');
      const modelTasks = H.b3.calls.slice(callsBefore);
      return { status: completed ? 'COMPLETED' : status, walkMs, worldIdBefore, worldAttempts, abandonedRounds,
        callsBefore, modelTasks: modelTasks.map((call) => ({ task: call.task, key: call.key, ms: call.ms, promptChars: call.promptChars,
          raw: call.raw, output: call.output, backfills: call.backfills ?? [], completion: call.completion ?? null })),
        wire: H.wireCaptures.slice(-4) };
    });
    report.status = 'PASS_CHAIN_SCENE'; save();
    console.log(`[world-b3] scene chain: ${JSON.stringify(report.scenes.chain.status)} walk=${report.scenes.chain.walkMs}ms ` +
      `modelCalls=${(report.scenes.chain.modelTasks ?? []).length}`);
  } catch (error) { harnessError(error, 'scene chain'); }

  // ---- final report ----
  report.status = 'PASS_B3';
  save();
  console.log(`[world-b3] PASS_B3 → ${output}`);
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
