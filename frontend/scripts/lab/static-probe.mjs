// Static-server probe: visit a plain HTML page (no Next) and wait for stages.
import { chromium } from 'playwright';
const url = process.argv[2];
const seconds = Number(process.argv[3] ?? 120);
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await (await browser.newContext()).newPage();
await page.goto(url, { waitUntil: 'domcontentloaded' }).catch(() => undefined);
const started = Date.now();
while (Date.now() - started < seconds * 1000) {
  const stage = await page.evaluate(() => window.__labStage ?? null).catch(() => null);
  if (stage === 'done' || stage === 'error') break;
  await new Promise((r) => setTimeout(r, 1000));
}
const result = await page.evaluate(() => ({ stage: window.__labStage, timings: window.__labTimings, error: window.__labError })).catch(() => null);
console.log(JSON.stringify(result));
await browser.close();
