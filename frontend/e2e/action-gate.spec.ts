import { expect, test } from "@playwright/test";

import {
  ACTIVE_TURN_ID,
  MODEL,
  SESSION_ID,
  gameState,
  installApiMocks,
  seedSession,
  storyOutput,
  timelineNodeDetail,
} from "./fixtures";

/**
 * Track behaviour is verified from the outside only:
 * - `?typing=off` must skip both animations and land on the narration.
 * - with animation on, the gate appears first and holds the narration back.
 */

const NEXT_NARRATION = "行动检查结束，场景继续。";

async function mockGenerate(page: import("@playwright/test").Page, delayMs = 0) {
  await page.route(`**/sessions/${SESSION_ID}/generate`, async (route) => {
    if (delayMs > 0) await new Promise((resolve) => setTimeout(resolve, delayMs));
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        session_id: SESSION_ID,
        state: { ...gameState, turn: ACTIVE_TURN_ID + 1 },
        output: { ...storyOutput, narration: NEXT_NARRATION, dialogue: [], options: [], option_checks: [] },
        retrieved_chunks: [],
        model_output_id: 42,
        used_model: MODEL,
        source: "llm",
        timeline_node_id: ACTIVE_TURN_ID + 1,
        parent_timeline_node_id: ACTIVE_TURN_ID,
        memory: timelineNodeDetail.memory,
        declared: timelineNodeDetail.declared,
        caps: timelineNodeDetail.caps,
      }),
    });
  });
}

test("typing=off skips the gate and goes straight to the narration", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  await mockGenerate(page);

  await page.setViewportSize({ width: 1536, height: 730 });
  await page.goto("/?typing=off");
  await page.waitForSelector(".narration", { state: "attached" });
  await page.waitForLoadState("networkidle");

  await page.locator(".option-button").first().click();

  await expect(page.locator(".narration")).toContainText(NEXT_NARRATION);
  await expect(page.locator('[data-testid="gate-chip"]')).toHaveCount(0);
  await expect(page.locator("#action")).toBeEnabled();
});

test("the gate walks the cast through before the narration starts", async ({ page }) => {
  await seedSession(page, { typewriter: true });
  await installApiMocks(page);
  await mockGenerate(page);

  await page.setViewportSize({ width: 1536, height: 730 });
  await page.goto("/");
  await page.waitForSelector(".narration", { state: "attached" });
  await page.waitForLoadState("networkidle");

  await page.locator(".option-button").first().click();

  // Cast: the player plus the only present fixture NPC.
  const chips = page.locator('[data-testid="gate-chip"]');
  await expect(chips).toHaveCount(2);
  await expect(chips.first()).toBeVisible();
  await expect(page.locator('[data-testid="gate-label"]')).toContainText("行动中");

  // The response is already mocked in, but the gate holds it back and clears
  // the stage: neither the previous nor the new narration may be visible.
  await expect(page.locator(".narration")).not.toContainText(NEXT_NARRATION);
  await expect(page.locator(".narration")).not.toContainText("雨是在你下车后三分钟开始变大的");
  await expect(page.locator("#action")).toBeDisabled();

  // After two one-second passes plus the closing beat the narration starts.
  await expect(page.locator(".narration")).toContainText(NEXT_NARRATION, { timeout: 15_000 });
  await expect(chips).toHaveCount(0, { timeout: 10_000 });
  await expect(page.locator("#action")).toBeEnabled();
});

test("keeps the previous scene on screen while the response is pending", async ({ page }) => {
  // A short opening keeps the initial typewriter reveal quick, so the test can
  // spend its time on the in-flight window instead of on fixture narration.
  const shortOpening = {
    ...timelineNodeDetail,
    output: {
      ...storyOutput,
      narration: "旧的一幕还停在屏幕上。",
      dialogue: [],
      options: ["继续"],
      option_checks: [null],
    },
  };

  await seedSession(page, { typewriter: true });
  await installApiMocks(page);
  await page.route(`**/sessions/${SESSION_ID}/timeline/${ACTIVE_TURN_ID}`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(shortOpening) }),
  );
  await mockGenerate(page, 900);

  await page.setViewportSize({ width: 1536, height: 730 });
  await page.goto("/");
  await page.waitForSelector(".narration", { state: "attached" });
  await expect(page.locator(".option-button").first()).toBeVisible({ timeout: 10_000 });

  await page.locator(".option-button").first().click();

  // In flight: the old scene is still there, and the track has not started.
  await expect(page.locator(".narration")).toContainText("旧的一幕还停在屏幕上");
  await expect(page.locator('[data-testid="gate-chip"]')).toHaveCount(0);
  await expect(page.locator("#action")).toBeDisabled();

  // The response lands: the stage is cleared and the track walks the cast.
  await expect(page.locator('[data-testid="gate-chip"]')).toHaveCount(2, { timeout: 10_000 });
  await expect(page.locator(".narration")).not.toContainText("旧的一幕还停在屏幕上");
  await expect(page.locator(".narration")).not.toContainText(NEXT_NARRATION);

  // After the walk the new text types in and the track gets out of the way.
  await expect(page.locator(".narration")).toContainText(NEXT_NARRATION, { timeout: 15_000 });
  await expect(page.locator('[data-testid="gate-chip"]')).toHaveCount(0, { timeout: 3_000 });
});
