import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { writeFileSync } from 'node:fs';
const require = createRequire(resolve('package.json'));
const { chromium } = require('@playwright/test');
const base = process.env.PAGE_BASE ?? 'http://127.0.0.1:3100';
const browser = await chromium.launch({ headless: true, channel: 'msedge', args: ['--enable-unsafe-webgpu'] });
const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
const logs = [];
page.on('console', (m) => { if (m.type() === 'error') logs.push(m.text()); });
const result = { ok: false, logs };
try {
  await page.goto(`${base}/world-local`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.body.innerText.includes('本地世界已就绪') || document.body.innerText.includes('等待输入'), null, { timeout: 240_000 });
  await page.locator('textarea').fill('我沿着车道向西回廊快走，贴着墙，注意听枪声。');
  await page.getByRole('button', { name: '行动', exact: true }).click();
  await page.waitForFunction(() => document.body.innerText.includes('本轮已交还') || document.body.innerText.includes('本轮完成'), null, { timeout: 300_000 });
  result.first = (await page.locator('main').innerText()).slice(0, 1200);
  const saved1 = await page.evaluate(() => JSON.parse(localStorage.getItem('jity.world.local.snapshot.v1') ?? 'null'));
  result.saved1 = { time: saved1?.transport?.state?.time, place: saved1?.transport?.state?.characters?.lu?.position, points: Object.keys(saved1?.transport?.points ?? {}) };
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.body.innerText.includes('已恢复本地存档') || document.body.innerText.includes('等待输入'), null, { timeout: 240_000 });
  result.restored = (await page.locator('main').innerText()).slice(0, 1200);
  result.saved2 = await page.evaluate(() => JSON.parse(localStorage.getItem('jity.world.local.snapshot.v1') ?? 'null'));
  result.ok = result.restored.includes('已恢复本地存档');
} catch (e) {
  result.error = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
  try { result.final = (await page.locator('main').innerText()).slice(0, 3000); } catch {}
} finally {
  writeFileSync('../../artifacts/local-game/page-restore.json', JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ ok: result.ok, error: result.error, saved1: result.saved1, restoredHead: result.restored?.slice(0, 300) }, null, 2));
  await browser.close();
}
