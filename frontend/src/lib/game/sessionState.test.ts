import { describe, expect, it } from "vitest";

import { sessionResponse, timelineNodeDetail, saveSlots } from "../../../e2e/fixtures";
import { ENTRY_ACTION, loadingOutput } from "@/lib/game/initialOutput";
import { gameSessionReducer, initialSessionState } from "./sessionState";
import type { GameSessionEvent } from "./sessionState";
import type { GenerateResponse } from "@/types";

const response: GenerateResponse = {
  session_id: sessionResponse.session_id,
  state: { ...sessionResponse.state, turn: 8 },
  output: { ...timelineNodeDetail.output!, narration: "新的一幕", game_over: true },
  retrieved_chunks: [{ id: "clue", title: "线索", content: "记录", source_type: "lore", score: 1 }],
  model_output_id: 42, used_model: "new-model", source: "llm",
  timeline_node_id: 8, parent_timeline_node_id: 7,
  memory: timelineNodeDetail.memory, declared: timelineNodeDetail.declared, caps: timelineNodeDetail.caps,
  campaign_progress: {
    turns_total: 8, max_turns_per_campaign: 50, arc_index: 0, arc_name: "第一幕", arc_goal: "调查",
    session_index: 0, session_name: "报到", current_goal: "寻找线索", campaign_title: "测试战役",
  },
};
const restored: GameSessionEvent = {
  type: "sessionRestored", session: sessionResponse, node: timelineNodeDetail,
  slots: saveSlots, preferredSlotName: saveSlots[1].slot_name,
};
const dirty = {
  ...gameSessionReducer(initialSessionState, { type: "turnSucceeded", response }),
  action: "尚未提交的行动", error: "上次错误", pendingGenerate: ENTRY_ACTION,
};

describe("complete session events", () => {
  it("publishes the story, node, memory, budget and model from one generated result", () => {
    const next = gameSessionReducer(dirty, { type: "turnSucceeded", response });
    expect(next).toMatchObject({
      sessionId: response.session_id, state: response.state, activeTurnId: 8,
      output: response.output, outputSource: "llm", model: "new-model",
      campaignProgress: response.campaign_progress, chunks: response.retrieved_chunks,
      turnReport: { memory: response.memory, declared: response.declared, caps: response.caps },
      action: "", error: "", pendingGenerate: null,
    });
  });

  it("restores the whole snapshot and clears data belonging to the previous turn", () => {
    const next = gameSessionReducer(dirty, restored);
    expect(next).toMatchObject({
      sessionId: sessionResponse.session_id, state: sessionResponse.state,
      activeTurnId: timelineNodeDetail.id, model: sessionResponse.model,
      output: timelineNodeDetail.output, outputSource: timelineNodeDetail.source,
      turnReport: { memory: timelineNodeDetail.memory, declared: timelineNodeDetail.declared, caps: timelineNodeDetail.caps },
      selectedCampaign: sessionResponse.campaign_filename,
      selectedSlot: saveSlots[1].slot_name, selectedSlotId: saveSlots[1].id,
      campaignProgress: null, chunks: [], action: "", error: "", pendingGenerate: null,
    });
    expect(next.restoreVersion).toBe(dirty.restoreVersion + 1);
  });

  it("invalidates cached progress even when restoring the same session, node and slot", () => {
    const once = gameSessionReducer(dirty, restored);
    const twice = gameSessionReducer(once, restored);
    expect(twice.activeTurnId).toBe(once.activeTurnId);
    expect(twice.selectedSlotId).toBe(once.selectedSlotId);
    expect(twice.restoreVersion).toBe(once.restoreVersion + 1);
  });

  it.each([null, { ...timelineNodeDetail, output: null }])("schedules a fresh opening without retaining an ending or memory report", (node) => {
    const next = gameSessionReducer(dirty, { ...restored, node });
    expect(next.output).toEqual(loadingOutput);
    expect(next.output.game_over).toBe(false);
    expect(next).toMatchObject({ pendingGenerate: ENTRY_ACTION, turnReport: null, outputSource: "scripted", chunks: [], campaignProgress: null });
    expect(gameSessionReducer(next, { type: "openingConsumed" }).pendingGenerate).toBeNull();
  });

  it("does not queue an opening for an unlinked legacy session", () => {
    const next = gameSessionReducer(dirty, {
      ...restored, session: { ...sessionResponse, campaign_filename: null, active_turn_id: null }, node: null,
    });
    expect(next.pendingGenerate).toBeNull();
    expect(next.activeTurnId).toBeNull();
    expect(next.error).toContain("未关联战役");
  });

  it("keeps the last complete snapshot and action when a request fails", () => {
    const started = gameSessionReducer(dirty, { type: "requestStarted" });
    const failed = gameSessionReducer(started, { type: "requestFailed", error: "刷新失败" });
    const finished = gameSessionReducer(failed, { type: "requestFinished" });
    expect(finished).toEqual({ ...dirty, isLoading: false, error: "刷新失败" });
  });

  it("ignores a late slot-list response for a different session", () => {
    const current = gameSessionReducer(dirty, restored);
    expect(gameSessionReducer(current, {
      type: "slotsRefreshed", sessionId: "old-session", slots: [], preferredSlotName: "",
    })).toBe(current);
  });

  it("keeps autosaves on the current branch after its active save is deleted", () => {
    const current = gameSessionReducer(dirty, restored);
    const next = gameSessionReducer(current, {
      type: "slotsRefreshed", sessionId: current.sessionId,
      slots: [{ ...saveSlots[0], is_active: false }], preferredSlotName: current.selectedSlot,
    });
    expect(next.selectedSlot).toBe(current.selectedSlot);
    expect(next.selectedSlotId).toBe("");
    expect(next.output).toBe(current.output);
    expect(next.activeTurnId).toBe(current.activeTurnId);
  });
});
