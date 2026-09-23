import path from "node:path";

import { test } from "@playwright/test";

import { SESSION_ID, installApiMocks, seedSession } from "./fixtures";

/**
 * Visual baseline capture.
 *
 * Every route is rendered against frozen API fixtures, at two viewports, and
 * written to a flat directory. Run it once before touching CSS, and again after
 * (`BASELINE_DIR=...`); the two directories must be pixel-identical except for
 * the intentional fixes listed in the plan.
 *
 * 1024x768 is chosen deliberately: it lands in the 900-1100px band where
 * globals.css currently has no rules at all.
 */

const VIEWPORTS = [
  { name: "1440x900", width: 1440, height: 900 },
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

const OUT_DIR = process.env.BASELINE_DIR
  ? path.resolve(process.env.BASELINE_DIR)
  : path.resolve(__dirname, "../../docs/frontend-baseline");

for (const shot of SHOTS) {
  test(`capture ${shot.name}`, async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);

    for (const viewport of VIEWPORTS) {
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
