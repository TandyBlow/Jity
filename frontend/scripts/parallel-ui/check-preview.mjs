#!/usr/bin/env node
/**
 * Small real-browser check for the component preview route.
 *
 * It uses the installed Edge (no browser download) and needs no model, GPU or
 * lease: the preview page only renders fixture data and local React state.
 *
 *   cd frontend
 *   npx next dev --port 3219
 *   node scripts/parallel-ui/check-preview.mjs
 *
 * Exit code 0 means every listed check passed. Failures print the failing
 * check name and the observed value.
 */
import { chromium } from 'playwright';

const baseUrl = process.env.BASE_URL ?? 'http://127.0.0.1:3219';
const previewUrl = `${baseUrl}/world-local-components-preview`;
const checks = [];

function check(name, pass, detail = '') {
  checks.push({ name, pass: Boolean(pass), detail: pass ? '' : String(detail) });
}

async function text(page, selector) {
  return (await page.locator(selector).first().innerText()).trim();
}

async function waitForServer() {
  const deadline = Date.now() + 90_000;
  let lastError = '';
  while (Date.now() < deadline) {
    try {
      const response = await fetch(previewUrl, { redirect: 'follow' });
      if (response.ok) return;
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 1_000));
  }
  throw new Error(`preview server not ready: ${lastError}`);
}

await waitForServer();

const browser = await chromium.launch({ channel: 'msedge', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.on('pageerror', (error) => checks.push({ name: 'no page errors', pass: false, detail: error.message }));
  await page.goto(previewUrl, { waitUntil: 'networkidle' });
  await page.locator('[data-testid="world-local-layout"]').waitFor({ state: 'visible' });

  check('preview is clearly marked as fixture data', (await page.getByText('组件预览，不是游戏。').count()) > 0);
  check('preview is noindex', ((await page.locator('meta[name="robots"]').getAttribute('content')) ?? '').includes('noindex'));
  check('noindex note points back to the real entry', (await page.locator('a[href="/world-local"]').count()) > 0);
  check('all five panels render', (await page.locator('[data-testid="narration-view"]').count()) === 1
    && (await page.locator('[data-testid="history-panel"]').count()) === 1
    && (await page.locator('[data-testid="world-status"]').count()) === 1
    && (await page.locator('[data-testid="progress-status"]').count()) === 1
    && (await page.locator('[data-testid="action-input"]').count()) === 1);
  check('sanity is exposed as a meter', (await page.locator('[data-testid="world-status"] [role="meter"]').getAttribute('aria-valuenow')) === '43');
  check('history marks the head point', (await page.locator('[data-testid="history-pt_4"]').getAttribute('aria-current')) === 'true');

  // Accepted narration: real text, not invented by the component.
  check('initial narration is accepted', (await text(page, '[data-testid="narration-status"]')) === '已接受');
  const acceptedText = await text(page, '[data-testid="narration-content"]');
  check('accepted text is visible', acceptedText.includes('枪声在回廊另一头'));
  check('accepted article is not busy', (await page.locator('[data-testid="narration-content"]').getAttribute('aria-busy')) === 'false');

  // Streaming.
  await page.locator('[data-preview="narration-streaming"]').click();
  check('streaming status is announced', (await text(page, '[data-testid="narration-status"]')) === '正在生成');
  check('streaming article is busy', (await page.locator('[data-testid="narration-content"]').getAttribute('aria-busy')) === 'true');
  check('streaming live region is polite', (await page.locator('[data-testid="narration-live"]').getAttribute('aria-live')) === 'polite');
  check('streaming text appears', (await text(page, '[data-testid="narration-content"]')).includes('半步'));
  check('submit is disabled while streaming', await page.locator('[data-testid="submit-action"]').isDisabled());
  check('streaming disables submit for a stated reason',
    (await page.locator('[data-testid="submit-action"]').getAttribute('title')) === '本轮回合尚未交还');
  check('pause is available while streaming', !(await page.locator('[data-testid="pause-action"]').isDisabled()));

  // Pause / resume wiring.
  await page.locator('[data-testid="pause-action"]').click();
  check('pause reaches the callback', (await text(page, '[data-testid="narration-view"]')).length > 0 && (await page.locator('[data-testid="resume-action"]').count()) === 1);
  check('submit is disabled while paused',
    (await page.locator('[data-testid="submit-action"]').getAttribute('title')) === '当前已暂停，继续后才能提交行动');
  check('cancel is disabled with a wiring reason by default',
    (await page.locator('[data-testid="cancel-action"]').isDisabled())
    && (await text(page, '[data-testid="controls-notes"]')).includes('当前会话尚未接入取消'));
  await page.locator('[data-testid="resume-action"]').click();
  check('resume returns to the action controls', (await page.locator('[data-testid="pause-action"]').count()) === 1);

  // Accepted + warning.
  await page.locator('[data-preview="narration-warning"]').click();
  check('warning keeps the accepted text', (await text(page, '[data-testid="narration-status"]')) === '已接受');
  check('warning is a non-blocking note', (await text(page, '[data-testid="narration-warning"]')).includes('事实校验提示'));

  // Failed + regeneration wiring.
  await page.locator('[data-preview="narration-failed"]').click();
  check('failed status is explicit', (await text(page, '[data-testid="narration-status"]')) === '生成失败');
  check('failed reason is an alert', (await text(page, '[data-testid="narration-failure"]')).includes('120 秒'));
  check('failed previous text stays available', (await page.locator('[data-testid="narration-content"] details').count()) === 1
    || (await page.getByText('查看上一次已接受的正文').count()) > 0);
  check('regeneration is disabled with a reason by default', await page.locator('[data-testid="narration-regenerate"]').isDisabled());
  check('regeneration reason is visible',
    (await text(page, '[data-testid="narration-regenerate-reason"]')) === '当前会话尚未接入正文重生成');
  await page.locator('[data-preview="regenerate-wired"]').check();
  await page.locator('[data-testid="narration-regenerate"]').click();
  check('wired regeneration reaches the callback', (await text(page, '[data-testid="preview-note"]')).includes('重新生成本轮正文'));

  // Submit callback and keyboard shortcut.
  await page.locator('[data-preview="narration-accepted"]').click();
  await page.locator('[data-testid="action-input"]').fill('我贴着墙往西走');
  await page.locator('[data-testid="action-input"]').press('Control+Enter');
  check('Ctrl+Enter submits the draft', (await text(page, '[data-testid="preview-request"]')).includes('我贴着墙往西走'));
  check('submit does not invent prose', (await text(page, '[data-testid="narration-content"]')).includes('枪声在回廊另一头'));
  check('preview explains the submit is not generated', (await text(page, '[data-testid="preview-note"]')).includes('不调用模型'));

  // Keyboard reachability: only the submit button is enabled after typing.
  await page.locator('[data-testid="action-input"]').fill('再看一眼');
  await page.locator('[data-testid="action-input"]').focus();
  await page.keyboard.press('Tab');
  check('Tab moves from the textarea to the enabled submit button',
    (await page.evaluate(() => document.activeElement?.getAttribute('data-testid'))) === 'submit-action');
  check('textarea advertises the submit shortcut',
    (await page.locator('[data-testid="action-input"]').getAttribute('aria-keyshortcuts')) === 'Control+Enter Meta+Enter');

  // History: cache missing + regeneration request.
  await page.locator('[data-preview="history-missing"]').check();
  await page.locator('[data-preview="regenerate-wired"]').uncheck();
  check('history marks a missing cache', (await text(page, '[data-testid="history-pt_3"]')).includes('正文缓存缺失'));
  check('history regeneration is disabled until wired', await page.locator('[data-testid="regenerate-pt_3"]').isDisabled());
  check('history explains the disabled regeneration',
    (await text(page, '[data-testid="history-regenerate-reason"]')).includes('当前会话尚未接入正文重生成'));
  await page.locator('[data-preview="regenerate-wired"]').check();
  await page.locator('[data-testid="regenerate-pt_3"]').click();
  check('history regeneration reaches the callback', (await text(page, '[data-testid="preview-note"]')).includes('时间点 pt_3'));

  // Progress: save failure + retry.
  await page.locator('[data-preview="save-state"]').selectOption('failed');
  check('save failure is an alert', (await text(page, '[data-testid="progress-status"]')).includes('本地保存失败'));
  await page.locator('[data-testid="save-retry"]').click();
  check('save retry reaches the callback', (await text(page, '[data-testid="save-state"]')) === '已保存');

  // Progress: unwired sync, then wired + failure + retry.
  await page.locator('[data-preview="sync-wired"]').uncheck();
  check('unwired sync is disabled', await page.locator('[data-testid="sync-action"]').isDisabled());
  check('unwired sync states why', (await text(page, '[data-testid="sync-reason"]')).includes('同步尚未接线'));
  await page.locator('[data-preview="sync-wired"]').check();
  await page.locator('[data-preview="sync-state"]').selectOption('failed');
  check('sync failure is visible', (await text(page, '[data-testid="progress-status"]')).includes('示例：进度服务返回 503。'));
  await page.locator('[data-testid="sync-action"]').click();
  check('sync retry reaches the callback', (await text(page, '[data-testid="sync-state"]')) === '已同步');

  // Offline banner and sync lock.
  await page.locator('[data-preview="offline"]').check();
  check('offline banner is a status', (await page.locator('[data-testid="offline-banner"]').getAttribute('role')) === 'status');
  check('offline sync is disabled', await page.locator('[data-testid="sync-action"]').isDisabled());
  check('offline sync reason is visible', (await text(page, '[data-testid="sync-reason"]')).includes('当前离线'));
  await page.locator('[data-preview="offline"]').uncheck();

  // Forks: metadata, active branch, explicit choice callback.
  await page.locator('[data-testid="fork-snap_a"]').check();
  check('fork choice reaches the callback', (await text(page, '[data-testid="preview-note"]')).includes('snap_a'));
  check('fork choice switches the active branch', await page.locator('[data-testid="fork-snap_a"]').isChecked());
  await page.locator('[data-preview="fork-wired"]').uncheck();
  check('unwired fork choice is disabled', await page.locator('[data-testid="fork-snap_b"]').isDisabled());
  check('unwired fork choice states why', (await text(page, '[data-testid="fork-reason"]')).includes('分叉选择尚未接线'));

  // Cancel wiring after all state switches.
  await page.locator('[data-preview="cancel-wired"]').check();
  await page.locator('[data-preview="narration-streaming"]').click();
  check('wired cancel is enabled during a round', !(await page.locator('[data-testid="cancel-action"]').isDisabled()));
  await page.locator('[data-testid="cancel-action"]').click();
  check('cancel reaches the callback', (await text(page, '[data-testid="preview-note"]')).includes('取消回调已触发'));

  // Mobile layout must not scroll sideways.
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check('mobile preview has no horizontal overflow', overflow <= 1, `overflow=${overflow}px`);

  if (process.env.SHOT) {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: process.env.SHOT, fullPage: false });
  }
} finally {
  await browser.close();
}

const failed = checks.filter((entry) => !entry.pass);
for (const entry of checks) {
  console.log(`${entry.pass ? 'PASS' : 'FAIL'}  ${entry.name}${entry.detail ? ` (${entry.detail})` : ''}`);
}
console.log(`\n${checks.length - failed.length}/${checks.length} checks passed`);
if (failed.length > 0) process.exitCode = 1;
