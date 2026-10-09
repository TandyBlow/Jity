import { expect, test } from "@playwright/test";
import type { Route } from "@playwright/test";

import {
  ACTIVE_TURN_ID, MODEL, SESSION_ID, gameState, installApiMocks,
  saveSlots, seedSession, sessionResponse, storyOutput, timelineNodeDetail,
} from "./fixtures";

const progress = {
  turns_total: 7, max_turns_per_campaign: 50,
  arc_index: 0, arc_name: "第一幕", arc_goal: "调查",
  session_index: 0, session_name: "入学日", current_goal: "完成报到",
  campaign_title: "进度测试",
};

const json = (route: Route, body: unknown) => route.fulfill({
  contentType: "application/json", body: JSON.stringify(body),
});

test("switching to free play hides the previous campaign while progress loads", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  await page.route(`**/sessions/${SESSION_ID}/progress`, route => json(route, progress));
  const nextSession = "free-play-test-session";
  await page.route("**/sessions", route => json(route, {
    ...sessionResponse, session_id: nextSession, campaign_filename: null,
    active_turn_id: 99, state: { ...gameState, turn: 0 },
  }));
  let release!: () => void;
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/sessions/${nextSession}/progress`, async route => {
    await delayed;
    await json(route, {});
  });

  await page.goto("/");
  const toolbar = page.locator(".toolbar-row");
  await expect(toolbar).toContainText("第 7 / 50 回合");
  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.locator("#settings-campaign")).toBeEnabled();
  await page.locator("#settings-campaign").selectOption("");
  try {
    await expect(toolbar).toContainText("Session free-pla");
    await expect(toolbar).toContainText("Turn 0");
    await expect(toolbar).not.toContainText("第 7 / 50 回合");
  } finally {
    release();
  }
});

test("restoring a slot with the same session and turn refreshes its budget", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  let restored = false;
  let release!: () => void;
  const delayed = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/sessions/${SESSION_ID}/progress`, async route => {
    if (restored) await delayed;
    await json(route, { ...progress, turns_total: restored ? 4 : 7 });
  });
  await page.route("**/campaigns/slots/2/load", route => {
    restored = true;
    return json(route, { status: "loaded", slot: saveSlots[1], session: sessionResponse });
  });

  await page.goto("/");
  const toolbar = page.locator(".toolbar-row");
  await expect(toolbar).toContainText("第 7 / 50 回合");
  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.locator("#settings-slot")).toBeEnabled();
  await page.locator("#settings-slot").selectOption("2");
  try {
    await expect(page.locator("#settings-slot")).toBeEnabled();
    await expect(toolbar).not.toContainText("第 7 / 50 回合");
    release();
    await expect(toolbar).toContainText("第 4 / 50 回合");
  } finally {
    release();
  }
});

test("a legacy progress response never displays an undefined turn cap", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  await page.route(`**/sessions/${SESSION_ID}/progress`, route => json(route, { turns_total: 7 }));
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  const toolbar = page.locator(".toolbar-row");
  await expect(toolbar).toContainText("Turn 7");
  await expect(toolbar).not.toContainText("undefined");
});

test("the closing response updates the budget and disables further actions", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  const ending = {
    ...storyOutput, narration: "调查在黎明结束。", options: [], option_checks: [],
    game_over: true, game_over_reason: "回合预算耗尽·未完成的调查",
  };
  let ended = false;
  await page.route(`**/sessions/${SESSION_ID}/progress`, route =>
    json(route, { ...progress, turns_total: ended ? 50 : 49 }));
  await page.route(`**/sessions/${SESSION_ID}/generate`, route => {
    ended = true;
    return json(route, {
      session_id: SESSION_ID, state: { ...gameState, turn: 50 }, output: ending,
      retrieved_chunks: [], model_output_id: 42, used_model: MODEL, source: "llm",
      timeline_node_id: ACTIVE_TURN_ID + 1, parent_timeline_node_id: ACTIVE_TURN_ID,
      campaign_progress: { ...progress, turns_total: 50 },
      memory: timelineNodeDetail.memory, declared: timelineNodeDetail.declared,
      caps: timelineNodeDetail.caps,
    });
  });
  await page.route(`**/sessions/${SESSION_ID}`, route => json(route, ended
    ? { ...sessionResponse, active_turn_id: ACTIVE_TURN_ID + 1, state: { ...gameState, turn: 50 } }
    : sessionResponse));
  await page.route(`**/sessions/${SESSION_ID}/timeline/*`, route => json(route, ended
    ? { ...timelineNodeDetail, id: ACTIVE_TURN_ID + 1, state: { ...gameState, turn: 50 }, output: ending }
    : timelineNodeDetail));

  await page.goto("/");
  await expect(page.locator(".toolbar-row")).toContainText("第 49 / 50 回合");
  await expect(page.locator(".option-button").first()).toBeEnabled();
  await page.locator(".option-button").first().click();
  await expect(page.locator(".toolbar-row")).toContainText("第 50 / 50 回合");
  await expect(page.locator(".ending-card")).toContainText("回合预算耗尽");
  await expect(page.locator("#action")).toBeDisabled();
  await expect(page.locator(".player-controls-row > button")).toBeDisabled();
  await page.reload();
  await expect(page.locator(".ending-card")).toContainText("回合预算耗尽");
  await expect(page.locator("#action")).toBeDisabled();
  await expect(page.locator(".toolbar-row")).toContainText("第 50 / 50 回合");
});
