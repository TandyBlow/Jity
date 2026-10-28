// Full-chain acceptance, first round: two real scenarios over the real Python
// service (persistent world app) and the real browser model (wllama in a real
// Edge, cross-origin isolated). Deliverable of the 整链验收 batch: a rerunnable
// script, raw records and the problem list — first answer "can one player
// input complete correctly, and how long does it take".
//
//   action  普通行动点：页面同款 RuleWorldSession（规则权威结算——action/
//           results/updates/continuation 全部零模型调用）+ 真实模型叙事
//           （checkFactNarration 门控、失败重生成一次、模板兜底）。七条
//           玩家输入覆盖：移动、被拒绝命令、任务达成（人格+理智联动）、
//           未识别命令。
//   chain   连锁共同结算：完整 ControllerDriver + 真实 HTTP + 真实服务端
//           d20 骰点（重试世界直到首环准入，realized branch 如实记录）。
//           结算文本（行动/反应/结果/更新候选）为脚本候选——结算组件的
//           模型化属 B3 独立批次，不在本批；叙事走与页面同源的
//           narrateFromReads + 真实模型门（同一 narration-polisher）。
//
//   node scripts/run-world-chain-full.mjs --out ../artifacts/world-chain/first-round.json
//        [--phase action|chain|both] [--server-checkout .local/world-server-worktree] [--python python]
import assert from 'node:assert/strict';
import { execFileSync, spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createWriteStream, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer as createNetServer } from 'node:net';
import { createServer } from 'vite';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const phase = option('--phase', 'both');
const a = resolve(root, option('--server-checkout', '.local/world-server-worktree'));
const output = resolve(root, option('--out', 'artifacts/world-chain/first-round.json'));
const privateDir = resolve(root, `.local/world-chain-full-${Date.now()}`); // SQLite 跨运行持久：固定目录会让新进程再造 world_1、撞上旧幂等台账（request_id_reused）
mkdirSync(privateDir, { recursive: true });
const sources = ['frontend/scripts/run-world-chain-full.mjs', 'frontend/src/app/world/page.tsx', 'frontend/src/app/world/narration-polisher.ts',
  ...['runtime/rule-session', 'runtime/rule-facts', 'runtime/committed-narration', 'runtime/prompts', 'runtime/wllama-engine',
    'controller', 'schedule', 'http-transport', 'recovery'].map((name) => `frontend/src/lib/world-engine/${name}.ts`)];
const git = (checkout, ...args) => { try {
  // 只去尾部换行：status 首行的前导空格是 porcelain 格式的一部分，
  // 整串 trim 会把它吃掉（守卫按 slice(3) 解析就会切错首行）
  return execFileSync('git', ['-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).replace(/\n+$/, '');
} catch { return null; } };
// 服务端钉档=backend/app 全部代码文件（首轮教训：serverSource 只有 head/status，
// head 还写错过——sha256 逐文件钉住实际执行的代码，不依赖 git 状态陈述）。
const walkServerFiles = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((entry) => entry.isDirectory()
  ? (entry.name === '__pycache__' ? [] : walkServerFiles(resolve(dir, entry.name))) : [resolve(dir, entry.name)]);
const serverAppRoot = resolve(a, 'backend', 'app').replaceAll('\\', '/');
const serverFiles = walkServerFiles(resolve(a, 'backend', 'app'))
  .map((file) => ({ path: `backend/app/${file.replaceAll('\\', '/').slice(serverAppRoot.length + 1)}`, file }));
const report = {
  status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), phase,
  browserSource: { head: git(root, 'rev-parse', 'HEAD'), status: git(root, 'status', '--short'),
    sha256: Object.fromEntries(sources.map((file) => [file, createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex')])) },
  serverSource: { head: git(a, 'rev-parse', 'HEAD'), status: git(a, 'status', '--short'),
    sha256: Object.fromEntries(serverFiles.map(({ path, file }) => [path, createHash('sha256').update(readFileSync(file)).digest('hex')])) },
  modelLoad: null, action: null, chain: null,
};
const save = () => { mkdirSync(resolve(output, '..'), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };
save();

// 钉住集必须 tracked-clean，否则 sha256 对不上任何提交、复跑不保证同代码；
// 豁免开关（--allow-dirty-server / --allow-dirty-browser）只是放行，artifact 仍如实记录。
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
  console.error(`[world-chain] FAILED: ${report.error}`);
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

const service = spawn(option('--python', 'python'), ['-X', 'utf8', '-m', 'uvicorn', 'app.world_app:create_persistent_world_app', '--factory',
  '--host', '127.0.0.1', '--port', String(apiPort)], {
  cwd: resolve(a, 'backend'),
  env: { ...process.env, WORLD_SQLITE_PATH: resolve(privateDir, 'world.db'), WORLD_ALLOWED_ORIGINS: viteOrigin },
  windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
});
const serverLog = createWriteStream(resolve(privateDir, 'server.log'));
service.stdout.pipe(serverLog);
service.stderr.pipe(serverLog);

const vite = await createServer({ root: frontend, configFile: false, logLevel: 'warn', cacheDir: '../.local/world-chain-vite',
  server: { host: '127.0.0.1', port: vitePort, hmr: false },
  plugins: [{ name: 'world-chain', configureServer(vite) { vite.middlewares.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
    if (req.url !== '/__chain') return next();
    res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><title>World chain acceptance</title>');
  }); } }] });
await vite.listen();
report.lifecycle = { apiOrigin, viteOrigin };
save();

const cleanup = () => {
  try { vite.close(); } catch {}
  try { service.kill(); } catch {}
};

let browser;
try {
  for (let attempt = 0; ; attempt++) {
    if (service.exitCode !== null) throw new Error('World HTTP service exited before readiness');
    try {
      const response = await fetch(`${apiOrigin}/openapi.json`, { signal: AbortSignal.timeout(8000) });
      if (response.ok) break;
    } catch { /* boot still running */ }
    if (attempt >= 40) throw new Error('World HTTP service readiness timeout');
    await new Promise((done) => setTimeout(done, 500));
  }
  report.lifecycle.serviceReady = true; save();

  const { chromium } = await import('@playwright/test');
  browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const page = await browser.newPage();
  const consoleTrail = [];
  page.on('console', (message) => consoleTrail.push(message.text()));
  page.on('pageerror', (error) => consoleTrail.push(`[pageerror] ${error.message}`));
  const netTrail = [];
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
  assert.equal(await page.evaluate(() => window.crossOriginIsolated), true, 'chain acceptance requires cross-origin isolation');
  report.modelLoad = await page.evaluate(async (modelUrl) => {
    const { warmNarrationEngine } = await import('/src/app/world/narration-polisher.ts');
    return { model: modelUrl, ...await warmNarrationEngine(modelUrl) };
  }, '/models/Qwen3-0.6B-Q4_K_M.gguf');
  save();

  if (phase === 'action' || phase === 'both') {
    report.action = await page.evaluate(async ({ api: apiBase }) => {
      const evidence = [];
      const modelAttempts = [];
      const events = [];
      const opLog = [];
      const wireCaptures = [];
      try {
      const [{ HttpWorldTransport }, { RuleWorldSession }, { defaultInitialTemplate, WORLD_POLICY, DEFAULT_POLISH_MODEL },
        { narrationPolisher }] = await Promise.all([
        import('/src/lib/world-engine/http-transport.ts'), import('/src/lib/world-engine/runtime/rule-session.ts'),
        import('/src/app/world/world-defaults.ts'), import('/src/app/world/narration-polisher.ts')]);

      const capturingFetcher = async (input, init) => {
        const response = await fetch(input, init);
        if (response.status >= 400) wireCaptures.push({ url: String(input), body: String(init?.body ?? ''), status: response.status, response: await response.clone().text() });
        return response;
      };
      const basePolisher = await narrationPolisher(DEFAULT_POLISH_MODEL);
      const polish = async (input, packet, focused, attempt) => {
        const started = performance.now();
        const evidenceBefore = evidence.length;
        // 证据回调必须逐调用传入：实例级 onCompletion 会被 polisher 的模块级
        // 缓存吞掉（v2 的 chain completion 证据为空即此因——action 先建实例、
        // chain 复用同一实例，chain 的回调被忽略）
        const text = await basePolisher(input, packet, focused, attempt, (item) => evidence.push(item));
        modelAttempts.push({ at: Date.now(), attempt: attempt.index, ms: Math.round(performance.now() - started), chars: text.length, text,
          pointId: input?.pointId ?? null,
          facts: (focused?.facts ?? []).map((fact) => ({ id: fact.id, phrase: fact.allowedPhrases[0] })),
          completion: evidence.slice(evidenceBefore) }); // usage/timings/raw 逐尝试落盘（首轮只存了数量）
        return text;
      };
      const http = new HttpWorldTransport(apiBase, capturingFetcher);
      const transport = { async execute(operation, request, scope, signal) {
        const started = performance.now();
        const response = await http.execute(operation, request, scope, signal);
        opLog.push({ op: operation, ms: Math.round(performance.now() - started) });
        return response;
      } };
      const session = RuleWorldSession.createNew({ transport, initial: defaultInitialTemplate(), policy: WORLD_POLICY,
        polish, onEvent: (event) => events.push({ ...event, at: Date.now() }), holderId: 'chain_action' });

      const attachStarted = performance.now();
      const attachTerminal = await session.attach();
      const attachMs = Math.round(performance.now() - attachStarted);
      if (attachTerminal.kind === 'error' || (attachTerminal.kind === 'stop' && attachTerminal.reason !== 'world_complete')) {
        throw new Error(`attach terminal: ${JSON.stringify(attachTerminal)} wire=${JSON.stringify(wireCaptures)} events=${JSON.stringify(events.slice(-4))}`);
      }
      const worldId = session.worldId;
      const attachStatus = attachTerminal;
      const rootNarrations = events.slice().filter((event) => event.kind === 'narration');
      const rootModelAttempts = modelAttempts.slice();
      const commandList = ['走到门厅', '完成压力试验', '走到走廊', '完成压力试验', '完成恢复练习', '上下打量四周', '走到门厅'];
      const inputs = [];
      events.length = 0;
      modelAttempts.length = 0;
      let mark = 0;
      let attemptMark = 0;
      let opMark = opLog.length;
      for (const command of commandList) {
        const started = performance.now();
        const terminal = await session.submit(command);
        const slice = events.slice(mark);
        inputs.push({
          command, wallMs: Math.round(performance.now() - started), terminal, wireCaptures: wireCaptures.splice(0),
          decision: slice.find((event) => event.kind === 'decision') ?? null,
          unparsed: slice.some((event) => event.kind === 'unparsed'),
          narration: slice.filter((event) => event.kind === 'narration')
            .map((event) => ({ pointId: event.pointId, version: event.version, polished: event.polished,
              polishReason: event.polishReason, attempts: event.attempts, text: event.text })),
          polishFallback: slice.filter((event) => event.kind === 'polishFallback').map((event) => event.detail),
          modelAttempts: modelAttempts.slice(attemptMark),
          serverOps: opLog.length - opMark,
        });
        mark = events.length; attemptMark = modelAttempts.length; opMark = opLog.length;
      }
      const state = (await http.execute('get_state', {}, { worldId })).data;
      const points = (await http.execute('list_points', { after: null, limit: 100 }, { worldId })).data.points;
      const narrations = [];
      for (const point of points) narrations.push((await http.execute('narration_get', {}, { worldId, pointId: point.pointId })).data);
      const protagonist = state.state.characters[state.state.protagonistId];
      return {
        worldId, attach: { ms: attachMs, status: attachStatus, narrations: rootNarrations, modelAttempts: rootModelAttempts },
        inputs,
        finalState: { version: state.version, location: protagonist.position.containerId, sanity: protagonist.sanity,
          tasks: Object.values(protagonist.tasks).map((task) => ({ goal: task.goal, status: task.status })),
          personality: [...protagonist.personalityChanges].filter((change) => change.active).map((change) => change.text) },
        points: points.map((point, index) => ({ pointId: point.pointId, narrationStatus: narrations[index].narrationStatus, text: narrations[index].text })),
        totals: { modelAttempts: modelAttempts.length, serverOps: opLog.length, completionEvidence: evidence.length,
          inputWallRange: { minMs: Math.min(...inputs.map((item) => item.wallMs)), maxMs: Math.max(...inputs.map((item) => item.wallMs)) } },
        opLog, modelAttempts, events,
      };
      } catch (error) {
        return { failed: true, error: String(error?.stack ?? error), wireCaptures, opLog, events, modelAttempts };
      }
    }, { api: apiOrigin });
    report.action.netTrail = netTrail.splice(0); // 原始 wire 逐场景落盘（首轮成功路径缺原始轨迹）
    if (report.action.failed) {
      report.netTrail = netTrail;
      save();
      throw new Error(`action failed: ${report.action.error}\nwire=${JSON.stringify(report.action.wireCaptures)}\nops=${JSON.stringify((report.action.opLog ?? []).slice(-10))}\nevents=${JSON.stringify((report.action.events ?? []).slice(-4))}\nnet=${JSON.stringify(netTrail, null, 1).slice(0, 3000)}`);
    }
    if (report.action.totals.completionEvidence < 1) {
      throw new Error('action narration produced no completion evidence — per-call onCompletion plumbing regressed');
    }
    report.status = 'PASS_ACTION'; save();
    console.log(`[world-chain] action: attach=${report.action.attach.ms}ms inputs=${report.action.inputs.length} ` +
      `modelAttempts=${report.action.totals.modelAttempts} wall=${Math.round(report.action.inputs.reduce((sum, item) => sum + item.wallMs, 0))}ms`);
  }

  if (phase === 'chain' || phase === 'both') {
    report.chain = await page.evaluate(async ({ api: apiBase }) => {
      const [{ HttpWorldTransport }, { ControllerDriver, initialMemory }, { narrateFromReads },
        { defaultInitialTemplate, WORLD_POLICY, DEFAULT_POLISH_MODEL }, { narrationPolisher }] = await Promise.all([
        import('/src/lib/world-engine/http-transport.ts'), import('/src/lib/world-engine/controller.ts'),
        import('/src/lib/world-engine/runtime/rule-session.ts'), import('/src/app/world/world-defaults.ts'),
        import('/src/app/world/narration-polisher.ts')]);

      const setupOps = [];
      const evidence = [];
      const modelAttempts = [];
      const events = [];
      const opLog = [];
      const rollsOut = [];
      const reads = new Map();
      try {
      const basePolisher = await narrationPolisher(DEFAULT_POLISH_MODEL);
      const polish = async (input, packet, focused, attempt) => {
        const started = performance.now();
        const evidenceBefore = evidence.length;
        // 证据回调必须逐调用传入：实例级 onCompletion 会被 polisher 的模块级
        // 缓存吞掉（v2 的 chain completion 证据为空即此因——action 先建实例、
        // chain 复用同一实例，chain 的回调被忽略）
        const text = await basePolisher(input, packet, focused, attempt, (item) => evidence.push(item));
        modelAttempts.push({ at: Date.now(), attempt: attempt.index, ms: Math.round(performance.now() - started), chars: text.length, text,
          pointId: input?.pointId ?? null,
          facts: (focused?.facts ?? []).map((fact) => ({ id: fact.id, phrase: fact.allowedPhrases[0] })),
          completion: evidence.slice(evidenceBefore) }); // usage/timings/raw 逐尝试落盘（首轮只存了数量）
        return text;
      };
      const http = new HttpWorldTransport(apiBase);
      const transport = { async execute(operation, request, scope, signal) {
        const started = performance.now();
        const response = await http.execute(operation, request, scope, signal);
        opLog.push({ op: operation, ms: Math.round(performance.now() - started) });
        if (operation === 'get_state') reads.set(response.data.pointId, structuredClone(response.data));
        if (operation === 'create_rolls') rollsOut.push(structuredClone(response.data.rolls));
        return response;
      } };

      // ---- scripted-API side: raw HTTP with explicit lease bindings ----
      let worldId = null;
      let lease = null;
      let head = null;
      let revision = null;
      const namespace = `chain_${Date.now().toString(36)}`;
      let sequence = 0;
      const next = () => `${namespace}_${++sequence}`;
      const api = async (operation, payload) => {
        setupOps.push({ op: operation, at: Date.now() });
        try {
        // setup 期必须走带记录的 transport（首轮直连 http.execute，create_rolls/
        // checkpoint 全部绕过 opLog/rollsOut——secondRoll 恒 null、首骰未落盘的根因）
        const result = await transport.execute(operation, payload, worldId ? { worldId } : {});
        if (result.world) { worldId = result.world.worldId; head = result.world.head; }
        const flat = result.data?.leaseToken != null ? result.data : null;
        const granted = result.data?.lease ?? flat ?? result.world?.lease;
        if (granted?.leaseToken) lease = granted;
        if (result.control) revision = result.control.revision;
        return result;
        } catch (error) {
          setupOps.push({ op: `${operation}:REFUSED`, error: error?.response?.error ?? null, payload: JSON.stringify(payload).slice(0, 400), at: Date.now() });
          throw error;
        }
      };
      const base = () => ({ protocolVersion: 2, requestId: next(), worldId, leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch });
      const ck = () => ({ ...base(), expectedPointId: head.pointId, expectedVersion: head.version, expectedCheckpointRevision: revision });
      const allocate = async (slots) => {
        const allocation = await api('allocate_ids', { ...base(), allocationKey: `${namespace}_ids`, slots });
        return Object.fromEntries(allocation.data.allocations.map((a) => [a.slotKey, a.id]));
      };
      const createWorld = async () => {
        worldId = null; // a fresh world must not inherit the previous scope
        await api('create_world', { protocolVersion: 2, requestId: next(), initial: defaultInitialTemplate() });
        const pointId = head.pointId;
        const claim = (await api('narration_claim', { ...base(), mode: 'head', pointId })).data;
        await api('narration_submit', { ...base(), mode: 'head', pointId, claimToken: claim.claimToken, generation: claim.generation,
          issuedAtEpochMilli: claim.issuedAtEpochMilli, outcome: 'ready', text: '根点模板叙事（脚本引导，不计入模型成本）。', failureReason: null });
      };

      // 服务端冻结顺序规则（world_store.finish_operation）：start_advance 后
      // 轮次顺序按（理智值，ID）升序重排——同为 10 时恒为 ['person_a','person_c']，
      // cursor 0 = person_a，发起人必须是 order[0]（discover 绑定校验
      // 「initiatorId == order[cursor]」的触发者）。
      const roster = ['person_a', 'person_c'];
      const initiator = 'person_a';
      const reactor = 'person_c';
      const inputText = '林川推开门厅深处的重门，示意周宁到门边一起撑住。';
      const setupStarted = performance.now();
      let attempts = 0;
      let ids = null;
      const worldAttempts = []; // 每次世界尝试的骰点逐条落盘（首轮重试覆盖 firstRoll，被丢弃世界的骰值丢失）
      let firstAdmitted = false;
      for (attempts = 1; attempts <= 6 && !firstAdmitted; attempts++) {
        await createWorld(); // 每次尝试都从全新世界开始（含根叙事引导）
        const attemptWorldId = worldId;
        ids = await allocate([
          { slotKey: 'advance', kind: 'advance' }, { slotKey: 'input', kind: 'input' }, { slotKey: 'round', kind: 'round' },
          { slotKey: 'point_1', kind: 'point' }, { slotKey: 'group_1', kind: 'group' },
          { slotKey: 'trigger:group_1:person_a:person_c', kind: 'trigger' },
        ]);
        await api('checkpoint_start_advance', { ...ck(), operation: 'start_advance', advanceId: ids.advance, inputId: ids.input,
          roundId: ids.round, inputText, order: roster });
        await api('checkpoint_begin_point', { ...ck(), operation: 'begin_point', pointId: ids.point_1, kind: 'normal',
          timeAdvance: { boundary: 'elapsed', duration: { amount: 2, unit: 'second' } } });
        await api('checkpoint_discover_group', { ...ck(), operation: 'discover_group', pointId: ids.point_1, groupId: ids.group_1,
          initiatorId: initiator, actionText: inputText, targetIds: null });
        await api('checkpoint_extend_group', { ...ck(), operation: 'extend_group', pointId: ids.point_1, groupId: ids.group_1,
          sourceId: initiator, targets: [{ targetId: reactor, triggerKey: ids['trigger:group_1:person_a:person_c'] }], admittedMember: null });
        const ringRoll = (await api('create_rolls', { ...ck(), rolls: [{ advanceId: ids.advance, roundId: ids.round, groupId: ids.group_1,
          sourceId: initiator, targetId: reactor, triggerKey: ids['trigger:group_1:person_a:person_c'],
          ruleVersion: 'reaction-d20-v1', target: 11 }] })).data.rolls[0];
        worldAttempts.push({ attempt: attempts, worldId: attemptWorldId,
          roll: { admitted: ringRoll.admitted, rollId: ringRoll.rollId, result: ringRoll.result, ruleVersion: ringRoll.ruleVersion } });
        if (ringRoll.admitted) {
          await api('checkpoint_extend_group', { ...ck(), operation: 'extend_group', pointId: ids.point_1, groupId: ids.group_1,
            sourceId: initiator, targets: null, admittedMember: { memberId: reactor,
              actionText: '周宁在门边稳住身形，与林川一起撑住重门。',
              rollRefs: [{ sourceId: initiator, targetId: reactor, triggerKey: ids['trigger:group_1:person_a:person_c'], rollId: ringRoll.rollId }] } });
          firstAdmitted = true;
        }
      }
      if (!firstAdmitted) throw new Error('no admitting first-link roll in six attempts');
      const setupMs = Math.round(performance.now() - setupStarted);

      // ---- hybrid port: scripted settlement candidates + REAL narrated gate ----
      const modelLog = [];
      const summarizeReturned = (value) => {
        const text = typeof value === 'string' ? value : JSON.stringify(value);
        return typeof text === 'string' && text.length > 800 ? `${text.slice(0, 800)}…[truncated, total ${text.length}]` : value;
      };
      const generateTask = async (task, key, input) => {
        if (task === 'action') return { kind: 'skip' };
        if (task === 'targets') return input.sourceId === reactor ? { targets: [{ targetId: initiator }] } : { targets: [] };
        if (task === 'reaction') return `${input.memberId} 稳住身形，撑住门轴。`;
        if (task === 'results') return Object.fromEntries(input.members.map((member) => [member.memberId, `${member.memberId} 的既定结果。`]));
        if (task === 'updates') {
          if (input.mode === 'time_scan') return input.stage ? { stage: input.stage, changes: {} } : [];
          // committed 叙事投影只支持 位置/任务/人格/理智——外貌变化会在
          // narrateFromReads 的 projectCommittedNarration 处抛
          // unsupported_committed_delta；这里改用发起人的完整数值因果
          // （任务达成＋人格＋理智，§6.3 步骤 5）。
          return [
            { stage: 'tasks', changes: { [initiator]: { entityId: initiator, tasksAchieved: ['task_watch'] } } },
            { stage: 'personality', changes: { [initiator]: { entityId: initiator, personalityChanges: [{ id: `${namespace}_change_1`, text: '撑住重门后更加沉稳', supersedes: [] }] } } },
            { stage: 'sanity', changes: { [initiator]: { entityId: initiator, sanitySet: 8 } } }];
        }
        if (task === 'continuation') return { kind: 'handback', closedBy: 'model', cancelReason: null };
        if (task === 'narration') {
          const after = reads.get(key);
          if (!after) throw new Error('narration_requires_saved_point_read');
          const before = after.previousPointId ? reads.get(after.previousPointId) : null;
          if (before === undefined) throw new Error('narration_requires_saved_predecessor_read');
          return narrateFromReads(after, before, polish, (event) => events.push({ ...event, at: Date.now() }));
        }
        throw new Error(`unexpected model task ${task} (${String(key)})`);
      };
      const port = { async generate(task, key, input) {
        const returned = await generateTask(task, key, input);
        modelLog.push({ task, key, at: Date.now(), returned: summarizeReturned(returned) });
        return returned;
      } };
      const driver = new ControllerDriver({ transport, model: port }, initialMemory(`${namespace}_driver`, 'chain_full_holder'));
      const walkStarted = performance.now();
      await driver.recover(worldId, { leaseToken: lease.leaseToken, fenceEpoch: lease.fenceEpoch });
      const status = await driver.run();
      const walkMs = Math.round(performance.now() - walkStarted);
      const completed = status === undefined || (status.kind === 'stop' && status.reason === 'world_complete');

      const state = (await http.execute('get_state', {}, { worldId })).data;
      const points = (await http.execute('list_points', { after: null, limit: 100 }, { worldId })).data.points;
      const narrations = [];
      for (const point of points) narrations.push((await http.execute('narration_get', {}, { worldId, pointId: point.pointId })).data);
      const commitCount = opLog.filter((entry) => entry.op === 'commit_point').length;
      return {
        // attempts 必须取实际尝试数：循环变量退出时已自增 +1（首轮 README
        // 的「换世界重试」叙事正是把这个退出值 2 误读成了两次尝试）
        worldId, attempts: worldAttempts.length, worldAttempts,
        status: completed ? 'COMPLETED' : status, setupMs, walkMs,
        modelTasks: modelLog, narrationEvents: events, modelAttempts,
        commitCount, rollsRolled: rollsOut.flat().map((roll) => ({ sourceId: roll.sourceId, targetId: roll.targetId, admitted: roll.admitted, result: roll.result })),
        points: points.map((point, index) => ({ pointId: point.pointId, version: point.version, narrationStatus: narrations[index].narrationStatus, text: narrations[index].text })),
        finalState: { version: state.version, time: state.state.time.dateTime,
          characters: Object.fromEntries(Object.entries(state.state.characters).map(([id, actor]) => [id, {
            position: actor.position.containerId, sanity: actor.sanity,
            tasks: Object.values(actor.tasks).map((task) => ({ goal: task.goal, status: task.status })),
            personality: [...actor.personalityChanges].filter((change) => change.active).map((change) => change.text),
            appearance: actor.appearanceChanges.map((change) => change.text) }])) },
        totals: { modelAttempts: modelAttempts.length, serverOps: opLog.length, completionEvidence: evidence.length },
        opLog, setupOps, readPointIds: [...reads.keys()],
      };
      } catch (error) {
        return { failed: true, error: String(error?.stack ?? error), setupOps, opLog, events, modelAttempts, reads: [...reads.keys()] };
      }
    }, { api: apiOrigin });
    report.chain.netTrail = netTrail.splice(0); // 原始 wire 逐场景落盘（首轮成功路径缺原始轨迹）
    if (report.chain.failed) {
      report.netTrail = netTrail;
      save();
      throw new Error(`chain failed: ${report.chain.error}
setupOps=${JSON.stringify(report.chain.setupOps)}
ops=${JSON.stringify((report.chain.opLog ?? []).slice(-8))}
events=${JSON.stringify((report.chain.events ?? []).slice(-3))}`);
    }
    if (report.chain.totals.completionEvidence < 1) {
      // v2 的阻断项：chain 的 completion 证据为空（polisher 实例级回调被缓存吞掉），
      // 断言钉住这条管道，防回归
      throw new Error('chain narration produced no completion evidence — per-call onCompletion plumbing regressed');
    }
    report.status = phase === 'both' ? 'PASS_BOTH' : 'PASS_CHAIN'; save();
    console.log(`[world-chain] chain: attempts=${report.chain.attempts} setup=${report.chain.setupMs}ms walk=${report.chain.walkMs}ms ` +
      `commits=${report.chain.commitCount} modelAttempts=${report.chain.totals.modelAttempts} status=${JSON.stringify(report.chain.status)}`);
  }
  save();
  cleanup();
  await browser.close();
  console.log(`[world-chain] ${report.status} → ${output}`);
  process.exit(0);
} catch (error) {
  report.status = 'FAILED';
  report.error = String(error?.stack ?? error);
  report.consoleTrail = typeof consoleTrail !== 'undefined' ? consoleTrail.slice(-40) : [];
  save();
  cleanup();
  try { if (browser) await browser.close(); } catch {}
  console.error('[world-chain] FAILED:', error);
  process.exit(1);
}
