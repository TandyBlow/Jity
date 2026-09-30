"use client";

import { useCallback, useRef } from "react";

import { APIError, createSession, createSlot, deleteSlot, generateScene, getSession, loadSlot } from "@/lib/api";
import {
  CAMPAIGN_CONSTRAINTS,
  CAMPAIGN_STORY_STYLE,
  ENTRY_ACTION,
  SLOT_DEFAULT,
  loadingOutput,
} from "@/lib/game/initialOutput";
import type { GenerateResponse } from "@/types";

const ACTIVE_SESSION_STORAGE_KEY = "jity_active_session_id";

function rememberActiveSession(sessionId: string) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
  }
}
import type { GameSessionCore } from "@/components/game/useGameSession";

export function useGameActions(core: GameSessionCore) {
  const generating = useRef(false);
  const {
    sessionId, setSessionId, setState, activeTurnId, setActiveTurnId, model, setModel,
    action, setAction, setOutput, setOutputSource, setChunks, setError,
    selectedSlot, setSelectedSlot, setSelectedSlotId,
    selectedCampaign, setSelectedCampaign, gameOver,
    refreshSlots, restoreLastOutput,
    setIsLoading, setPendingGenerate,
  } = core;

  const handleGenerate = useCallback(async (nextAction = action, overrideSessionId?: string) => {
    const sid = overrideSessionId ?? sessionId;
    if (!sid || !nextAction.trim() || generating.current || gameOver) return;
    generating.current = true;
    setIsLoading(true);
    setError("");
    try {
      const response: GenerateResponse = await generateScene({
        sessionId: sid,
        playerAction: nextAction,
        model,
        style: CAMPAIGN_STORY_STYLE,
        constraints: CAMPAIGN_CONSTRAINTS,
        slotName: selectedSlot,
        timelineNodeId: activeTurnId,
      });
      setOutput(response.output);
      setOutputSource(response.source);
      setState(response.state);
      setActiveTurnId(response.timeline_node_id);
      setChunks(response.retrieved_chunks);
      setModel(response.used_model);
      setAction("");
    } catch (err) {
      if (err instanceof APIError && err.status === 409) {
        const latest = await getSession(sid);
        setState(latest.state);
        setActiveTurnId(latest.active_turn_id ?? null);
        setModel(latest.model);
        setChunks([]);
        await restoreLastOutput(sid, latest.campaign_filename, latest.active_turn_id);
        setError("");
        return;
      }
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      generating.current = false;
      setIsLoading(false);
    }
  }, [sessionId, action, model, selectedSlot, activeTurnId, gameOver, setIsLoading, setError, setOutput, setOutputSource, setState, setActiveTurnId, setChunks, setModel, setAction, restoreLastOutput]);

  const handleNewSession = useCallback(async () => {
    setIsLoading(true);
    setError("");
    setOutput(loadingOutput);
    setAction("");
    setPendingGenerate(null);
    try {
      const campaignOpts = { campaignFilename: selectedCampaign || "default_campaign.json", arcIndex: 0, sessionIndex: 0 };
      const session = await createSession(model, campaignOpts);
      rememberActiveSession(session.session_id);
      setSessionId(session.session_id);
      setState(session.state);
      setActiveTurnId(session.active_turn_id ?? null);
      setSelectedCampaign(session.campaign_filename || campaignOpts.campaignFilename);
      setOutput(loadingOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction("");
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      await refreshSlots(session.session_id, SLOT_DEFAULT);
      setPendingGenerate(ENTRY_ACTION);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建会话失败");
    } finally {
      setIsLoading(false);
    }
  }, [model, selectedCampaign, setSelectedCampaign, setIsLoading, setError, setSessionId, setState, setActiveTurnId, setOutput, setOutputSource, setChunks, setAction, setSelectedSlot, setSelectedSlotId, refreshSlots, setPendingGenerate]);

  const handleCampaignChange = useCallback(async (value: string) => {
    if (!value) return;
    setIsLoading(true);
    setError("");
    setOutput(loadingOutput);
    setAction("");
    setPendingGenerate(null);
    const opts = { campaignFilename: value, arcIndex: 0, sessionIndex: 0 };
    try {
      const session = await createSession(model, opts);
      setSelectedCampaign(value);
      rememberActiveSession(session.session_id);
      setSessionId(session.session_id);
      setState(session.state);
      setActiveTurnId(session.active_turn_id ?? null);
      setOutput(loadingOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction("");
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      refreshSlots(session.session_id, SLOT_DEFAULT).catch((err) => console.error("refreshSlots failed:", err));
      setPendingGenerate(ENTRY_ACTION);
    } catch (err: Error | unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, [model, setIsLoading, setSelectedCampaign, setError, setSessionId, setState, setActiveTurnId, setOutput, setOutputSource, setChunks, setAction, setSelectedSlot, setSelectedSlotId, refreshSlots, setPendingGenerate]);

  const handleSlotChange = useCallback(async (slotId: number) => {
    if (!slotId) return;
    setIsLoading(true);
    setError("");
    setOutput(loadingOutput);
    setAction("");
    setPendingGenerate(null);
    try {
      const loaded = await loadSlot(slotId);
      rememberActiveSession(loaded.session.session_id);
      setSelectedSlotId(slotId);
      setSelectedSlot(loaded.slot.slot_name);
      setSessionId(loaded.session.session_id);
      setState(loaded.session.state);
      setActiveTurnId(loaded.session.active_turn_id ?? null);
      setModel(loaded.session.model);
      setChunks([]);
      await refreshSlots(loaded.session.session_id, loaded.slot.slot_name);
      await restoreLastOutput(loaded.session.session_id, loaded.slot.campaign_filename, loaded.session.active_turn_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载存档失败");
    } finally {
      setIsLoading(false);
    }
  }, [setIsLoading, setError, setOutput, setAction, setPendingGenerate, setSelectedSlotId, setSelectedSlot, setSessionId, setState, setActiveTurnId, setModel, setChunks, restoreLastOutput, refreshSlots]);

  const handleCreateSlot = useCallback(async (name: string) => {
    if (!name || !sessionId) return;
    try {
      await createSlot(name, sessionId, selectedSlot);
      await refreshSlots(sessionId, name);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }, [sessionId, selectedSlot, refreshSlots]);

  const handleDeleteSlot = useCallback(async (slotId: number) => {
    try {
      await deleteSlot(slotId);
      await refreshSlots(sessionId, selectedSlot);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }, [sessionId, selectedSlot, refreshSlots]);

  return {
    handleGenerate, handleNewSession, handleCampaignChange, handleSlotChange, handleCreateSlot, handleDeleteSlot,
  };
}
