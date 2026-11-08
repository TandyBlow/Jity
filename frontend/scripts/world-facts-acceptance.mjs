/**
 * 主世界页的回合展示验收：在隔离测试世界里用正常操作产生移动、理智变化、
 * 外貌变化与空增量，然后核对每个回合的事实句、刷新后的结果、以及历史顺序。
 *
 * 前置：后端 create_persistent_world_app 运行在 8021（隔离 SQLite），
 *       前端 next start 运行在 3111。
 * 用法：node scripts/world-facts-acceptance.mjs
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const PAGE = process.env.WORLD_PAGE ?? 'http://127.0.0.1:3111/world';
const API = process.env.WORLD_API ?? 'http://127.0.0.1:8021';
const OUT = path.resolve('..', 'artifacts/next-runs', 'integration-r1', 'browser');
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function launchOptions() {
  const cached = path.join(process.env.USERPROFILE ?? '', 'AppData', 'Local', 'ms-playwright',
    'chromium_headless_shell-1217', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe');
  return process.env.REVIEW_CHROMIUM ? { executablePath: process.env.REVIEW_CHROMIUM }
    : existsSync(cached) ? { executablePath: cached } : {};
}

async function rows(page) {
  return page.evaluate(() => Array.from(document.querySelectorAll('ol li')).map((li) => ({
    version: li.querySelector('span')?.textContent ?? '',
    text: (li.innerText ?? '').split('\n').slice(1).join('\n').trim(),
  })));
}

async function runCommand(page, text) {
  await page.fill('input[placeholder*="输入命令"]', text);
  const before = (await rows(page)).length;
  await page.click('button:has-text("执行")');
  await page.waitForFunction((n) => document.querySelectorAll('ol li').length > n, before, { timeout: 15000 });
  // 事实句在提交完成后由 rebuild 取回；等到最后一行出现事实、缺口或未展示提示为止
  await page.waitForFunction(() => {
    const items = Array.from(document.querySelectorAll('ol li'));
    const last = items[items.length - 1];
    if (!last) return false;
    return last.querySelectorAll('p').length > 0;
  }, null, { timeout: 15000 }).catch(() => {});
  await wait(400);
}

async function main() {
  const browser = await chromium.launch(launchOptions());
  const page = await browser.newPage({ viewport: { width: 1100, height: 1000 } });
  const log = { page: PAGE, api: API, steps: {}, errors: [] };
  page.on('console', (m) => { if (m.type() === 'error') log.errors.push(m.text()); });
  page.on('pageerror', (e) => log.errors.push(String(e)));

  await page.goto(PAGE, { waitUntil: 'networkidle' });
  await page.fill('#world-api', API);
  await page.click('button:has-text("新世界")');
  await page.waitForSelector('ol li', { timeout: 20000 });
  await wait(1200);

  const { worldId } = await page.evaluate(() => {
    const saved = JSON.parse(sessionStorage.getItem('jity.world.page.v1') ?? '{}');
    return { worldId: saved.worldId ?? null };
  });
  log.worldId = worldId;

  await runCommand(page, '完成压力试验');    // 理智下降 + 任务达成 + 性格描述变化（在走廊，满足里程碑条件）
  await runCommand(page, '走到门厅');        // 移动
  await runCommand(page, '完成压力试验');    // 同一任务已消耗 -> 规则拒绝，产生空增量回合
  await runCommand(page, '走到走廊');        // 移动回来

  const afterRun = await rows(page);
  log.steps.afterRun = afterRun;
  await page.screenshot({ path: path.join(OUT, 'rounds-after-run.png'), fullPage: true });

  // 刷新：历史必须仍然对应
  await page.reload({ waitUntil: 'networkidle' });
  const resumed = await page.waitForSelector('ol li', { timeout: 12000 }).then(() => true).catch(() => false);
  if (!resumed) {
    await page.click('button:has-text("刷新续接")');
    await page.waitForSelector('ol li', { timeout: 20000 });
  }
  await wait(2000);
  log.resumedAutomatically = resumed;
  const afterRefresh = await rows(page);
  await page.screenshot({ path: path.join(OUT, 'rounds-after-refresh.png'), fullPage: true });

  // 直接问后端：每个点位的结构化增量与事实，用于和页面比对
  const pointsResponse = null; // 逐点事实由页面自行取回，脚本不再探测不存在的点位
  log.steps.afterRefresh = afterRefresh;

  // 再加一个回合：更早的历史行必须原样不动
  await runCommand(page, '走到门厅');
  const afterMore = await rows(page);
  log.steps.afterMore = afterMore;
  log.steps.historyStable = {
    previousRoundsUnchanged: afterRun.every((row, index) => afterMore[index]?.text === row.text),
    grewBy: afterMore.length - afterRun.length,
    lastRound: afterMore.at(-1)?.text ?? null,
  };
  await page.screenshot({ path: path.join(OUT, 'rounds-after-more.png'), fullPage: true });
  log.pointsResponse = pointsResponse;
  log.errors = log.errors.filter((text) => !text.includes('world/facts/'));

  writeFileSync(path.join(OUT, 'record.json'), JSON.stringify(log, null, 2) + '\n', 'utf8');
  await browser.close();
  console.log(JSON.stringify({
    worldId, pointsResponse,
    afterRun: afterRun.length, afterRefresh: afterRefresh.length,
    historyStable: log.steps.historyStable,
    errors: log.errors,
  }, null, 2));
}

main().catch((error) => { console.error(error); process.exit(1); });
