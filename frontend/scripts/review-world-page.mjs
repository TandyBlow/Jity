// Minimal world PAGE acceptance. One uvicorn (persistent world app) + one
// `next dev` + a real Chromium session drive the /world page through the
// closed loop the batch requires: 连续命令 → 刷新续接 → 丢回执不重复消费.
// Two Node probes run against the same server through RuleWorldSession:
// P1 连续会话＋提交回执丢失（同 requestId 重试、服务端 replay），
// P2 提交前放弃（seal 已受理但回执被扣住）→ recover 续走 → 恰好一次提交。
// Usage: node scripts/review-world-page.mjs [--out artifacts/world-page-review.json]
//        [--server-checkout .local/world-server-worktree] [--skip-browser]
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createWriteStream, mkdirSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { createServer } from 'vite';
import { createServer as createNetServer } from 'node:net';

const frontend = fileURLToPath(new URL('../', import.meta.url));
const root = resolve(frontend, '..');
const option = (flag, fallback) => process.argv.includes(flag) ? process.argv[process.argv.indexOf(flag) + 1] : fallback;
const a = resolve(root, option('--server-checkout', '.local/world-server-worktree'));
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
const sourceFiles = ['frontend/scripts/review-world-page.mjs', 'frontend/src/app/world/page.tsx', 'frontend/src/app/world/world-defaults.ts',
  ...['runtime/rule-session', 'runtime/session', 'runtime/rule-facts', 'runtime/committed-narration', 'controller', 'recovery', 'http-transport']
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
    const statusSection = page.locator('section').filter({ hasText: '状态（服务端事实）' });
    const commandSection = page.locator('section').filter({ hasText: '支持命令与执行状态' });
    const logSection = page.locator('section').filter({ hasText: '叙事（提交模板；润色仅为实验）' });
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

    // r6 可选实验：模型润色（失败保持模板）——时间预算放宽
    await logSection.locator('label').filter({ hasText: '模型润色' }).locator('input').check();
    await runCommand('走到门厅', 300_000);
    await logSection.getByText('v6·').first().waitFor({ timeout: 30_000 });
    await expect(statusSection.getByText('门厅', { exact: true })).toBeVisible();
    const polishedBadge = await logSection.getByText('润色', { exact: true }).count();
    step('r6-polish', { polishedBadge, note: 'either a fact-valid polish or the template fallback is displayed' });

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
