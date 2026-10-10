import { expect, test } from "@playwright/test";
import { SESSION_ID, installApiMocks, saveSlots, seedSession, timelineNodeDetail } from "./fixtures";

for (const viewport of [{ width: 1536, height: 730 }, { width: 390, height: 844 }]) {
  test(`slot deletion is explicit and isolated at ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await seedSession(page);
    await installApiMocks(page);
    let slots = [saveSlots[0], { ...saveSlots[1], slot_name: "同名存档" },
      { ...saveSlots[1], id: 3, campaign_id: "another-session", slot_name: "同名存档" }];
    const deleted: number[] = [];
    let loads = 0;
    let reject = false;
    let release!: () => void;
    let delayed: Promise<void> | null = null;
    await page.route("**/campaigns/slots", route => route.fulfill({ json: { slots } }));
    await page.route("**/campaigns/slots/*/load", route => { loads++; return route.abort(); });
    await page.route("**/campaigns/slots/*", async route => {
      if (route.request().method() !== "DELETE") return route.fallback();
      const id = Number(new URL(route.request().url()).pathname.split("/").pop());
      deleted.push(id);
      if (delayed) await delayed;
      if (reject) return route.fulfill({ status: 500, json: { detail: "删除服务暂不可用" } });
      slots = slots.filter(slot => slot.id !== id);
      return route.fulfill({ json: { status: "deleted", slot_id: id, slot_name: "同名存档" } });
    });
    await page.goto("/");
    await expect(page.locator(".option-button").first()).toBeEnabled();
    await page.getByRole("button", { name: "设置", exact: true }).click();
    await expect(page.locator("#settings-slot")).toHaveValue("1");
    await page.getByRole("button", { name: "管理存档" }).click();
    await expect(page.getByTestId("slot-1").getByRole("button", { name: "删除", exact: true })).toBeDisabled();
    const target = page.getByTestId("slot-2");
    await target.getByRole("button", { name: "删除", exact: true }).click();
    await target.getByRole("button", { name: "取消" }).click();
    expect(deleted).toEqual([]);
    expect(loads).toBe(0);
    await target.getByRole("button", { name: "删除", exact: true }).click();
    delayed = new Promise<void>(resolve => { release = resolve; });
    await target.getByRole("button", { name: "确认删除" }).click();
    await expect(target.getByRole("button", { name: "删除中…" })).toBeDisabled();
    await expect(page.locator("#settings-slot")).toBeDisabled();
    release();
    delayed = null;
    await expect(target).toHaveCount(0);
    await expect(page.getByTestId("slot-3")).toBeVisible();
    await expect(page.locator("#settings-slot")).toHaveValue("1");
    expect(deleted).toEqual([2]);
    expect(loads).toBe(0);
    reject = true;
    const other = page.getByTestId("slot-3");
    await other.getByRole("button", { name: "删除", exact: true }).click();
    await other.getByRole("button", { name: "确认删除" }).click();
    await expect(page.getByRole("region", { name: "存档管理" }).getByRole("alert")).toContainText("删除服务暂不可用");
    await expect(other).toBeVisible();
    await expect(other.getByRole("button", { name: "确认删除" })).toBeEnabled();
    expect(loads).toBe(0);
    await expect(page.locator("#settings-slot")).toHaveValue("1");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: test.info().outputPath(`slot-management-${viewport.width}.png`) });
  });
}

for (const failRefresh of [false, true]) {
  test(`409 refresh ${failRefresh ? "reports failure" : "restores the current node"}`, async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);
    let conflict = false;
    await page.route(`**/sessions/${SESSION_ID}/generate`, route => {
      conflict = true;
      return route.fulfill({ status: 409, json: { detail: "节点已改变" } });
    });
    await page.route(`**/sessions/${SESSION_ID}`, route => conflict && failRefresh
      ? route.fulfill({ status: 503, json: { detail: "刷新服务暂不可用" } }) : route.fallback());
    await page.route(`**/sessions/${SESSION_ID}/timeline/*`, route => conflict
      ? route.fulfill({ json: { ...timelineNodeDetail, output: { ...timelineNodeDetail.output, narration: "已恢复当前节点" } } })
      : route.fallback());
    await page.goto("/");
    await expect(page.locator(".option-button").first()).toBeEnabled();
    await page.locator("#action").fill("继续");
    await page.locator(".player-controls-row > button").click();
    if (failRefresh) await expect(page.locator(".error")).toContainText("刷新失败");
    else await expect(page.locator(".narration")).toContainText("已恢复当前节点");
  });
}

test("unlimited inventory never shows a full 20-item cap", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  await page.route(`**/sessions/${SESSION_ID}/timeline/*`, route => route.fulfill({ json: {
    ...timelineNodeDetail, caps: { ...timelineNodeDetail.caps, items: null },
  } }));
  await page.goto("/");
  await expect(page.locator(".memory-panel")).toContainText("无固定上限");
  await expect(page.locator(".memory-panel")).not.toContainText("/20");
});
