import { expect, test } from "@playwright/test";

import { installApiMocks, seedSession } from "./fixtures";

/**
 * B3 confirmed narrow screens are in scope, so the memory column cannot just
 * disappear below 1100px. It becomes a drawer — modal, because a fixed overlay
 * a keyboard user cannot leave is the defect the check overlay already has.
 */
test.describe("below the docked breakpoint", () => {
  test.use({ viewport: { width: 1024, height: 768 } });

  test.beforeEach(async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);
    await page.goto("/");
    await page.waitForSelector(".narration", { state: "attached" });
    await page.waitForLoadState("networkidle");
  });

  test("the docked column is replaced by a trigger", async ({ page }) => {
    await expect(page.locator(".memory-panel")).toBeHidden();
    await expect(page.getByRole("button", { name: "记忆面板" })).toBeVisible();
  });

  test("opening moves focus in and Escape returns it", async ({ page }) => {
    const trigger = page.getByRole("button", { name: "记忆面板" });
    await trigger.click();

    const dialog = page.getByRole("dialog", { name: "记忆面板" });
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveAttribute("aria-modal", "true");
    await expect(dialog.locator(".turn-memory")).toContainText("本轮记忆变更");
    await expect(dialog).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("Tab never leaves the drawer", async ({ page }) => {
    await page.getByRole("button", { name: "记忆面板" }).click();
    const dialog = page.getByRole("dialog", { name: "记忆面板" });
    await expect(dialog).toBeVisible();

    for (let step = 0; step < 8; step += 1) {
      await page.keyboard.press("Tab");
      expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
    }
    for (let step = 0; step < 3; step += 1) {
      await page.keyboard.press("Shift+Tab");
      expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(true);
    }
  });

  test("opening again after a close does not strand focus", async ({ page }) => {
    const trigger = page.getByRole("button", { name: "记忆面板" });
    await trigger.click();
    await page.keyboard.press("Escape");
    await trigger.click();

    await expect(page.getByRole("dialog", { name: "记忆面板" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
  });
});
