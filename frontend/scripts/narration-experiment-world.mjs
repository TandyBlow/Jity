/**
 * Drives the real world page to create one isolated world whose committed
 * points cover the narration experiment scenarios: initial equal sanity, sanity
 * + task + personality, appearance, refused repeats, moves, the second
 * milestone, and a command after a page reload.
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
  await wait(1500); // the first milestone requires one elapsed second

  const worldId = await page.evaluate(() => JSON.parse(sessionStorage.getItem('jity.world.page.v1') ?? '{}').worldId ?? null);
  log.worldId = worldId;

  // 1-4: task+sanity+personality, appearance, refused repeat, move
  for (const command of ['完成压力试验', '露出微笑', '露出微笑', '走到门厅']) {
    log.commands.push(await runCommand(page, command));
  }
  // 5-8: refused recover outside the corridor, move back, recover, refused repeat
  for (const command of ['完成恢复练习', '走到走廊', '完成恢复练习', '完成恢复练习']) {
    log.commands.push(await runCommand(page, command));
  }
  // 9-11: two moves and a refused second strain
  for (const command of ['走到门厅', '走到走廊', '完成压力试验']) {
    log.commands.push(await runCommand(page, command));
  }
  log.snapshots.beforeRefresh = await rows(page);
  await page.screenshot({ path: path.join(OUT, 'world-before-refresh.png'), fullPage: true });

  // refresh, then one more command: the post-refresh packet
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForSelector('ol li', { timeout: 12000 }).catch(async () => {
    await page.click('button:has-text("刷新续接")');
    await page.waitForSelector('ol li', { timeout: 20000 });
  });
  await page.waitForFunction((n) => document.querySelectorAll('ol li').length >= n, log.snapshots.beforeRefresh.length, { timeout: 20000 });
  await wait(800);
  log.commands.push(await runCommand(page, '走到门厅'));
  log.snapshots.afterRefresh = await rows(page);
  await page.screenshot({ path: path.join(OUT, 'world-after-refresh.png'), fullPage: true });

  log.rowCount = log.snapshots.afterRefresh.length;
  log.problems = [];
  if (!worldId) log.problems.push('world id missing');
  if (log.rowCount !== 13) log.problems.push(`expected 13 rows (root + 12 commands), saw ${log.rowCount}`);
  if (log.errors.length) log.problems.push('browser errors');
  const decisions = log.commands.map((entry) => entry.decision);
  const expected = [
    '已执行：', '已执行：', '已拒绝（appearance_already_applied）', '已执行：',
    '已拒绝（milestone_location_mismatch）', '已执行：', '已执行：', '已拒绝（task_already_achieved）',
    '已执行：', '已执行：', '已拒绝（task_already_achieved）', '已执行：',
  ];
  expected.forEach((prefix, index) => {
    if (!(decisions[index] ?? '').startsWith(prefix)) log.problems.push(`command ${index + 1} decision ${decisions[index]} != ${prefix}`);
  });

  writeFileSync(path.join(OUT, 'world-record.json'), JSON.stringify(log, null, 1) + '\n', 'utf8');
  await browser.close();
  console.log(JSON.stringify({ worldId, rowCount: log.rowCount, problems: log.problems, errors: log.errors }, null, 2));
  if (log.problems.length) process.exit(1);
}

main().catch((error) => { console.error(error); process.exit(1); });
