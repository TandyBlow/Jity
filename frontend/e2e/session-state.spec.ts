import { expect, test } from "@playwright/test";
import {
  ACTIVE_TURN_ID, SESSION_ID, installApiMocks, seedSession,
  sessionResponse, storyOutput, timelineNodeDetail,
} from "./fixtures";

for (const failNode of [false, true]) {
  test(`conflict restoration applies a complete snapshot${failNode ? " after a failed node read and retry" : ""}`, async ({ page }) => {
    await seedSession(page);
    await installApiMocks(page);
    let attempts = 0;
    let rejectNode = failNode;
    let release!: () => void;
    const delayed = new Promise<void>(resolve => { release = resolve; });
    const submittedParents: number[] = [];
    await page.route(`**/sessions/${SESSION_ID}/generate`, route => {
      submittedParents.push(route.request().postDataJSON().timeline_node_id);
      attempts++;
      if (attempts < 3) return route.fulfill({ status: 409, json: { detail: "节点已变化" } });
      return route.fulfill({ json: {
        session_id: SESSION_ID, state: { ...sessionResponse.state, turn: 100 },
        output: { ...storyOutput, narration: "恢复后继续成功" }, retrieved_chunks: [],
        model_output_id: 101, used_model: sessionResponse.model, source: "llm",
        timeline_node_id: 100, parent_timeline_node_id: 99, campaign_progress: null,
        memory: timelineNodeDetail.memory, declared: timelineNodeDetail.declared, caps: timelineNodeDetail.caps,
      } });
    });
    await page.route(`**/sessions/${SESSION_ID}`, route => route.fulfill({ json: attempts
      ? { ...sessionResponse, active_turn_id: 99, state: { ...sessionResponse.state, turn: 99 } }
      : sessionResponse }));
    await page.route(`**/sessions/${SESSION_ID}/timeline/99`, async route => {
      await delayed;
      return rejectNode
        ? route.fulfill({ status: 503, json: { detail: "节点读取失败" } })
        : route.fulfill({ json: { ...timelineNodeDetail, id: 99, output: { ...storyOutput, narration: "恢复的完整剧情" } } });
    });
    await page.goto("/");
    const input = page.locator("#action");
    const submit = page.locator(".player-controls-row > button");
    await expect(input).toBeEnabled();
    await input.fill("继续行动");
    await submit.click();
    await expect.poll(() => attempts).toBe(1);
    // While the node is pending, keep the previous state/story pair visible.
    await expect(page.locator(".toolbar-row")).toContainText(`Turn ${sessionResponse.state.turn}`);
    await expect(page.locator(".narration")).toContainText(storyOutput.narration.slice(0, 12));
    release();
    if (failNode) {
      await expect(page.locator(".error")).toContainText("刷新失败");
      await expect(input).toHaveValue("继续行动");
      await expect(page.locator(".toolbar-row")).toContainText(`Turn ${sessionResponse.state.turn}`);
    } else {
      await expect(page.locator(".narration")).toContainText("恢复的完整剧情");
      await expect(page.locator(".toolbar-row")).toContainText("Turn 99");
    }
    rejectNode = false;
    await input.fill("再试一次");
    await submit.click();
    await expect(page.locator(".narration")).toContainText("恢复的完整剧情");
    await expect(page.locator(".error")).toHaveCount(0);
    await expect(input).toBeEnabled();
    await input.fill("从恢复节点继续");
    await submit.click();
    await expect(page.locator(".narration")).toContainText("恢复后继续成功");
    expect(submittedParents).toEqual([ACTIVE_TURN_ID, failNode ? ACTIVE_TURN_ID : 99, 99]);
    await expect(page.locator(".toolbar-row")).toContainText("Turn 100");
    await expect(input).toHaveValue("");
  });
}

test("a conflict refresh invalidates budget cached under the same node and slot", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  let refreshed = false;
  await page.route(`**/sessions/${SESSION_ID}/progress`, route => route.fulfill({ json: {
    turns_total: refreshed ? 9 : 7, max_turns_per_campaign: 50,
    arc_index: 0, arc_name: "第一幕", arc_goal: "调查", session_index: 0,
    session_name: "报到", current_goal: "调查", campaign_title: "测试",
  } }));
  await page.route(`**/sessions/${SESSION_ID}/generate`, route => {
    refreshed = true;
    return route.fulfill({ status: 409, json: { detail: "需要刷新" } });
  });
  await page.goto("/");
  await expect(page.locator(".toolbar-row")).toContainText("第 7 / 50 回合");
  await page.locator("#action").fill("继续");
  await page.locator(".player-controls-row > button").click();
  await expect(page.locator(".toolbar-row")).toContainText("第 9 / 50 回合");
});

test("starting again after an ending generates exactly one opening for the new session", async ({ page }) => {
  await seedSession(page);
  await installApiMocks(page);
  const nextSessionId = "fresh-session-after-ending";
  const requests: Array<{ timeline_node_id: number; player_action: string }> = [];
  await page.route(`**/sessions/${SESSION_ID}/timeline/*`, route => route.fulfill({ json: {
    ...timelineNodeDetail, output: { ...storyOutput, game_over: true, options: [], game_over_reason: "结束" },
  } }));
  await page.route("**/sessions", route => route.fulfill({ json: {
    ...sessionResponse, session_id: nextSessionId, active_turn_id: 90,
    state: { ...sessionResponse.state, turn: 0 },
  } }));
  await page.route(`**/sessions/${nextSessionId}/generate`, route => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({ json: {
      session_id: nextSessionId, state: { ...sessionResponse.state, turn: 1 },
      output: { ...storyOutput, narration: "全新战役的开场" }, retrieved_chunks: [],
      model_output_id: 91, used_model: sessionResponse.model, source: "scripted",
      timeline_node_id: 91, parent_timeline_node_id: 90, campaign_progress: null,
      memory: timelineNodeDetail.memory, declared: timelineNodeDetail.declared, caps: timelineNodeDetail.caps,
    } });
  });
  await page.goto("/");
  await expect(page.locator("#action")).toBeDisabled();
  await page.getByRole("button", { name: "设置", exact: true }).click();
  await page.getByRole("button", { name: "新建会话", exact: true }).click();
  await expect(page.locator(".narration")).toContainText("全新战役的开场");
  await expect(page.locator("#action")).toBeEnabled();
  await expect(page.locator(".toolbar-row")).toContainText("Turn 1");
  await page.waitForLoadState("networkidle");
  expect(requests).toHaveLength(1);
  expect(requests[0].timeline_node_id).toBe(90);
  expect(requests[0].player_action).toContain("入场");
});
