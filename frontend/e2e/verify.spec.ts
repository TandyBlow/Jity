import { expect, test } from "@playwright/test";

import { SESSION_ID, installApiMocks, seedSession } from "./fixtures";

/**
 * Compares the live app against the recorded baseline in docs/frontend-baseline.
 *
 * A failing assertion prints the number of differing pixels and writes
 * `*-actual.png` / `*-diff.png` next to the baseline (both gitignored).
 *
 * Run: npx playwright test e2e/verify.spec.ts
 */

const VIEWPORTS = [
  { name: "1536x730", width: 1536, height: 730 },
  { name: "1024x768", width: 1024, height: 768 },
];

const SHOTS = [
  { name: "console", path: "/", ready: ".narration" },
  { name: "timeline-story", path: `/timeline?session=${SESSION_ID}`, ready: ".story-timeline-layout" },
  { name: "timeline-anchors", path: `/timeline?session=${SESSION_ID}&tab=anchors`, ready: ".anchor-tree" },
  { name: "timeline-clues", path: `/timeline?session=${SESSION_ID}&tab=clues`, ready: ".clue-board" },
  { name: "curator", path: "/curator", ready: ".timeline-layout" },
  { name: "dev-log", path: "/dev-log", ready: ".dev-log-list" },
];

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
