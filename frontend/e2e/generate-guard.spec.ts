import { expect, test } from "@playwright/test";

import { installApiMocks, seedSession } from "./fixtures";

/**
 * An empty textarea left the generate button enabled, so clicking it did
 * nothing and said nothing. The button now reports whether there is an action
 * to send.
 */

async function openConsole(page: import("@playwright/test").Page) {
  await seedSession(page);
  await installApiMocks(page);
  await page.goto("/");
  await page.waitForSelector(".narration", { state: "attached" });
  await page.waitForLoadState("networkidle");
}

test("the generate button follows the textarea", async ({ page }) => {
  await openConsole(page);

  const button = page.locator(".player-controls-row > button");
  const textarea = page.locator("#action");

  await expect(textarea).toHaveValue("");
  await expect(button).toBeDisabled();

  await textarea.fill("推开报到处的大门。");
  await expect(button).toBeEnabled();

  // Whitespace is not an action, and `handleGenerate` trims before it decides.
  await textarea.fill("   ");
  await expect(button).toBeDisabled();
});

test("an empty textarea does not block the option buttons", async ({ page }) => {
  await openConsole(page);

  await expect(page.locator("#action")).toHaveValue("");
  await expect(page.locator(".option-button").first()).toBeEnabled();
});
