// G7 two-device acceptance on the real page: both devices advance from one
// remote head; the reconnect flush uploads the second branch, the page opens
// the fork panel, the player keeps one branch and the other stays readable.
// Sequenced contexts keep one browser alive at a time (host memory).

import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { acquireLease } from './lease.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const arg = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index > 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const has = (name) => process.argv.includes(name);

const base = arg('--base', 'http://127.0.0.1:3177');
const api = arg('--api', 'http://127.0.0.1:8000/local-progress');
const out = resolve(root, arg('--out', 'artifacts/goal/sync/two-device-20261121.json'));
const world = 'world_dragon_raja_free_day';
// One engine per page and no off-screen judge: sync does not depend on them.
const arm = arg('--arm', 'narrationModel=semantic&offscreenPolicy=skip');
const turnTimeoutMs = Number(arg('--turn-timeout-ms', '480000'));
const readyTimeoutMs = Number(arg('--ready-timeout-ms', '240000'));
const choice = has('--keep-remote') ? 'keep-remote' : 'keep-local-fork';
const inputs = JSON.parse(arg('--inputs',
  '["我低头检查护目镜、识别带和胸袋里的弹匣，确认都在。","我沿着器材棚外侧往仓库方向走，留意有没有人跟着。"]'));

const evidence = {
  kind: 'jity-g7-two-device-fork',
  startedAt: new Date().toISOString(),
  base,
  api,
  world,
  arm,
  choice,
  inputs,
  steps: {},
  failures: [],
};
const save = () => {
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify(evidence, null, 2) + '\n');
};
const fail = (scope, message, detail = null) => {
  evidence.failures.push({ at: new Date().toISOString(), scope, message, detail });
  save();
  console.error(`[fail] ${scope}: ${message}`);
};

const apiJson = async (path) => {
  const response = await fetch(`${api}${path}`);
  if (!response.ok) throw new Error(`${path} -> ${response.status}`);
  return response.json();
};
const head = () => apiJson(`/worlds/${world}/head`);
const graph = () => apiJson(`/worlds/${world}/graph`);

/** The page's own sync storage: the offline queue and the last known head. */
const syncStorage = (page) => page.evaluate(() => ({
  queue: localStorage.getItem('jity.progress-sync.queue.v1'),
  heads: localStorage.getItem('jity.progress-sync.heads.v1'),
})).catch(() => null);

async function boot(context, label) {
  const page = await context.newPage();
  const log = [];
  page.on('console', (message) => {
    const text = message.text();
    if (/world-local|progress-sync/.test(text)) log.push(text.slice(0, 300));
  });
  page.on('pageerror', (error) => log.push(`pageerror:${error.message}`.slice(0, 300)));
  const startedAt = Date.now();
  await page.goto(`${base}/world-local${arm ? `?${arm}` : ''}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForFunction(() => Array.isArray(globalThis.__worldTurns), null, { timeout: 30000 });
  await page.waitForFunction(
    () => /本地世界已就绪|已恢复本地存档|加载失败|Error/.test(document.body.innerText),
    null,
    { timeout: readyTimeoutMs },
  );
  const text = await page.evaluate(() => document.body.innerText);
  const pageArm = await page.evaluate(() => globalThis.__worldArm ?? null).catch(() => null);
  const step = { label, readyMs: Date.now() - startedAt, restored: /已恢复本地存档/.test(text), text: text.slice(-700), arm: pageArm };
  evidence.steps[label] = { ...(evidence.steps[label] ?? {}), boot: step, console: log.slice(0, 60) };
  save();
  console.log(`[boot ${label}] ${step.readyMs}ms restored=${step.restored}`);
  return { page, log };
}

async function playTurn(page, input, label) {
  // Sync evidence needs one committed, saved point per device, not the whole
  // narrated turn: wait for the offline queue to receive that save, then stop
  // the still-running turn. Narration completeness belongs to G8.
  const queueLength = () => page.evaluate(() => {
    try {
      const raw = localStorage.getItem('jity.progress-sync.queue.v1');
      return raw ? JSON.parse(raw).length : 0;
    } catch { return 0; }
  });
  const before = await queueLength();
  const commandsOf = (text) => Number((/已行动：(\d+)/u.exec(text) ?? [])[1] ?? 0);
  const beforeCommands = commandsOf(await page.evaluate(() => document.body.innerText));
  await page.fill('textarea', input);
  const startedAt = Date.now();
  await page.click('button:has-text("行动")', { timeout: 30000 });
  const deadline = startedAt + turnTimeoutMs;
  let sample = null;
  while (Date.now() < deadline) {
    sample = await page.evaluate(() => {
      let queue = 0;
      try {
        const raw = localStorage.getItem('jity.progress-sync.queue.v1');
        queue = raw ? JSON.parse(raw).length : 0;
      } catch { queue = 0; }
      const body = document.body.innerText;
      const commands = Number((/已行动：(\d+)/u.exec(body) ?? [])[1] ?? 0);
      return {
        queue,
        commands,
        busy: /结算中|正在写正文|正在取消/.test(body),
        doneLine: body.split(String.fromCharCode(10)).find((line) => /^本轮(完成|已交还|已到|停止)/.test(line.trim())) ?? '',
        syncLine: body.split(String.fromCharCode(10)).find((line) => /已同步|已存本地|等待联网|离线|另一台设备|只存本机|仅本机/.test(line)) ?? null,
      };
    });
    // A queued save alone can be the boot no-op replay; the turn's own commit
    // must also have consumed a command.
    if (sample.queue > before && sample.commands > beforeCommands) break;
    if (sample.doneLine && !sample.busy) break;
    await page.waitForTimeout(2000);
  }
  const saved = sample != null && sample.queue > before && (sample.commands ?? 0) > beforeCommands;
  const cancelClicked = await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')].find((node) => /取消本轮|取消|停止/.test(node.textContent ?? ''));
    if (!button) return false;
    button.click();
    return true;
  });
  const quietBy = Date.now() + 60000;
  while (Date.now() < quietBy) {
    const busy = await page.evaluate(() => /结算中|正在写正文|正在取消/.test(document.body.innerText));
    if (!busy) break;
    await page.waitForTimeout(1000);
  }
  const step = {
    input,
    ms: Date.now() - startedAt,
    saved,
    cancelClicked,
    queueAtStop: (await syncStorage(page))?.queue ?? null,
    doneLine: sample?.doneLine ?? null,
    syncLine: sample?.syncLine ?? null,
  };
  evidence.steps[label] = { ...(evidence.steps[label] ?? {}), turn: step };
  save();
  console.log(`[turn ${label}] ${step.ms}ms saved=${saved} cancel=${cancelClicked} sync="${step.syncLine}"`);
  return step;
}

async function waitForNewHead(differentFrom, timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    try {
      last = await head();
      if (last.headSnapshotId && last.headSnapshotId !== differentFrom) return last;
    } catch (error) {
      last = { error: String(error) };
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 1500));
  }
  throw new Error(`head did not change from ${differentFrom}: ${JSON.stringify(last)}`);
}

async function waitForSettledHead(quietMs = 15000, timeoutMs = 180000) {
  const deadline = Date.now() + timeoutMs;
  let lastId = null;
  let quietSince = null;
  while (Date.now() < deadline) {
    const current = await head().catch(() => null);
    const id = current?.headSnapshotId ?? null;
    if (id && id === lastId) {
      if (quietSince == null) quietSince = Date.now();
      if (Date.now() - quietSince >= quietMs) return current;
    } else {
      lastId = id;
      quietSince = null;
    }
    await new Promise((resolveWait) => setTimeout(resolveWait, 1500));
  }
  return head().catch(() => null);
}

const lease = acquireLease({ purpose: `G7 two-device fork ${base}` });
evidence.lease = lease.record;
const browser = await chromium.launch({
  headless: !has('--headed'),
  channel: 'msedge',
  args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'],
});
evidence.harness = { edgeVersion: browser.version(), launchArgs: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'] };

try {
  const health = await apiJson('/health');
  evidence.apiHealth = health;

  const contextA = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const contextB = await browser.newContext({ viewport: { width: 1280, height: 900 } });

  // A1: the shared base is the root snapshot this boot uploads. Two real
  // turns (one per device) then diverge from it.
  {
    const { page } = await boot(contextA, 'A1');
    const base = await waitForNewHead(null, 60000).catch((error) => {
      fail('A1', 'the root upload never reached the server', String(error));
      return null;
    });
    const syncLine = await page.evaluate(() => document.body.innerText).then((text) => text.split(String.fromCharCode(10))
      .find((line) => /已同步|等待联网|离线/.test(line)) ?? null).catch(() => null);
    evidence.steps.A1 = { ...evidence.steps.A1, base, syncLine };
    save();
    await page.close();
  }

  // B1: pull the base, advance offline, keep the queued branch.
  {
    const { page } = await boot(contextB, 'B1');
    const restoredLine = await page.evaluate(() => document.body.innerText.split(String.fromCharCode(10))
      .find((line) => /已行动：\d+/.test(line)) ?? null);
    evidence.steps.B1 = { ...evidence.steps.B1, restoredLine, pulled: (evidence.steps.B1.console ?? []).some((line) => /restored remote progress/.test(line)) };
    if (!evidence.steps.B1.pulled) fail('B1', 'the remote head was not pulled');
    await contextB.setOffline(true);
    const turn = await playTurn(page, inputs[0], 'B1');
    if (!turn.saved) fail('B1', 'no offline save reached the queue', turn);
    if (/本轮停止/.test(turn.doneLine ?? '')) fail('B1', `the offline turn stopped: ${turn.doneLine}`);
    evidence.steps.B1.offlineQueueReported = turn.syncLine;
    evidence.steps.B1.storage = await syncStorage(page);
    save();
    await page.close();
  }

  // A2: reopen, advance offline, reconnect: the online flush uploads branch 1.
  let branch1 = null;
  {
    const { page } = await boot(contextA, 'A2');
    const beforeTurn = await head().catch((error) => ({ error: String(error) }));
    evidence.steps.A2 = { ...evidence.steps.A2, headBeforeTurn: beforeTurn };
    await contextA.setOffline(true);
    const turn = await playTurn(page, inputs[1], 'A2');
    if (!turn.saved) fail('A2', 'no offline save reached the queue', turn);
    if (/本轮停止/.test(turn.doneLine ?? '')) fail('A2', `the offline turn stopped: ${turn.doneLine}`);
    await contextA.setOffline(false);
    branch1 = await waitForNewHead(beforeTurn.headSnapshotId ?? null, 120000).catch((error) => {
      fail('A2', 'the reconnect flush did not upload branch 1', String(error));
      return null;
    });
    branch1 = await waitForSettledHead();
    const onlineText = await page.evaluate(() => document.body.innerText).catch(() => '');
    evidence.steps.A2 = {
      ...evidence.steps.A2,
      branch1Head: branch1,
      storage: await syncStorage(page),
      syncLine: onlineText.split(String.fromCharCode(10)).find((line) => /已同步|等待联网|失败/.test(line)) ?? null,
    };
    save();
    await page.close();
  }

  // B2: the startup flush meets the moved head, the page asks, the player picks.
  let otherBranchId = null;
  {
    await contextB.setOffline(false);
    const { page } = await boot(contextB, 'B2');
    evidence.steps.B2 = { ...evidence.steps.B2, storageAtBoot: await syncStorage(page) };
    otherBranchId = branch1?.headSnapshotId ?? null;
    const conflictAt = Date.now();
    await page.waitForFunction(
      () => /另一台设备也保存了/.test(document.body.innerText),
      null,
      { timeout: 90000 },
    ).catch((error) => fail('B2', 'the fork panel never appeared', String(error)));
    const panelText = await page.evaluate(() => document.body.innerText);
    const panelLine = panelText.split(String.fromCharCode(10)).find((line) => /远端 .*分支/.test(line)) ?? null;
    evidence.steps.B2 = { ...evidence.steps.B2, conflict: { ms: Date.now() - conflictAt, panelLine, otherBranchId } };
    save();
    await page.click(choice === 'keep-remote' ? 'button:has-text("保留远端")' : 'button:has-text("保留本地并分叉")', { timeout: 20000 });
    if (choice === 'keep-remote') {
      await page.waitForLoadState('domcontentloaded').catch(() => undefined);
    } else {
      await page.waitForFunction(
        () => /已保留本地分支并上传/.test(document.body.innerText),
        null,
        { timeout: 120000 },
      ).catch((error) => fail('B2', 'the local-fork choice did not confirm', String(error)));
    }
    const afterText = await page.evaluate(() => document.body.innerText).catch(() => '');
    evidence.steps.B2.afterChoose = {
      message: afterText.split(String.fromCharCode(10)).find((line) => /已保留|冲突选择失败/.test(line)) ?? null,
      panelVisible: /另一台设备也保存了/.test(afterText),
    };
    const graphAfter = await graph().catch((error) => ({ error: String(error) }));
    evidence.steps.B2.graphAfterChoose = graphAfter;
    const headAfter = await head().catch((error) => ({ error: String(error) }));
    evidence.steps.B2.headAfterChoose = headAfter;
    if (otherBranchId) {
      const other = await fetch(`${api}/worlds/${world}/snapshots/${otherBranchId}`)
        .then(async (response) => ({ status: response.status, body: await response.json().catch(() => null) }))
        .catch((error) => ({ error: String(error) }));
      evidence.steps.B2.otherBranchReadable = {
        status: other.status ?? null,
        payloadBytes: other.body?.payload ? JSON.stringify(other.body.payload).length : null,
        snapshotId: other.body?.snapshotId ?? null,
        error: other.error ?? null,
      };
      if (other.status !== 200) fail('B2', 'the other branch is not readable', evidence.steps.B2.otherBranchReadable);
    }
    save();
    // Reload proves the chosen branch is the one this device plays.
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => /本地世界已就绪|已恢复本地存档|加载失败|Error/.test(document.body.innerText),
      null,
      { timeout: readyTimeoutMs },
    ).catch((error) => fail('B2', 'reload after the choice never became ready', String(error)));
    const reloadText = await page.evaluate(() => document.body.innerText).catch(() => '');
    evidence.steps.B2.reload = {
      restored: /已恢复本地存档/.test(reloadText),
      history: reloadText.split(String.fromCharCode(10)).find((line) => /已行动：\d+/.test(line)) ?? null,
      panelVisible: /另一台设备也保存了/.test(reloadText),
    };
    if (!evidence.steps.B2.reload.restored) fail('B2', 'the chosen branch did not reload as the local save');
    save();
    await page.close();
  }
} catch (error) {
  fail('driver', error instanceof Error ? error.message : String(error));
} finally {
  await browser.close().catch(() => undefined);
  lease.release();
}

evidence.finishedAt = new Date().toISOString();
evidence.status = evidence.failures.length ? 'FAILED' : 'PASSED';
save();
console.log(`[two-device] ${evidence.status} failures=${evidence.failures.length} -> ${out}`);
process.exitCode = evidence.failures.length ? 1 : 0;
