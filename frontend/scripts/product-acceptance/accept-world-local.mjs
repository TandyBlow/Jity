// Independent acceptance driver for the ONE product page: 06's /world-local.
//
// Rules this script follows (PRODUCT-ORGANIZATION.md, tasks/product-09-acceptance.md):
//   - it only drives visible controls (textarea + 行动 button), never injects
//     state, never computes settlement, never selects a candidate;
//   - it records what the page showed and when, not what the engine "should"
//     have produced;
//   - it fails loudly when the integrator has not published a runnable product
//     (no results/product/integration.json, dead URL, missing model);
//   - one JSON file per acceptance session, written after every turn so a crash
//     keeps the earlier turns.
//
// Usage:
//   node scripts/product-acceptance/accept-world-local.mjs \
//     --base http://127.0.0.1:3177 --turns scripts/product-acceptance/turns-10.json \
//     --out ../../../results/product/evidence/09-acceptance-<stamp>.json \
//     [--history 0|1] [--resume] [--keep-storage] [--turn-timeout-ms 330000]
//     [--intent 10-turn|20-turn|smoke] [--fresh]
//
// Cross-origin isolation (COOP/COEP) is a product requirement, not a harness
// convenience: without it the page cannot use multi-threaded wllama. By default
// the driver requests the page exactly as served and records
// `crossOriginIsolated` and the resulting behaviour. `--header-shim` repeats the
// run with the two headers added to the document response only, and the run is
// labelled `shimmed` so it can never be mistaken for a product pass.

import { createRequire } from 'node:module';
import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');
const here = dirname(fileURLToPath(import.meta.url));

function flag(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}
const has = (name) => process.argv.includes(name);

const base = (flag('--base', 'http://127.0.0.1:3177')).replace(/\/$/, '');
const out = resolve(flag('--out', resolve(here, '../../../results/product/evidence/09-acceptance.json')));
const turnsFile = flag('--turns', resolve(here, 'turns-10.json'));
const turnTimeoutMs = Number(flag('--turn-timeout-ms', '330000'));
const readyTimeoutMs = Number(flag('--ready-timeout-ms', '900000'));
const intent = flag('--intent', '10-turn');
const preflightOnly = has('--preflight');
const qualityHandoff = flag('--quality-handoff', null);
const selfTest = has('--harness-selftest');
const keepStorage = has('--keep-storage') || has('--resume');
const fresh = has('--fresh') || !has('--resume');
const settleDelayMs = Number(flag('--settle-delay-ms', '120'));

if (!existsSync(turnsFile)) {
  console.error(`[fail] turns file missing: ${turnsFile}`);
  process.exit(2);
}
const turns = preflightOnly ? [] : JSON.parse(readFileSync(turnsFile, 'utf8'));
if (!preflightOnly && (!Array.isArray(turns) || turns.length === 0)) {
  console.error(`[fail] turns file has no turns: ${turnsFile}`);
  process.exit(2);
}

// The integrator's contract. Without it there is no product to accept.
const integrationPath = resolve(here, '../../../../../results/product/integration.json');
let integration = null;
if (existsSync(integrationPath)) {
  integration = JSON.parse(readFileSync(integrationPath, 'utf8'));
} else if (!selfTest) {
  console.error(`[fail] ${integrationPath} is missing: 06 has not published the product tree/URL/model yet.`);
  process.exit(2);
}
const integrationUrl = integration?.product?.url ?? integration?.url ?? null;
if (integrationUrl && !base.startsWith(integrationUrl.replace(/\/$/, '')) && !base.includes(new URL(integrationUrl).port)) {
  console.error(`[warn] --base ${base} does not match integration.json ${integrationUrl}`);
}

const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const evidence = {
  kind: '09-product-acceptance',
  intent,
  harness: { selfTest },
  status: 'IN_PROGRESS',
  startedAt: new Date().toISOString(),
  base,
  turnsFile,
  integration: integration
    ? {
      head: integration?.product?.head ?? integration?.head ?? null,
      branch: integration?.product?.branch ?? integration?.branch ?? null,
      url: integrationUrl,
      model: integration?.model ?? integration?.assets?.models ?? null,
      startup: integration?.startup ?? integration?.product?.startup ?? null,
      sha256: null,
    }
    : null,
  harness: {
    driver: 'scripts/product-acceptance/accept-world-local.mjs',
    selfTest,
    driverSha256: sha256(readFileSync(new URL(import.meta.url), 'utf8')),
    edgeVersion: null,
    launchArgs: null,
    coopCoepShim: has('--header-shim'),
    saveServiceBlocked: has('--block-api'),
    candidateInjection: false,
    storageReset: fresh,
    note: '--header-shim adds COOP/COEP to the document response; --block-api refuses every /api/** request to test save-service independence',
  },
  productState: { gitHead: null, pageSha256: null, turnEvidenceAvailable: null },
  environment: { userAgent: null, crossOriginIsolated: null, adapter: null, ggmlConsole: [] },
  modelRequests: [],
  readyMs: null,
  readyText: null,
  turns: [],
  failures: [],
  finishes: [],
};

function sha256(text) {
  const { createHash } = require('node:crypto');
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function save() {
  evidence.updatedAt = new Date().toISOString();
  mkdirSync(dirname(out), { recursive: true });
  const tmp = `${out}.tmp-${process.pid}`;
  writeFileSync(tmp, JSON.stringify(evidence, null, 2));
  renameSync(tmp, out);
}

function noteFailure(scope, message, detail = null) {
  evidence.failures.push({ at: new Date().toISOString(), scope, message, detail });
  save();
}

const browser = await chromium.launch({
  headless: !has('--headed'),
  channel: 'msedge',
  args: [
    '--enable-unsafe-webgpu',
    '--force_high_performance_gpu',
    '--ignore-gpu-blocklist',
  ],
});
evidence.harness.launchArgs = ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'];

try {
  evidence.harness.edgeVersion = browser.version();
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  evidence.environment.userAgent = await page.evaluate(() => navigator.userAgent).catch(() => null);

  page.on('console', (message) => {
    const text = message.text();
    if (/ggml_webgpu|adapter_info|nvidia|lovelace|wllama|narration|world-local/i.test(text)) {
      evidence.environment.ggmlConsole.push(`[${message.type()}] ${text}`.slice(0, 600));
    }
  });
  page.on('pageerror', (error) => noteFailure('page', `pageerror: ${error.message}`));
  page.on('response', (response) => {
    const url = response.url();
    if (/\/models\/.*\.gguf/.test(url) || /api\/.*(progress|save|session)/.test(url)) {
      evidence.modelRequests.push({
        url,
        status: response.status(),
        length: response.headers()['content-length'] ?? null,
        type: response.request().resourceType(),
        at: new Date().toISOString(),
      });
    }
  });

  if (has('--block-api')) {
    // "Server only stores progress": with that service down the game must keep
    // playing locally. Every API call is refused and the run is labelled.
    await page.route('**/api/**', (route) => route.abort('failed'));
  }

  if (has('--header-shim')) {
    await page.route('**/world-local*', async (route) => {
      const response = await route.fetch();
      await route.fulfill({
        response,
        headers: {
          ...response.headers(),
          'cross-origin-opener-policy': 'same-origin',
          'cross-origin-embedder-policy': 'require-corp',
        },
      });
    });
  }


  // A fresh player must not inherit anything from an earlier run. The product
  // persists in IndexedDB (writer lease + revision), so clearing localStorage
  // alone leaves a stale lease/revision and the first save conflicts. Clear all
  // origin storage on a same-origin blank document before the product boots.
  if (!keepStorage) {
    await page.goto(`${base}/`, { waitUntil: 'domcontentloaded', timeout: 60000 }).catch(() => undefined);
    evidence.freshReset = await page.evaluate(async () => {
      const result = { localStorageKeys: 0, databases: [], caches: [], errors: [] };
      try { result.localStorageKeys = localStorage.length; localStorage.clear(); } catch (error) { result.errors.push(`localStorage:${String(error)}`); }
      try {
        const databases = (await indexedDB.databases?.()) ?? [];
        for (const db of databases) {
          await new Promise((done) => {
            const request = indexedDB.deleteDatabase(db.name);
            request.onsuccess = request.onerror = request.onblocked = () => done(null);
          });
        }
        result.databases = databases.map((db) => db.name);
      } catch (error) { result.errors.push(`indexedDB:${String(error)}`); }
      try {
        const keys = await caches.keys();
        await Promise.all(keys.map((key) => caches.delete(key)));
        result.caches = keys;
      } catch (error) { result.errors.push(`cache:${String(error)}`); }
      try { await navigator.storage?.getDirectory?.().then((root) => root?.remove?.()).catch(() => undefined); } catch { /* OPFS optional */ }
      return result;
    });
    evidence.freshReset.after = await page.evaluate(async () => ({
      localStorageKeys: localStorage.length,
      databases: ((await indexedDB.databases?.()) ?? []).map((db) => db.name),
    }));
    if (evidence.freshReset.after.databases.length > 0) {
      noteFailure('fresh-reset', 'IndexedDB still has databases after delete', evidence.freshReset.after.databases);
    }
  }

  // WebGPU identity is read from the page itself, before any model load.
  await page.goto(`${base}/world-local`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  evidence.environment.crossOriginIsolated = await page.evaluate(() => globalThis.crossOriginIsolated === true);
  evidence.environment.adapter = await page.evaluate(async () => {
    try {
      const adapter = await navigator.gpu?.requestAdapter?.({ powerPreference: 'high-performance' });
      if (!adapter) return { available: false };
      const info = adapter.info ?? {};
      return {
        available: true,
        vendor: info.vendor ?? null, architecture: info.architecture ?? null,
        device: info.device ?? null, description: info.description ?? null,
        isFallback: adapter.isFallbackAdapter ?? null,
        features: [...(adapter.features ?? [])].slice(0, 20),
      };
    } catch (error) {
      return { available: false, error: String(error) };
    }
  }).catch((error) => ({ available: false, error: String(error) }));
  save();

  evidence.productState = await page.evaluate(() => ({
    gitHead: null,
    pageSha256: null,
    turnEvidenceAvailable: Array.isArray(globalThis.__worldTurns),
  })).catch(() => ({ turnEvidenceAvailable: false }));
  try {
    const rootDir = resolve(here, '../../../../..');
    const declared = integration?.product?.worktree ?? 'worktrees/06-recovery';
    const productWorktree = existsSync(resolve(declared, 'frontend'))
      ? resolve(declared)
      : resolve(rootDir, declared);
    evidence.productState.worktree = productWorktree;
    evidence.productState.gitHead = execSync(`git -C "${productWorktree}" rev-parse HEAD`, { encoding: 'utf8' }).trim();
    evidence.productState.pageSha256 = sha256(readFileSync(resolve(productWorktree, 'frontend/src/app/world-local/page.tsx'), 'utf8'));
  } catch (error) {
    evidence.productState.error = String(error).slice(0, 200);
  }
  const pageResponse = await page.request.get(`${base}/world-local`, { timeout: 30000 }).catch(() => null);
  evidence.pageHttp = pageResponse ? pageResponse.status() : null;
  if (!pageResponse || pageResponse.status() !== 200) {
    noteFailure('page', `GET /world-local returned ${evidence.pageHttp ?? 'no response'}`);
    evidence.status = 'FAILED';
    evidence.finishedAt = new Date().toISOString();
    save();
    console.log(`[fail] page not served: ${evidence.pageHttp}`);
    process.exitCode = 1;
    throw new Error(`page_unavailable:${evidence.pageHttp ?? 'none'}`);
  }
  const textareaVisible = await page.waitForSelector('textarea', { timeout: 60000 }).then(() => true).catch(() => false);
  evidence.textareaVisible = textareaVisible;
  if (!textareaVisible) {
    noteFailure('page', 'the page rendered no textarea: cannot play');
    evidence.status = 'FAILED';
    evidence.finishedAt = new Date().toISOString();
    save();
    throw new Error('textarea_missing');
  }

  const readyStarted = Date.now();
  try {
    await page.waitForFunction(
      () => /本地世界已就绪|已恢复本地存档|加载失败|Error/.test(document.body.innerText),
      null,
      { timeout: readyTimeoutMs },
    );
  } catch (error) {
    noteFailure('ready', `page did not become ready in ${readyTimeoutMs} ms`, String(error).slice(0, 400));
  }
  evidence.readyMs = Date.now() - readyStarted;
  evidence.readyText = (await page.evaluate(() => document.body.innerText)).slice(0, 600);
  const readyText = evidence.readyText ?? '';
  evidence.restored = /已恢复本地存档/.test(readyText);
  if (/加载失败|Error/.test(readyText)) noteFailure('ready', 'page reported a load error', readyText.slice(0, 400));
  const modelGets = evidence.modelRequests.filter((request) => /\/models\/.*\.gguf/.test(request.url));
  evidence.models = {
    requests: modelGets.length,
    ok: modelGets.filter((request) => request.status === 200).length,
    failed: modelGets.filter((request) => request.status !== 200).map((request) => ({ url: request.url, status: request.status })),
  };
  if (modelGets.length === 0) noteFailure('models', 'the page requested no model file: it cannot have loaded a local model');
  const failedModels = evidence.models.failed;
  if (failedModels.length) noteFailure('models', `model request(s) failed: ${failedModels.map((entry) => `${entry.status} ${entry.url}`).join(', ')}`);
  save();

  const entryCount = () => page.evaluate(() => document.querySelectorAll('article').length);
  const snapshot = async () => page.evaluate(() => {
    const read = (label) => {
      const nodes = [...document.querySelectorAll('aside div')];
      const hit = nodes.find((node) => node.textContent?.trim().startsWith(label));
      return hit ? hit.textContent.trim().slice(label.length).replace(/^：/, '').trim() : null;
    };
    const panel = [...document.querySelectorAll('aside')].map((node) => node.innerText).join('\n');
    return {
      sanity: read('精神值'),
      place: read('地点'),
      nearby: panel.split('在附近')[1]?.split('当前任务')[0]?.trim() ?? null,
      tasks: [...document.querySelectorAll('aside li')].map((node) => ({
        goal: node.textContent?.trim() ?? '',
        done: (node.style?.textDecoration ?? '').includes('line-through'),
      })),
      historyCount: /已行动：(\d+)/.exec(panel)?.[1] ?? null,
      storageChars: (localStorage.getItem('jity.world.local.snapshot.v1') ?? '').length,
      header: document.querySelector('main section div div span')?.textContent ?? null,
    };
  });

  if (preflightOnly) {
    evidence.status = 'PREFLIGHT';
    evidence.finishedAt = new Date().toISOString();
    save();
    console.log(`[preflight] ready=${evidence.readyMs}ms isolated=${evidence.environment.crossOriginIsolated} adapter=${JSON.stringify(evidence.environment.adapter)} models=${evidence.modelRequests.filter((r) => /gguf/.test(r.url)).length} -> ${out}`);
  } else
  for (let index = 0; index < turns.length; index += 1) {
    const turn = typeof turns[index] === 'string' ? { id: `t${index + 1}`, input: turns[index] } : turns[index];
    const beforeCount = await entryCount();
    const beforeState = await snapshot();
    const beforeBody = await page.evaluate(() => document.body.innerText);
    const timer = { submittedAt: new Date().toISOString(), submittedAtMs: Date.now() };
    const entry = {
      turn: index + 1,
      id: turn.id ?? `t${index + 1}`,
      input: turn.input,
      purpose: turn.purpose ?? null,
      before: beforeState,
      timings: { waitMs: null, firstStageMs: null, firstTokenMs: null, firstReadableMs: null, doneMs: null },
      stages: [],
      text: null,
      note: null,
      after: null,
      console: [],
      problems: [],
    };
    const consoleStart = evidence.environment.ggmlConsole.length;

    try {
      await page.fill('textarea', turn.input);
      const submitAt = Date.now();
      await page.click('button:has-text("行动")');

      // A mid-settlement refresh must restore the last complete settlement and
      // must not consume the same input twice. This is a product behaviour the
      // driver can only provoke, not fake: it reloads the real page.
      if (turn.cancelAfterMs) {
        await page.waitForTimeout(turn.cancelAfterMs);
        const clicked = await page.evaluate(() => {
          const button = [...document.querySelectorAll('button')].find((node) => /取消本轮|取消|停止/.test(node.textContent ?? ''));
          if (!button) return false;
          button.click();
          return true;
        });
        // Wait for the page to leave the busy state.
        const cancelDeadline = Date.now() + 60000;
        while (Date.now() < cancelDeadline) {
          const busy = await page.evaluate(() => /结算中|正在写正文|正在取消/.test(document.body.innerText));
          if (!busy) break;
          await page.waitForTimeout(200);
        }
        entry.cancelled = {
          clicked,
          ms: Date.now() - submitAt,
          historyAfter: (await snapshot()).historyCount,
          historyBefore: beforeState.historyCount,
          text: (await page.evaluate(() => document.body.innerText)).slice(-800),
          product: await page.evaluate(() => {
            const turns = globalThis.__worldTurns;
            const record = Array.isArray(turns) ? turns[turns.length - 1] : null;
            return record ? { index: record.index, cancelled: record.cancelled ?? false, acceptedMs: record.acceptedMs ?? null, source: record.source ?? null } : null;
          }).catch(() => null),
        };
        entry.timings.doneMs = Date.now() - submitAt;
        if (!entry.cancelled.clicked) entry.problems.push('cancel_control_missing');
        if (entry.cancelled.historyAfter !== entry.cancelled.historyBefore) entry.problems.push('cancel_consumed_input');
        if (entry.cancelled.product && entry.cancelled.product.acceptedMs != null) entry.problems.push('cancel_committed_model_text');
        evidence.turns.push(entry);
        save();
        console.log(`[turn ${entry.turn}] ${entry.id} cancelled clicked=${entry.cancelled.clicked} history=${entry.cancelled.historyBefore}->${entry.cancelled.historyAfter}`);
        continue;
      }

      if (turn.refreshMidSettleMs) {
        await page.waitForTimeout(turn.refreshMidSettleMs);
        const beforeState = await snapshot();
        const reloadAt = Date.now();
        await page.reload({ waitUntil: 'domcontentloaded' });
        await page.waitForFunction(
          () => /本地世界已就绪|已恢复本地存档|加载失败|Error/.test(document.body.innerText),
          null,
          { timeout: readyTimeoutMs },
        );
        const afterText = await page.evaluate(() => document.body.innerText);
        entry.refreshMidSettle = {
          waitedMs: turn.refreshMidSettleMs,
          reloadMs: Date.now() - reloadAt,
          restored: /已恢复本地存档/.test(afterText),
          beforeState,
          afterState: await snapshot(),
          entryCount: await entryCount(),
          text: afterText.slice(-1200),
        };
        entry.timings.doneMs = Date.now() - submitAt;
        entry.problems.push('mid_settle_refresh');
        if (!entry.refreshMidSettle.restored) entry.problems.push('mid_settle_refresh_not_restored');
        const beforeHistory = Number(entry.refreshMidSettle.beforeState?.historyCount ?? NaN);
        const afterHistory = Number(entry.refreshMidSettle.afterState?.historyCount ?? NaN);
        entry.refreshMidSettle.historyDelta = Number.isFinite(beforeHistory) && Number.isFinite(afterHistory)
          ? afterHistory - beforeHistory : null;
        if (entry.refreshMidSettle.historyDelta !== null && entry.refreshMidSettle.historyDelta < 0) {
          entry.problems.push('history_went_backwards_after_refresh');
        }
        evidence.turns.push(entry);
        save();
        console.log(`[turn ${entry.turn}] ${entry.id} mid-settle refresh restored=${entry.refreshMidSettle.restored}`);
        continue;
      }

      // Sample the header stage line + narration text until this turn's entry settles.
      let lastStage = '';
      let firstReadableAt = null;
      const deadline = submitAt + turnTimeoutMs;
      while (Date.now() < deadline) {
        const sample = await page.evaluate((count) => {
          const articles = [...document.querySelectorAll('article')];
          const last = articles.at(-1);
          const stage = [...document.querySelectorAll('span')]
            .map((node) => (node.textContent ?? '').trim())
            .find((label) => /^(结算中|正在写正文|本轮完成|本轮已交还|本轮停止)/.test(label)) ?? '';
          const text = last?.querySelector('div[style*="pre-wrap"]')?.textContent ?? '';
          const bodyText = document.body.innerText;
          return {
            count: articles.length,
            stage,
            text,
            busy: /结算中|正在写正文/.test(bodyText),
            done: /本轮完成|本轮已交还|本轮停止/.test(bodyText),
            doneText: (bodyText.split(String.fromCharCode(10)).find((line) => /本轮完成|本轮已交还|本轮停止/.test(line)) ?? ''),
            failed: /Error|加载失败/.test(bodyText),
          };
        }, beforeCount);
        if (sample.count <= beforeCount && !sample.failed) {
          await page.waitForTimeout(settleDelayMs);
          continue;
        }
        if (sample.stage && sample.stage !== lastStage) {
          lastStage = sample.stage;
          entry.stages.push({ atMs: Date.now() - submitAt, label: sample.stage });
          if (entry.timings.firstStageMs === null) entry.timings.firstStageMs = Date.now() - submitAt;
        }
        if (sample.text && firstReadableAt === null) {
          firstReadableAt = Date.now() - submitAt;
          entry.timings.firstReadableMs = firstReadableAt;
        }
        if (!sample.busy && sample.count > beforeCount && (sample.text || sample.done)) break;
        // A submit can be refused synchronously (e.g. progress_conflict): the
        // page shows 本轮停止 and no narration will ever stream. Waiting out the
        // full turn budget would misreport a 300 s timeout.
        if (sample.done && /本轮停止/.test(sample.doneText ?? '')) break;
        if (sample.failed) {
          entry.problems.push('page_error');
          break;
        }
        await page.waitForTimeout(settleDelayMs);
      }
      entry.timings.waitMs = Date.now() - submitAt;
      entry.doneText = await page.evaluate(() => (document.body.innerText.split(String.fromCharCode(10)).find((line) => /本轮完成|本轮已交还|本轮停止/.test(line)) ?? '')).catch(() => '');
      if (/本轮停止/.test(entry.doneText)) {
        entry.refused = { reason: entry.doneText.replace(/^本轮停止[:：]?/, '').trim(), ms: entry.timings.waitMs };
        entry.problems.push(`submit_refused:${entry.refused.reason || 'unknown'}`);
      }
      if (entry.timings.waitMs >= turnTimeoutMs) entry.problems.push('turn_timeout');

      const afterInfo = await page.evaluate((count) => {
        const articles = [...document.querySelectorAll('article')];
        const last = articles.at(-1);
        const text = last?.querySelector('div[style*="pre-wrap"]')?.textContent ?? '';
        const input = last?.querySelector('div')?.textContent ?? '';
        const noteNode = [...(last?.querySelectorAll('div') ?? [])].find((node) => node.textContent?.startsWith('正文已按已结算事实修正'));
        return {
          count: articles.length,
          text,
          input,
          note: noteNode ? noteNode.textContent : null,
          body: document.body.innerText.slice(-4000),
          message: /本轮完成|本轮已交还|本轮停止|Error|加载失败/.exec(document.body.innerText)?.[0] ?? null,
        };
      }, beforeCount);
      entry.text = afterInfo.text || null;
      entry.inputLine = afterInfo.input || null;
      entry.note = afterInfo.note;
      entry.message = afterInfo.message;
      entry.timings.doneMs = Date.now() - timer.submittedAtMs;
      entry.after = await snapshot();
      const loadCounts = (entry.product?.engines ?? []).map((engine) => `${engine.label}:${engine.loadCount}/${engine.workersCreated}/${engine.generations}`);
      entry.engineCounters = loadCounts;
      entry.warmTurn = entry.turn > 1;
      // The page already exposes its narration debug object; the driver only
      // reads it. Absence is recorded, never filled in by the harness.
      entry.product = await page.evaluate(() => {
        const turns = globalThis.__worldTurns;
        if (!Array.isArray(turns) || turns.length === 0) return null;
        const record = turns[turns.length - 1];
        return {
          index: record.index ?? null, input: record.input ?? null,
          acceptedMs: record.acceptedMs ?? null, draftMs: record.draftMs ?? null, programMs: record.programMs ?? null,
          cancelled: record.cancelled ?? false, source: record.source ?? null, modelId: record.modelId ?? null,
          engines: Array.isArray(record.engines) ? record.engines : null,
          submission: record.submission ? {
            inputText: record.submission.inputText ?? null,
            startedAtMs: record.submission.startedAtMs ?? null,
            endedAtMs: record.submission.endedAtMs ?? null,
            resultsCalls: record.submission.resultsCalls ?? null,
            updatesCalls: record.submission.updatesCalls ?? null,
            continuationCalls: record.submission.continuationCalls ?? null,
            continuationDecision: record.submission.continuationDecision ?? null,
            stops: record.submission.stops ?? null,
            calls: (record.submission.calls ?? []).map((call) => ({
              task: call.task, key: call.key, stage: call.stage ?? null, ms: call.ms ?? null,
              promptChars: call.promptChars ?? null, fallback: Boolean(call.fallback), error: call.error ?? null,
              calls: call.calls ?? null, stages: call.stages ?? null, coverage: call.coverage ?? null,
              stageMs: call.stageMs ?? null,
              raw: typeof call.raw === 'string' ? call.raw.slice(0, 4000) : (call.raw ?? null),
              attempts: Array.isArray(call.attempts) ? call.attempts.map((attempt) => ({
                ms: attempt?.ms ?? null, error: attempt?.error ?? null, finishReason: attempt?.finishReason ?? null,
                raw: typeof attempt?.raw === 'string' ? attempt.raw.slice(0, 4000) : (attempt?.raw ?? null),
              })) : (call.attempts ?? null),
            })),
          } : null,
        };
      }).catch(() => null);
      entry.submission = entry.product?.submission ?? null;
      entry.narrationDebug = await page.evaluate(() => {
        const debug = globalThis.__worldDebug;
        if (!debug || typeof debug !== 'object') return null;
        return {
          violations: Array.isArray(debug.violations) ? debug.violations.slice(0, 20) : null,
          attempts: Array.isArray(debug.attempts) ? debug.attempts.map((attempt) => (Array.isArray(attempt) ? attempt.length : attempt)) : null,
          rawChars: typeof debug.raw === 'string' ? debug.raw.length : null,
          cleanedChars: typeof debug.cleaned === 'string' ? debug.cleaned.length : null,
          prunedChars: typeof debug.pruned === 'string' ? debug.pruned.length : null,
          supportedChars: typeof debug.supported === 'string' ? debug.supported.length : null,
        };
      }).catch(() => null);
      entry.console = evidence.environment.ggmlConsole.slice(consoleStart);
      entry.shownChars = (entry.text ?? '').length;
      if (!entry.text) entry.problems.push('empty_text');
      if (afterInfo.count <= beforeCount) entry.problems.push('no_entry_added');
      if (/Error|加载失败/.test(afterInfo.body.slice(-1200))) entry.problems.push('error_visible');
      entry.textSource = entry.product?.source ?? (entry.note ? 'program' : (entry.text ? 'unknown_or_draft' : 'none'));
      entry.modelId = entry.product?.modelId ?? null;
      if (entry.note) entry.problems.push('program_fallback_labelled');
      if (entry.textSource === 'program') entry.problems.push('program_text_not_model');
      const prose = entry.text ?? '';
      if (/^(…+|。|，|、|\s)$/.test(prose.trim())) entry.problems.push('placeholder_only_text');
      if (/(结算|回退|fallback|本拍|本组|模型未|无法确认|未产生)/.test(prose)) entry.problems.push('internal_note_in_prose');
      if (/^(上一|刚才|此前)/.test(prose.trim()) && /(结算|修正|回退)/.test(prose)) entry.problems.push('internal_note_in_prose');
      if (entry.shownChars > 0 && entry.shownChars < 30) entry.problems.push('very_short_text');
      if (entry.text && turn.input && entry.text.includes(turn.input)) entry.problems.push('echoes_player_input');
      const beforeHistory = Number(entry.before?.historyCount ?? NaN);
      const afterHistory = Number(entry.after?.historyCount ?? NaN);
      if (Number.isFinite(beforeHistory) && Number.isFinite(afterHistory)) {
        entry.historyDelta = afterHistory - beforeHistory;
        if (entry.text && entry.historyDelta !== 1) entry.problems.push(`history_delta_${entry.historyDelta}`);
      }
      const stageText = entry.stages.map((stage) => stage.label).join('|');
      entry.stageSequence = stageText;
      if (!/正在写正文/.test(stageText)) entry.problems.push('no_streaming_stage_observed');
      if (entry.timings.firstReadableMs === null) entry.problems.push('no_readable_text_observed');
      if (entry.timings.doneMs > 300000) entry.problems.push('over_300s');
      const product = entry.product;
      if (!product) entry.problems.push('no_product_turn_evidence');
      else {
        if (product.source !== 'model') entry.problems.push(`source_${product.source ?? 'unknown'}`);
        if (product.cancelled) entry.problems.push('cancelled');
        if (product.acceptedMs == null) entry.problems.push('no_accepted_model_text');
        if (product.acceptedMs != null && product.acceptedMs > 60000) entry.problems.push('accepted_over_60s');
        if (product.draftMs != null && product.acceptedMs == null) entry.problems.push('draft_only_not_accepted');
        if (product.programMs != null && product.acceptedMs == null) entry.problems.push('program_only_not_model_text');
      }
      const beforeBodyLength = beforeBody.length;
      entry.bodyGrowth = afterInfo.body.length - beforeBodyLength;
    } catch (error) {
      entry.problems.push(`driver_error:${String(error).slice(0, 200)}`);
      noteFailure(entry.id, String(error).slice(0, 400));
    }

    evidence.turns.push(entry);
    save();
    if (turn.refreshAfter) {
      const before = await snapshot();
      const startedReload = Date.now();
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.waitForFunction(
        () => /本地世界已就绪|已恢复本地存档|加载失败|Error/.test(document.body.innerText),
        null,
        { timeout: readyTimeoutMs },
      );
      const after = await snapshot();
      const restoredText = await page.evaluate(() => document.body.innerText);
      entry.refreshAfter = {
        ms: Date.now() - startedReload,
        restored: /已恢复本地存档/.test(restoredText),
        entriesAfter: await entryCount(),
        beforeHistory: before.historyCount, afterHistory: after.historyCount,
        samePlace: before.place === after.place, sameSanity: before.sanity === after.sanity,
      };
      if (!entry.refreshAfter.restored) entry.problems.push('refresh_after_not_restored');
      if (entry.refreshAfter.beforeHistory !== entry.refreshAfter.afterHistory) entry.problems.push('history_changed_across_refresh');
      if (!entry.refreshAfter.samePlace || !entry.refreshAfter.sameSanity) entry.problems.push('state_changed_across_refresh');
      save();
      console.log(`[refresh-after ${entry.id}] restored=${entry.refreshAfter.restored} history ${entry.refreshAfter.beforeHistory}->${entry.refreshAfter.afterHistory}`);
    }
    console.log(`[turn ${entry.turn}] ${entry.id} chars=${entry.shownChars ?? 0} wait=${entry.timings.doneMs ?? '?'}ms firstReadable=${entry.timings.firstReadableMs ?? '?'}ms problems=${entry.problems.join(',') || 'none'}`);
    if (entry.problems.includes('page_error') || entry.problems.includes('turn_timeout')) break;
  }

  if (!preflightOnly) {
  // Refresh/restore is a product behaviour, not a driver convenience: reload the
  // page and check the entries survive from the browser's own save.
  const entriesBeforeReload = await entryCount();
  const stateBeforeReload = await snapshot();
  await page.reload({ waitUntil: 'domcontentloaded' });
  const reloadStarted = Date.now();
  try {
    await page.waitForFunction(
      () => /本地世界已就绪|已恢复本地存档|加载失败|Error/.test(document.body.innerText),
      null,
      { timeout: readyTimeoutMs },
    );
  } catch (error) {
    noteFailure('reload', `page did not become ready after reload in ${readyTimeoutMs} ms`, String(error).slice(0, 300));
  }
  const entriesAfterReload = await entryCount();
  const stateAfterReload = await snapshot();
  const restoredText2 = await page.evaluate(() => document.body.innerText);
  const beforeEntries = await page.evaluate(() => window.__acceptEntryInputs ?? null).catch(() => null);
  // Entry identity, not just a count: a page can report 'restored' while the
  // visible history is empty.
  const entriesContract = await page.evaluate(() => {
    const entries = [...document.querySelectorAll('article')].map((node) => node.querySelector('div')?.textContent ?? '');
    return { count: entries.length, inputs: entries.map((line) => line.replace(/^你：/, '').split(' · ')[0]) };
  });
  const stateRestored = stateBeforeReload.place === stateAfterReload.place
    && stateBeforeReload.sanity === stateAfterReload.sanity;
  const historyRestored = stateBeforeReload.historyCount === stateAfterReload.historyCount;
  const entriesRestored = entriesAfterReload >= entriesBeforeReload
    && entriesContract.count >= entriesBeforeReload;
  evidence.refreshRestore = {
    ms: Date.now() - reloadStarted,
    pageSaysRestored: /已恢复本地存档/.test(restoredText2),
    entriesBefore: entriesBeforeReload,
    entriesAfter: entriesAfterReload,
    entriesNow: entriesContract,
    stateBefore: stateBeforeReload,
    stateAfter: stateAfterReload,
    stateRestored,
    historyRestored,
    inputConsumptionRestored: historyRestored,
    entriesRestored,
    // The product may only claim recovery when everything a player relies on
    // is actually back. A matching place/sanity is not enough.
    overallRestored: stateRestored && historyRestored && entriesRestored,
  };
  if (!entriesRestored) noteFailure('reload', `entries were not restored after refresh: ${entriesBeforeReload} -> ${entriesAfterReload}`, evidence.refreshRestore);
  if (!stateRestored) noteFailure('reload', 'state changed across refresh/restore', evidence.refreshRestore);
  if (!historyRestored) noteFailure('reload', 'history count changed across refresh/restore', evidence.refreshRestore);
  if (!evidence.refreshRestore.overallRestored) evidence.refreshRestore.failure = 'overall_not_restored';
  save();

  // Contract checks that do not need inference: cancel control and save service.
  evidence.controls = {
    cancelButton: await page.evaluate(() => [...document.querySelectorAll('button')].some((node) => /取消|停止|中断/.test(node.textContent ?? ''))),
    resetButton: await page.evaluate(() => [...document.querySelectorAll('button')].some((node) => /重新开始/.test(node.textContent ?? ''))),
    historyVisible: await page.evaluate(() => /已行动：\d+/.test(document.body.innerText)),
  };
  evidence.network = {
    persistenceRequests: evidence.modelRequests.filter((request) => /api\//.test(request.url)),
    modelRequests: evidence.modelRequests.filter((request) => /\/models\/.*\.gguf/.test(request.url)),
  };
  if (!evidence.controls.cancelButton) noteFailure('controls', 'no visible cancel/stop control in the product page');

  }
  evidence.status = selfTest ? (evidence.failures.some((failure) => /models/.test(failure.scope)) && evidence.turns.every((turn) => turn.text) ? 'SELFTEST' : (evidence.failures.length && !selfTest ? 'FAILED' : 'SELFTEST')) : (evidence.failures.length ? 'FAILED' : (preflightOnly ? 'PREFLIGHT' : 'COMPLETED'));
  evidence.finishedAt = new Date().toISOString();
  if (qualityHandoff) {
    // What 01 needs to review sentence by sentence: the input, the displayed
    // prose, any fallback label and the page-visible state around the turn.
    // Nothing here is a verdict; 09 does not grade prose.
    const handoff = {
      kind: '09-quality-handoff',
      at: evidence.finishedAt,
      reviewer: '01-input (independent)',
      recordedBy: '09-ui',
      product: evidence.integration,
      driver: 'scripts/product-acceptance/accept-world-local.mjs',
      pageConditions: { crossOriginIsolated: evidence.environment.crossOriginIsolated, adapter: evidence.environment.adapter },
      turns: evidence.turns.map((turn) => ({
        id: turn.id, input: turn.input, purpose: turn.purpose,
        text: turn.text, fallbackNote: turn.note, message: turn.message,
        before: turn.before, after: turn.after, historyDelta: turn.historyDelta ?? null,
        timings: turn.timings, problems: turn.problems,
        narrationDebug: turn.narrationDebug ?? null,
      })),
      note: '01 reviews fact fidelity/prose across turns; 09 records playability, provenance, timing and fallbacks. Neither substitutes for human/user review.',
    };
    const target = resolve(qualityHandoff);
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, JSON.stringify(handoff, null, 2));
    evidence.qualityHandoff = target;
    console.log(`[handoff] ${target}`);
  }
  evidence.submissions = evidence.turns.map((turn) => turn.submission).filter(Boolean);
  evidence.summary = {
    turns: evidence.turns.length,
    turnsWithText: evidence.turns.filter((turn) => turn.text).length,
    turnsWithFallbackNote: evidence.turns.filter((turn) => turn.note).length,
    turnsOver60sFirstReadable: evidence.turns.filter((turn) => (turn.timings.firstReadableMs ?? 0) > 60000).length,
    turnsOver300s: evidence.turns.filter((turn) => (turn.timings.doneMs ?? 0) > 300000).length,
    turnsWithEmptyText: evidence.turns.filter((turn) => !turn.text).length,
    turnsEchoingInput: evidence.turns.filter((turn) => turn.problems.includes('echoes_player_input')).length,
    turnsWithSubmissionLedger: evidence.submissions.length,
    submissionCalls: evidence.submissions.map((submission) => ({
      turn: evidence.turns.find((turn) => turn.submission === submission)?.id ?? null,
      results: submission.resultsCalls, updates: submission.updatesCalls,
      continuation: submission.continuationCalls, stops: submission.stops,
    })),
    distinctPlaces: [...new Set(evidence.turns.map((turn) => turn.after?.place).filter(Boolean))],
    distinctHistoryCounts: [...new Set(evidence.turns.map((turn) => turn.after?.historyCount).filter(Boolean))],
  };
  save();
  console.log(`[done] status=${evidence.status} turns=${evidence.turns.length} failures=${evidence.failures.length} -> ${out}`);
  if (has('--print')) console.log(JSON.stringify(evidence.summary, null, 2));
} catch (error) {
  noteFailure('driver', String(error).slice(0, 800));
  evidence.status = 'FAILED';
  evidence.finishedAt = new Date().toISOString();
  save();
  console.error('[driver-error]', error);
  process.exitCode = 1;
} finally {
  await browser.close();
}
