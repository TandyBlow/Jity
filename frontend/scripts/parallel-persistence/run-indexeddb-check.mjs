#!/usr/bin/env node
/** Real-browser verification of durable local progress (IndexedDB, refresh
 * recovery, multi-tab fencing, legacy migration, cancel). Uses Playwright's
 * Chromium and a bundled fake model port: no GGUF weights, no GPU, no server.
 *
 *   node scripts/parallel-persistence/run-indexeddb-check.mjs [--headed] [--out <file>]
 */
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { rolldown } from 'rolldown';
import { chromium } from 'playwright';

const here = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(here, '../..');
const ORIGIN = 'https://local.test';

function arg(name, fallback = null) {
  const index = process.argv.indexOf(name);
  return index >= 0 && process.argv[index + 1] ? process.argv[index + 1] : fallback;
}

async function bundle() {
  const bundle = await rolldown({
    input: join(here, 'browser-entry.ts'),
    platform: 'browser',
    resolve: { extensions: ['.ts', '.tsx', '.mjs', '.js', '.json'] },
    transform: { typescript: { tsconfig: join(frontend, 'tsconfig.world-contract.json') } },
  });
  const { output } = await bundle.generate({ format: 'iife', sourcemap: false });
  const chunk = output.find((item) => item.type === 'chunk');
  if (!chunk) throw new Error('bundle produced no chunk');
  return chunk.code;
}

function html() {
  return '<!doctype html><html><head><meta charset="utf-8"><title>persistence check</title></head>'
    + '<body><script src="/bundle.js"></script></body></html>';
}

async function newPage(context, code, tag) {
  const page = await context.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') console.error(`[${tag} console] ${message.text()}`);
  });
  page.on('pageerror', (error) => console.error(`[${tag} pageerror] ${error.message}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) return route.abort();
    if (url.pathname === '/bundle.js') {
      return route.fulfill({ status: 200, contentType: 'text/javascript; charset=utf-8', body: code });
    }
    return route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: html() });
  });
  await page.goto(`${ORIGIN}/`);
  await page.waitForFunction(() => !!window.PersistenceCheck);
  return page;
}

async function main() {
  const headed = process.argv.includes('--headed');
  const out = arg('--out', null);
  const code = await bundle();
  const temp = await mkdtemp(join(tmpdir(), 'persistence-check-'));
  await writeFile(join(temp, 'bundle.js'), code, 'utf8');

  // System Edge is the browser the product is checked in; no browser download.
  const browser = await chromium.launch({ channel: process.env.PW_CHANNEL ?? 'msedge', headless: !headed });
  const context = await browser.newContext();
  const evidence = { startedAt: new Date().toISOString(), origin: ORIGIN, steps: [], browser: browser.version(), bundleBytes: code.length, failures: [] };
  let failure = null;
  try {
    const tabA = await newPage(context, code, 'tabA');
    await tabA.evaluate(() => window.PersistenceCheck.reset());
    await tabA.evaluate(() => window.PersistenceCheck.storeCheck());
    await tabA.evaluate(() => window.PersistenceCheck.createAndPlay());
    await tabA.evaluate(() => window.PersistenceCheck.midTurnSnapshot());

    // Second real tab, same origin and IndexedDB.
    const tabB = await newPage(context, code, 'tabB');
    await tabB.evaluate(() => window.PersistenceCheck.storeCheck());
    evidence.tabBClaim = await tabB.evaluate(() => window.PersistenceCheck.claimInSecondTab());
    // The page's explicit "play in this tab" takeover fences the first tab.
    evidence.tabBTakeover = await tabB.evaluate(() => window.PersistenceCheck.takeoverWorld());
    await tabA.evaluate(() => window.PersistenceCheck.staleWorldWriterFenced());
    // A crashed tab stops renewing its lease: wait for the TTL, then take over.
    await tabB.waitForTimeout(1_800);
    evidence.tabBResume = await tabB.evaluate(() => window.PersistenceCheck.resumeAfterRefresh());
    evidence.steps.push(...(await tabB.evaluate(() => window.PersistenceCheck.steps())));
    await tabB.close();

    await tabA.evaluate(() => window.PersistenceCheck.takeoverAfterExpiry());
    await tabA.evaluate(() => window.PersistenceCheck.staleTabSaveFenced());
    await tabA.evaluate(() => window.PersistenceCheck.legacyMigration());
    await tabA.evaluate(() => window.PersistenceCheck.duplicateSubmit());
    await tabA.evaluate(() => window.PersistenceCheck.cancelInFlight());
    await tabA.evaluate(() => window.PersistenceCheck.pauseAndResume());
    await tabA.evaluate(() => window.PersistenceCheck.resumeAtContinuation());
    await tabA.evaluate(() => window.PersistenceCheck.listAndDelete());
    evidence.steps = await tabA.evaluate(() => window.PersistenceCheck.steps());
  } catch (error) {
    failure = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    evidence.failures.push(failure);
  } finally {
    await browser.close();
  }

  const failed = evidence.steps.filter((step) => !step.ok);
  evidence.failedSteps = failed;
  evidence.passed = failure === null && failed.length === 0;
  evidence.finishedAt = new Date().toISOString();
  if (out) {
    await mkdir(dirname(out), { recursive: true });
    await writeFile(out, `${JSON.stringify(evidence, null, 2)}\n`, 'utf8');
  }
  console.log(JSON.stringify({ passed: evidence.passed, steps: evidence.steps.length, failed: failed.map((step) => step.name), failure }, null, 2));
  for (const step of evidence.steps) {
    console.log(`${step.ok ? 'PASS' : 'FAIL'} ${step.name} ${JSON.stringify(step.detail).slice(0, 240)}`);
  }
  if (!evidence.passed) process.exitCode = 1;
}

await main();
