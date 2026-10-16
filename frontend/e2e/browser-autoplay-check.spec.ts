import { expect, test } from "@playwright/test";

import { ACTIVE_TURN_ID, MODEL, SESSION_ID, gameState, installApiMocks, seedSession, storyOutput, timelineNodeDetail } from "./fixtures";

for (const requiresCheck of [true, false]) {
  test(`browser auto-play preflights and ${requiresCheck ? "retries the same roll" : "honors a declined check"}`, async ({ page }) => {
    const action = "  试着说服诺诺让我先看看档案。  ";
    const checks: Record<string, unknown>[] = [];
    const generations: Record<string, unknown>[] = [];
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await seedSession(page);
    await installApiMocks(page);
    await page.route(`**/sessions/${SESSION_ID}/timeline/${ACTIVE_TURN_ID}`, (route) => route.fulfill({
      json: {
        ...timelineNodeDetail,
        output: { ...storyOutput, options: ["", action], option_checks: [null, storyOutput.option_checks?.[1]] },
      },
    }));
    await page.route(`**/sessions/${SESSION_ID}/check`, async (route) => {
      checks.push(route.request().postDataJSON());
      await route.fulfill({ json: { check: requiresCheck ? storyOutput.option_checks?.[1] : null, option_index: 1 } });
    });
    await page.route(`**/sessions/${SESSION_ID}/generate`, async (route) => {
      generations.push(route.request().postDataJSON());
      if (requiresCheck && generations.length === 1) {
        await route.fulfill({ status: 502, json: { detail: "临时生成错误" } });
        return;
      }
      await route.fulfill({
        json: {
          session_id: SESSION_ID,
          state: { ...gameState, turn: ACTIVE_TURN_ID + 1 },
          output: { ...storyOutput, narration: "自动游玩已完成此次行动。", options: [], option_checks: [] },
          retrieved_chunks: [],
          used_model: MODEL,
          source: "llm",
          timeline_node_id: ACTIVE_TURN_ID + 1,
          parent_timeline_node_id: ACTIVE_TURN_ID,
          memory: timelineNodeDetail.memory,
          declared: timelineNodeDetail.declared,
          caps: timelineNodeDetail.caps,
        },
      });
    });
    await page.goto(`/?autoplay=1&session=${SESSION_ID}&turns=${ACTIVE_TURN_ID + 1}&delay=100&seed=42`);
    await expect(page.locator(".narration")).toContainText("自动游玩已完成此次行动。", { timeout: 20_000 });
    await expect(page.locator(".autoplay-complete")).toBeVisible();
    expect(checks).toEqual([{ player_action: action, timeline_node_id: ACTIVE_TURN_ID, option_index: 1 }]);
    expect(generations).toHaveLength(requiresCheck ? 2 : 1);
    expect(generations[0].player_action).toBe(action);
    expect(generations[0].timeline_node_id).toBe(ACTIVE_TURN_ID);
    expect(generations[0].option_index).toBe(1);
    if (requiresCheck) {
      expect(generations[0].action_check).toMatchObject({ option_index: 1, roll: expect.any(Number) });
      expect(generations[1]).toEqual(generations[0]);
    } else {
      expect(generations[0].action_check).toBeUndefined();
    }
    expect(errors).toEqual([]);
  });
}
