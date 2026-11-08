"use client";

import { useCallback, useRef } from "react";

import { APIError, createSession, createSlot, deleteSlot, generateScene, getSession, loadSlot, previewActionCheck } from "@/lib/api";
import {
  CAMPAIGN_CONSTRAINTS,
  CAMPAIGN_STORY_STYLE,
  SLOT_DEFAULT,
} from "@/lib/game/initialOutput";
import type { ActionCheckPreview, ActionCheckSubmission, GenerateResponse } from "@/types";

import type { GameSessionCore } from "@/components/game/useGameSession";

const ACTIVE_SESSION_STORAGE_KEY = "jity_active_session_id";

function rememberActiveSession(sessionId: string) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
  }
}

export function useGameActions(core: GameSessionCore) {
  const generating = useRef(false);
  const {
    sessionId, activeTurnId, model, action, selectedSlot, selectedCampaign,
    gameOver, dispatch, refreshSlots, restoreSession,
  } = core;

  const refreshAfterConflict = useCallback(async (sid: string) => {
    try {
      await restoreSession(await getSession(sid), "");
    } catch (refreshError) {
      dispatch({ type: "requestFailed", error: `状态已变化，但刷新失败：${refreshError instanceof Error ? refreshError.message : String(refreshError)}。请重试或重新加载存档。` });
    }
  }, [restoreSession, dispatch]);

  const handlePrepareCheck = useCallback(async (nextAction: string, optionIndex?: number): Promise<ActionCheckPreview | null> => {
    if (!sessionId || !nextAction.trim() || generating.current || gameOver) return null;
    generating.current = true;
    dispatch({ type: "requestStarted" });
    try {
      return await previewActionCheck({ sessionId, playerAction: nextAction, timelineNodeId: activeTurnId, optionIndex });
    } catch (err) {
      if (err instanceof APIError && err.status === 409) {
        await refreshAfterConflict(sessionId);
      } else {
        dispatch({ type: "requestFailed", error: err instanceof Error ? err.message : "行动判定检查失败" });
      }
      return null;
    } finally {
      generating.current = false;
      dispatch({ type: "requestFinished" });
    }
  }, [sessionId, activeTurnId, gameOver, dispatch, refreshAfterConflict]);

  const handleGenerate = useCallback(async (nextAction = action, overrideSessionId?: string, actionCheck?: ActionCheckSubmission, optionIndex?: number) => {
    const sid = overrideSessionId ?? sessionId;
    if (!sid || !nextAction.trim() || generating.current || gameOver) return;
    generating.current = true;
    dispatch({ type: "requestStarted" });
    try {
      const response: GenerateResponse = await generateScene({
        sessionId: sid,
        playerAction: nextAction,
        model,
        style: CAMPAIGN_STORY_STYLE,
        constraints: CAMPAIGN_CONSTRAINTS,
        slotName: selectedSlot,
        timelineNodeId: activeTurnId,
        actionCheck,
        optionIndex,
      });
      dispatch({ type: "turnSucceeded", response });
    } catch (err) {
      if (err instanceof APIError && err.status === 409) {
        await refreshAfterConflict(sid);
        return;
      }
      dispatch({ type: "requestFailed", error: err instanceof Error ? err.message : "生成失败" });
    } finally {
      generating.current = false;
      dispatch({ type: "requestFinished" });
    }
  }, [sessionId, action, model, selectedSlot, activeTurnId, gameOver, dispatch, refreshAfterConflict]);

  const startCampaign = useCallback(async (campaignFilename: string) => {
    dispatch({ type: "requestStarted" });
    try {
      const session = await createSession(model, { campaignFilename, arcIndex: 0, sessionIndex: 0 });
      await restoreSession({ ...session, campaign_filename: session.campaign_filename || campaignFilename }, SLOT_DEFAULT, { fresh: true });
      rememberActiveSession(session.session_id);
    } catch (err) {
      dispatch({ type: "requestFailed", error: err instanceof Error ? err.message : "创建会话失败" });
    } finally {
      dispatch({ type: "requestFinished" });
    }
  }, [model, dispatch, restoreSession]);

  const handleNewSession = useCallback(() =>
    startCampaign(selectedCampaign || "default_campaign.json"), [startCampaign, selectedCampaign]);

  const handleCampaignChange = useCallback(async (value: string) => {
    if (value) await startCampaign(value);
  }, [startCampaign]);

  const handleSlotChange = useCallback(async (slotId: number) => {
    if (!slotId) return;
    dispatch({ type: "requestStarted" });
    try {
      const loaded = await loadSlot(slotId);
      await restoreSession({
        ...loaded.session, campaign_filename: loaded.slot.campaign_filename ?? loaded.session.campaign_filename,
      }, loaded.slot.slot_name);
      rememberActiveSession(loaded.session.session_id);
    } catch (err) {
      dispatch({ type: "requestFailed", error: err instanceof Error ? err.message : "加载存档失败" });
    } finally {
      dispatch({ type: "requestFinished" });
    }
  }, [dispatch, restoreSession]);

  /** Error message on failure, null when the slot was created. */
  const handleCreateSlot = useCallback(async (name: string): Promise<string | null> => {
    if (!name || !sessionId) return null;
    try {
      await createSlot(name, sessionId, selectedSlot);
      await refreshSlots(sessionId, name);
      return null;
    } catch (err: unknown) {
      return err instanceof Error ? err.message : String(err);
    }
  }, [sessionId, selectedSlot, refreshSlots]);

  const handleDeleteSlot = useCallback(async (slotId: number): Promise<string | null> => {
    try {
      await deleteSlot(slotId);
      try {
        await refreshSlots(sessionId, selectedSlot);
      } catch (err) {
        return `存档已删除，但列表刷新失败：${err instanceof Error ? err.message : String(err)}。请重新打开页面核对。`;
      }
      return null;
    } catch (err: unknown) {
      return err instanceof Error ? err.message : String(err);
    }
  }, [sessionId, selectedSlot, refreshSlots]);

  return {
    handleGenerate, handlePrepareCheck, handleNewSession, handleCampaignChange, handleSlotChange, handleCreateSlot, handleDeleteSlot,
  };
}
