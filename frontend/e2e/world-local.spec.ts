import { expect, test } from '@playwright/test';

/** Real product page: model load, two inputs, pause/resume, reload restore and
 * a read-only history selection. Narration regeneration is covered by unit
 * tests until the page grows a visible delete control. */
test.use({
  launchOptions: { args: ['--enable-unsafe-webgpu', '--force_high_performance_gpu', '--ignore-gpu-blocklist'] },
});

const ready = async (page: import('@playwright/test').Page, timeout = 240_000) => {
  await page.waitForFunction(
    () => /本地世界已就绪|已恢复本地存档/.test(document.body.innerText),
    null,
    { timeout },
  );
};

async function play(page: import('@playwright/test').Page, text: string) {
  const before = await page.evaluate(() => (globalThis as { __worldTurns?: unknown[] }).__worldTurns?.length ?? 0);
  await page.fill('textarea', text);
  await page.click('button:has-text("行动")');
  // The page pushes its turn record at submit; wait for that record, let the
  // busy effect publish, then wait until the page leaves the settlement stage.
  await page.waitForFunction(
    (count) => {
      const app = globalThis as { __worldTurns?: unknown[] };
      return Array.isArray(app.__worldTurns) && app.__worldTurns.length > count;
    },
    before,
    { timeout: 30_000 },
  );
  await page.waitForTimeout(500);
  await page.waitForFunction(
    () => {
      const app = globalThis as { __worldBusy?: boolean };
      return app.__worldBusy !== true && !/结算中|正在写正文/.test(document.body.innerText);
    },
    null,
    { timeout: 330_000 },
  );
}

test.describe('world-local product page', () => {
  test.setTimeout(900_000);

  test('plays, pauses, restores and keeps history read-only', async ({ page }) => {
    await page.goto('/world-local');
    await ready(page);

    expect(await page.evaluate(() => globalThis.crossOriginIsolated === true)).toBe(true);
    const arm = await page.evaluate(() => (globalThis as { __worldArm?: { narrationModel?: string; narrationSha256?: string } }).__worldArm ?? null);
    expect(arm?.narrationModel).toBe('qwen3-1.7b');
    expect(arm?.narrationSha256).toHaveLength(64);

    await play(page, '我在墙边站一会儿，侧耳听服务巷外面的脚步声和远处的枪声。');
    await play(page, '我蹲下检查脚边的地面和墙根，看看有没有新的脚印或擦痕。');

    // Pause keeps the frozen record; resume continues the same session.
    const headBeforePause = await page.evaluate(() => (globalThis as { __worldSnapshot?: () => { transport: { headPointId: string } } }).__worldSnapshot?.().transport.headPointId);
    await page.click('button:has-text("暂停")', { timeout: 30_000 });
    await page.waitForFunction(
      () => (globalThis as { __worldSnapshot?: () => { transport: { control: { paused: boolean } } } }).__worldSnapshot?.().transport.control.paused === true,
      null,
      { timeout: 30_000 },
    );
    await page.click('button:has-text("继续")', { timeout: 30_000 });
    await page.waitForFunction(
      () => (globalThis as { __worldSnapshot?: () => { transport: { control: { paused: boolean } } } }).__worldSnapshot?.().transport.control.paused === false,
      null,
      { timeout: 30_000 },
    );

    // Reload restores the committed history from IndexedDB.
    await page.reload({ waitUntil: 'domcontentloaded' });
    await ready(page);
    const restored = await page.evaluate(() => (globalThis as { __worldRestore?: { entriesRestored?: number; headPointId?: string } }).__worldRestore ?? null);
    expect(restored?.entriesRestored ?? 0).toBeGreaterThanOrEqual(1);

    // Selecting history is read-only: the head and digest do not move.
    const headBeforeSelect = await page.evaluate(() => (globalThis as { __worldSnapshot?: () => { transport: { headPointId: string; pointStates: Record<string, { stateDigest: string }> } } }).__worldSnapshot?.().transport.headPointId);
    expect(headBeforeSelect).toBe(headBeforePause);
    const historyButton = page.locator('[data-testid="history-panel"] button').first();
    if (await historyButton.count()) {
      await historyButton.click({ timeout: 10_000 });
      const headAfterSelect = await page.evaluate(() => (globalThis as { __worldSnapshot?: () => { transport: { headPointId: string } } }).__worldSnapshot?.().transport.headPointId);
      expect(headAfterSelect).toBe(headBeforeSelect);
    }
  });
});
