// Minimal world PAGE acceptance. One uvicorn (persistent world app) + one
// `next dev` + a real Chromium session drive the /world page through the
// closed loop the batch requires: 连续命令 → 刷新续接 → 丢回执不重复消费.
// Two Node probes run against the same server through RuleWorldSession:
// P1 连续会话＋提交回执丢失（同 requestId 重试、服务端 replay），
// P2 提交前放弃（seal 已受理但回执被扣住）→ recover 续走 → 恰好一次提交。
// Usage: node scripts/review-world-page.mjs [--out artifacts/world-page-review.json]
//        --server-checkout <服务检出>（必填） [--skip-browser]
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer } from 'vite';
import { createServer as createNetServer } from 'node:net';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
// 服务检出必填：旧默认 .local/world-server-worktree 已随工作树重组退役。
// 缺旗标或检出缺 backend/app/world_app.py 一律拒绝起跑；
// --expect-server-head <sha 前缀> 可选比对（不写死任何检出 HEAD）。
const requireServerCheckout = (tag) => {
  const given = option('--server-checkout', null);
  if (!given) {
    console.error(`[${tag}] FAILED: --server-checkout <服务检出> is required (the old default checkout is retired)`);
    process.exit(1);
  }
  const checkout = resolve(root, given);
  if (!existsSync(resolve(checkout, 'backend', 'app', 'world_app.py'))) {
    console.error(`[${tag}] FAILED: --server-checkout ${given} has no backend/app/world_app.py`);
    process.exit(1);
  }
  const head = execFileSync('git', ['-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  console.log(`[${tag}] server checkout HEAD ${head}`);
  const expected = option('--expect-server-head', null);
  if (expected && !head.startsWith(expected)) {
    console.error(`[${tag}] FAILED: server HEAD ${head} does not match --expect-server-head ${expected}`);
    process.exit(1);
  }
  return checkout;
};
const a = requireServerCheckout('world-page');
const output = resolve(root, option('--out', 'artifacts/world-page/review.json'));
const skipBrowser = process.argv.includes('--skip-browser');
const privateDir = resolve(root, `.local/world-page-${Date.now()}`);
mkdirSync(privateDir, { recursive: true });

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
const nextPort = await freePort();
const apiOrigin = `http://127.0.0.1:${apiPort}`;
const nextOrigin = `http://127.0.0.1:${nextPort}`;

const git = (checkout, ...args) => execFileSync('git', ['-c', `safe.directory=${checkout.replaceAll('\\', '/')}`, '-C', checkout, ...args], { encoding: 'utf8' }).trim();
const sourceFiles = ['frontend/scripts/review-world-page.mjs', 'frontend/next.config.ts', 'frontend/src/app/world/page.tsx', 'frontend/src/app/world/world-defaults.ts',
  ...['runtime/rule-session', 'runtime/session', 'runtime/rule-facts', 'runtime/committed-narration', 'runtime/prompts', 'runtime/focused-input',
    'runtime/world-reads', 'runtime/wllama-engine', 'controller', 'recovery', 'http-transport']
    .map((name) => `frontend/src/lib/world-engine/${name}.ts`)];
const report = { status: 'IN_PROGRESS', recordedAt: new Date().toISOString(), apiOrigin, nextOrigin,
  browserSource: { head: git(root, 'rev-parse', 'HEAD'), status: git(root, 'status', '--short'),
    sha256: Object.fromEntries(sourceFiles.map((file) => [file, createHash('sha256').update(readFileSync(resolve(root, file))).digest('hex')])) },
  serverSource: { head: git(a, 'rev-parse', 'HEAD'), status: git(a, 'status', '--short') },
  probes: {}, browser: { steps: [] }, lifecycle: [] };
const save = () => { mkdirSync(resolve(output, '..'), { recursive: true }); writeFileSync(output, JSON.stringify(report, null, 2) + '\n'); };

const service = spawn(option('--python', 'python'), ['-X', 'utf8', '-m', 'uvicorn', 'app.world_app:create_persistent_world_app', '--factory',
  '--host', '127.0.0.1', '--port', String(apiPort)], {
  cwd: resolve(a, 'backend'),
  env: { ...process.env, WORLD_SQLITE_PATH: resolve(privateDir, 'world.db'),
    WORLD_ALLOWED_ORIGINS: `${nextOrigin},http://localhost:${nextPort}` },
  windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
});
const serverLog = createWriteStream(resolve(privateDir, 'server.log'));
service.stdout.pipe(serverLog);
service.stderr.pipe(serverLog);
const next = spawn(process.execPath, [resolve(frontend, 'node_modules/next/dist/bin/next'), 'dev', '--port', String(nextPort)], {
  cwd: frontend, env: { ...process.env, NEXT_TELEMETRY_DISABLED: '1' }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
});
const nextLog = createWriteStream(resolve(privateDir, 'next.log'));
next.stdout.pipe(nextLog);
next.stderr.pipe(nextLog);

async function waitReady(url, label, budgetMs, child) {
  for (let attempt = 0; ; attempt++) {
    if (child?.exitCode !== null) throw new Error(`${label} exited before readiness`);
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(8000) });
      if (response.ok) return;
    } catch { /* boot or on-demand compile still running */ }
    if (attempt >= Math.ceil(budgetMs / 500)) throw new Error(`${label} readiness timeout`);
    await new Promise((done) => setTimeout(done, 500));
  }
}

let vite;
const cleanup = () => {
  try { vite?.close(); } catch {}
  for (const child of [service, next]) { try { child?.kill(); } catch {} }
};
try {
  for (const [url, label, budget, child] of [
    [`${apiOrigin}/openapi.json`, 'World HTTP service', 20_000, service],
    [`${nextOrigin}/`, 'Next dev server', 180_000, next],
  ]) {
    await waitReady(url, label, budget, child);
    report.lifecycle.push({ event: 'ready', label, url });
  }
  save();

  // ---------------- Node probes over RuleWorldSession ----------------
  vite = await createServer({ root: frontend, configFile: false, server: { middlewareMode: true }, cacheDir: '../.local/world-page-vite' });
  const { RuleWorldSession } = await vite.ssrLoadModule('/src/lib/world-engine/runtime/rule-session.ts');
  const { WorldTimeoutError } = await vite.ssrLoadModule('/src/lib/world-engine/transport.ts');
  const { HttpWorldTransport } = await vite.ssrLoadModule('/src/lib/world-engine/http-transport.ts');
  const { SHORT_STATE } = await vite.ssrLoadModule('/src/lib/world-engine/runtime/b3-short-samples.ts');
  const { defaultInitialTemplate, WORLD_POLICY } = await vite.ssrLoadModule('/src/app/world/world-defaults.ts');

  const http = new HttpWorldTransport(apiOrigin);
  const initial = defaultInitialTemplate();
  const milestone = WORLD_POLICY.sanity.milestones;

  const sessionOptions = (transport, onEvent) => ({
    transport, initial, policy: WORLD_POLICY, onEvent, holderId: `probe_${Math.random().toString(36).slice(2, 8)}`,
  });

  // ---- P1: 连续会话＋提交回执丢失 ----
  {
    const events = [];
    const commits = [];
    let dropsLeft = 1;
    const inner = new HttpWorldTransport(apiOrigin);
    const transport = { async execute(operation, request, scope, signal) {
      const response = await inner.execute(operation, request, scope, signal);
      if (operation === 'commit_point') {
        commits.push({ requestId: request.requestId, pointId: request.point.id });
        if (dropsLeft > 0) { dropsLeft -= 1; throw new WorldTimeoutError('probe: lost accepted commit receipt'); }
      }
      return response;
    } };
    const session = RuleWorldSession.createNew(sessionOptions(transport, (event) => events.push(event)));
    const t1 = await session.submit('完成压力试验');
    assert.deepEqual(t1, { kind: 'stop', reason: 'world_complete' }, `P1 round1 terminal ${JSON.stringify(t1)}`);
    const wid = session.worldId;
    assert.ok(wid, 'P1 worldId missing');
    const afterRound1 = (await http.execute('get_state', {}, { worldId: wid })).data;
    assert.equal(afterRound1.version, 1, 'P1 round1 committed exactly once');
    const t2 = await session.submit('走到门厅');
    assert.deepEqual(t2, { kind: 'stop', reason: 'world_complete' }, `P1 round2 terminal ${JSON.stringify(t2)}`);
    const final = (await http.execute('get_state', {}, { worldId: wid })).data;
    assert.equal(final.version, 2, 'P1 two rounds → version 2');
    const points = (await http.execute('list_points', { after: null, limit: 100 }, { worldId: wid })).data.points;
    assert.equal(points.length, 3, 'P1 root + two rounds, no duplicate points');
    assert.equal(final.state.characters.person_c.position.containerId, 'hall');
    assert.equal(final.state.characters.person_c.sanity, 8);
    assert.ok(final.state.characters.person_c.tasks[milestone.strain.taskId].status === 'achieved');
    const narrationRows = [];
    for (const point of points) {
      const narration = (await http.execute('narration_get', {}, { worldId: wid, pointId: point.pointId })).data;
      narrationRows.push({ pointId: point.pointId, status: narration.narrationStatus, text: narration.text });
    }
    assert.ok(narrationRows.every((row) => row.status === 'ready' && row.text?.length), 'P1 every point has ready narration');
    const strainText = narrationRows.find((row) => row.text?.includes('完成压力试验'));
    assert.ok(strainText, `P1 strain narration missing: ${JSON.stringify(narrationRows)}`);
    const decisions = events.filter((event) => event.kind === 'decision');
    assert.equal(decisions.length, 2);
    assert.deepEqual(decisions.map((event) => event.outcome), ['allowed', 'allowed']);
    assert.equal(commits.length, 3, 'P1 commit attempts: 1 lost + retried (2) + round2 (1)');
    assert.equal(commits[0].requestId, commits[1].requestId, 'P1 retry preserves the requestId');
    assert.notEqual(commits[0].requestId, commits[2].requestId, 'P1 round2 mints a fresh requestId');
    report.probes.p1 = { status: 'PASS', worldId: wid, version: final.version, points: points.length,
      commits, narrationRows, sanity: final.state.characters.person_c.sanity };
    console.log('[world-page] P1 continuous-session + lost receipt: PASS');
    save();
  }

  // ---- P2: 提交前放弃 → recover 续走 → 恰好一次提交 ----
  {
    const events = [];
    let gateArmed = false;
    let gateReachedResolve;
    const gateReached = new Promise((done) => { gateReachedResolve = done; });
    const gateStall = new Promise(() => {}); // 永不结算：回执被无限期扣住
    const grants = [];
    const inner = new HttpWorldTransport(apiOrigin);
    const transport = { async execute(operation, request, scope, signal) {
      const response = await inner.execute(operation, request, scope, signal);
      const data = response?.data ?? {};
      const grant = operation === 'create_world' ? data.lease
        : operation === 'lease_acquire' || operation === 'lease_renew' ? data : undefined;
      if (grant?.leaseToken) grants.push({ leaseToken: grant.leaseToken, fenceEpoch: grant.fenceEpoch });
      if (operation === 'checkpoint_seal_point' && gateArmed) {
        gateReachedResolve(); // 服务端已受理，回执被扣住——模拟提交前刷新窗口
        await gateStall;
      }
      return response;
    } };
    const session = RuleWorldSession.createNew(sessionOptions(transport, (event) => events.push(event)));
    gateArmed = true;
    const stalled = session.submit('走到门厅');
    const race = await Promise.race([gateReached.then(() => 'gated'), stalled.then(() => 'finished')]);
    assert.equal(race, 'gated', 'P2 seal receipt must be captured before the round finishes');
    const wid = session.worldId;
    const grant = grants.at(-1);
    assert.ok(wid && grant, 'P2 worldId/lease missing');
    session.stop(); // 模拟刷新：旧会话终止，不再有任何写路径
    assert.deepEqual(await stalled, { kind: 'stop', reason: 'session_stopped' }, 'P2 abandoned submit settles as session_stopped');
    const sealedRead = (await http.execute('get_state', {}, { worldId: wid })).data;
    assert.equal(sealedRead.version, 0, 'P2 nothing committed before the refresh');
    const recovered = RuleWorldSession.createRecovered(sessionOptions(new HttpWorldTransport(apiOrigin), (event) => events.push(event)),
      wid, { leaseToken: grant.leaseToken, fenceEpoch: grant.fenceEpoch });
    const terminal = await recovered.attach();
    assert.deepEqual(terminal, { kind: 'stop', reason: 'world_complete' }, `P2 recovered terminal ${JSON.stringify(terminal)}`);
    const final = (await http.execute('get_state', {}, { worldId: wid })).data;
    assert.equal(final.version, 1, 'P2 the abandoned round commits exactly once after recovery');
    const points = (await http.execute('list_points', { after: null, limit: 100 }, { worldId: wid })).data.points;
    assert.equal(points.length, 2, 'P2 root + one round point');
    assert.equal(final.state.characters.person_c.position.containerId, 'hall');
    const narration = (await http.execute('narration_get', {}, { worldId: wid, pointId: points.at(-1).pointId })).data;
    assert.equal(narration.narrationStatus, 'ready');
    report.probes.p2 = { status: 'PASS', worldId: wid, versionBeforeRefresh: sealedRead.version, versionAfterRecovery: final.version,
      points: points.length, narrationText: narration.text };
    console.log('[world-page] P2 pre-commit abandon + recover: PASS');
    save();
  }

  // ---- P3: handback 边界恢复 → 恢复会话继续接新命令 ----
  {
    const events = [];
    const grants = [];
    const wrap = (inner) => ({ async execute(operation, request, scope, signal) {
      const response = await inner.execute(operation, request, scope, signal);
      const data = response?.data ?? {};
      const grant = operation === 'create_world' ? data.lease
        : operation === 'lease_acquire' || operation === 'lease_renew' ? data : undefined;
      if (grant?.leaseToken) grants.push({ leaseToken: grant.leaseToken, fenceEpoch: grant.fenceEpoch });
      return response;
    } });
    const first = RuleWorldSession.createNew(sessionOptions(wrap(new HttpWorldTransport(apiOrigin)), (event) => events.push(event)));
    await first.submit('走到门厅');
    await first.submit('走到走廊');
    const wid = first.worldId;
    const held = grants.at(-1);
    assert.ok(wid && held, 'P3 worldId/lease missing');
    first.stop(); // 模拟刷新：旧页面死亡，租约留待续租
    const recovered = RuleWorldSession.createRecovered(sessionOptions(wrap(new HttpWorldTransport(apiOrigin)), (event) => events.push(event)),
      wid, { leaseToken: held.leaseToken, fenceEpoch: held.fenceEpoch });
    const attachStatus = await recovered.attach();
    assert.deepEqual(attachStatus, { kind: 'stop', reason: 'world_complete' }, `P3 handback-boundary attach ${JSON.stringify(attachStatus)}`);
    const submitStatus = await recovered.submit('完成压力试验');
    assert.deepEqual(submitStatus, { kind: 'stop', reason: 'world_complete' }, `P3 recovered submit ${JSON.stringify(submitStatus)}`);
    const final = (await http.execute('get_state', {}, { worldId: wid })).data;
    assert.equal(final.version, 3, 'P3 two pre-refresh rounds + one post-recovery round');
    assert.equal(final.state.characters.person_c.sanity, 8);
    assert.equal(final.state.characters.person_c.position.containerId, 'corridor');
    assert.ok(final.state.characters.person_c.tasks[milestone.strain.taskId].status === 'achieved');
    const decisions = events.filter((event) => event.kind === 'decision');
    assert.equal(decisions.length, 3);
    assert.deepEqual(decisions.map((event) => event.outcome), ['allowed', 'allowed', 'allowed']);
    report.probes.p3 = { status: 'PASS', worldId: wid, version: final.version, sanity: 8, decisions: decisions.length };
    console.log('[world-page] P3 handback-boundary recovery + recovered submit: PASS');
    save();
  }

  if (skipBrowser) {
    report.status = 'PASS_PROBES_ONLY';
    save();
    cleanup();
    console.log(`[world-page] ${report.status} → ${output}`);
    process.exit(0);
  }

  // ---------------- Real browser closed loop ----------------
  const { chromium, expect } = await import('@playwright/test');
  // The project's playwright config drives the system Edge (channel msedge);
  // the downloaded chromium build is not part of this machine's setup.
  const browser = await chromium.launch({ headless: true, channel: 'msedge' });
  const step = (name, detail) => { report.browser.steps.push({ name, detail, at: new Date().toISOString() }); save(); };
  try {
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();
    page.on('pageerror', (error) => report.browser.steps.push({ name: 'pageerror', detail: String(error) }));
    const modelConsole = [];
    page.on('console', (message) => {
      const text = message.text();
      if (text.includes('[narration-model]') || text.includes('[narration]')) modelConsole.push(text);
    });
    const statusSection = page.locator('section').filter({ hasText: '状态（服务端事实）' });
    const commandSection = page.locator('section').filter({ hasText: '支持命令与执行状态' });
    const logSection = page.locator('section').filter({ hasText: '叙事（默认模板；模型叙事为可选实验）' });
    const commandInput = commandSection.locator('input[placeholder*="输入命令"]');
    const runButton = commandSection.getByRole('button', { name: '执行', exact: true });

    await page.goto(`${nextOrigin}/world?api=${apiOrigin}`, { waitUntil: 'domcontentloaded', timeout: 120_000 });
    await page.getByRole('button', { name: '新世界' }).click();
    await statusSection.getByText('走廊', { exact: true }).waitFor({ timeout: 60_000 });
    await expect(statusSection.getByText('10', { exact: true })).toBeVisible();
    await logSection.getByText('周宁位于走廊').first().waitFor({ timeout: 30_000 });
    const rootRows = await logSection.locator('li').count();
    assert.ok(rootRows >= 1, 'root narration row visible');
    step('new-world', { location: '走廊', sanity: 10, logRows: rootRows });

    async function runCommand(text, expectTimeoutMs = 60_000) {
      await commandInput.fill(text);
      await runButton.click();
      await expect(runButton).toBeDisabled({ timeout: 5_000 }).catch(() => {});
      try {
        await expect(runButton).toBeEnabled({ timeout: expectTimeoutMs });
      } catch (error) {
        const diagnostics = { note: await page.locator('p.text-amber-700').allTextContents(),
          lastAction: await commandSection.locator('p').allTextContents(),
          commandSection: (await commandSection.innerText()).slice(0, 500) };
        step(`runCommand-diagnostic:${text}`, diagnostics);
        throw error;
      }
    }

    // r1 移动：走廊 → 门厅
    await runCommand('走到门厅');
    await logSection.getByText('周宁从走廊走到门厅。').first().waitFor({ timeout: 30_000 });
    await expect(statusSection.getByText('门厅', { exact: true })).toBeVisible();
    await expect(logSection.getByText('v1·+1秒').first()).toBeVisible();
    step('r1-move', { command: '走到门厅', narration: '周宁从走廊走到门厅。', timeAdvance: '+1秒' });

    // r2 被拒绝的命令：门厅做压力试验 → 显示拒绝原因，数值不变
    await runCommand('完成压力试验');
    await commandSection.getByText('已拒绝（milestone_location_mismatch）').waitFor({ timeout: 30_000 });
    await expect(statusSection.getByText('10', { exact: true })).toBeVisible();
    step('r2-refused', { command: '完成压力试验', reason: 'milestone_location_mismatch' });

    // r3 移动回走廊
    await runCommand('走到走廊');
    await logSection.getByText('周宁从门厅走到走廊。').first().waitFor({ timeout: 30_000 });
    step('r3-move-back', { command: '走到走廊' });

    // 刷新续接：sessionStorage 里的 worldId+租约 → recover 自动重连
    await page.reload({ waitUntil: 'domcontentloaded' });
    await statusSection.getByText('走廊', { exact: true }).waitFor({ timeout: 60_000 });
    await expect(statusSection.getByText('10', { exact: true })).toBeVisible();
    const reloadedRows = await logSection.locator('li').count();
    assert.equal(reloadedRows, 4, `reload must rebuild all 4 narrations, got ${reloadedRows}`);
    step('reload-recover', { logRows: reloadedRows, location: '走廊', sanity: 10 });

    // r4 提交后继续：压力试验（走廊）10→8，任务达成
    await runCommand('完成压力试验');
    try {
      await logSection.getByText('周宁完成了任务「完成压力试验」').first().waitFor({ timeout: 30_000 });
    } catch (error) {
      step('r4-diagnostic', { log: (await logSection.innerText()).slice(0, 800),
        command: (await commandSection.innerText()).slice(0, 400),
        status: (await statusSection.innerText()).slice(0, 300) });
      throw error;
    }
    await expect(statusSection.getByText('8', { exact: true })).toBeVisible();
    step('r4-strain', { sanity: 8, task: '完成压力试验 achieved' });

    // r5 丢回执重试：勾选注入 → 恢复练习 8→9，世界不重复消费
    await logSection.locator('label').filter({ hasText: '下一次提交丢回执' }).locator('input').check();
    await runCommand('完成恢复练习');
    await logSection.getByText('周宁的精神值从8变为9').first().waitFor({ timeout: 30_000 });
    await expect(statusSection.getByText('9', { exact: true })).toBeVisible();
    const worldId = (await page.locator('header .font-mono').first().textContent())?.trim();
    assert.ok(worldId, 'worldId chip visible in the page header');
    step('r5-lost-receipt', { sanity: 9, worldId });

    // r6 模型叙事（本批核心）：模型为主、判分器门控、失败重生成一次后模板
    // 兜底。硬断言：至少一条叙事由模型生成并通过事实校验（badge≥1）——
    // 模板回退永远可用，但小模型必须真实接入并产出。
    const polishStart = Date.now();
    await logSection.locator('label').filter({ hasText: '模型叙事' }).locator('input').check();
    await runCommand('走到门厅', 420_000);
    const narrationMs = Date.now() - polishStart;
    await logSection.getByText('v6·').first().waitFor({ timeout: 30_000 });
    await expect(statusSection.getByText('门厅', { exact: true })).toBeVisible();
    const polishedBadge = await logSection.getByText('模型', { exact: true }).count();
    if (polishedBadge < 1) {
      step('r6-diagnostic', { narrationMs, log: (await logSection.innerText()).slice(-500),
        note: await page.locator('p.text-amber-700').allTextContents(),
        modelConsole: modelConsole.slice(-12),
        lastAction: (await commandSection.innerText()).slice(-200) });
    }
    assert.ok(polishedBadge >= 1, `the model narration must be adopted at least once, got ${polishedBadge} adopted rows`);
    step('r6-model-narration', { polishedBadge, narrationMs, note: 'model-first narration adopted by the fact judge; regeneration and template fallback remain wired' });

    // 服务端事实核对：root + 6 rounds，逐点叙事就绪，无重复点（走带协议头
    // 的传输层——裸 fetch 缺 v2 头只会拿到错误信封）
    const stateCheck = await http.execute('get_state', {}, { worldId });
    assert.equal(stateCheck.data.version, 6, `browser loop must commit exactly 6 rounds, got ${stateCheck.data.version}`);
    const pointsCheck = await http.execute('list_points', { after: null, limit: 100 }, { worldId });
    assert.equal(pointsCheck.data.points.length, 7, 'root + 6 rounds, no duplicate consumption');
    assert.equal(stateCheck.data.state.characters.person_c.sanity, 9);
    assert.equal(stateCheck.data.state.characters.person_c.position.containerId, 'hall');
    for (const point of pointsCheck.data.points) {
      const narration = await http.execute('narration_get', {}, { worldId, pointId: point.pointId });
      assert.equal(narration.data.narrationStatus, 'ready', `narration ready for ${point.pointId}`);
    }
    step('server-facts', { version: 6, points: 7, sanity: 9, location: 'hall' });

    // r7 客户端导航往返：SPA 离开（卸载，会话停止）→ 返回（组件级重新
    // 初始化 + 自动续接 + 服务端事实重建）。模块级 boot 标记会让这一步
    // 永远停在 boot——本探针即该回归。
    await page.getByRole('link', { name: '返回控制台' }).click();
    await page.waitForURL((url) => !url.pathname.endsWith('/world'), { timeout: 30_000 });
    await page.goBack();
    await page.waitForURL((url) => url.pathname.endsWith('/world'), { timeout: 30_000 });
    await statusSection.getByText('门厅', { exact: true }).waitFor({ timeout: 60_000 });
    await expect(statusSection.getByText('9', { exact: true })).toBeVisible({ timeout: 30_000 });
    const returnRows = await logSection.locator('li').count();
    assert.equal(returnRows, 7, `navigation round-trip must rebuild all 7 narrations, got ${returnRows}`);
    step('spa-roundtrip', { logRows: returnRows, location: '门厅', sanity: 9 });

    // r10 SPA 进入隔离回归：COOP/COEP 只在文档创建时生效——从 /（无隔离
    // 头）经客户端路由进入 /world 时，响应头不会追认既有文档的隔离状态，
    // crossOriginIsolated 仍为 false，多线程模型路径（SharedArrayBuffer）
    // 全程不可用。修复=挂载自检失败整页重载一次（sessionStorage 护栏防
    // 循环），重载后的文档由 /world 的响应头创建即隔离。判据：软导航后
    // 隔离为真、本次导航类型是 reload、世界凭 sessionStorage 自动续接
    // （7 行、门厅/9），且护栏标记已清除（没有重载循环）。
    // 软导航由 next dev 暴露的 window.next.router 触发——与真实 <Link> 走
    // 同一个 App Router 动作；页面当前没有从控制台进入 /world 的链接。
    // 路由器在 hydration 前已存在但派发会抛「dispatched before initialization」，
    // 所以先用设置菜单的开合作 hydration 判据（点击只在 hydration 后生效）。
    await page.goto(`${nextOrigin}/`, { waitUntil: 'load', timeout: 120_000 });
    assert.equal(await page.evaluate(() => window.crossOriginIsolated), false,
      'the console document must start without the isolation headers');
    await page.getByRole('button', { name: '设置' }).click();
    await page.getByRole('menu', { name: '游戏设置' }).waitFor({ timeout: 60_000 });
    await page.keyboard.press('Escape');
    await page.getByRole('menu', { name: '游戏设置' }).waitFor({ state: 'detached', timeout: 10_000 });
    await page.evaluate(() => window.next.router.push('/world'));
    await page.waitForURL((url) => url.pathname.endsWith('/world'), { timeout: 30_000 });
    // 自检的整页重载会销毁执行上下文，waitForFunction 会因此直接失败；
    // 从 Node 侧轮询，把导航中的 evaluate 异常当作「正在重载」吞掉。
    let isolated = null;
    let navigationType = null;
    for (const deadline = Date.now() + 60_000; Date.now() < deadline;) {
      try {
        isolated = await page.evaluate(() => window.crossOriginIsolated);
        if (isolated) navigationType = await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.type ?? null);
      } catch { /* the mount self-check is reloading the document */ }
      if (isolated) break;
      await page.waitForTimeout(200);
    }
    if (!isolated) {
      const diagnostic = { isolated: null, navigationType: null, pathname: null, flag: null, hasWorldUi: 0, body: '' };
      try {
        diagnostic.pathname = await page.evaluate(() => window.location.pathname);
        diagnostic.flag = await page.evaluate(() => window.sessionStorage.getItem('jity.world.isoReload'));
        diagnostic.body = (await page.evaluate(() => document.body.innerText)).slice(0, 200);
        diagnostic.hasWorldUi = await page.getByText('世界最小交互页').count();
      } catch { /* navigation still in flight */ }
      step('spa-entry-diagnostic', diagnostic);
      assert.fail('a soft entry into /world must end up in a cross-origin isolated document');
    }
    assert.equal(navigationType, 'reload',
      'the mount self-check must reload into a document created with the isolation headers');
    // 隔离状态在文档创建时即为真，早于 React 挂载——护栏清除要等挂载后的
    // else 分支，所以用「世界已重建完成」作为挂载完成的判据再读护栏。
    await statusSection.getByText('门厅', { exact: true }).waitFor({ timeout: 90_000 });
    await expect(statusSection.getByText('9', { exact: true })).toBeVisible({ timeout: 30_000 });
    const spaEntryRows = await logSection.locator('li').count();
    assert.equal(spaEntryRows, 7, `SPA entry must rebuild all 7 narrations, got ${spaEntryRows}`);
    assert.equal(await page.evaluate(() => window.sessionStorage.getItem('jity.world.isoReload')), null,
      'the reload guard must be cleared once the isolated document is mounted');
    step('spa-entry-isolation', { crossOriginIsolated: true, navigationType, logRows: spaEntryRows,
      location: '门厅', sanity: 9,
      note: 'the mount self-check reloaded the soft entry once into an isolated document, world re-attached' });

    // r8 异步竞态回归（漏传 isStale 时转红）：旧代挂载的 attach 首读
    // （get_state）被扣到新代完成之后才放行。修复前旧 attach 继续创建会话、
    // 发布 activeRef 并触发 rebuild（逐点 state 读）——覆盖新代引用，外层
    // 按实例清理随后清空引用，命令失效。确定性判据有二：放行后窗口内
    // 「逐点 state 读增量必须为 0」（漏传时旧代 rebuild 必然发出这些读，
    // 与任何按钮/渲染时序无关），以及下一条命令照常提交 v7。
    let stateCalls = 0;
    let heldStateRoute = null;
    await page.route(/\/worlds\/[^/]+\/state$/, async (route) => {
      stateCalls += 1;
      if (stateCalls === 1 && !heldStateRoute) { heldStateRoute = route; return; } // 扣住旧代首读
      await route.continue();
    });
    let pagedStateReads = 0; // /state?point=…：rebuild 的逐点读
    let pagedBaseline = 0;
    await page.route(/\/worlds\/[^/]+\/state\?/, async (route) => {
      pagedStateReads += 1;
      await route.continue();
    });
    try {
      await page.getByRole('link', { name: '返回控制台' }).click();
      await page.waitForTimeout(300);
      await page.goBack();
      await page.waitForTimeout(300); // 挂载 B：其 attach 首读此刻被扣住
      await page.getByRole('link', { name: '返回控制台' }).click();
      await page.waitForTimeout(300); // 卸载 B（attach 悬挂中，cleanup 已置失效）
      await page.goBack();
      await page.waitForTimeout(300); // 挂载 C：第 2 次首读直接放行
      await statusSection.getByText('门厅', { exact: true }).waitFor({ timeout: 60_000 });
      await expect(statusSection.getByText('9', { exact: true })).toBeVisible({ timeout: 30_000 });
      const cRows = await logSection.locator('li').count();
      assert.equal(cRows, 7, `generation C must rebuild all 7 narrations, got ${cRows}`);
      assert.ok(heldStateRoute, 'generation B get_state must have been captured');
      pagedBaseline = pagedStateReads; // C 的恢复读到此为止；此后增量都属旧代
      let rebuildReadsAfterRelease = 0; // 断言时刻快照（step 诊断用）
      const lateResponse = await heldStateRoute.fetch(); // 旧代读真实转发（幂等读）
      await heldStateRoute.fulfill({ response: lateResponse });
      heldStateRoute = null;
      await page.waitForTimeout(2000); // 旧代 attach 晚到路径稳定结算
      // 确定性判据 1：放行后旧代不得发出任何 rebuild 逐点读（漏传 isStale
      // 时旧 attach 走到 rebuild，增量 ≥1，此处转红）。
      rebuildReadsAfterRelease = pagedStateReads - pagedBaseline;
      assert.equal(rebuildReadsAfterRelease, 0,
        `late attach must not issue any rebuild read after release, got ${rebuildReadsAfterRelease}`);
      // 旧代未夺走页面：状态/日志原样
      await expect(statusSection.getByText('门厅', { exact: true })).toBeVisible();
      await expect(statusSection.getByText('9', { exact: true })).toBeVisible();
      assert.equal(await logSection.locator('li').count(), 7, 'late attach must not rebuild or alter the log');
      // 确定性判据 2：引用存活，下一条命令照常执行
      await runCommand('走到走廊');
      await logSection.getByText('周宁从门厅走到走廊。').first().waitFor({ timeout: 30_000 });
      await expect(statusSection.getByText('走廊', { exact: true })).toBeVisible();
      const facts = await http.execute('get_state', {}, { worldId });
      assert.equal(facts.data.version, 7, 'the post-race command must commit exactly one more round');
      assert.equal(facts.data.state.characters.person_c.position.containerId, 'corridor');
      step('late-attach-race', { logRows: 7, commandAfter: '走到走廊', version: 7,
        rebuildReadsAfterRelease,
        note: 'late get_state cancelled before any session/reference/page write' });
    } finally {
      await page.unroute(/\/worlds\/[^/]+\/state$/);
      await page.unroute(/\/worlds\/[^/]+\/state\?/);
    }

    // r9 恢复期间取消回归（attachOnce 漏停时转红）：旧代挂载已过首读与
    // lease_renew、挂起在恢复流程的 get_context（即 session.attach() 悬挂
    // 中）时卸载。恢复中途的读在 attach 返回前发出、闸门拦不住（观察为
    // 软诊断）；修复版在恢复返回处取消并 stopOwned——会话死亡、心跳永不
    // 启动；漏停版会话泄漏，其心跳（服务端 TTL 120s、lead 30s → 恢复完成
    // 后 ~90s 首次续租）必然出现。确定性判据：断开活跃会话后 100s 窗口内
    // lease 续租必须为 0。随后新代会话照常执行命令（引用未被旧代破坏）。
    let contextCalls = 0;
    let heldContextRoute = null;
    await page.route(/\/worlds\/[^/]+\/context/, async (route) => {
      contextCalls += 1;
      if (contextCalls === 1 && !heldContextRoute) { heldContextRoute = route; return; } // 扣住旧代恢复首读
      await route.continue();
    });
    let recoveryReads = 0;
    let recoveryBaseline = 0;
    const recoveryReadUrls = [];
    await page.route(/\/worlds\/[^/]+\/points\?/, async (route) => {
      recoveryReads += 1; recoveryReadUrls.push(`${new Date().toISOString().slice(11, 19)} ${route.request().url()}`);
      await route.continue();
    });
    await page.route(/\/worlds\/[^/]+\/state\?/, async (route) => {
      recoveryReads += 1; recoveryReadUrls.push(`${new Date().toISOString().slice(11, 19)} ${route.request().url()}`);
      await route.continue();
    });
    try {
      await page.getByRole('link', { name: '返回控制台' }).click();
      await page.waitForTimeout(300);
      await page.goBack();
      await page.waitForTimeout(800); // 挂载 B：过首读与续租，挂起在恢复 get_context
      await page.getByRole('link', { name: '返回控制台' }).click();
      await page.waitForTimeout(300); // 卸载 B：恢复悬挂中，cleanup 已置失效
      await page.goBack();
      await page.waitForTimeout(300); // 挂载 C：第 2 个 context 直接放行，恢复完成
      await statusSection.getByText('走廊', { exact: true }).waitFor({ timeout: 60_000 });
      await expect(statusSection.getByText('9', { exact: true })).toBeVisible({ timeout: 30_000 });
      const cRows9 = await logSection.locator('li').count();
      assert.equal(cRows9, 8, `generation C must rebuild all 8 narrations, got ${cRows9}`);
      assert.ok(heldContextRoute, 'generation B recovery get_context must have been captured');
      recoveryBaseline = recoveryReads; // C 的恢复读到此为止
      let recoveryReadsAfterRelease = 0;
      const lateRecovery = await heldContextRoute.fetch(); // 恢复读幂等，真实转发
      await heldContextRoute.fulfill({ response: lateRecovery });
      heldContextRoute = null;
      await page.waitForTimeout(3000); // 旧代恢复晚到路径稳定结算
      // 确定性判据：放行后旧会话不得继续恢复（漏停时它走完剩余恢复读，
      // 增量 ≥1，此处转红；修复后 attachOnce 在恢复返回处取消并停止会话）。
      recoveryReadsAfterRelease = recoveryReads - recoveryBaseline;
      // 软诊断（不 assert）：死代恢复中途的读不可拦，数量取决于恢复 filter。
      await expect(statusSection.getByText('走廊', { exact: true })).toBeVisible();
      assert.equal(await logSection.locator('li').count(), 8, 'late recovery must not alter the log');
      // 新代引用存活：命令照常提交
      await runCommand('走到门厅');
      await logSection.getByText('周宁从走廊走到门厅。').first().waitFor({ timeout: 30_000 });
      await expect(statusSection.getByText('门厅', { exact: true })).toBeVisible();
      const facts9 = await http.execute('get_state', {}, { worldId });
      assert.equal(facts9.data.version, 8, 'the post-race command must commit exactly one more round');
      assert.equal(facts9.data.state.characters.person_c.position.containerId, 'hall');
      // 硬判据：断开活跃会话后，泄漏的旧会话心跳必然出现（~90s 相位）；
      // 修复版旧会话已在 attachOnce 内停止——窗口内零续租。
      let leasePuts = 0;
      await page.route(/\/worlds\/[^/]+\/lease$/, async (route) => {
        leasePuts += 1;
        await route.continue();
      });
      try {
        await page.getByRole('button', { name: '断开' }).click();
        await statusSection.getByText('尚未连接世界。').waitFor({ timeout: 30_000 });
        const cut = leasePuts; // 断开瞬间的计数即基线
        await page.waitForTimeout(100_000);
        const leaked = leasePuts - cut;
        assert.equal(leaked, 0,
          `a cancelled attach must not keep renewing the lease after disconnect, got ${leaked} lease renewals in 100s`);
        step('cancelled-recovery', { logRows: 8, commandAfter: '走到门厅', version: 8,
          recoveryReadsAfterRelease, leaseRenewalsAfterDisconnect: leaked,
          note: 'cancelled attach stopped inside attachOnce; new generation reference intact' });
      } finally {
        await page.unroute(/\/worlds\/[^/]+\/lease$/);
      }
    } finally {
      await page.unroute(/\/worlds\/[^/]+\/context/);
      await page.unroute(/\/worlds\/[^/]+\/points\?/);
      await page.unroute(/\/worlds\/[^/]+\/state\?/);
    }
    report.browser.status = 'PASS_BROWSER_LOOP';
    report.status = 'PASS_WORLD_PAGE';
  } finally {
    await browser.close();
  }
  save();
  cleanup();
  console.log(`[world-page] ${report.status} → ${output}`);
  process.exit(0);
} catch (error) {
  report.status = 'FAILED';
  report.error = String(error);
  report.stack = error?.stack;
  save();
  cleanup();
  console.error('[world-page] FAILED:', error);
  process.exit(1);
}
