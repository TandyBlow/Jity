import path from "node:path";

import { test } from "@playwright/test";

import { SHOTS, VIEWPORTS, installApiMocks, seedSession } from "./fixtures";

/**
 * Visual baseline capture — the only thing that writes the recorded baseline.
 *
 * Recording is opt-in. Without BASELINE_DIR this file skips, so a plain
 * `npx playwright test` compares the live app against the recorded baseline
 * instead of overwriting it and then agreeing with itself.
 *
 *   BASELINE_DIR=docs/frontend-baseline npx playwright test e2e/capture.spec.ts
 *
 * Relative paths resolve against the repository root.
 *
 * 1024x768 is chosen deliberately: it lands in the 900-1100px band where
 * globals.css currently has no rules at all.
 */

// 1536x730 is the author's real browser viewport: a 1536x864 screen (125%
// scaling on a 1920x1080 panel), working area 1536x816, minus browser chrome.
// 1024x768 is the narrow-desktop target — it is where the memory panel
// currently dies, and narrow support is confirmed in scope.
const RECORD_DIR = process.env.BASELINE_DIR;

test.skip(
  !RECORD_DIR,
  "Recording is opt-in: set BASELINE_DIR to the directory to record into.",
);

const OUT_DIR = path.resolve(__dirname, "../..", RECORD_DIR ?? "");

for (const shot of SHOTS) {
  test(`capture ${shot.name}`, async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);

    for (const viewport of VIEWPORTS.filter((v) => !shot.only || shot.only.includes(v.name))) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(shot.path);

      await page.waitForSelector(shot.ready, { state: "attached" });
      await page.waitForLoadState("networkidle");
      // Web fonts change text metrics; let them settle before measuring layout.
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(400);

      await page.screenshot({
        path: path.join(OUT_DIR, `${shot.name}--${viewport.name}.png`),
        animations: "disabled",
      });
    }
  });
}
