import { expect, test, type Page } from "@playwright/test";

import {
  ACTIVE_TURN_ID,
  MODEL,
  SESSION_ID,
  gameState,
  installApiMocks,
  seedSession,
  sessionResponse,
  storyOutput,
  timelineNodeDetail,
} from "./fixtures";

type ActionRequest = {
  player_action: string;
  timeline_node_id: number;
  option_index?: number | null;
  action_check?: { roll: number; option_index?: number | null };
};

const checkedAction = storyOutput.options[1];
const check = storyOutput.option_checks?.[1];
const nextNarration = "判定结果已经进入下一幕。";

async function openGame(page: Page, requiresCheck = true) {
  const checks: ActionRequest[] = [];
  const generations: ActionRequest[] = [];
  const errors: string[] = [];
  const controls = { generationFailures: 0, preflightStatus: 200 };
  page.on("pageerror", (error) => errors.push(error.message));
  await seedSession(page);
  await installApiMocks(page);
  await page.route(`**/sessions/${SESSION_ID}/check`, async (route) => {
    const request = route.request().postDataJSON() as ActionRequest;
    checks.push(request);
    if (controls.preflightStatus !== 200) {
      await route.fulfill({ status: controls.preflightStatus, json: { detail: "当前剧情已变化，请刷新。" } });
      return;
    }
    await route.fulfill({
      json: {
        check: requiresCheck ? check : null,
        option_index: request.player_action === checkedAction ? 1 : null,
      },
    });
  });
  await page.route(`**/sessions/${SESSION_ID}/generate`, async (route) => {
    generations.push(route.request().postDataJSON() as ActionRequest);
    if (controls.generationFailures > 0) {
      controls.generationFailures -= 1;
      await route.fulfill({ status: 502, json: { detail: "临时生成失败，请重试。" } });
      return;
    }
    await route.fulfill({
      json: {
        session_id: SESSION_ID,
        state: { ...gameState, turn: ACTIVE_TURN_ID + 1 },
        output: { ...storyOutput, narration: nextNarration, options: [], option_checks: [] },
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
  await page.setViewportSize({ width: 1536, height: 730 });
  await page.goto("/");
  await expect(page.locator(".option-button")).toHaveCount(3);
  await page.waitForLoadState("networkidle");
  return { checks, generations, errors, controls };
}

async function rollRealDice(page: Page, roll: number, degree: string) {
  const rollButton = page.getByRole("button", { name: "掷骰", exact: true });
  await expect(rollButton).toBeVisible();
  // Fix only the outcome selection. Restore randomness before open-dice-dnd
  // initializes so the real WebGL renderer and physics still run normally.
  await rollButton.evaluate((button, value) => {
    const originalRandom = Math.random;
    Math.random = () => {
      Math.random = originalRandom;
      return (value - 0.5) / 20;
    };
    (button as HTMLButtonElement).click();
    Math.random = originalRandom;
  }, roll);
  await expect(page.locator(".main-check-overlay canvas")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(".main-check-result-title strong")).toHaveText(degree, { timeout: 35_000 });
}

test.describe("action checks reach the generation API", () => {
  for (const [roll, degree] of [[1, "大失败"], [11, "失败"], [12, "成功"], [20, "大成功"]] as const) {
    test(`real d20 roll ${roll} produces ${degree} and submits once`, async ({ page }) => {
      const { generations, errors } = await openGame(page);
      await page.locator(".option-button").nth(1).click();
      await rollRealDice(page, roll, degree);
      expect(generations).toHaveLength(0);

      // Repeated activation must not turn one completed roll into two turns.
      await page.getByRole("button", { name: "继续", exact: true }).evaluate((button) => {
        (button as HTMLButtonElement).click();
        (button as HTMLButtonElement).click();
      });
      await expect(page.locator(".narration")).toContainText(nextNarration);
      await page.waitForLoadState("networkidle");
      expect(generations).toHaveLength(1);
      expect(generations[0]).toMatchObject({
        player_action: checkedAction,
        timeline_node_id: ACTIVE_TURN_ID,
        action_check: { roll, option_index: 1 },
      });
      expect(errors).toEqual([]);
    });
  }

  test("return and Escape cancel without submitting a turn", async ({ page }) => {
    const { generations } = await openGame(page);
    for (const cancel of ["button", "keyboard"]) {
      await page.locator(".option-button").nth(1).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      if (cancel === "button") {
        await page.getByRole("button", { name: "返回", exact: true }).click();
      } else {
        await page.keyboard.press("Escape");
      }
      await expect(page.getByRole("dialog")).toHaveCount(0);
      expect(generations).toHaveLength(0);
    }
  });

  test("server preflight can submit a marked option without rolling", async ({ page }) => {
    const { checks, generations, errors } = await openGame(page, false);
    await page.locator(".option-button").nth(1).click();
    await expect(page.locator(".narration")).toContainText(nextNarration);
    await page.waitForLoadState("networkidle");
    expect(checks).toHaveLength(1);
    expect(checks[0]).toMatchObject({
      player_action: checkedAction,
      timeline_node_id: ACTIVE_TURN_ID,
      option_index: 1,
    });
    expect(generations).toHaveLength(1);
    expect(generations[0].player_action).toBe(checkedAction);
    expect(generations[0].action_check ?? null).toBeNull();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("duplicate action labels preserve the selected unchecked option index", async ({ page }) => {
    const { checks, generations, errors } = await openGame(page, false);
    await page.route(`**/sessions/${SESSION_ID}/timeline/${ACTIVE_TURN_ID}`, async (route) => {
      await route.fulfill({
        json: {
          ...timelineNodeDetail,
          output: {
            ...storyOutput,
            options: [checkedAction, checkedAction],
            option_checks: [check, null],
          },
        },
      });
    });
    await page.reload();
    await expect(page.locator(".option-button")).toHaveCount(2);
    await expect(page.locator(".option-button").nth(0).locator(".option-check-badge")).toHaveCount(1);
    await expect(page.locator(".option-button").nth(1).locator(".option-check-badge")).toHaveCount(0);
    await page.locator(".option-button").nth(1).click();
    await expect(page.locator(".narration")).toContainText(nextNarration);
    await page.waitForLoadState("networkidle");
    expect(checks).toHaveLength(1);
    expect(checks[0]).toMatchObject({ player_action: checkedAction, option_index: 1 });
    expect(generations).toHaveLength(1);
    expect(generations[0]).toMatchObject({
      player_action: checkedAction,
      timeline_node_id: ACTIVE_TURN_ID,
      option_index: 1,
    });
    expect(generations[0].action_check ?? null).toBeNull();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("custom action receives preflight, rolls, and keeps the original action", async ({ page }) => {
    const { checks, generations, errors } = await openGame(page);
    const action = "我试着说服诺诺让我先看看档案。";
    await page.getByLabel("你的行动", { exact: true }).fill(action);
    await page.getByRole("button", { name: "生成下一幕", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(checks).toHaveLength(1);
    expect(checks[0]).toMatchObject({ player_action: action, timeline_node_id: ACTIVE_TURN_ID });
    expect(generations).toHaveLength(0);
    await rollRealDice(page, 12, "成功");
    await page.getByRole("button", { name: "继续", exact: true }).click();
    await expect(page.locator(".narration")).toContainText(nextNarration);
    await page.waitForLoadState("networkidle");
    expect(generations).toHaveLength(1);
    expect(generations[0]).toMatchObject({
      player_action: action,
      timeline_node_id: ACTIVE_TURN_ID,
      action_check: { roll: 12 },
    });
    expect(generations[0].action_check?.option_index ?? null).toBeNull();
    expect(errors).toEqual([]);
  });

  test("custom action without a check submits once through the keyboard shortcut", async ({ page }) => {
    const { checks, generations, errors } = await openGame(page, false);
    const action = "我站在门口，等诺诺把话说完。";
    await page.getByLabel("你的行动", { exact: true }).fill(action);
    await page.getByLabel("你的行动", { exact: true }).press("Control+Enter");
    await expect(page.locator(".narration")).toContainText(nextNarration);
    await page.waitForLoadState("networkidle");
    expect(checks).toHaveLength(1);
    expect(checks[0]).toMatchObject({ player_action: action, timeline_node_id: ACTIVE_TURN_ID });
    expect(generations).toHaveLength(1);
    expect(generations[0].player_action).toBe(action);
    expect(generations[0].action_check ?? null).toBeNull();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("cancelling a custom-action check preserves the typed action", async ({ page }) => {
    const { checks, generations } = await openGame(page);
    const action = "我试着说服诺诺让我先看看档案。";
    await page.getByLabel("你的行动", { exact: true }).fill(action);
    await page.getByRole("button", { name: "生成下一幕", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.getByRole("button", { name: "返回", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByLabel("你的行动", { exact: true })).toHaveValue(action);
    expect(checks).toHaveLength(1);
    expect(generations).toHaveLength(0);
  });

  test("a failed generation retries the same completed roll without rolling again", async ({ page }) => {
    const { generations, controls, errors } = await openGame(page);
    controls.generationFailures = 1;
    await page.locator(".option-button").nth(1).click();
    await rollRealDice(page, 11, "失败");
    await page.getByRole("button", { name: "继续", exact: true }).click();
    await expect(page.getByRole("dialog").getByRole("alert")).toContainText("临时生成失败");
    await expect(page.locator(".main-check-result-title strong")).toHaveText("失败");
    await expect(page.getByRole("button", { name: "掷骰", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "重试此次判定", exact: true }).click();
    await expect(page.locator(".narration")).toContainText(nextNarration);
    await page.waitForLoadState("networkidle");
    expect(generations).toHaveLength(2);
    expect(generations[1]).toEqual(generations[0]);
    expect(generations[1].action_check).toEqual({ roll: 11, option_index: 1 });
    expect(errors).toEqual([]);
  });

  test("stale custom-action preflight refreshes the current scene without generating", async ({ page }) => {
    const { checks, generations, controls } = await openGame(page);
    let refreshRequests = 0;
    await page.route(`**/sessions/${SESSION_ID}`, async (route) => {
      refreshRequests += 1;
      await route.fulfill({ json: sessionResponse });
    });
    controls.preflightStatus = 409;
    await page.getByLabel("你的行动", { exact: true }).fill("我试着推开这扇锁住的门。");
    await page.getByRole("button", { name: "生成下一幕", exact: true }).click();
    await expect(page.getByLabel("你的行动", { exact: true })).toHaveValue("");
    await page.waitForLoadState("networkidle");
    expect(checks).toHaveLength(1);
    expect(refreshRequests).toBe(1);
    expect(generations).toHaveLength(0);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator(".option-button")).toHaveCount(3);
  });
});
