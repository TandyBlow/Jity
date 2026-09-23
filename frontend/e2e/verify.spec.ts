import { expect, test } from "@playwright/test";

import { SHOTS, VIEWPORTS, installApiMocks, seedSession } from "./fixtures";

/**
 * Compares the live app against the recorded baseline in docs/frontend-baseline.
 *
 * A failing assertion prints the number of differing pixels and writes
 * `*-actual.png` / `*-diff.png` next to the baseline (both gitignored).
 *
 * Run: npx playwright test e2e/verify.spec.ts
 */

for (const shot of SHOTS) {
  test(`verify ${shot.name}`, async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);

    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(shot.path);

      await page.waitForSelector(shot.ready, { state: "attached" });
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(400);

      await expect(page).toHaveScreenshot(`${shot.name}--${viewport.name}.png`, {
        animations: "disabled",
        maxDiffPixels: 0,
      });
    }
  });
}
