import { expect, test } from "@playwright/test";
import entries from "../../docs/dev-log/entries.json";

test("the development log reads its documentation archive and retains search and filters", async ({ page }) => {
  await page.goto("/dev-log");
  const cards = page.locator(".dev-log-entry");
  await expect(cards).toHaveCount(entries.length);
  await expect(cards.first()).toContainText(entries[0].title);
  await expect(cards.last()).toContainText(entries[entries.length - 1].title);
  await page.locator("#dev-log-search").fill(entries[0].title);
  await expect(cards).toHaveCount(1);
  await expect(cards.first()).toContainText(entries[0].summary);
  await page.locator("#dev-log-search").fill("");
  const area = entries[0].areas[0];
  await page.locator("#dev-log-area").selectOption(area);
  await expect(cards).toHaveCount(entries.filter(entry => entry.areas.includes(area)).length);
  await page.locator("#dev-log-search").fill("no-such-development-entry-7391");
  await expect(page.getByText("没有匹配的开发日志。")).toBeVisible();
  await page.locator("#dev-log-search").fill("");
  await page.locator("#dev-log-area").selectOption("all");
  await expect(cards).toHaveCount(entries.length);
});
