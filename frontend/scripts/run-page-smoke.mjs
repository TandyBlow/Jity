/* Headless acceptance probe for the real /world-local page. */
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';
import { writeFileSync, mkdirSync } from 'node:fs';
const require = createRequire(resolve('package.json'));
const { createServer } = await import(pathToFileURL(require.resolve('vite')).href);
const { chromium } = require('@playwright/test');
const args = process.argv.slice(2);
const arg = (n, f) => { const i = args.indexOf(n); return i >= 0 ? args[i+1] : f; };
const input = arg('--input', '我沿着车道向西回廊快走，贴着墙，注意听枪声。');
const out = arg('--out', '../../artifacts/local-game/page-smoke.json');

const server = await createServer({ root: process.cwd(), configFile: false, logLevel: 'warn', server: { host: '127.0.0.1', port: 0 } });
await server.listen();
const origin = `http://127.0.0.1:${server.config.server.port}`;
const browser = await chromium.launch({ headless: true, channel: 'msedge', args: ['--enable-unsafe-webgpu'] });
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
const logs = [];
page.on('console', (m) => { logs.push(`[${m.type()}] ${m.text()}`); if (m.type() === 'error') console.log(`[console:error] ${m.text().slice(0, 400)}`); });
page.on('pageerror', (e) => { logs.push(`[pageerror] ${e.message}`); console.log(`[pageerror] ${e.message}`); });
const started = Date.now();
const result = { ok: false, logs };
try {
  await page.goto(`${origin}/world-local`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.body.innerText.includes('本地世界已就绪') || document.body.innerText.includes('已恢复本地存档') || document.body.innerText.includes('等待输入'), null, { timeout: 240_000 });
  result.readyMs = Date.now() - started;
  result.initialText = (await page.locator('main').innerText()).slice(0, 2000);
  const before = await page.locator('textarea').inputValue();
  await page.locator('textarea').fill(input);
  const turnStart = Date.now();
  await page.getByRole('button', { name: '行动', exact: true }).click();
  await page.waitForFunction(() => document.body.innerText.includes('本轮完成') || document.body.innerText.includes('本轮停止') || document.body.innerText.includes('加载失败') || document.body.innerText.includes('Error'), null, { timeout: 300_000 });
  result.turnMs = Date.now() - turnStart;
  await page.waitForTimeout(1500);
  result.finalText = (await page.locator('main').innerText()).slice(0, 5000);
  result.screenshot = resolve(out, '../world-local-page.png');
  await page.screenshot({ path: result.screenshot, fullPage: true });
  result.saved = await page.evaluate(() => !!localStorage.getItem('jity.world.local.snapshot.v1'));
  result.ok = result.finalText.includes('本轮完成') || result.finalText.includes('本轮停止');
} catch (e) {
  result.error = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
  try { result.finalText = (await page.locator('main').innerText()).slice(0, 5000); } catch {}
  try { await page.screenshot({ path: resolve(out, '../world-local-page-error.png'), fullPage: true }); } catch {}
} finally {
  result.wallMs = Date.now() - started;
  mkdirSync(resolve(out, '..'), { recursive: true });
  writeFileSync(resolve(out), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ ok: result.ok, error: result.error, readyMs: result.readyMs, turnMs: result.turnMs, wallMs: result.wallMs, saved: result.saved }, null, 2));
  await browser.close();
  await server.close();
}
