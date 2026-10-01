import { expect, test } from "@playwright/test";
import type { Route } from "@playwright/test";

import { SESSION_ID, installApiMocks, seedSession } from "./fixtures";

/**
 * A failed fetch used to fall back to an empty value, which renders exactly
 * like a result that is genuinely empty: an empty tree, an empty picker. Each
 * test forces one request to fail and checks that the page says so, and that
 * the "there is nothing here" wording stays away.
 *
 * Routes registered here come after installApiMocks' catch-all, so they win.
 */

const SERVER_MESSAGE = "后端挂了";

function fail(route: Route) {
  return route.fulfill({
    status: 500,
    contentType: "application/json",
    body: JSON.stringify({ detail: SERVER_MESSAGE }),
  });
}

test("a failed timeline load names itself on every tab", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  // The trailing wildcard covers a query string; it still cannot match the
  // deeper /timeline/<nodeId> path, because `*` does not cross a slash.
  await page.route("**/sessions/*/timeline*", fail);

  await page.goto(`/timeline?session=${SESSION_ID}`);

  const banner = page.locator(".load-error");
  await expect(banner).toContainText("剧情时间线加载失败");

  // The whole point: a broken load must not read as an empty session.
  await expect(page.getByText("当前会话还没有可显示的剧情节点")).toHaveCount(0);

  // The banner lives above the tab list, so it is not tied to one panel.
  await page.getByRole("tab", { name: "战役锚点" }).click();
  await expect(banner).toBeVisible();
});

test("naming a new slot opens an in-page field, not a native dialog", async ({ page }) => {
  const dialogs: string[] = [];
  page.on("dialog", (dialog) => {
    dialogs.push(dialog.message());
    void dialog.dismiss();
  });

  await seedSession(page);
  await installApiMocks(page);
  await page.goto("/");
  await page.waitForSelector(".narration", { state: "attached" });

  await page.getByRole("button", { name: "设置" }).click();
  await page.getByRole("button", { name: "新增存档" }).click();

  await expect(page.getByLabel("新存档名称")).toBeVisible();
  expect(dialogs).toEqual([]);
});

test("a rejected slot name is reported beside the field it came from", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  // Reading the slot list hits the same path, so only the write may fail.
  await page.route("**/campaigns/slots*", (route) =>
    route.request().method() === "POST" ? fail(route) : route.fallback(),
  );

  await page.goto("/");
  await page.waitForSelector(".narration", { state: "attached" });

  await page.getByRole("button", { name: "设置" }).click();
  await page.getByRole("button", { name: "新增存档" }).click();

  const name = page.getByLabel("新存档名称");
  await name.fill("测试存档");
  await page.getByRole("button", { name: "确定" }).click();

  await expect(page.locator(".settings-slot-error")).toContainText(SERVER_MESSAGE);
  // The name survives, so the retry does not start from scratch.
  await expect(name).toHaveValue("测试存档");
});
