// Memory baseline v1: open the product page, sample phases and JS heap from
// inside, while an external process sampler (PowerShell) records Edge RSS.
import { appendFileSync, writeFileSync } from 'node:fs';
import { chromium } from 'playwright';

const url = process.argv[2] ?? 'http://127.0.0.1:3177/world-local';
const label = process.argv[3] ?? 'default';
const out = process.argv[4] ?? `baseline-${label}.jsonl`;
const durationMs = Number(process.argv[5] ?? 180000);
const turnText = process.argv[6] ?? null;
writeFileSync(out, '');
const log = (row) => appendFileSync(out, JSON.stringify(row) + '\n');

const headless = process.env.HEADLESS !== '0';
const browser = await chromium.launch({ channel: 'msedge', headless });
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const started = Date.now();
await page.goto(url, { waitUntil: 'domcontentloaded' });
let submitted = false;
while (Date.now() - started < durationMs) {
  const expensive = !globalThis.__lastDetail || Date.now() - globalThis.__lastDetail > 60000;
  if (expensive) globalThis.__lastDetail = Date.now();
  const sample = await page.evaluate(async (withDetail) => {
    const memory = performance.memory;
    const isolated = Boolean(globalThis.crossOriginIsolated);
    let detailed = null;
    if (withDetail && isolated && typeof performance.measureUserAgentSpecificMemory === 'function') {
      try {
        const result = await performance.measureUserAgentSpecificMemory();
        detailed = result.breakdown.reduce((sum, item) => sum + (item.bytes ?? 0), 0);
      } catch { detailed = null; }
    }
    return {
      phase: window.__worldPhase ?? null,
      jsHeap: memory ? memory.usedJSHeapSize : null,
      jsHeapTotal: memory ? memory.totalJSHeapSize : null,
      isolated,
      visibility: document.visibilityState,
      wasmEstimate: detailed,
    };
  }, expensive).catch(() => null);
  if (turnText && !submitted && sample && sample.phase === 'ready') {
    submitted = true;
    await page.fill('textarea', turnText).catch(() => undefined);
    await page.waitForFunction(() => {
      const button = [...document.querySelectorAll('button')].find((b) => b.textContent?.trim() === '行动');
      return Boolean(button && !button.disabled);
    }, { timeout: 20000 }).catch(() => undefined);
    await page.click('button:has-text("行动")', { timeout: 10000 }).catch(() => undefined);
    const accepted = await page.waitForFunction(() => window.__worldPhase === 'thinking' || window.__worldPhase === 'streaming',
      { timeout: 15000 }).then(() => true).catch(() => false);
    log({ at: Date.now() - started, event: accepted ? 'turn-submitted' : 'submit-failed' });
    if (!accepted) {
      await browser.close();
      process.exit(2);
    }
  }
  log({ at: Date.now() - started, ...sample });
  await new Promise((resolve) => setTimeout(resolve, 2000));
}
await browser.close();
