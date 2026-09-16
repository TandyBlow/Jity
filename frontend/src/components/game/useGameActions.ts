"use client";

import { useCallback, useRef } from "react";

import { createSession, createSlot, generateScene, loadSlot } from "@/lib/api";
import {
  DEFAULT_CONSTRAINTS,
  DEFAULT_STORY_STYLE,
  CAMPAIGN_CONSTRAINTS,
  CAMPAIGN_STORY_STYLE,
  ENTRY_ACTION,
  INITIAL_ACTION,
  SLOT_DEFAULT,
  initialOutput,
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
    selectedCampaign, setSelectedCampaign,
    refreshSlots, restoreLastOutput,
    setIsLoading, setPendingGenerate,
  } = core;

  const handleGenerate = useCallback(async (nextAction = action, overrideSessionId?: string) => {
    const sid = overrideSessionId ?? sessionId;
    if (!sid || !nextAction.trim() || generating.current) return;
    generating.current = true;
    setIsLoading(true);
    setError("");
    try {
      const response: GenerateResponse = await generateScene({
        sessionId: sid,
        playerAction: nextAction,
        model,
        style: selectedCampaign ? CAMPAIGN_STORY_STYLE : DEFAULT_STORY_STYLE,
        constraints: selectedCampaign ? CAMPAIGN_CONSTRAINTS : DEFAULT_CONSTRAINTS,
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
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      generating.current = false;
      setIsLoading(false);
    }
  }, [sessionId, action, model, selectedSlot, selectedCampaign, activeTurnId, setIsLoading, setError, setOutput, setOutputSource, setState, setActiveTurnId, setChunks, setModel, setAction]);

  const handleNewSession = useCallback(async () => {
    setIsLoading(true);
    setError("");
    setOutput(loadingOutput);
    setAction("");
    setPendingGenerate(null);
    try {
      const campaignOpts = selectedCampaign
        ? { campaignFilename: selectedCampaign, arcIndex: 0, sessionIndex: 0, slotName: SLOT_DEFAULT }
        : undefined;
      const session = await createSession(model, campaignOpts);
      rememberActiveSession(session.session_id);
      setSessionId(session.session_id);
      setState(session.state);
      setActiveTurnId(session.active_turn_id ?? null);
      setOutput(campaignOpts ? loadingOutput : initialOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction(campaignOpts ? "" : INITIAL_ACTION);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      await refreshSlots(session.session_id, SLOT_DEFAULT);
      if (campaignOpts) {
        setPendingGenerate(ENTRY_ACTION);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建会话失败");
    } finally {
      setIsLoading(false);
    }
  }, [model, selectedCampaign, setIsLoading, setError, setSessionId, setState, setActiveTurnId, setOutput, setOutputSource, setChunks, setAction, setSelectedSlot, setSelectedSlotId, refreshSlots, setPendingGenerate]);

  const handleCampaignChange = useCallback(async (value: string) => {
    setIsLoading(true);
    setError("");
    setOutput(loadingOutput);
    setAction("");
    setPendingGenerate(null);
    const opts = value
      ? { campaignFilename: value, arcIndex: 0, sessionIndex: 0, slotName: SLOT_DEFAULT }
      : undefined;
    try {
      const session = await createSession(model, opts);
      setSelectedCampaign(value);
      rememberActiveSession(session.session_id);
      setSessionId(session.session_id);
      setState(session.state);
      setActiveTurnId(session.active_turn_id ?? null);
      setOutput(opts ? loadingOutput : initialOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction(opts ? "" : INITIAL_ACTION);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      refreshSlots(session.session_id, SLOT_DEFAULT).catch((err) => console.error("refreshSlots failed:", err));
      if (opts) setPendingGenerate(ENTRY_ACTION);
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

  return {
    handleGenerate, handleNewSession, handleCampaignChange, handleSlotChange, handleCreateSlot,
  };
}
