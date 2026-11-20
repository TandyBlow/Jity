/**
 * Second isolated world for the narration experiment: four more distinct fact
 * packets at sanity 10 (move out, refused wrong location, move back, first
 * smile). The other world already covers the task/recover states.
 *
 * The page and backend are the current branch's build; the model is not
 * involved. The resulting SQLite and record are the input for the offline
 * model experiment.
 *
 * Usage:
 *   WORLD_PAGE=http://127.0.0.1:3113/world WORLD_API=http://127.0.0.1:8024 \
 *   WORLD_OUT=<dir> node scripts/narration-experiment-world.mjs
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const PAGE = process.env.WORLD_PAGE ?? 'http://127.0.0.1:3113/world';
const API = process.env.WORLD_API ?? 'http://127.0.0.1:8024';
const OUT = process.env.WORLD_OUT ?? path.resolve('..', 'artifacts/next-runs/narration-model-r1');
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function launchOptions() {
  const cached = path.join(process.env.USERPROFILE ?? '', 'AppData', 'Local', 'ms-playwright',
    'chromium_headless_shell-1217', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe');
  return process.env.REVIEW_CHROMIUM ? { executablePath: process.env.REVIEW_CHROMIUM }
    : existsSync(cached) ? { executablePath: cached } : {};
}

async function rows(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll('ol li')).map((li) => {
    const parts = [];
    const walk = (node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const value = (node.textContent ?? '').trim();
        if (value) parts.push(value);
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.tagName === 'DETAILS' || node.tagName === 'SPAN') return;
      if (node.tagName === 'P') {
        const value = (node.textContent ?? '').trim();
        if (value) parts.push(value);
        return;
      }
      for (const child of node.childNodes) walk(child);
    };
    for (const child of li.childNodes) walk(child);
    return { version: li.querySelector('span')?.textContent ?? '', text: parts.join('\n\n') };
  }));
}

async function runCommand(page, text) {
  const before = (await rows(page)).length;
  await page.fill('input[placeholder*="输入命令"]', text);
  await page.click('button:has-text("执行")');
  await page.waitForFunction((n) => document.querySelectorAll('ol li').length > n, before, { timeout: 20000 });
  await page.waitForFunction(() => !document.querySelector('input[placeholder*="输入命令"]')?.disabled, null, { timeout: 20000 });
  await wait(500);
  const decision = await page.locator('p').filter({ hasText: /^(已执行：|已拒绝（|未识别的命令)/ }).last().innerText();
  return { command: text, decision };
}

async function main() {
  const browser = await chromium.launch(launchOptions());
  const page = await browser.newPage({ viewport: { width: 1100, height: 1000 } });
  const log = { page: PAGE, api: API, commands: [], errors: [], snapshots: {} };
  page.on('console', (m) => { if (m.type() === 'error') log.errors.push(m.text()); });
  page.on('pageerror', (e) => log.errors.push(String(e)));

  await page.goto(PAGE, { waitUntil: 'networkidle' });
  await page.fill('#world-api', API);
  await page.click('button:has-text("新世界")');
  await page.waitForSelector('ol li', { timeout: 20000 });
  await wait(1500);
  const worldId = await page.evaluate(() => JSON.parse(sessionStorage.getItem('jity.world.page.v1') ?? '{}').worldId ?? null);
  log.worldId = worldId;

  for (const command of ['走到门厅', '完成压力试验', '走到走廊', '露出微笑']) {
    log.commands.push(await runCommand(page, command));
  }
  log.snapshots.afterRun = await rows(page);
  await page.screenshot({ path: path.join(OUT, 'world2-after-run.png'), fullPage: true });
  log.rowCount = log.snapshots.afterRun.length;
  log.problems = [];
  if (!worldId) log.problems.push('world id missing');
  if (log.rowCount !== 5) log.problems.push(`expected 5 rows (root + 4 commands), saw ${log.rowCount}`);
  if (log.errors.length) log.problems.push('browser errors');
  const expected = ['已执行：', '已拒绝（milestone_location_mismatch）', '已执行：', '已执行：'];
  log.commands.forEach((entry, index) => {
    if (!entry.decision.startsWith(expected[index])) log.problems.push(`command ${index + 1} decision ${entry.decision} != ${expected[index]}`);
  });

  writeFileSync(path.join(OUT, 'world2-record.json'), JSON.stringify(log, null, 1) + '\n', 'utf8');
  await browser.close();
  console.log(JSON.stringify({ worldId, rowCount: log.rowCount, problems: log.problems, errors: log.errors }, null, 2));
  if (log.problems.length) process.exit(1);
}

main().catch((error) => { console.error(error); process.exit(1); });
