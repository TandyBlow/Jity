import fs from "node:fs";
import path from "node:path";

import { test } from "@playwright/test";

import { SESSION_ID, installApiMocks, seedSession } from "./fixtures";

/**
 * Layout probe: dumps numeric geometry for every route so layout problems are
 * stated as measurements rather than impressions.
 *
 * Like capture, this is opt-in: without BASELINE_DIR it skips, because its
 * output is the tracked reference and a plain test run must not move it.
 *
 *   BASELINE_DIR=docs/frontend-baseline npx playwright test e2e/probe.spec.ts
 *
 * PROBE_OUT overrides the file name; relative paths resolve like BASELINE_DIR.
 */

const RECORD_DIR = process.env.BASELINE_DIR;

test.skip(
  !RECORD_DIR,
  "Recording is opt-in: set BASELINE_DIR to the directory to record into.",
);

const VIEWPORTS = [
  { name: "1536x730", width: 1536, height: 730 },
  { name: "1024x768", width: 1024, height: 768 },
];

const PAGES = [
  { name: "console", path: "/", ready: ".narration" },
  { name: "timeline-story", path: `/timeline?session=${SESSION_ID}`, ready: ".story-timeline-layout" },
  { name: "timeline-anchors", path: `/timeline?session=${SESSION_ID}&tab=anchors`, ready: ".anchor-tree" },
  { name: "timeline-clues", path: `/timeline?session=${SESSION_ID}&tab=clues`, ready: ".clue-board" },
  { name: "curator", path: "/curator", ready: ".timeline-layout" },
  { name: "dev-log", path: "/dev-log", ready: ".dev-log-list" },
];

const report: Record<string, unknown> = {};

for (const page of PAGES) {
  test(`probe ${page.name}`, async ({ page: browserPage }) => {
    await seedSession(browserPage);
    await installApiMocks(browserPage);

    for (const viewport of VIEWPORTS) {
      await browserPage.setViewportSize({ width: viewport.width, height: viewport.height });
      await browserPage.goto(page.path);
      await browserPage.waitForSelector(page.ready, { state: "attached" });
      await browserPage.waitForLoadState("networkidle");
      await browserPage.evaluate(() => document.fonts.ready);
      await browserPage.waitForTimeout(300);

      report[`${page.name}@${viewport.name}`] = await browserPage.evaluate((selectors: string[]) => {
        const measure = (selector: string) => {
          const element = document.querySelector(selector);
          if (!element) return null;
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return {
            top: Math.round(rect.top),
            left: Math.round(rect.left),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            contentHeight: (element as HTMLElement).scrollHeight,
            display: style.display,
            overflowY: style.overflowY,
            fontSize: style.fontSize,
            color: style.color,
            background: style.backgroundColor,
          };
        };

        const boxes: Record<string, unknown> = {};
        for (const selector of selectors) boxes[selector] = measure(selector);

        return {
          viewport: { w: window.innerWidth, h: window.innerHeight },
          documentScrollHeight: document.documentElement.scrollHeight,
          inlineStyledElements: document.querySelectorAll("[style]").length,
          boxes,
        };
      }, [
        ".app-shell",
        ".game-brand",
        ".settings-menu",
        ".story-panel",
        ".scene-output",
        ".narration",
        ".dialogue-list",
        ".option-list",
        ".player-controls",
        ".memory-panel",
        ".timeline-shell",
        ".timeline-header",
        ".timeline-tabs",
        ".timeline-layout",
        ".timeline-tab-panel",
        ".story-timeline-layout",
        ".turn-navigator",
        ".story-tree-scroll",
        ".anchor-tree",
        ".clue-board",
        ".dev-log-list",
      ]);
    }
  });
}

test.afterAll(() => {
  // Skipped files still reach this hook, so the guard has to be here too.
  if (!RECORD_DIR) return;
  const outPath = process.env.PROBE_OUT
    ? path.resolve(__dirname, "../..", process.env.PROBE_OUT)
    : path.resolve(__dirname, "../..", RECORD_DIR, "layout-probe.json");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2), "utf8");
});
