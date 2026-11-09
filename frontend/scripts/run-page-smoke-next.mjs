import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { writeFileSync, mkdirSync } from 'node:fs';
const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');
const base = process.env.PAGE_BASE ?? 'http://127.0.0.1:3100';
const input = process.env.PAGE_INPUT ?? '我沿着车道向西回廊快走，贴着墙，注意听枪声。';
const out = process.env.PAGE_OUT ?? '../../artifacts/local-game/page-smoke-next.json';
const browser = await chromium.launch({ headless: true, channel: 'msedge', args: ['--enable-unsafe-webgpu'] });
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
const logs = [];
page.on('console', (m) => { logs.push(`[${m.type()}] ${m.text()}`); if (m.type() === 'error') console.log(`[console:error] ${m.text().slice(0, 300)}`); });
page.on('pageerror', (e) => { logs.push(`[pageerror] ${e.message}`); console.log(`[pageerror] ${e.message}`); });
const started = Date.now();
const result = { ok: false, logs };
try {
  await page.goto(`${base}/world-local`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.body.innerText.includes('本地世界已就绪') || document.body.innerText.includes('已恢复本地存档') || document.body.innerText.includes('等待输入'), null, { timeout: 240_000 });
  result.readyMs = Date.now() - started;
  result.initialText = (await page.locator('main').innerText()).slice(0, 2500);
  await page.locator('textarea').fill(input);
  const turnStart = Date.now();
  await page.getByRole('button', { name: '行动', exact: true }).click();
  await page.waitForFunction(() => document.body.innerText.includes('本轮完成') || document.body.innerText.includes('本轮停止') || document.body.innerText.includes('本轮已交还') || document.body.innerText.includes('加载失败') || document.body.innerText.includes('Error'), null, { timeout: 300_000 });
  result.turnMs = Date.now() - turnStart;
  await page.waitForTimeout(1000);
  result.finalText = (await page.locator('main').innerText()).slice(0, 6000);
  result.screenshot = resolve(out, '../world-local-page.png');
  await page.screenshot({ path: result.screenshot, fullPage: true });
  result.saved = await page.evaluate(() => !!localStorage.getItem('jity.world.local.snapshot.v1'));
  result.ok = result.finalText.includes('本轮完成') || result.finalText.includes('本轮停止') || result.finalText.includes('本轮已交还');
} catch (e) {
  result.error = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
  try { result.finalText = (await page.locator('main').innerText()).slice(0, 6000); } catch {}
  try { await page.screenshot({ path: resolve(out, '../world-local-page-error.png'), fullPage: true }); } catch {}
} finally {
  result.wallMs = Date.now() - started;
  mkdirSync(resolve(out, '..'), { recursive: true });
  writeFileSync(resolve(out), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ ok: result.ok, error: result.error, readyMs: result.readyMs, turnMs: result.turnMs, wallMs: result.wallMs, saved: result.saved }, null, 2));
  await browser.close();
}
