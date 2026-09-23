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
 * A35: reading a turn leaves the scene scrolled wherever you stopped, and the
 * next turn replaces the content underneath that offset — so the new turn
 * opened part-way through its own narration.
 */
test("a new turn opens at the top of the scene", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  // Registered after the catch-all so this path wins.
  await page.route(`**/sessions/${SESSION_ID}/generate`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        session_id: SESSION_ID,
        state: gameState,
        output: storyOutput,
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
    }),
  );

  await page.setViewportSize({ width: 1536, height: 730 });
  await page.goto("/");
  await page.waitForSelector(".narration", { state: "attached" });
  await page.waitForLoadState("networkidle");

  const scene = page.locator(".scene-output");
  const scrollable = await scene.evaluate((el) => el.scrollHeight > el.clientHeight);
  expect(scrollable, "the fixture scene must be tall enough to scroll").toBe(true);

  await scene.evaluate((el) => { el.scrollTop = el.scrollHeight; });
  expect(await scene.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);

  // Generating straight from the textarea needs text in it; picking an option
  // is the path that always carries an action.
  await page.locator(".option-button").first().click();

  await expect.poll(() => scene.evaluate((el) => el.scrollTop)).toBe(0);
});
