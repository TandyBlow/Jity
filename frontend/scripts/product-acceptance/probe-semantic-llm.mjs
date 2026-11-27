// Dev driver: open the semantic-LLM probe page, wait for its result, save it.
// Usage: node scripts/product-acceptance/probe-semantic-llm.mjs --base http://127.0.0.1:3177 --out ../artifacts/goal/micro-workflow/evidence-semantic-llm-probe-1.json
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { chromium } from 'playwright';
import { acquireLease } from './lease.mjs';

const flag = (name, fallback) => {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
};
const base = flag('--base', 'http://127.0.0.1:3177');
const out = resolve(process.cwd(), flag('--out', '../artifacts/goal/micro-workflow/evidence-semantic-llm-probe-1.json'));
const timeoutMs = Number(flag('--timeout', '1200000'));

const lease = acquireLease({ lane: '09-ui', purpose: 'semantic LLM probe', ttlSeconds: 1800 });
const browser = await chromium.launch({
  headless: true,
  channel: 'msedge',
  args: ['--enable-unsafe-webgpu', '--ignore-gpu-blocklist'],
});
try {
  const page = await browser.newPage();
  await page.goto(`${base}/semantic-llm-probe`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => Boolean(window.__probeResult), null, { timeout: timeoutMs });
  const result = await page.evaluate(() => window.__probeResult);
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify({ kind: 'semantic-llm-probe', at: new Date().toISOString(), result }, null, 1));
  console.log(`[probe] ok=${result?.ok} rows=${result?.rows?.length ?? 0} -> ${out}`);
} finally {
  await browser.close();
  lease.release();
}
