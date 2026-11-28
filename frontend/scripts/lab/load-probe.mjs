// Staged load probe runner: opens /lab-load at one stage in a fresh headless
// profile and records page-attributed memory at every stage boundary.
// Usage: node load-probe.mjs <stage> <ctx> <out> [durationMs]
import { appendFileSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright';

const stage = process.argv[2] ?? 'page';
const ctx = Number(process.argv[3] ?? 2048);
const out = process.argv[4] ?? `lab-load-${stage}.jsonl`;
const durationMs = Number(process.argv[5] ?? 90000);
const nb = Number(process.argv[6] ?? 0);
writeFileSync(out, '');
const log = (row) => appendFileSync(out, JSON.stringify(row) + '\n');
const started = Date.now();

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await (await browser.newContext({ viewport: { width: 1000, height: 700 } })).newPage();
let lastStage = null;
const url = `http://127.0.0.1:3177/lab-load?stage=${stage}&ctx=${ctx}&cpu=1${nb ? `&nb=${nb}` : ''}`;
await page.goto(url, { waitUntil: 'domcontentloaded' }).catch((error) => log({ at: 0, event: 'goto-failed', error: String(error) }));

while (Date.now() - started < durationMs) {
  const quick = await page.evaluate(() => ({
    stage: window.__labStage ?? null,
    timings: window.__labTimings ?? null,
    error: window.__labError ?? null,
    isolated: Boolean(globalThis.crossOriginIsolated),
    jsHeap: performance.memory ? performance.memory.usedJSHeapSize : null,
  })).catch(() => null);
  if (quick) {
    let detail = null;
    if (quick.stage !== lastStage && quick.isolated) {
      detail = await page.evaluate(async () => performance.measureUserAgentSpecificMemory
        ? await performance.measureUserAgentSpecificMemory().then((r) => r.breakdown.reduce((s, i) => s + (i.bytes ?? 0), 0)).catch(() => null)
        : null).catch(() => null);
    }
    log({ at: Date.now() - started, ...quick, detail });
    lastStage = quick.stage;
    if (quick.stage === 'done' || quick.stage === 'error') break;
  }
  await new Promise((resolve) => setTimeout(resolve, 1000));
}
await browser.close();
