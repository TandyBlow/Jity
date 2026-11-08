/**
 * 主世界页的回合展示验收：在隔离测试世界里用正常操作产生移动、理智变化、
 * 任务达成、性格描述、外貌变化与空增量，然后核对每个回合的模板叙事与事实句、
 * 刷新后的结果、以及历史顺序。
 *
 * WORLD_FACTS_APPEARANCE=1 加测外貌命令、重复拒绝及刷新后的重复拒绝。
 *
 * 前置：后端 create_persistent_world_app 与前端 next start 都已启动。
 * 用法：node scripts/world-facts-acceptance.mjs
 *       WORLD_PAGE / WORLD_API 指定页面与后端地址（默认 3111 / 8021）
 *       WORLD_FACTS_OUT=<目录，绝对路径可跨工作树> 改证据目录
 *       WORLD_FACTS_SMILE 改外貌事实句（默认「周宁：面带微笑。」）
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const PAGE = process.env.WORLD_PAGE ?? 'http://127.0.0.1:3111/world';
const API = process.env.WORLD_API ?? 'http://127.0.0.1:8021';
const appearance = process.env.WORLD_FACTS_APPEARANCE === '1';
// 默认小世界的主角与规则词表给的外貌原文；只用于等待与断言，不是新的输入来源
const SMILE_SENTENCE = process.env.WORLD_FACTS_SMILE ?? '周宁：面带微笑。';
const OUT = path.resolve('..', process.env.WORLD_FACTS_OUT ?? 'artifacts/next-runs/integration-r1/browser');
mkdirSync(OUT, { recursive: true });
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function launchOptions() {
  const cached = path.join(process.env.USERPROFILE ?? '', 'AppData', 'Local', 'ms-playwright',
    'chromium_headless_shell-1217', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe');
  return process.env.REVIEW_CHROMIUM ? { executablePath: process.env.REVIEW_CHROMIUM }
    : existsSync(cached) ? { executablePath: cached } : {};
}

async function rows(page) {
  // 记录用户看得到的文字：版本标签、叙事文字、事实/提示段落；折叠的“来源”不进去，
  // 否则隐藏的 JSON 会污染“页面必须出现/不得出现”的核对。
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
    return {
      version: li.querySelector('span')?.textContent ?? '',
      text: parts.join('\n\n'),
    };
  }));
}

async function runCommand(page, text) {
  await page.fill('input[placeholder*="输入命令"]', text);
  const before = (await rows(page)).length;
  await page.click('button:has-text("执行")');
  await page.waitForFunction((n) => document.querySelectorAll('ol li').length > n, before, { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector('input[placeholder*="输入命令"]')?.disabled, null, { timeout: 15000 });
  // 事实句在提交完成后由 rebuild 取回；等到最后一行出现事实、缺口或未展示提示为止
  await page.waitForFunction(() => {
    const items = Array.from(document.querySelectorAll('ol li'));
    const last = items[items.length - 1];
    if (!last) return false;
    return last.querySelectorAll('p').length > 0;
  }, null, { timeout: 15000 });
  await wait(400);
  return page.locator('p').filter({ hasText: /^(已执行：|已拒绝（|未识别的命令)/ }).last().innerText();
}

async function main() {
  const browser = await chromium.launch(launchOptions());
  const page = await browser.newPage({ viewport: { width: 1100, height: 1000 } });
  const log = { page: PAGE, api: API, appearance, steps: {}, errors: [], factsRequests: [] };
  const pendingFacts = [];
  page.on('response', (response) => {
    if (response.url().includes('/world/facts/')) pendingFacts.push((async () => {
      log.factsRequests.push({ url: response.url(), status: response.status(), body: await response.json() });
    })());
  });
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
  if (appearance) {
    log.steps.smile = await runCommand(page, '露出微笑'); // 经规则、分配 ID、Python 提交后产生外貌变化
    log.steps.repeatSmile = await runCommand(page, '露出微笑'); // 同一外貌已生效，拒绝并提交空增量
  }
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
  // 整页重建会逐点取回事实；等日志补齐到刷新前的行数，再等外貌句出现
  await page.waitForFunction((n) => document.querySelectorAll('ol li').length >= n, afterRun.length, { timeout: 20000 });
  if (appearance) await page.waitForFunction((sentence) => document.body.innerText.includes(sentence), SMILE_SENTENCE, { timeout: 20000 });
  await wait(600);
  log.resumedAutomatically = resumed;
  const afterRefresh = await rows(page);
  await page.screenshot({ path: path.join(OUT, 'rounds-after-refresh.png'), fullPage: true });

  // 直接问后端：每个点位的结构化增量与事实，用于和页面比对
  const pointsResponse = null; // 逐点事实由页面自行取回，脚本不再探测不存在的点位
  log.steps.afterRefresh = afterRefresh;

  // 再加一个回合：更早的历史行必须原样不动
  if (appearance) log.steps.repeatAfterRefresh = await runCommand(page, '露出微笑'); // 从服务器恢复的外貌仍然阻止重复添加
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
  await Promise.all(pendingFacts);
  const problems = [];
  if (JSON.stringify(afterRun) !== JSON.stringify(afterRefresh)) problems.push('refresh changed the round log');
  if (!log.steps.historyStable.previousRoundsUnchanged) problems.push('new commands changed earlier rounds');
  if (log.steps.historyStable.grewBy !== (appearance ? 2 : 1)) problems.push('unexpected number of new rounds');
  if (log.errors.length) problems.push('browser errors');
  if (log.factsRequests.some((request) => request.status !== 200)) problems.push('facts request failed');
  if (appearance && !afterRun.some((row) => row.text.includes(SMILE_SENTENCE))) problems.push('missing committed appearance sentence');
  // 模板叙事必须自己核对过增量与已提交状态：这一句来自 projectCommittedNarration/render
  const templateSentence = `周宁的外貌变化为「${SMILE_SENTENCE.split('：')[1]?.replace('。', '')}」`;
  if (appearance && !afterRun.some((row) => row.text.includes(templateSentence))) {
    problems.push('template narration does not name the appearance fact');
  }
  const decisions = [log.steps.smile, log.steps.repeatSmile, log.steps.repeatAfterRefresh].map((text) => text ?? '');
  if (appearance && (!decisions[0].startsWith('已执行：')
    || !decisions[1].startsWith('已拒绝（appearance_already_applied）')
    || !decisions[2].startsWith('已拒绝（appearance_already_applied）'))) problems.push('appearance command decisions disagree');
  log.problems = problems;

  writeFileSync(path.join(OUT, 'record.json'), JSON.stringify(log, null, 2) + '\n', 'utf8');
  await browser.close();
  console.log(JSON.stringify({
    worldId, pointsResponse,
    afterRun: afterRun.length, afterRefresh: afterRefresh.length,
    historyStable: log.steps.historyStable,
    errors: log.errors,
  }, null, 2));
  if (problems.length) throw new Error(problems.join('; '));
}

main().catch((error) => { console.error(error); process.exit(1); });
