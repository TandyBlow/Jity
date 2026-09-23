import { expect, test } from "@playwright/test";

import { installApiMocks, seedSession } from "./fixtures";

/**
 * A11: the check overlay was a full-screen fixed layer with only an
 * aria-label. A keyboard user who reached it had no Escape and, once the roll
 * was under way, no visible control at all.
 */
test.describe("the action check overlay", () => {
  test.beforeEach(async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);
    await page.setViewportSize({ width: 1536, height: 730 });
    await page.goto("/");
    await page.waitForSelector(".narration", { state: "attached" });
    await page.waitForLoadState("networkidle");
  });

  // The second fixture option is the one carrying an option_check.
  const checkedOption = (page: import("@playwright/test").Page) => page.locator(".option-button").nth(1);

  test("is announced as a modal dialog", async ({ page }) => {
    await checkedOption(page).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  test("Escape closes it and returns focus to the option", async ({ page }) => {
    await checkedOption(page).click();
    await expect(page.getByRole("dialog")).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(page.locator(".main-check-overlay")).toHaveCount(0);
    await expect(checkedOption(page)).toBeFocused();
  });

  test("Tab never leaves the overlay", async ({ page }) => {
    await checkedOption(page).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();

    for (let step = 0; step < 6; step += 1) {
      await page.keyboard.press("Tab");
      expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
    }
  });
});
