// Twenty-input acceptance over the real Python service and the real browser
// model — ONE world, four phases, the §798 stage-5 scope: end-to-end
// correctness + persistence (restart read-back) + real-model narration.
// Settlement semantics stay scripted/rule-authoritative (B3 boundary).
//
//   A  RuleWorldSession, 8 player inputs (rule-authoritative settlement +
//      real-model narration). Every commit runs an S₀ fold: the full point
//      chain's recorded deltas+timeAdvances are replayed over the initial
//      state and compared with the served state.
//   B  external checkpoint_pause → service process restart (same SQLite
//      file) → paused flag must survive → checkpoint_resume → recovered
//      RuleWorldSession attach + state parity.
//   C  ControllerDriver takeover on the SAME world: scripted advance with a
//      real d20 joint settlement → empty linked successor segment (T08
//      prepare_successor path, real-model narration) → conclude-continue ×2
//      automatic rounds (real-model narration each) → handback. Player
//      input #9 = the chain input text.
//   D  recovered RuleWorldSession, 12 more player inputs (#10–#21), then
//      narration cache delete (claim → delete → claim → regenerate →
//      submit) with the real model and the same judge gate.
//
//   node scripts/run-world-twenty.mjs --out ../artifacts/world-chain/twenty-round.json
//        [--server-checkout .local/world-server-worktree] [--python python]
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
const output = resolve(root, option('--out', 'artifacts/world-chain/twenty-round.json'));
const privateDir = resolve(root, `.local/world-twenty-${Date.now()}`); // SQLite 跨运行持久：独立目录防撞旧幂等台账
mkdirSync(privateDir, { recursive: true });
const sources = ['frontend/scripts/run-world-twenty.mjs', 'frontend/src/app/world/page.tsx', 'frontend/src/app/world/narration-polisher.ts',
  ...['runtime/rule-session', 'runtime/rule-facts', 'runtime/committed-narration', 'runtime/prompts', 'runtime/wllama-engine',
    'controller', 'schedule', 'http-transport', 'recovery'].map((name) => `frontend/src/lib/world-engine/${name}.ts`)];

const git = (checkout, ...args) => { try {
  // 只去尾部换行：status 首行的前导空格是 porcelain 格式的一部分，整串 trim
  // 会把它吃掉（脏树守卫按 slice(3) 解析就会对首行失明——v2 复核教训）
  return execFileSync('git', ['-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).replace(/\n+$/, '');
} catch { return null; } };
// 钉档=实际执行的代码逐文件 sha256（服务端 backend/app 全部代码文件；浏览器侧 sources）
const walkServerFiles = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => entry.isDirectory()
  ? (entry.name === '__pycache__' ? [] : walkServerFiles(resolve(dir, entry.name))) : [resolve(dir, entry.name)]);
const serverAppRoot = resolve(a, 'backend', 'app').replaceAll('\\', '/');
const serverFiles = walkServerFiles(resolve(a, 'backend', 'app'))
  .map((file) => ({ path: `backend/app/${file.replaceAll('\\', '/').slice(serverAppRoot.length + 1)}`, file }));
const report = {
  status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), kind: 'twenty-input',
  privateDir, browserSource: { head: git(root, 'rev-parse', 'HEAD'), status: git(root, 'status', '--short'),
    sha256: Object.fromEntries(sources.map((file) => [file, createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex')])) },
  serverSource: { head: git(a, 'rev-parse', 'HEAD'), status: git(a, 'status', '--short'),
    sha256: Object.fromEntries(serverFiles.map(({ path, file }) => [path, createHash('sha256').update(readFileSync(file)).digest('hex')])) },
  modelLoad: null, phases: {}, restarts: [], inputs: [],
};
const save = () => { mkdirSync(resolve(output, '..'), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();

// 钉住集 tracked 脏时拒绝起跑（按侧豁免；artifact 仍记录 status）
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
  console.error(`[world-twenty] FAILED: ${report.error}`);
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

const serviceArgs = ['-X', 'utf8', '-m', 'uvicorn', 'app.world_app:create_persistent_world_app', '--factory',
  '--host', '127.0.0.1', '--port', String(apiPort)];
const serviceEnv = { ...process.env, WORLD_SQLITE_PATH: resolve(privateDir, 'world.db'), WORLD_ALLOWED_ORIGINS: viteOrigin };
let service = null;
const startService = () => {
  service = spawn(option('--python', 'python'), serviceArgs, { cwd: resolve(a, 'backend'), env: serviceEnv, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  const log = createWriteStream(resolve(privateDir, 'server.log'), { flags: 'a' });
  service.stdout.pipe(log);
  service.stderr.pipe(log);
  return service;
};
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
startService();

const vite = await createServer({ root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/world-chain-vite',
  server: { host: '127.0.0.1', port: vitePort, hmr: false },
  plugins: [{ name: 'world-twenty', configureServer(vite) { vite.middlewares.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    if (req.url !== '/__chain') return next();
    res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>World twenty acceptance</title>');
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
const netTrail = [];
try {
  await waitReady();
  report.lifecycle.serviceReady = true; save();

  const { chromium } = await import('@playwright/test');
  browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage();
  page.on('console', (message) => consoleTrail.push(message.text()));
  page.on('pageerror', (error) => consoleTrail.push(`[pageerror] ${error.message}`));
  page.on('request', (request) => {
    if (!request.url().includes(apiOrigin)) return;
    netTrail.push({ at: new Date().toISOString(), method: request.method(), url: request.url().slice(apiOrigin.length),
      body: request.method() === 'GET' ? null : (request.postData() ?? '').slice(0, 400) });
  });
  page.on('response', (response) => {
    if (!response.url().includes(apiOrigin)) return;
    const entry = netTrail.find((item) => item.url === response.url().slice(apiOrigin.length) && item.status === undefined);
    if (entry) entry.status = response.status();
    if (response.status() >= 400) response.text().then((text) => { if (entry) entry.responseBody = text.slice(0, 300); }).catch(() => {});
  });
  await page.goto(`${viteOrigin}/__chain`, { waitUntil: 'domcontentloaded' });
  assert.equal(await page.evaluate(() => window.crossOriginIsolated), true, 'twenty acceptance requires cross-origin isolation');
  report.modelLoad = await page.evaluate(async (modelUrl) => {
    const { warmNarrationEngine } = await import('/src/app/world/narration-polisher.ts');
    return { model: modelUrl, ...await warmNarrationEngine(modelUrl) };
  }, '/models/Qwen3-0.6B-Q4_K_M.gguf');
  save();

  // ---- shared page-side harness: evidence, tracked transport, S₀ fold ----
  // 同一 page realm：模块缓存与 window.__h 跨 evaluate 存活，各阶段直接取句柄。
  await page.evaluate(async ({ api: apiBase }) => {
    const [{ HttpWorldTransport }, { RuleWorldSession, narrateFromReads },
      { defaultInitialTemplate, WORLD_POLICY, DEFAULT_POLISH_MODEL }, { narrationPolisher }] = await Promise.all([
      import('/src/lib/world-engine/http-transport.ts'), import('/src/lib/world-engine/runtime/rule-session.ts'),
      import('/src/app/world/world-defaults.ts'), import('/src/app/world/narration-polisher.ts')]);

    const H = {
      apiBase, worldId: null, lease: null, revision: null,
      opLog: [], wireCaptures: [], events: [], modelAttempts: [], completionEvidence: [],
      reads: new Map(), foldLog: [], continuationLog: [], narrationExports: { narrateFromReads },
      sessionOptions(holderId) {
        return { transport: H.transport, initial: defaultInitialTemplate(), policy: WORLD_POLICY, polish: H.polish,
          onEvent: (event) => H.events.push({ ...event, at: Date.now() }), holderId };
      },
    };
    window.__h = H;

    // T02 recorded-rails time fold（秒粒度；S₀ 折算本身就是对服务端的持续校验）
    const advanceTime = (time, timeAdvance) => {
      const next = { ...time };
      const amount = timeAdvance?.duration?.amount ?? 0;
      const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})/.exec(next.dateTime);
      if (!match) throw new Error(`Unreadable dateTime: ${next.dateTime}`);
      if (amount > 0) {
        const total = Number(match[2]) * 3600 + Number(match[3]) * 60 + Number(match[4]) + amount;
        next.dateTime = `${match[1]}T${String(Math.floor(total / 3600)).padStart(2, '0')}:${String(Math.floor((total % 3600) / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
        next.instantOrdinal = 0;
      } else {
        next.instantOrdinal = next.instantOrdinal + 1;
      }
      return next;
    };
    const stableStringify = (value) => {
      if (value === null || typeof value !== 'object') return JSON.stringify(value);
      if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
      return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
    };

    const basePolisher = await narrationPolisher(DEFAULT_POLISH_MODEL);
    let polishReload = 0;
    H.polish = async (input, packet, focused, attempt) => {
      const started = performance.now();
      const evidenceBefore = H.completionEvidence.length;
      // 证据回调必须逐调用传入：实例级 onCompletion 会被 polisher 模块级缓存吞掉
      let text;
      try {
        text = await basePolisher(input, packet, focused, attempt, (item) => H.completionEvidence.push(item));
      } catch (error) {
        if (!/wllama has crashed|unreachable|abort/i.test(String(error))) throw error;
        // wasm 崩溃会毒化模块级引擎缓存：换新模块实例重建引擎后重试一次
        polishReload += 1;
        const fresh = await import(`/src/app/world/narration-polisher.ts?crash-reload=${polishReload}`);
        await fresh.warmNarrationEngine(DEFAULT_POLISH_MODEL);
        const rebuilt = await fresh.narrationPolisher(DEFAULT_POLISH_MODEL);
        text = await rebuilt(input, packet, focused, attempt, (item) => H.completionEvidence.push(item));
      }
      H.modelAttempts.push({ at: Date.now(), attempt: attempt.index, ms: Math.round(performance.now() - started), chars: text.length,
        pointId: input?.pointId ?? null,
        facts: (focused?.facts ?? []).map((fact) => ({ id: fact.id, phrase: fact.allowedPhrases[0] })),
        completion: H.completionEvidence.slice(evidenceBefore) });
      return text;
    };

    const capturingFetcher = async (input, init) => {
      const response = await fetch(input, init);
      if (response.status >= 400) H.wireCaptures.push({ url: String(input), body: String(init?.body ?? '').slice(0, 400), status: response.status, response: (await response.clone().text()).slice(0, 300) });
      return response;
    };
    const http = new HttpWorldTransport(apiBase, capturingFetcher);

    // 折算一个点：prev 状态 + 该点 recorded timeAdvance/entityDeltas = 重建状态
    H.foldPoint = (prev, read, point) => {
      const next = structuredClone(prev);
      next.time = advanceTime(next.time, read.timeAdvance);
      for (const [entityId, delta] of Object.entries(read.entityDeltas ?? {})) {
        const character = next.characters[entityId] ?? null;
        const item = next.items[entityId] ?? null;
        const location = next.locations[entityId] ?? null;
        if (delta.positionSet != null) {
          if (character) character.position = structuredClone(delta.positionSet);
          else if (item) item.position = structuredClone(delta.positionSet);
        }
        const appearanceHolder = character ?? item ?? location;
        const applyChanges = (holder, changes) => {
          for (const change of changes) {
            holder.push({ ...change, sourcePointId: point.pointId, sourceSequence: point.sequence, active: true });
            for (const superseded of change.supersedes ?? []) {
              const prior = holder.find((entry) => entry.id === superseded);
              if (prior) prior.active = false;
            }
          }
        };
        if (delta.appearanceChanges?.length) applyChanges(appearanceHolder.appearanceChanges, delta.appearanceChanges);
        if (character && delta.personalityChanges?.length) applyChanges(character.personalityChanges, delta.personalityChanges);
        if (character && delta.sanitySet != null) character.sanity = delta.sanitySet;
        if (character && delta.tasksAchieved?.length) for (const taskId of delta.tasksAchieved) character.tasks[taskId].status = 'achieved';
        if (character && delta.subtasksAdded?.length) for (const task of delta.subtasksAdded) character.tasks[task.id] = structuredClone(task);
      }
      return next;
    };

    // 从 S₀ 折算整条点链并与各点 served state 逐一比对。
    // 严格模式：缺读即失败（ok:null 曾让逐 commit fold 永远跳过刚提交的点——
    // 二轮复核 P1-2）。调用方必须先缓存刚提交 head 的读取（H.afterCommit）。
    H.foldAll = async (reason) => {
      const points = (await H.rawOp('list_points', { after: null, limit: 100 }, { tag: 'fold' })).points;
      const steps = [];
      let state = null;
      let ok = true;
      for (const point of points) {
        const read = H.reads.get(point.pointId) ?? null;
        if (!read) {
          ok = false; // 缺读点与其后所有点都无法折算——显式失败，不静默跳过
          steps.push({ pointId: point.pointId, kind: point.kind, ok: false, note: 'no_recorded_read' });
          break;
        }
        if (!state) {
          state = structuredClone(read.state); // S₀ = root 点的 committed 状态
          steps.push({ pointId: point.pointId, kind: point.kind, ok: true, note: 's0' });
          continue;
        }
        const rebuilt = H.foldPoint(state, read, point);
        const equal = stableStringify(rebuilt) === stableStringify(read.state);
        if (!equal) ok = false;
        steps.push({ pointId: point.pointId, kind: point.kind, ok: equal,
          diff: equal ? undefined : { rebuilt: stableStringify(rebuilt).slice(0, 600), served: stableStringify(read.state).slice(0, 600) } });
        state = read.state; // 链式续算：失配已记录，不中断
      }
      const entry = { at: Date.now(), reason, ok, steps };
      H.foldLog.push(entry);
      return entry;
    };
    // 提交后的完整核验：先读新 head（缓存该点 committed 状态），再折算全链。
    // 缺任何点的读取或任何失配都抛错（transport 钩子与 raw commit 共用）。
    H.afterCommit = async (committedPointId) => {
      await H.rawOp('get_state', {}, { tag: 'fold' }); // 缓存刚提交点的读取
      const fold = await H.foldAll(`commit:${committedPointId}`);
      if (!fold.ok) throw new Error(`S0 fold failed after commit ${committedPointId}: ` +
        `${JSON.stringify(fold.steps.filter((step) => step.ok !== true))}`);
    };

    // 无 lease 的读操作；写操作自动合并 requestId+当前 lease 绑定——
    // checkpoint_*/create_rolls 另需 head 乐观并发三元组
    // （expectedPointId/expectedVersion/expectedCheckpointRevision）。
    // 注意：handback 后服务端释放租约（信封 world.lease=null），pause 前须先
    // lease_acquire 重新取得。
    const LEASE_FREE = new Set(['create_world', 'list_points', 'get_state', 'get_context', 'preview_point']);
    const LEASE_OWN = new Set(['lease_acquire']); // schema 禁额外字段：undefined 键也会被客户端校验拒绝
    // narration_delete 是查询串模型（无 worldId/pointId 字段）：body 必须逐字构造
    const DELETE_RAW = new Set(['narration_delete']);
    const NEEDS_HEAD = (operation) => operation.startsWith('checkpoint_') || operation === 'create_rolls';
    // narration_delete/narration_get：查询串/无 body 操作——pointId 走 scope 进
    // 路径，payload 不得进 body（客户端按 bodyless 校验）
    const PATH_POINT_OPS = new Set(['narration_delete', 'narration_get']);
    // history 模式的叙述操作绑定 {mode:'history', leaseToken?:null}——不得合并
    // lease 字段（string token 会破坏判别联合）
    const isHistoryNarration = (operation, payload) =>
      ['narration_claim', 'narration_submit', 'narration_delete'].includes(operation) && payload.mode === 'history';
    H.rawSeq = 0;
    H.rawOp = async (operation, payload = {}, opts = {}) => {
      const started = performance.now();
      const scope = PATH_POINT_OPS.has(operation) ? { worldId: H.worldId, pointId: payload.pointId }
        : H.worldId && operation !== 'create_world' ? { worldId: H.worldId } : {};
      const historyMode = isHistoryNarration(operation, payload);
      const body = DELETE_RAW.has(operation) ? { protocolVersion: 2, requestId: payload.requestId ?? `twenty_raw_${++H.rawSeq}`,
          mode: payload.mode,
          ...(payload.mode === 'head' ? { leaseToken: H.lease?.leaseToken, fenceEpoch: H.lease?.fenceEpoch } : {}),
          claimToken: payload.claimToken, generation: payload.generation, issuedAtEpochMilli: payload.issuedAtEpochMilli }
        : operation === 'narration_get' ? {}
        : LEASE_FREE.has(operation) ? payload
        : { protocolVersion: 2, requestId: payload.requestId ?? `twenty_raw_${++H.rawSeq}`, worldId: H.worldId,
            ...(LEASE_OWN.has(operation) || historyMode ? {} : { leaseToken: H.lease?.leaseToken, fenceEpoch: H.lease?.fenceEpoch }),
            ...(NEEDS_HEAD(operation) ? { expectedPointId: H.head?.pointId, expectedVersion: H.head?.version,
              expectedCheckpointRevision: H.revision } : {}),
            ...payload };
      const response = await http.execute(operation, body, scope);
      H.opLog.push({ op: operation, ms: Math.round(performance.now() - started), tag: opts.tag });
      H.captureEnvelope(response);
      if (operation === 'get_state') H.reads.set(response.data.pointId, structuredClone(response.data));
      if (operation === 'commit_point' && H.head) await H.afterCommit(H.head.pointId); // raw 提交与 transport 钩子同一核验
      return response.data ?? response;
    };
    // 信封里的 world.lease 形状不含 leaseToken（token 只在 create/acquire/renew
    // 的 data 里）——合并而不是整体覆盖，否则 token 被无 token 形状冲掉
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
    H.ensureLease = async () => {
      if (H.lease?.leaseToken) return H.lease;
      await H.rawOp('lease_acquire', { holderId: 'twenty_harness' }, { tag: 'setup' });
      if (!H.lease?.leaseToken) throw new Error('lease_acquire did not yield a lease');
      return H.lease;
    };
    H.control = async () => (await H.rawOp('get_context', { includeRecovery: false }, { tag: 'probe' })).control;
    H.snapshot = async () => {
      const read = await H.rawOp('get_state', {}, { tag: 'probe' });
      const protagonist = read.state.characters[read.state.protagonistId];
      return { version: read.version, headPointId: read.pointId, sanity: protagonist.sanity, location: protagonist.position.containerId };
    };

    // 带逐 commit S₀ 折算的共享 tracked transport（规则会话与驱动器共用）
    H.transport = { async execute(operation, request, scope, signal) {
      const started = performance.now();
      const response = await http.execute(operation, request, scope, signal);
      H.opLog.push({ op: operation, ms: Math.round(performance.now() - started) });
      H.captureEnvelope(response);
      if (operation === 'get_state') H.reads.set(response.data.pointId, structuredClone(response.data));
      if (operation === 'commit_point' && response.world) {
        await H.afterCommit(response.world.head.pointId); // 读取新点+全链折算，失败即抛
      }
      return response;
    } };

    // 逐输入记录包装：RuleWorldSession.submit 外面套计时/事件切片
    H.submitRecorded = async (session, command, phase, index) => {
      const eventMark = H.events.length;
      const attemptMark = H.modelAttempts.length;
      const opMark = H.opLog.length;
      const wireMark = H.wireCaptures.length;
      const started = performance.now();
      const terminal = await session.submit(command);
      const slice = H.events.slice(eventMark);
      return { index, phase, command, wallMs: Math.round(performance.now() - started), terminal,
        decision: slice.find((event) => event.kind === 'decision') ?? null,
        unparsed: slice.some((event) => event.kind === 'unparsed'),
        narration: slice.filter((event) => event.kind === 'narration')
          .map((event) => ({ pointId: event.pointId, version: event.version, polished: event.polished, polishReason: event.polishReason, attempts: event.attempts, text: event.text })),
        polishFallback: slice.filter((event) => event.kind === 'polishFallback').map((event) => event.detail),
        modelAttempts: H.modelAttempts.slice(attemptMark),
        serverOps: H.opLog.length - opMark,
        wireCaptures: H.wireCaptures.slice(wireMark) };
    };
    H.attachRecorded = async (session, phase) => {
      const attemptMark = H.modelAttempts.length;
      const opMark = H.opLog.length;
      const started = performance.now();
      const terminal = await session.attach();
      return { phase, wallMs: Math.round(performance.now() - started), terminal, modelAttempts: H.modelAttempts.slice(attemptMark), serverOps: H.opLog.length - opMark };
    };
    H.assertCleanTerminal = (record, label) => {
      if (record.terminal?.kind !== 'stop' || record.terminal.reason !== 'world_complete') {
        throw new Error(`${label} terminal: ${JSON.stringify(record.terminal)} wire=${JSON.stringify(H.wireCaptures.slice(-4))} events=${JSON.stringify(H.events.slice(-4))}`);
      }
    };
  }, { api: apiOrigin });
  report.lifecycle.harnessReady = true; save();

  // 失败处理必须同步原子：async 未 await 的失败处理曾让执行流冲进后续阶段、
  // 错误标签互相覆盖（首轮运行实证）。浏览器关闭走 fire-and-forget。
  const browserDeaths = [];
  browser.on('disconnected', () => browserDeaths.push({ at: new Date().toISOString(), reason: 'browser disconnected' }));
  page.on('crash', () => browserDeaths.push({ at: new Date().toISOString(), reason: 'page crash' }));
  report.browserDeaths = browserDeaths;
  const harnessError = (error, label) => {
    report.status = 'FAILED';
    report.error = `${label}: ${error?.stack ?? error}`;
    report.consoleTrail = consoleTrail.slice(-40);
    report.browserDeaths = browserDeaths;
    save();
    cleanup();
    try { browser?.close()?.catch(() => {}); } catch {}
    console.error(`[world-twenty] FAILED at ${label}:`, error);
    process.exit(1);
  };

  // ---- phase A: rule session, 8 player inputs ----
  try {
    report.phases.A = await page.evaluate(async () => {
      const H = window.__h;
      const { RuleWorldSession } = await import('/src/lib/world-engine/runtime/rule-session.ts');
      const session = RuleWorldSession.createNew(H.sessionOptions('twenty_a'));
      const attach = await H.attachRecorded(session, 'A');
      if (attach.terminal.kind === 'error' || (attach.terminal.kind === 'stop' && attach.terminal.reason !== 'world_complete')) {
        throw new Error(`A attach terminal: ${JSON.stringify(attach.terminal)}`);
      }
      const s0 = await H.snapshot();
      const commands = ['完成压力试验', '走到门厅', '完成压力试验', '上下打量四周', '走到走廊', '完成恢复练习', '走到门厅', '走到走廊'];
      const inputs = [];
      for (let index = 0; index < commands.length; index++) {
        inputs.push(await H.submitRecorded(session, commands[index], 'A', index + 1));
        H.assertCleanTerminal(inputs[index], `A input ${index + 1}`);
      }
      return { worldId: H.worldId, attach, s0, inputs, totals: { modelAttempts: H.modelAttempts.length, completionEvidence: H.completionEvidence.length } };
    });
    report.worldId = report.phases.A.worldId;
    report.inputs.push(...report.phases.A.inputs);
    report.status = 'PASS_A'; save();
    console.log(`[world-twenty] A: inputs=${report.phases.A.inputs.length} wall=${report.phases.A.inputs.reduce((sum, item) => sum + item.wallMs, 0)}ms modelAttempts=${report.phases.A.totals.modelAttempts}`);
  } catch (error) { harnessError(error, 'phase A'); }

  // ---- phase B: pause → restart → resume → recovered attach ----
  try {
    report.phases.B_pause = await page.evaluate(async () => {
      const H = window.__h;
      const before = await H.snapshot();
      const controlBefore = await H.control();
      if (controlBefore.paused) throw new Error('world already paused before external pause');
      await H.ensureLease(); // phase A 的租约 token 已随信封合并保留；TTL 过期则换新
      try {
        await H.rawOp('checkpoint_pause', { operation: 'pause' });
      } catch (error) {
        if (!String(error).includes('lease_invalid')) throw error;
        H.lease = null; // 租约 TTL 过期：换新租约再暂停
        await H.ensureLease();
        await H.rawOp('checkpoint_pause', { operation: 'pause' });
      }
      const controlAfter = await H.control();
      if (!controlAfter.paused) throw new Error('world not paused after checkpoint_pause');
      return { before, pausedAfterPause: true, revisionAfterPause: H.revision };
    });
    save();

    const restart = { reason: 'phase B restart under external pause', pidBefore: service.pid };
    const exited = new Promise((done) => service.once('exit', done));
    service.kill();
    await exited;
    const downtimeStarted = Date.now();
    startService();
    await waitReady();
    restart.pidAfter = service.pid;
    restart.downtimeMs = Date.now() - downtimeStarted;
    report.restarts.push(restart); save();

    report.phases.B_recover = await page.evaluate(async () => {
      const H = window.__h;
      const { RuleWorldSession } = await import('/src/lib/world-engine/runtime/rule-session.ts');
      const control = await H.control();
      if (!control.paused) throw new Error(`paused flag lost across restart: ${JSON.stringify(control)}`);
      await H.rawOp('checkpoint_resume', { operation: 'resume' });
      const controlResumed = await H.control();
      if (controlResumed.paused) throw new Error('world still paused after checkpoint_resume');
      const session = RuleWorldSession.createRecovered(H.sessionOptions('twenty_b'), H.worldId,
        H.lease ? { leaseToken: H.lease.leaseToken, fenceEpoch: H.lease.fenceEpoch } : undefined); // 无租约时驱动器自行 lease_acquire
      const attach = await H.attachRecorded(session, 'B');
      if (attach.terminal.kind === 'error' || (attach.terminal.kind === 'stop' && attach.terminal.reason !== 'world_complete')) {
        throw new Error(`B attach terminal: ${JSON.stringify(attach.terminal)}`);
      }
      return { pausedAcrossRestart: true, attach, after: await H.snapshot() };
    });
    const before = report.phases.B_pause.before;
    const after = report.phases.B_recover.after;
    report.phases.B_recover.parity = { version: after.version === before.version, headPointId: after.headPointId === before.headPointId,
      sanity: after.sanity === before.sanity, location: after.location === before.location };
    if (!Object.values(report.phases.B_recover.parity).every(Boolean)) {
      throw new Error(`B state parity broken: ${JSON.stringify({ before, after })}`);
    }
    report.status = 'PASS_B'; save();
    console.log(`[world-twenty] B: paused across restart=${report.phases.B_recover.pausedAcrossRestart} downtime=${restart.downtimeMs}ms parity=ok`);
  } catch (error) { harnessError(error, 'phase B'); }

  // ---- phase C: driver takeover — joint settlement + linked segment + auto chains ----
  try {
    report.phases.C = await page.evaluate(async () => {
      const H = window.__h;
      const { ControllerDriver, initialMemory } = await import('/src/lib/world-engine/controller.ts');
      const { narrateFromReads } = H.narrationExports;

      // ---- scripted-API setup: raw ops with explicit lease bindings ----
      const namespace = `twenty_${Date.now().toString(36)}`;
      let sequence = 0;
      const next = () => `${namespace}_${++sequence}`;
      const setupOps = [];
      const api = async (operation, payload) => {
        setupOps.push({ op: operation, at: Date.now() });
        try { return await H.rawOp(operation, payload, { tag: 'setup' }); }
        catch (error) {
          setupOps.push({ op: `${operation}:REFUSED`, error: error?.response?.error ?? null });
          // 服务错误信封不带 detail（问题清单 4）——把操作名与 wire 尾巴拼进
          // 错误消息，否则定位只能盲猜
          throw new Error(`${operation} refused: ${error?.message ?? error} ` +
            `wire=${JSON.stringify(H.wireCaptures.slice(-2))}`);
        }
      };
      const base = () => ({ requestId: next() });
      const allocate = async (slots) => {
        const allocation = await api('allocate_ids', { ...base(), allocationKey: `${namespace}_ids`, slots });
        return Object.fromEntries(allocation.allocations.map((entry) => [entry.slotKey, entry.id]));
      };

      // 服务端冻结顺序规则（world_store.finish_operation）：start_advance 后轮次
      // 顺序按（理智值，ID）升序重排——A 阶段已改变理智，order[0] 不再可预设
      //（首轮问题 2 在同世界延续下的显形：发起人必须动态读取冻结顺序）。
      const roster = ['person_a', 'person_c'];
      const inputText = '林川推开门厅深处的重门，示意周宁到门边一起撑住。';
      const TA_SUCCESSOR = { boundary: 'instant', duration: { amount: 0, unit: 'second' } }; // T08 s7 录制形状
      const TA_CHAIN = { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } };
      const TA_AUTO = { boundary: 'elapsed', duration: { amount: 1, unit: 'second' } };
      // P1-1（二轮复核）：链场景必须发生在同一世界——不再重建世界；未准入的
      // 尝试在同一世界内整轮取消（cancel 任意阶段合法：置 phase=complete、清
      // advance），下一轮尝试重新开局。全部 21 次输入因此落在同一个世界。
      const worldIdBefore = H.worldId;
      if (!worldIdBefore) throw new Error('C requires the world created in phase A');
      const attemptMark = H.modelAttempts.length;
      const opMark = H.opLog.length;
      const wireMark = H.wireCaptures.length;
      const setupStarted = performance.now();
      const worldAttempts = [];
      const abandonedRounds = [];
      let ids = null;
      let initiator = null;
      let reactor = null;
      let admitted = false;
      for (let attempt = 1; attempt <= 6 && !admitted; attempt++) {
        ids = await allocate([
          { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
          { slotKey: 'point_1', kind: 'point' }, { slotKey: 'group_1', kind: 'group' },
          { slotKey: 'trigger:ring', kind: 'trigger' },
          { slotKey: 'successor', kind: 'point' }, { slotKey: 'round_2', kind: 'round' }, { slotKey: 'round_3', kind: 'round' },
          { slotKey: 'point_auto2', kind: 'point' }, { slotKey: 'point_auto3', kind: 'point' },
          { slotKey: 'change_1', kind: 'change' },
        ]);
        await api('checkpoint_start_advance', { ...base(), operation: 'start_advance', advanceId: ids.advance, inputId: ids.input,
          roundId: ids.round, inputText, order: roster });
        // 发起人必须是重排后的 order[0]（discover 的绑定校验）
        const frozenOrder = (await H.rawOp('get_context', { includeRecovery: false }, { tag: 'setup' })).world?.round?.order ?? roster;
        initiator = frozenOrder[0];
        reactor = frozenOrder[1] ?? frozenOrder[0];
        const triggerKey = ids['trigger:ring'];
        await api('checkpoint_begin_point', { ...base(), operation: 'begin_point', pointId: ids.point_1, kind: 'normal',
          timeAdvance: TA_CHAIN });
        await api('checkpoint_discover_group', { ...base(), operation: 'discover_group', pointId: ids.point_1, groupId: ids.group_1,
          initiatorId: initiator, actionText: inputText, targetIds: null });
        await api('checkpoint_extend_group', { ...base(), operation: 'extend_group', pointId: ids.point_1, groupId: ids.group_1,
          sourceId: initiator, targets: [{ targetId: reactor, triggerKey }], admittedMember: null });
        const ringRoll = (await api('create_rolls', { ...base(), rolls: [{ advanceId: ids.advance, roundId: ids.round, groupId: ids.group_1,
          sourceId: initiator, targetId: reactor, triggerKey,
          ruleVersion: 'reaction-d20-v1', target: 11 }] })).rolls[0];
        worldAttempts.push({ attempt, roundId: ids.round, initiator, reactor,
          roll: { admitted: ringRoll.admitted, rollId: ringRoll.rollId, result: ringRoll.result, eligible: ringRoll.eligible } });
        if (ringRoll.admitted) {
          await api('checkpoint_extend_group', { ...base(), operation: 'extend_group', pointId: ids.point_1, groupId: ids.group_1,
            sourceId: initiator, targets: null, admittedMember: { memberId: reactor,
              actionText: '另一人赶到门边，与发起者一起撑住了重门。',
              rollRefs: [{ sourceId: initiator, targetId: reactor, triggerKey, rollId: ringRoll.rollId }] } });
          // 被接纳的反应者成为新 source（有自己的行动机会）：显式空目标集
          // 完成其 source 槽位，否则 close_group 拒绝
          await api('checkpoint_extend_group', { ...base(), operation: 'extend_group', pointId: ids.point_1, groupId: ids.group_1,
            sourceId: reactor, targets: [], admittedMember: null });
          // 结算文本为脚本候选（B3 边界）：组关闭→暂存结算单元→prepare_successor
          // 预绑定空 linked 续段。恢复路径原生支持 prepared successor（recovery
          // plan=[current, successor]+commit 后服务端自动提升），驱动器接手提交
          // 与后续点的驱动。
          await api('checkpoint_close_group', { ...base(), operation: 'close_group', pointId: ids.point_1, groupId: ids.group_1 });
          // 因果动态化：A 阶段已改变理智与任务。服务端裁定（units.py，2026-10-22）：
          // 人格变化必须搭配至少一个新达成任务，且 sanities 键集须与 personalities
          // 配对——从当前 served 状态动态取一个 pending 任务（owner 自己的，归属
          // 天然合法）构成 任务+人格+理智 三件套，对任意发起人都成立
          const headRead = await H.rawOp('get_state', {}, { tag: 'setup' });
          const pendingTask = Object.entries(headRead.state.characters)
            .flatMap(([ownerId, actor]) => Object.values(actor.tasks)
              .filter((task) => task.status === 'pending').map((task) => ({ ownerId, taskId: task.id })))[0];
          if (!pendingTask) throw new Error('no pending task available for the settlement causal triple');
          const initiatorSanity = headRead.state.characters[initiator]?.sanity ?? 10;
          await api('checkpoint_stage_unit', { ...base(), operation: 'stage_unit', pointId: ids.point_1, groupId: ids.group_1,
            candidates: { groupId: ids.group_1, actorIds: [initiator, reactor], positions: {}, appearances: {}, subtasksAdded: {},
              tasksAchieved: { [pendingTask.ownerId]: [pendingTask.taskId] },
              personalities: { [initiator]: [{ id: ids.change_1, text: '共同撑住重门后更加沉稳', supersedes: [] }] },
              sanities: { [initiator]: Math.max(0, initiatorSanity - 1) },
              taskCoverageIds: [initiator, reactor], personalityCoverageIds: [initiator, reactor] },
            results: { [initiator]: '重门终于在两人合力下被稳稳撑住。', [reactor]: '另一人赶到门边，与发起者一起撑住了重门。' } });
          await api('checkpoint_prepare_successor', { ...base(), operation: 'prepare_successor', pointId: ids.point_1,
            successorPointId: ids.successor, timeAdvance: TA_SUCCESSOR });
          admitted = true;
        } else {
          // 未准入：整轮取消（未提交工作一并放弃），身份随轮废弃，不产生点
          await api('round_conclusion_cancel', { ...base(), operation: 'cancel', advanceId: ids.advance,
            roundId: ids.round, cancelReason: `first_ring_roll_${ringRoll.result}_not_admitted` });
          abandonedRounds.push({ attempt, roundId: ids.round, rollResult: ringRoll.result });
        }
      }
      if (!admitted) throw new Error('no admitting first-link roll in six attempts');
      const setupMs = Math.round(performance.now() - setupStarted);
      const chainWorldId = H.worldId;
      if (chainWorldId !== worldIdBefore) throw new Error(`C left the world: ${chainWorldId} != ${worldIdBefore}`);
      const chainLease = { ...H.lease };

      // ---- hybrid port: REAL narrated gate + continue chain（结算已脚本化入 setup）----
      const modelLog = [];
      const summarizeReturned = (value) => {
        const text = typeof value === 'string' ? value : JSON.stringify(value);
        return typeof text === 'string' && text.length > 800 ? `${text.slice(0, 800)}…[truncated, total ${text.length}]` : value;
      };
      let continuationCalls = 0;
      const generateTask = async (task, key, input) => {
        if (task === 'pointPlan') {
          // commit 后服务端直接进 assess_continuation（轮随 commit 结束）；
          // 链轮的空 linked 续段由恢复计划携带（plan=[P_chain, P_link]），
          // 这里只为两个自动轮各出一普通点
          if (key === ids.round_2) return [{ pointId: ids.point_auto2, kind: 'normal', timeAdvance: TA_AUTO, actorIds: [...roster] }];
          if (key === ids.round_3) return [{ pointId: ids.point_auto3, kind: 'normal', timeAdvance: TA_AUTO, actorIds: [...roster] }];
          throw new Error(`unexpected pointPlan round ${String(key)}`);
        }
        if (task === 'action') return { kind: 'skip' };
        if (task === 'updates') {
          if (input.mode === 'time_scan') return input.stage ? { stage: input.stage, changes: {} } : [];
          throw new Error('group updates are settled in the scripted setup; the driver must not re-settle them');
        }
        if (task === 'narration') {
          const after = H.reads.get(key);
          if (!after) throw new Error('narration_requires_saved_point_read');
          const before = after.previousPointId ? H.reads.get(after.previousPointId) : null;
          if (before === undefined) throw new Error('narration_requires_saved_predecessor_read');
          return narrateFromReads(after, before, H.polish, (event) => H.events.push({ ...event, at: Date.now() }));
        }
        if (task === 'continuation') {
          continuationCalls += 1;
          // 链轮结束 → continue round_2 → continue round_3 → handback（2 条 continue 链）
          if (continuationCalls === 1) { H.continuationLog.push({ call: 1, kind: 'continue', nextRoundId: ids.round_2 }); return { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: [...roster], nextRoundId: ids.round_2 }; }
          if (continuationCalls === 2) { H.continuationLog.push({ call: 2, kind: 'continue', nextRoundId: ids.round_3 }); return { kind: 'continue', closedBy: 'model', cancelReason: null, candidateCharacterIds: [...roster], nextRoundId: ids.round_3 }; }
          H.continuationLog.push({ call: 3, kind: 'handback' }); return { kind: 'handback', closedBy: 'model', cancelReason: null };
        }
        throw new Error(`unexpected model task ${task} (${String(key)})`);
      };
      const port = { async generate(task, key, input) {
        const returned = await generateTask(task, key, input);
        modelLog.push({ task, key, at: Date.now(), returned: summarizeReturned(returned) });
        return returned;
      } };

      const driver = new ControllerDriver({ transport: H.transport, model: port }, initialMemory(`${namespace}_driver`, 'chain_twenty_holder'));
      await driver.recover(chainWorldId, { leaseToken: chainLease.leaseToken, fenceEpoch: chainLease.fenceEpoch });
      // 恢复计划=[P_chain, P_link]（recovery 原生携带 prepared successor），
      // 提交 P_chain 后服务端自动提升 successor 工作，无需 getMemory 注入
      const walkStarted = performance.now();
      const status = await driver.run();
      const walkMs = Math.round(performance.now() - walkStarted);
      const completed = status === undefined || (status.kind === 'stop' && status.reason === 'world_complete');
      if (!completed) throw new Error(`C driver status: ${JSON.stringify(status)} wire=${JSON.stringify(H.wireCaptures.slice(-3))} ` +
        `ops=${JSON.stringify(H.opLog.slice(-14))} modelTasks=${JSON.stringify(modelLog.slice(-6))} events=${JSON.stringify(H.events.slice(-3))}`);

      const points = await H.rawOp('list_points', { after: null, limit: 100 }, { tag: 'probe' });
      const chainRoundIds = new Set([ids.round, ids.round_2, ids.round_3]);
      const chainPoints = points.points.filter((point) => chainRoundIds.has(point.roundId));
      return {
        // P2-3：输入 9 的成本按切片记录（此前 modelAttempts 恒空、serverOps
        // 是累计值——切片覆盖 setup+walk 的全部模型尝试/操作/wire）
        chainInput: { index: 9, phase: 'C', command: inputText, wallMs: setupMs + walkMs,
          terminal: { kind: 'stop', reason: 'world_complete' },
          setupMs, walkMs,
          modelAttempts: H.modelAttempts.slice(attemptMark),
          serverOps: H.opLog.length - opMark,
          wireCaptures: H.wireCaptures.slice(wireMark) },
        chainWorldId, worldIdBefore, attempts: worldAttempts.length, worldAttempts, abandonedRounds,
        modelTasks: modelLog, continuationLog: H.continuationLog.slice(),
        chainPoints: chainPoints.map((point) => ({ pointId: point.pointId, kind: point.kind, roundId: point.roundId })),
        leaseTokenHead: H.lease?.leaseToken?.slice(0, 14) ?? null,
        totals: { modelAttempts: H.modelAttempts.length, completionEvidence: H.completionEvidence.length, continuationCalls },
      };
    });
    report.inputs.push(report.phases.C.chainInput);
    // 断言：2 条 continue 链 + 1 个空 linked 续段 + 4 次链段叙事。
    // list_points 的 wire 投影不含 linkedFromPointId——关联点由 kind='instant'
    // 证明（首轮点必须 normal），linked_from_point_id 列在留存的 SQLite 里核验。
    const continues = report.phases.C.continuationLog.filter((entry) => entry.kind === 'continue');
    const linked = report.phases.C.chainPoints.filter((point) => point.kind !== 'normal');
    const chainNarrations = report.phases.C.modelTasks.filter((task) => task.task === 'narration');
    assert.ok(continues.length >= 2, `expected ≥2 continue links, got ${JSON.stringify(report.phases.C.continuationLog)}`);
    assert.ok(linked.length >= 1, `expected ≥1 linked successor segment, got ${JSON.stringify(report.phases.C.chainPoints)}`);
    assert.equal(chainNarrations.length, 4, `expected 4 chain-segment narrations (chain point + linked segment + 2 auto rounds), got ${chainNarrations.length}`);
    assert.equal(report.phases.C.worldIdBefore, report.worldId, `C left the phase-A world: ${report.phases.C.worldIdBefore} != ${report.worldId}`);
    assert.equal(report.phases.C.chainWorldId, report.worldId, `C chain world mismatch: ${report.phases.C.chainWorldId} != ${report.worldId}`);
    assert.ok(report.phases.C.worldAttempts.some((entry) => entry.roll.admitted), 'no admitting roll recorded');
    assert.ok(report.phases.C.chainInput.modelAttempts.length >= 4, `chain input model slice too small: ${report.phases.C.chainInput.modelAttempts.length}`);
    assert.ok(report.phases.C.chainInput.serverOps > 0, 'chain input serverOps slice empty');
    report.status = 'PASS_C'; save();
    console.log(`[world-twenty] C: setup=${report.phases.C.chainInput.setupMs}ms walk=${report.phases.C.chainInput.walkMs}ms continues=${continues.length} linked=${linked.length}`);
  } catch (error) { harnessError(error, 'phase C'); }

  // ---- phase D: recovered rule session, 12 more inputs + narration regen ----
  try {
    report.phases.D = await page.evaluate(async () => {
      const H = window.__h;
      const { RuleWorldSession } = await import('/src/lib/world-engine/runtime/rule-session.ts');
      const { narrateFromReads } = H.narrationExports;
      // C 的 handback 可能释放/淘汰旧租约：恢复读的租约校验会直接抛
      // lease_invalid——换新租约重试一次（恢复只读，安全重入）
      const diag = async () => {
        const control = await H.control().catch((error) => ({ error: String(error) }));
        return { worldId: H.worldId, tokenHead: H.lease?.leaseToken?.slice(0, 14) ?? null,
          fenceEpoch: H.lease?.fenceEpoch ?? null, paused: control.paused ?? null, phase: control.phase ?? null };
      };
      let attach = null;
      let session = null;
      for (let tried = 0; ; tried++) {
        try {
          session = RuleWorldSession.createRecovered(H.sessionOptions('twenty_d'), H.worldId,
            H.lease ? { leaseToken: H.lease.leaseToken, fenceEpoch: H.lease.fenceEpoch } : undefined);
          attach = await H.attachRecorded(session, 'D');
          break;
        } catch (error) {
          if (tried >= 1 || !/lease_invalid/i.test(String(error))) throw new Error(`D attach failed (diag=${JSON.stringify(await diag())}): ${error?.stack ?? error}`);
          H.lease = null;
          await H.ensureLease();
        }
      }
      if (attach.terminal.kind === 'error' || (attach.terminal.kind === 'stop' && attach.terminal.reason !== 'world_complete')) {
        throw new Error(`D attach terminal (diag=${JSON.stringify(await diag())}): ${JSON.stringify(attach.terminal)}`);
      }
      const commands = ['走到门厅', '走到走廊', '完成压力试验', '上下打量四周', '走到门厅', '走到走廊',
        '走到门厅', '完成恢复练习', '走到走廊', '上下打量四周', '走到门厅', '走到走廊'];
      const inputs = [];
      for (let index = 0; index < commands.length; index++) {
        inputs.push(await H.submitRecorded(session, commands[index], 'D', index + 10));
        H.assertCleanTerminal(inputs[index], `D input ${index + 10}`);
      }

      // 每次 handback 后会话释放租约、下次 submit 重新 acquire（token 逐次更替）。
      // regen 的 raw 操作撞上释放后空窗会 lease_invalid：整段重试一次（先从
      // 会话内存克隆读回驱动器当前 token——克隆读取安全）。
      const regenPoint = async (pickPoint, mode) => {
        const points = (await H.rawOp('list_points', { after: null, limit: 100 }, { tag: 'regen' })).points;
        const target = pickPoint(points);
        if (!target) throw new Error('regen target point not found');
        const after = H.reads.get(target.pointId) ?? (mode === 'head' ? await H.rawOp('get_state', {}, { tag: 'regen' }) : null);
        if (!after || after.pointId !== target.pointId) throw new Error(`target read mismatch: ${after?.pointId} != ${target.pointId}`);
        const before = after.previousPointId ? H.reads.get(after.previousPointId) ?? null : null;
        const claim1 = await H.rawOp('narration_claim', { mode, pointId: target.pointId }, { tag: 'regen' });
        const del = await H.rawOp('narration_delete', { mode, pointId: target.pointId, claimToken: claim1.claimToken,
          generation: claim1.generation, issuedAtEpochMilli: claim1.issuedAtEpochMilli }, { tag: 'regen' });
        if (del.narrationStatus !== 'missing') throw new Error(`delete status ${del.narrationStatus}`);
        const gone = await H.rawOp('narration_get', { pointId: target.pointId }, { tag: 'regen' });
        if (gone.narrationStatus !== 'missing') throw new Error(`post-delete status ${gone.narrationStatus}`);
        const claim2 = await H.rawOp('narration_claim', { mode, pointId: target.pointId }, { tag: 'regen' });
        const eventMark = H.events.length;
        const regenerated = await narrateFromReads(after, before, H.polish, (event) => H.events.push({ ...event, at: Date.now() }));
        const regenEvents = H.events.slice(eventMark).filter((event) => event.kind === 'narration' || event.kind === 'polishFallback');
        await H.rawOp('narration_submit', { mode, pointId: target.pointId, claimToken: claim2.claimToken,
          generation: claim2.generation, issuedAtEpochMilli: claim2.issuedAtEpochMilli, outcome: 'ready', text: regenerated, failureReason: null }, { tag: 'regen' });
        const back = await H.rawOp('narration_get', { pointId: target.pointId }, { tag: 'regen' });
        if (back.narrationStatus !== 'ready') throw new Error(`regenerated narration status ${back.narrationStatus}`);
        return { pointId: target.pointId, mode, postDeleteStatus: gone.narrationStatus,
          invalidatedGeneration: del.invalidatedGeneration, claim1Generation: claim1.generation,
          claim2Generation: claim2.generation, regeneratedGeneration: back.generation ?? null, text: regenerated,
          polished: regenEvents.some((event) => event.kind === 'narration' && event.polished), events: regenEvents };
      };
      // P2-4：缓存清除重生成覆盖两头——当前头点（mode=head）与非头历史点
      // （mode=history，倒数第二点）
      let regen = null;
      let historyRegen = null;
      for (let tried = 0; ; tried++) {
        try {
          regen = await regenPoint((points) => points[points.length - 1], 'head');
          historyRegen = await regenPoint((points) => points[points.length - 2], 'history');
          break;
        } catch (error) {
          if (tried >= 1 || !/lease_invalid/i.test(String(error))) throw error;
          const current = session.getMemory().leaseToken ?? null;
          H.lease = { ...H.lease, leaseToken: current };
        }
      }
      const finalFold = await H.foldAll('final');
      return { attach, inputs, regen, historyRegen, finalFold, totals: { modelAttempts: H.modelAttempts.length, completionEvidence: H.completionEvidence.length } };
    });
    report.inputs.push(...report.phases.D.inputs);
    report.status = 'PASS_D'; save();
    console.log(`[world-twenty] D: inputs=${report.phases.D.inputs.length} regen=${report.phases.D.regen.pointId}(head) ` +
      `historyRegen=${report.phases.D.historyRegen.pointId} polished=${report.phases.D.regen.polished}/${report.phases.D.historyRegen.polished}`);
  } catch (error) { harnessError(error, 'phase D'); }

  // ---- final evidence + hard assertions ----
  try {
    report.phases.final = await page.evaluate(async () => {
      const H = window.__h;
      const points = (await H.rawOp('list_points', { after: null, limit: 100 }, { tag: 'probe' })).points;
      const headRead = await H.rawOp('get_state', {}, { tag: 'probe' });
      const narrations = [];
      for (const point of points) {
        const narration = await H.rawOp('narration_get', { pointId: point.pointId }, { tag: 'probe' });
        narrations.push({ pointId: point.pointId, narrationStatus: narration.narrationStatus, generation: narration.generation ?? null, text: narration.text });
      }
      const state = headRead.state;
      return {
        finalState: { version: headRead.version, time: state.time, protagonistId: state.protagonistId,
          characters: Object.fromEntries(Object.entries(state.characters).map(([id, actor]) => [id, {
            position: actor.position.containerId, sanity: actor.sanity,
            tasks: Object.values(actor.tasks).map((task) => ({ goal: task.goal, status: task.status })),
            personality: actor.personalityChanges.filter((change) => change.active).map((change) => change.text) }])) },
        points: points.map((point) => ({ pointId: point.pointId, sequence: point.sequence, kind: point.kind, roundId: point.roundId,
          trigger: point.trigger, linkedFromPointId: point.linkedFromPointId, previousPointId: point.previousPointId })),
        narrations, foldLog: H.foldLog, opLog: H.opLog, modelAttempts: H.modelAttempts, worldId: H.worldId,
        totals: { modelAttempts: H.modelAttempts.length, completionEvidence: H.completionEvidence.length, serverOps: H.opLog.length },
      };
    });
    report.netTrail = netTrail;
    // P2-3：全局校验——全部模型尝试（含链段、根叙事、重生成）都必须带
    // completion 证据；此前只遍历输入切片，链段缺证据不会被抓
    const globalWithoutCompletion = (report.phases.final.modelAttempts ?? [])
      .map((attempt, index) => ({ index, attempt: attempt.attempt, pointId: attempt.pointId, ok: Boolean(attempt.completion?.length) }))
      .filter((entry) => !entry.ok);
    // 输入切片完整性：每条输入切片的尝试数之和不得超过全局总数（切片来自同一数组）
    const inputSliceAttempts = report.inputs.reduce((sum, input) => sum + (input.modelAttempts?.length ?? 0), 0)
      + (report.phases.A.attach?.modelAttempts?.length ?? 0) + (report.phases.D.attach?.modelAttempts?.length ?? 0);
    assert.equal(report.inputs.length, 21, `expected 21 player inputs, got ${report.inputs.length}`);
    assert.ok(report.phases.final.narrations.every((narration) => narration.narrationStatus === 'ready'),
      `narrations not all ready: ${JSON.stringify(report.phases.final.narrations.filter((entry) => entry.narrationStatus !== 'ready'))}`);
    assert.ok(report.phases.final.foldLog.length > 0 && report.phases.final.foldLog.every((entry) => entry.ok
      && entry.steps.every((step) => step.ok === true)),
      `S₀ fold failures/skips: ${JSON.stringify(report.phases.final.foldLog.filter((entry) => !entry.ok || entry.steps.some((step) => step.ok !== true)))}`);
    assert.ok(report.phases.D.regen.invalidatedGeneration >= 1, 'head regeneration did not bump generation');
    assert.ok(report.phases.D.historyRegen && report.phases.D.historyRegen.mode === 'history'
      && report.phases.D.historyRegen.invalidatedGeneration >= 1, 'history regeneration missing or did not bump generation');
    assert.notEqual(report.phases.D.historyRegen.pointId, report.phases.D.regen.pointId, 'history regen must target a non-head point');
    assert.equal(globalWithoutCompletion.length, 0, `global attempts without completion: ${JSON.stringify(globalWithoutCompletion)}`);
    assert.ok(report.phases.final.totals.modelAttempts >= inputSliceAttempts,
      `global attempt count ${report.phases.final.totals.modelAttempts} < sliced total ${inputSliceAttempts}`);
    // P1-1：单世界——全程恰一次 create_world，各阶段 worldId 一致
    assert.equal((report.phases.final.opLog ?? []).filter((entry) => entry.op === 'create_world').length, 1,
      'expected exactly one create_world in the whole run');
    assert.equal(report.phases.C.chainWorldId, report.worldId, 'C ran in a different world');
    assert.equal(report.phases.final.worldId ?? report.worldId, report.worldId, 'final world mismatch');
    assert.ok(report.phases.D.historyRegen, 'history regen missing');
    report.status = 'PASS_TWENTY';
    save();
    console.log(`[world-twenty] PASS_TWENTY: inputs=${report.inputs.length} points=${report.phases.final.points.length} ` +
      `narrations=${report.phases.final.narrations.length} modelAttempts=${report.phases.final.totals.modelAttempts} folds=${report.phases.final.foldLog.length}`);
  } catch (error) { harnessError(error, 'final evidence'); }

  cleanup();
  await browser.close();
  // 原始数据库与日志随报告保留（取证后不得删除原始数据——存证 note 教训）
  try { service.kill(); } catch {}
  // Windows 下 uvicorn 的 SIGTERM 收尾可能悬挂：限时等待后 SIGKILL 兜底
  await new Promise((done) => {
    if (service.exitCode !== null) return done();
    const timer = setTimeout(done, 5000);
    service.once('exit', () => { clearTimeout(timer); done(); });
  });
  try { service.kill('SIGKILL'); } catch {}
  const dbSnapshotDir = resolve(root, option('--db-snapshot', 'artifacts/world-chain/twenty-run-db'));
  mkdirSync(dbSnapshotDir, { recursive: true });
  report.retainedEvidence = { privateDir, dbSnapshot: option('--db-snapshot', 'artifacts/world-chain/twenty-run-db') };
  for (const suffix of ['', '-wal', '-shm']) {
    const source = resolve(privateDir, `world.db${suffix}`);
    if (existsSync(source)) copyFileSync(source, resolve(dbSnapshotDir, `world.db${suffix}`));
  }
  if (existsSync(resolve(privateDir, 'server.log'))) copyFileSync(resolve(privateDir, 'server.log'), resolve(dbSnapshotDir, 'server.log'));
  save();
  console.log(`[world-twenty] ${report.status} → ${output} (db+log retained in ${dbSnapshotDir})`);
  process.exit(0);
} catch (error) {
  report.status = 'FAILED';
  report.error = String(error?.stack ?? error);
  report.consoleTrail = consoleTrail.slice(-40);
  save();
  cleanup();
  try { if (browser) await browser.close(); } catch {}
  console.error('[world-twenty] FAILED:', error);
  process.exit(1);
}
