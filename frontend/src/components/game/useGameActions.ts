"use client";

import { useCallback } from "react";

import { createSession, createSlot, generateScene, loadSlot } from "@/lib/api";
import {
  DEFAULT_CONSTRAINTS,
  DEFAULT_STORY_STYLE,
  ENTRY_ACTION,
  INITIAL_ACTION,
  SLOT_DEFAULT,
  initialOutput,
} from "@/lib/game/initialOutput";
import type { GenerateResponse, StoryOutput } from "@/types";
import type { GameSessionCore } from "@/components/game/useGameSession";

export function useGameActions(core: GameSessionCore) {
  const {
    sessionId, setSessionId, setState, model, setModel,
    action, setAction, setOutput, setOutputSource, setChunks, setError,
    selectedSlot, setSelectedSlot, setSelectedSlotId,
    selectedCampaign, setSelectedCampaign,
    refreshSlots, restoreLastOutput,
  } = core;

  const handleGenerate = useCallback(async (nextAction = action, overrideSessionId?: string) => {
    const sid = overrideSessionId ?? sessionId;
    if (!sid || !nextAction.trim()) return;
    core.setIsLoading(true);
    setError("");
    try {
      const response: GenerateResponse = await generateScene({
        sessionId: sid,
        playerAction: nextAction,
        model,
        style: DEFAULT_STORY_STYLE,
        constraints: DEFAULT_CONSTRAINTS,
        slotName: selectedSlot,
      });
      setOutput(response.output);
      setOutputSource(response.source);
      setState(response.state);
      setChunks(response.retrieved_chunks);
      setModel(response.used_model);
      setAction("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "生成失败");
    } finally {
      core.setIsLoading(false);
    }
  }, [sessionId, action, model, selectedSlot]);

  const handleNewSession = useCallback(async () => {
    core.setIsLoading(true);
    setError("");
    try {
      const campaignOpts = selectedCampaign
        ? { campaignFilename: selectedCampaign, arcIndex: 0, sessionIndex: 0, slotName: SLOT_DEFAULT }
        : undefined;
      const session = await createSession(model, campaignOpts);
      setSessionId(session.session_id);
      setState(session.state);
      setOutput(initialOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction(INITIAL_ACTION);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      await refreshSlots(session.session_id, SLOT_DEFAULT);
      if (campaignOpts) {
        core.setPendingGenerate(ENTRY_ACTION);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建会话失败");
    } finally {
      core.setIsLoading(false);
    }
  }, [model, selectedCampaign]);

  const handleCampaignChange = useCallback(async (value: string) => {
    setSelectedCampaign(value);
    setError("");
    const opts = value
      ? { campaignFilename: value, arcIndex: 0, sessionIndex: 0, slotName: SLOT_DEFAULT }
      : undefined;
    try {
      const session = await createSession(model, opts);
      setSessionId(session.session_id);
      setState(session.state);
      setOutput(initialOutput);
      setOutputSource("scripted");
      setChunks([]);
      setAction(INITIAL_ACTION);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      refreshSlots(session.session_id, SLOT_DEFAULT).catch((err) => console.error("refreshSlots failed:", err));
      core.setPendingGenerate(ENTRY_ACTION);
    } catch (err: Error | unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [model]);

  const handleSlotChange = useCallback(async (slotId: number) => {
    if (!slotId) return;
    setError("");
    try {
      const loaded = await loadSlot(slotId);
      setSelectedSlotId(slotId);
      setSelectedSlot(loaded.slot.slot_name);
      setSessionId(loaded.session.session_id);
      setState(loaded.session.state);
      setModel(loaded.session.model);
      setChunks([]);
      if (loaded.slot.campaign_filename) setSelectedCampaign(loaded.slot.campaign_filename);
      await restoreLastOutput(loaded.session.session_id);
      await refreshSlots(loaded.session.session_id, loaded.slot.slot_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载存档失败");
    }
  }, []);

  const handleCreateSlot = useCallback(async (name: string) => {
    if (!name || !sessionId) return;
    try {
      await createSlot(name, sessionId, selectedSlot);
      await refreshSlots(sessionId, name);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : String(err));
    }
  }, [sessionId, selectedSlot]);

  return {
    handleGenerate, handleNewSession, handleCampaignChange, handleSlotChange, handleCreateSlot,
  };
}
