// Five consecutive player actions in the real page, headless Edge + WebGPU.
// Records per-turn wall time, the prose actually shown, and whether the
// localStorage snapshot survives a reload. Writes one JSON artifact.
import { createRequire } from 'node:module';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');

const base = process.env.PAGE_BASE ?? 'http://127.0.0.1:3100';
const out = process.env.PAGE_OUT ?? '../../artifacts/local-game/page-play.json';
const inputs = (process.env.PAGE_INPUTS ?? [
  '我沿着车道向西回廊快走，贴着墙，注意听枪声',
  '我蹲下来问林亦舟伤得怎么样，需不需要帮忙',
  '我检查他放在地上的演习枪，确认保险是关着的',
  '我把护目镜戴好，问他红方现在在哪个方向',
  '我扶他站起来，一起往钟楼西门走',
].join('|')).split('|');

const browser = await chromium.launch({ headless: true, channel: 'msedge', args: ['--enable-unsafe-webgpu'] });
const page = await browser.newPage();
const logs = [];
page.on('console', (msg) => logs.push(`[${msg.type()}] ${msg.text()}`.slice(0, 400)));
page.on('requestfailed', (request) => logs.push(`[requestfailed] ${request.url()} ${request.failure()?.errorText ?? ''}`));
page.on('response', (response) => { if (response.status() >= 400) logs.push(`[http ${response.status()}] ${response.url()}`); });

const started = Date.now();
await page.goto(`${base}/world-local`, { waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => /本地世界已就绪|已恢复本地存档/.test(document.body.innerText), null, { timeout: 240_000 });
const readyMs = Date.now() - started;
const turns = [];
let prose = await page.evaluate(() => document.querySelector('main')?.innerText ?? '');

for (const input of inputs) {
  const before = await page.evaluate(() => document.body.innerText);
  const t0 = Date.now();
  await page.fill('textarea', input);
  await page.click('button:has-text("行动")');
  await page.waitForFunction((previous) => {
    const text = document.body.innerText;
    return text !== previous && /本轮已交还|本轮完成|本轮停止|加载失败|Error/.test(text) && !/结算中…/.test(text.split('本轮')[0] ?? '');
  }, before, { timeout: 300_000 });
  const turnMs = Date.now() - t0;
  const now = await page.evaluate(() => document.body.innerText);
  const body = now.split('Ctrl/⌘ + Enter 提交')[0];
  const paragraph = body.split('行动').pop()?.trim() ?? '';
  turns.push({ input, turnMs, text: paragraph.slice(-900), warning: /叙事事实校验未通过/.test(now) ? now.split('叙事事实校验未通过：')[1]?.split('\n')[0] : null });
  prose = now;
}

const savedBefore = await page.evaluate(() => localStorage.getItem('jity.world.local.snapshot.v1'));
await page.reload({ waitUntil: 'domcontentloaded' });
await page.waitForFunction(() => /本地世界已就绪|已恢复本地存档/.test(document.body.innerText), null, { timeout: 240_000 });
const afterReload = await page.evaluate(() => document.body.innerText);
const savedAfter = await page.evaluate(() => localStorage.getItem('jity.world.local.snapshot.v1'));

mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify({
  ok: turns.length === inputs.length && Boolean(savedBefore),
  readyMs,
  wallMs: Date.now() - started,
  turns,
  restored: /已恢复本地存档/.test(afterReload),
  snapshotBytes: savedAfter?.length ?? 0,
  snapshotStable: savedBefore === savedAfter,
  finalText: afterReload.slice(0, 1200),
  logs: logs.slice(-40),
}, null, 2));
console.log(JSON.stringify({ ok: turns.length === inputs.length, readyMs, turns: turns.map((t) => ({ turnMs: t.turnMs, warning: t.warning, chars: t.text.length })), restored: /已恢复本地存档/.test(afterReload), snapshotBytes: savedAfter?.length ?? 0 }, null, 1));
await browser.close();
