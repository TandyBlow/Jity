// One real product turn through the ACTUAL world-local page.
//
// The page is main-owned and unmodified: this script only uses the documented
// internal override (`globalThis.__jityNarrationCandidate`) to select the
// shipped candidate, so the same page — no experimental site — produces the
// evidence. Nothing is written back to the product tree.
//
// It records: model load time, the player action, wall time, the prose the page
// shows, the console line that reports a candidate fallback (if any), the
// narration debug object (present only when the in-model writer ran), the
// localStorage snapshot length, and whether the page reported an error.
//
// Local inference is an exclusive resource; acquire the lease first.
//
//   node scripts/candidate-shipping/run-product-turn.mjs \
//     --base http://127.0.0.1:3177 [--candidate trained] [--input "..."] \
//     [--out ../../../results/06-recovery/product-turn.json]
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');
const here = fileURLToPath(new URL('.', import.meta.url));
const flag = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};

const base = flag('--base', 'http://127.0.0.1:3177');
const candidate = flag('--candidate', 'trained');
const input = flag('--input', '我沿着服务巷的低墙走到器材棚门口，先看领用台上有谁。');
const out = resolve(flag('--out', resolve(here, '../../../results/06-recovery/product-turn.json')));
const timeoutMs = Number(flag('--timeout-ms', '1_200_000'));

const evidence = {
  status: 'IN_PROGRESS',
  recordedAt: new Date().toISOString(),
  base, candidate, input,
  console: [], requests: [],
};

const browser = await chromium.launch({ headless: true, channel: 'msedge', args: ['--enable-unsafe-webgpu'] });
try {
  const page = await browser.newPage();
  page.on('console', (message) => {
    const text = message.text();
    if (/world-local|narration|wllama|gpu/i.test(text)) evidence.console.push(`[${message.type()}] ${text}`.slice(0, 500));
  });
  page.on('response', (response) => {
    if (/\/models\//.test(response.url())) evidence.requests.push({ url: response.url(), status: response.status() });
  });
  // The /world-local route has no COOP/COEP headers in next.config; cross-origin
  // isolation is required for the multi-threaded wllama runtime. Add the two
  // headers to the document response only (same-origin subresources are fine).
  await page.route('**/world-local', async (route) => {
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
  // Internal selection only; the page never shows it.
  await page.addInitScript((value) => {
    globalThis.__jityNarrationCandidate = value;
  }, candidate);

  const started = Date.now();
  await page.goto(`${base}/world-local`, { waitUntil: 'domcontentloaded' });
  evidence.crossOriginIsolated = await page.evaluate(() => globalThis.crossOriginIsolated === true);
  await page.waitForFunction(() => /本地世界已就绪|已恢复本地存档/.test(document.body.innerText), null, { timeout: 900_000 });
  evidence.readyMs = Date.now() - started;
  evidence.readyText = (await page.evaluate(() => document.body.innerText)).slice(0, 400);
  const before = await page.evaluate(() => document.body.innerText);
  const submitStarted = Date.now();
  await page.fill('textarea', input);
  await page.click('button:has-text("行动")');
  await page.waitForFunction(
    (previous) => {
      const text = document.body.innerText;
      return text !== previous && /本轮完成|本轮已交还|本轮停止|Error|加载失败/.test(text) && !/结算中…/.test(text);
    },
    before,
    { timeout: timeoutMs },
  );
  evidence.turnMs = Date.now() - submitStarted;
  const after = await page.evaluate(() => document.body.innerText);
  const body = after.split('Ctrl/⌘ + Enter 提交')[0];
  const entry = body.split(/行动[\s\S]*?\n/).pop() ?? body;
  evidence.shownText = entry.trim().slice(-1600);
  evidence.note = /正文已按已结算事实修正|叙事/.exec(after)?.[0] ?? null;
  evidence.debugPresent = await page.evaluate(() => Boolean(globalThis.__worldDebug));
  evidence.snapshotBytes = await page.evaluate(() => (localStorage.getItem('jity.world.local.snapshot.v1') ?? '').length);
  evidence.sidePanel = body.split('本地存档')[1]?.slice(0, 200) ?? null;
  evidence.status = /Error/.test(after) ? 'FAILED_PAGE' : 'COMPLETED';
  if (/本轮已交还/.test(after)) evidence.stopReason = 'handback';
} catch (error) {
  evidence.status = 'FAILED';
  evidence.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
  process.exitCode = 1;
} finally {
  await browser.close();
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, `${JSON.stringify(evidence, null, 2)}\n`);
  console.log(JSON.stringify({
    status: evidence.status, readyMs: evidence.readyMs, turnMs: evidence.turnMs,
    crossOriginIsolated: evidence.crossOriginIsolated, debugPresent: evidence.debugPresent,
    note: evidence.note, console: evidence.console.slice(-12),
    shownText: evidence.shownText?.slice(0, 300), error: evidence.error, out,
  }, null, 2));
}
