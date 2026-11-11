import { expect, test } from "@playwright/test";

import { installApiMocks, seedSession, storyOutput } from "./fixtures";

/**
 * The only spec that runs with the typewriter enabled: everything else seeds
 * `jity_typewriter=off` so it can assert on the finished scene.
 *
 * The reveal is ~40 characters/second, so the full fixture narration needs
 * roughly fifteen seconds. The waits below are generous on purpose; the point
 * is the ordering (text → options → controls), not the exact clock.
 */
test.use({ reducedMotion: "no-preference" });

const FULL_LENGTH = storyOutput.narration.replace(/\s+/g, "").length;
const TAIL = "你咽了口唾沫";

function visibleLength(page: import("@playwright/test").Page): Promise<number> {
  return page.locator(".narration").evaluate(
    (element) => (element.textContent ?? "").replace(/\s+/g, "").length,
  );
}

test("narration types out, locks the controls, and only then reveals options", async ({ page }) => {
  await seedSession(page, { typewriter: true });
  await installApiMocks(page);
  await page.setViewportSize({ width: 1536, height: 730 });
  await page.goto("/");

  await page.waitForSelector(".narration", { state: "attached" });
  await page.waitForLoadState("networkidle");

  // Characters are landing, but the turn is not finished yet.
  await expect.poll(() => visibleLength(page)).toBeGreaterThan(0);
  await expect.poll(async () => (await visibleLength(page)) < FULL_LENGTH).toBe(true);

  // While the text is still being revealed the options are absent and both
  // controls are locked.
  await expect(page.locator(".option-button")).toHaveCount(0);
  await expect(page.locator("#action")).toBeDisabled();
  await expect(page.locator(".player-controls-row > button")).toBeDisabled();

  // The body is display-only: clicking it must not skip to the end.
  const beforeClick = await visibleLength(page);
  await page.locator(".narration").click();
  await page.waitForTimeout(300);
  const afterClick = await visibleLength(page);
  expect(afterClick).toBeGreaterThanOrEqual(beforeClick);
  expect(afterClick).toBeLessThan(FULL_LENGTH);
  await expect(page.locator(".option-button")).toHaveCount(0);

  // Once the reveal completes, dialogue and options arrive and the input
  // unlocks again.
  await expect(page.locator(".narration")).toContainText(TAIL, { timeout: 45_000 });
  await expect(page.locator(".dialogue-line").first()).toBeVisible();
  await expect(page.locator(".option-button")).toHaveCount(storyOutput.options.length);
  await expect(page.locator("#action")).toBeEnabled();
});
