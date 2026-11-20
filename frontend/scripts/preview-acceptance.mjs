/**
 * 真实浏览器验收：只读展示预览页。
 *
 * 覆盖：切换世界与点位、五类点位文案、快速连续切换不串结果、预览服务关闭后的失败态、
 * 以及“恢复失败优先于空 Δ”。
 *
 * 用法：先 `next build`，再
 *   node scripts/preview-acceptance.mjs
 * 脚本自己拉起只读预览服务，next 服务需已在 3111 端口运行。
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const PAGE = process.env.PREVIEW_PAGE ?? 'http://127.0.0.1:3111/world/preview';
const PREVIEW_PORT = process.env.PREVIEW_PORT ?? '8711';
const DB = process.env.PREVIEW_DB ?? 'artifacts/next-runs/adapt-r1/record.db';
const OUT = path.resolve('..', 'artifacts/next-runs/adapt-r4/browser');
mkdirSync(OUT, { recursive: true });

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function startPreview() {
  const child = spawn('python', ['-X', 'utf8', 'experiments/world-components/preview_server.py',
    '--db', DB, '--port', PREVIEW_PORT], { cwd: path.resolve('..'), stdio: ['ignore', 'pipe', 'pipe'] });
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${PREVIEW_PORT}/worlds`);
      if (response.ok) return child;
    } catch {
      // not up yet
    }
    await wait(150);
  }
  throw new Error('preview server did not start');
}

async function stopPreview(child) {
  if (process.platform === 'win32') {
    spawn('taskkill', ['/PID', String(child.pid), '/T', '/F']);
  } else {
    child.kill('SIGTERM');
  }
  for (let attempt = 0; attempt < 40; attempt += 1) {
    try {
      await fetch(`http://127.0.0.1:${PREVIEW_PORT}/worlds`);
    } catch {
      return;
    }
    await wait(150);
  }
  throw new Error('preview server still answering after kill');
}

async function select(page, world, point) {
  await page.selectOption('.preview-bar label:nth-of-type(1) select', world);
  await page.waitForFunction((w) => {
    const meta = document.querySelector('.preview-card .preview-meta');
    return meta !== null;
  }, world);
  await page.selectOption('.preview-bar label:nth-of-type(2) select', point);
  await page.waitForFunction((p) => {
    const meta = document.querySelector('.preview-card .preview-meta');
    return meta !== null && meta.textContent.includes(p);
  }, point, { timeout: 8000 });
  await wait(120);
}

async function readState(page) {
  return page.evaluate(() => {
    const text = (selector) => Array.from(document.querySelectorAll(selector)).map((n) => n.textContent.trim());
    return {
      meta: document.querySelector('.preview-card .preview-meta')?.textContent.trim() ?? null,
      facts: text('.preview-fact'),
      quiet: text('.preview-quiet'),
      warn: text('.preview-card--warn'),
      stop: text('.preview-card--stop'),
      diagnostics: document.querySelector('.preview-diagnostics pre')?.textContent.slice(0, 2000) ?? null,
    };
  });
}

async function main() {
  const server = await startPreview();
  // 本机 Playwright 与已下载的浏览器版本不一致，直接指定可执行文件
  const cached = path.join(process.env.USERPROFILE ?? '', 'AppData', 'Local', 'ms-playwright',
    'chromium_headless_shell-1217', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe');
  const executablePath = process.env.PREVIEW_CHROMIUM ?? (existsSync(cached) ? cached : undefined);
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const log = { page: PAGE, cases: {}, rapid: {}, offline: {}, errors: [] };

  const errors = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(String(error)));

  await page.goto(PAGE, { waitUntil: 'networkidle' });
  await page.waitForSelector('.preview-card');

  const cases = [
    ['facts', 'world_1', 'p1'],
    ['empty-delta', 'world_1', 'p4'],
    ['task-unshown', 'world_1', 'p6'],
    ['ledger-gap', 'world_1', 'p7'],
    ['ledger-with-checkpoint', 'world_3', 't2'],
    ['checkpoint-fallback', 'world_4', 'u1'],
    ['unrecoverable', 'world_4', 'u2'],
    ['gap-over-empty-delta', 'world_4', 'u3'],
  ];
  for (const [name, world, point] of cases) {
    await select(page, world, point);
    const state = await readState(page);
    log.cases[name] = { world, point, ...state };
    await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
  }

  // 快速连续切换：不等待中间结果，只等最后一次
  await select(page, 'world_1', 'p1');
  await page.selectOption('.preview-bar label:nth-of-type(1) select', 'world_1');
  for (const point of ['p7', 'p4', 'p6', 'p1', 'p4']) {
    await page.selectOption('.preview-bar label:nth-of-type(2) select', point);
  }
  await page.waitForFunction(() => {
    const meta = document.querySelector('.preview-card .preview-meta');
    return meta !== null && meta.textContent.includes('p4');
  }, null, { timeout: 8000 });
  await wait(400);
  log.rapid = { expected: 'world_1/p4', observed: await readState(page) };
  await page.screenshot({ path: path.join(OUT, 'rapid-switch-final.png'), fullPage: true });

  // 慢请求不覆盖新选择：把 p1 的响应拖后，再立刻切到 p4
  await page.route('**/preview?**', async (route) => {
    const url = route.request().url();
    if (url.includes('point=p1')) await wait(900);
    await route.continue();
  });
  await select(page, 'world_1', 'p1');
  await page.selectOption('.preview-bar label:nth-of-type(2) select', 'p4');
  await wait(1600);
  log.staleResponse = { expected: 'world_1/p4', observed: await readState(page) };
  await page.unroute('**/preview?**');
  await page.screenshot({ path: path.join(OUT, 'stale-response.png'), fullPage: true });

  // 关闭预览服务：必须显示加载失败，且不残留上一点位的句子
  await stopPreview(server);
  await wait(300);
  await page.goto(PAGE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelector('.preview-card--stop') !== null, null, { timeout: 8000 });
  await wait(500);
  log.offline = await readState(page);
  log.offline.bodyText = (await page.evaluate(() => document.body.innerText)).slice(0, 400);
  await page.screenshot({ path: path.join(OUT, 'offline.png'), fullPage: true });

  log.errors = errors;
  writeFileSync(path.join(OUT, 'record.json'), JSON.stringify(log, null, 2) + '\n', 'utf8');
  await browser.close();
  console.log(JSON.stringify({
    cases: Object.fromEntries(Object.entries(log.cases).map(([k, v]) => [k, {
      facts: v.facts, quiet: v.quiet.length, warn: v.warn.length > 0, stop: v.stop.length > 0 }])),
    rapid: { expected: log.rapid.expected, meta: log.rapid.observed.meta,
      facts: log.rapid.observed.facts, quiet: log.rapid.observed.quiet },
    staleResponse: { expected: log.staleResponse.expected, meta: log.staleResponse.observed.meta,
      facts: log.staleResponse.observed.facts },
    offline: { stop: log.offline.stop, facts: log.offline.facts, quiet: log.offline.quiet },
    errors,
  }, null, 2));
}

main().catch((error) => { console.error(error); process.exit(1); });
