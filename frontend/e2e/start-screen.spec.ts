import { expect, test } from "@playwright/test";
import { BUILTIN_CAMPAIGNS } from "../src/lib/game/campaignArtwork";
import { installApiMocks, saveSlots, sessionResponse, SESSION_ID, storyOutput, gameState, MODEL, timelineNodeDetail } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await installApiMocks(page);
  await page.route("**/campaigns", route => route.fulfill({ json: { campaigns: BUILTIN_CAMPAIGNS } }));
});

test("landing stays idle even with a remembered session; all four artworks are local", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("jity_active_session_id", "old-session"));
  const writes: string[] = [];
  page.on("request", request => { if (request.method() === "POST") writes.push(request.url()); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "卡塞尔入学档案" })).toBeVisible();
  await expect(page.getByLabel("自定义回合数")).toHaveValue("50");
  for (const [index, name] of ["cassell", "bronze", "rain", "tokyo"].entries()) {
    await page.locator("#start-campaign").selectOption(BUILTIN_CAMPAIGNS[index].filename);
    const image = page.locator(".start-artwork img.is-selected");
    await expect(image).toHaveAttribute("src", `/images/campaigns/${name}.webp`);
    await expect.poll(() => image.evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
  }
  await page.reload();
  await expect(page.locator(".start-screen")).toBeVisible();
  expect(writes).toEqual([]);
});

test("start sends selected campaign and budget once, then generates its opening", async ({ page }) => {
  const creations: unknown[] = [];
  let openings = 0;
  await page.route("**/sessions", async route => {
    creations.push(route.request().postDataJSON());
    await route.fulfill({ json: { ...sessionResponse, campaign_filename: BUILTIN_CAMPAIGNS[1].filename, active_turn_id: null } });
  });
  await page.route(`**/sessions/${SESSION_ID}/generate`, async route => {
    openings++;
    await route.fulfill({ json: { session_id: SESSION_ID, state: gameState, output: storyOutput, source: "scripted", used_model: MODEL, timeline_node_id: 1, retrieved_chunks: [], model_output_id: 1, memory: timelineNodeDetail.memory, declared: timelineNodeDetail.declared, caps: timelineNodeDetail.caps } });
  });
  await page.goto("/");
  await page.locator("#start-campaign").selectOption(BUILTIN_CAMPAIGNS[1].filename);
  await page.getByRole("button", { name: /30.*标准/ }).click();
  await page.getByRole("button", { name: "开始游戏", exact: true }).click();
  await expect(page.locator(".narration")).toBeVisible();
  expect(creations).toEqual([{ campaign_filename: BUILTIN_CAMPAIGNS[1].filename, arc_index: 0, session_index: 0, max_turns_per_campaign: 30 }]);
  await expect.poll(() => openings).toBe(1);
  await expect(page.locator(".narration")).toContainText(storyOutput.narration.split("\n")[0]);
});

test("loading a save restores its story without creating or generating", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", request => { if (request.method() === "POST") writes.push(new URL(request.url()).pathname); });
  await page.route("**/campaigns/slots/1/load", route => route.fulfill({ json: { session: sessionResponse, slot: saveSlots[0], status: "loaded" } }));
  await page.goto("/");
  await page.getByRole("button", { name: "加载存档", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "继续此存档" }).first().click();
  await expect(page.locator(".narration")).toBeVisible();
  // Restoring a scene may request its artwork, but must not create a session or story turn.
  expect(writes.filter(path => path !== "/backgrounds/generate")).toEqual(["/campaigns/slots/1/load"]);
});

test("save purpose filters stay separate and a legacy save keeps its purpose on load", async ({ page }) => {
  const labels: Record<string, string> = { user: "游玩存档", development: "开发存档", test: "测试存档", legacy: "历史未分类" };
  const seen: string[] = [];
  await page.route("**/campaigns/slots", route => {
    const purpose = route.request().headers()["x-jity-save-purpose"];
    seen.push(purpose);
    return route.fulfill({ json: { slots: [{ ...saveSlots[0], slot_name: `仅${purpose}可见`, save_purpose: purpose }] } });
  });
  await page.route("**/campaigns/slots/1/load", route => route.fulfill({ json: {
    status: "loaded", slot: saveSlots[0], session: { ...sessionResponse, save_purpose: "legacy" },
  } }));
  await page.goto("/");
  await page.getByRole("button", { name: "加载存档", exact: true }).click();
  for (const purpose of ["user", "development", "test", "legacy"]) {
    await page.getByRole("button", { name: labels[purpose], exact: true }).click();
    await expect(page.locator(".start-save")).toHaveCount(1);
    await expect(page.locator(".start-save strong")).toHaveText(`仅${purpose}可见`);
  }
  await page.getByRole("button", { name: "继续此存档" }).click();
  await expect(page.locator(".narration")).toBeVisible();
  await expect.poll(() => seen.at(-1)).toBe("legacy");
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "管理存档" }).click();
  await expect(page.locator(".settings-slot-entry strong")).toHaveText("仅legacy可见");
});

test("a late response from another purpose cannot replace the selected list", async ({ page }) => {
  let release!: () => void;
  const delay = new Promise<void>(resolve => { release = resolve; });
  let oldRequestStarted = false;
  await page.route("**/campaigns/slots", async route => {
    const purpose = route.request().headers()["x-jity-save-purpose"];
    if (purpose === "user") { oldRequestStarted = true; await delay; }
    await route.fulfill({ json: { slots: [{ ...saveSlots[0], slot_name: purpose }] } });
  });
  await page.goto("/");
  await page.getByRole("button", { name: "加载存档", exact: true }).click();
  await expect.poll(() => oldRequestStarted).toBe(true);
  await page.getByRole("button", { name: "测试存档", exact: true }).click();
  await expect(page.locator(".start-save strong")).toHaveText("test");
  const oldResponse = page.waitForResponse(response => response.url().endsWith("/campaigns/slots")
    && response.request().headers()["x-jity-save-purpose"] === "user");
  release();
  await oldResponse;
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.locator(".start-save strong")).toHaveText("test");
  await expect(page.getByRole("button", { name: "确认删除", exact: true })).toBeVisible();
});

for (const entry of ["加载存档", "存档管理"]) {
test(`${entry} confirms active-save deletion and allows cancellation`, async ({ page }) => {
  const deletes: string[] = [];
  await page.route("**/campaigns/slots/1", async route => { deletes.push(route.request().method()); await route.fulfill({ json: { status: "deleted" } }); });
  await page.goto("/");
  await page.getByRole("button", { name: entry, exact: true }).click();
  await page.locator(".start-save").first().getByRole("button", { name: "删除", exact: true }).click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(page.locator(".start-save")).toHaveCount(2);
  expect(deletes).toEqual([]);
  await page.locator(".start-save").first().getByRole("button", { name: "删除", exact: true }).click();
  expect(deletes).toEqual([]);
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.locator(".start-save")).toHaveCount(1);
  expect(deletes).toEqual(["DELETE"]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: entry, exact: true })).toBeFocused();
});
}

test("failed creation stays on the start page and invalid lengths cannot submit", async ({ page }) => {
  let calls = 0;
  await page.route("**/sessions", async route => { calls++; await route.fulfill({ status: 503, json: { detail: "服务暂时不可用" } }); });
  await page.goto("/");
  await page.getByLabel("自定义回合数").fill("51");
  await page.getByRole("button", { name: "开始游戏", exact: true }).click();
  expect(calls).toBe(0);
  await page.getByLabel("自定义回合数").fill("50");
  await page.getByRole("button", { name: "开始游戏", exact: true }).click();
  await expect(page.locator(".start-controls [role=alert]")).toHaveText("服务暂时不可用");
  await expect(page.locator(".start-screen")).toBeVisible();
  expect(calls).toBe(1);
});

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`layout is usable at ${viewport.width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.locator(".start-artwork img.is-selected")).toBeVisible();
    await expect.poll(() => page.locator(".start-artwork img.is-selected").evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
    const controls = await page.locator(".start-controls").boundingBox();
    expect(controls!.x).toBeGreaterThan(15);
    expect(viewport.width - controls!.x - controls!.width).toBeGreaterThan(15);
    expect(controls!.y + controls!.height).toBeLessThan(viewport.height - 30);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(viewport.width);
    await page.screenshot({ path: testInfo.outputPath(`start-${viewport.width}.png`), fullPage: true });
  });
}
