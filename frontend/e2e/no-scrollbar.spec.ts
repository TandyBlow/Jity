import { expect, test } from "@playwright/test";

import { SHOTS, VIEWPORTS, installApiMocks, seedSession } from "./fixtures";

/**
 * A painted scrollbar is chrome the design does not want.
 *
 * Running this is opt-in. It has to be headed: headless Chromium never paints a
 * scrollbar, so every gutter it reports is zero and an absence check there
 * passes for the wrong reason. A real window is what makes the measurement mean
 * anything, and a real window on every full test run is a nuisance.
 *
 *   NO_SCROLLBAR=1 npx playwright test e2e/no-scrollbar.spec.ts
 *
 * "A scrollbar exists" is measured, not assumed. A classic scrollbar occupies
 * layout space, so the gutter on an axis — `offset` minus `client` minus the
 * borders on that axis — is non-zero exactly when a bar is drawn. Borders have
 * to come out or every bordered element reports one. Only scroll containers are
 * tested, because only they can paint a bar; the viewport is tested separately
 * since `<html>` never says `overflow: auto` yet still grows a page scrollbar.
 *
 * This asserts the bar is not drawn, not that content never overflows —
 * scroll containers are expected to overflow.
 */
const ENABLED = process.env.NO_SCROLLBAR;

test.skip(!ENABLED, "Opt-in, and headed: set NO_SCROLLBAR=1 to run it.");

test.use({ headless: false });

/** Sub-pixel border rounding leaves noise under 1px; real bars are ~15px. */
const TOLERANCE = 1;

const scan = (tolerance: number) => {
  const label = (el: HTMLElement) => {
    if (el === document.documentElement) return "viewport";
    const classes = typeof el.className === "string" ? el.className.trim().split(/\s+/).filter(Boolean) : [];
    return el.tagName.toLowerCase() + (el.id ? `#${el.id}` : "") + classes.map((name) => `.${name}`).join("");
  };

  const SCROLLS = ["auto", "scroll", "overlay"];
  const hits: string[] = [];

  // The page scrollbar is measured against the window: `innerWidth` counts the
  // bar, the root's `clientWidth` does not.
  const pageX = window.innerWidth - document.documentElement.clientWidth;
  const pageY = window.innerHeight - document.documentElement.clientHeight;
  if (pageX > tolerance) hits.push(`viewport vertical ${pageX}px`);
  if (pageY > tolerance) hits.push(`viewport horizontal ${pageY}px`);

  for (const el of document.querySelectorAll("*")) {
    if (!(el instanceof HTMLElement)) continue;
    const style = getComputedStyle(el);

    if (SCROLLS.includes(style.overflowY)) {
      const gutter =
        el.offsetWidth - el.clientWidth - parseFloat(style.borderLeftWidth) - parseFloat(style.borderRightWidth);
      if (gutter > tolerance) hits.push(`${label(el)} vertical ${Math.round(gutter)}px`);
    }

    if (SCROLLS.includes(style.overflowX)) {
      const gutter =
        el.offsetHeight - el.clientHeight - parseFloat(style.borderTopWidth) - parseFloat(style.borderBottomWidth);
      if (gutter > tolerance) hits.push(`${label(el)} horizontal ${Math.round(gutter)}px`);
    }
  }

  return hits;
};

for (const shot of SHOTS) {
  test(`no scrollbar on ${shot.name}`, async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);

    for (const viewport of VIEWPORTS.filter((v) => !shot.only || shot.only.includes(v.name))) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto(shot.path);

      await page.waitForSelector(shot.ready, { state: "attached" });
      await page.waitForLoadState("networkidle");
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(400);

      const hits = await page.evaluate(scan, TOLERANCE);
      expect(hits, `${shot.name} at ${viewport.name} paints a scrollbar`).toEqual([]);
    }
  });
}

/**
 * The absence checks above pass trivially in any browser that cannot draw a
 * scrollbar, which is exactly how headless behaves. Forcing one back on proves
 * this run is capable of seeing what it claims is absent.
 */
test("a forced scrollbar is visible to this run", async ({ page }) => {
  await page.goto("/");
  await page.addStyleTag({
    content: `
      html { height: 300vh !important; }
      html, body { scrollbar-width: auto !important; }
      *::-webkit-scrollbar { display: block !important; width: 15px !important; }
    `,
  });

  const width = await page.evaluate(() => window.innerWidth - document.documentElement.clientWidth);
  expect(width, "this browser renders no scrollbar, so the absence checks prove nothing").toBeGreaterThan(TOLERANCE);
});
