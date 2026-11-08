"use client";

import { useCallback, useMemo, useReducer, useRef, useState } from "react";
import type { Dispatch } from "react";

import { getTimelineNode, listSlots } from "@/lib/api";
import { SLOT_DEFAULT } from "@/lib/game/initialOutput";
import { buildStatusDeltaHints } from "@/lib/game/format";
import { gameSessionReducer, initialSessionState } from "@/lib/game/sessionState";
import type { GameSessionEvent, GameSessionState } from "@/lib/game/sessionState";
import { useGameActions } from "@/components/game/useGameActions";
import { useGameEffects } from "@/components/game/useGameEffects";
import { useSceneBackground } from "@/components/game/useSceneBackground";
import { useBrowserAutoPlay } from "@/components/game/useBrowserAutoPlay";
import type { CampaignListItem, SavePurpose, SessionResponse } from "@/types";

/** Read-only inputs and complete state events shared by the session hooks. */
export type GameSessionCore = Pick<GameSessionState,
  "sessionId" | "activeTurnId" | "model" | "action" | "selectedSlot" | "selectedCampaign" | "pendingGenerate"
> & {
  dispatch: Dispatch<GameSessionEvent>;
  gameOver: boolean;
  refreshSlots: (sessionId?: string, preferredSlotName?: string) => Promise<void>;
  restoreSession: (session: SessionResponse, preferredSlotName?: string, options?: { fresh?: boolean }) => Promise<void>;
};

export function useGameSession(initialSession?: SessionResponse) {
  const [session, dispatch] = useReducer(gameSessionReducer, initialSessionState);
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const savePurpose = useRef<SavePurpose>("user");
  const {
    sessionId, activeTurnId, model, action, selectedSlot, selectedCampaign,
    pendingGenerate, state, output, isLoading, error,
  } = session;
  const statusDeltaHints = useMemo(() => buildStatusDeltaHints(output), [output]);

  const refreshSlots = useCallback(async (sid = sessionId, preferredSlotName = selectedSlot) => {
    const slots = sid ? (await listSlots(undefined, savePurpose.current)).slots ?? [] : [];
    dispatch({ type: "slotsRefreshed", sessionId: sid, slots, preferredSlotName });
  }, [sessionId, selectedSlot]);

  const restoreSession = useCallback(async (next: SessionResponse, preferredSlotName: string = SLOT_DEFAULT, options?: { fresh?: boolean }) => {
    // Read everything first: a failed refresh must not mix a new node ID/state
    // with the previous node's story, memory report or campaign progress.
    const [node, result] = await Promise.all([
      !options?.fresh && next.active_turn_id != null ? getTimelineNode(next.session_id, next.active_turn_id) : null,
      listSlots(undefined, next.save_purpose ?? "user"),
    ]);
    savePurpose.current = next.save_purpose ?? "user";
    dispatch({ type: "sessionRestored", session: next, node, slots: result.slots ?? [], preferredSlotName });
  }, []);

  const core: GameSessionCore = {
    sessionId, activeTurnId, model, action, selectedSlot, selectedCampaign,
    pendingGenerate, gameOver: output.game_over, dispatch, refreshSlots, restoreSession,
  };
  const actions = useGameActions(core);
  useGameEffects(core, { setCampaigns, handleGenerate: actions.handleGenerate }, initialSession);
  const autoPlay = useBrowserAutoPlay({
    sessionId, activeTurnId, selectedCampaign, state, output, isLoading, pendingGenerate, error,
    handleGenerate: actions.handleGenerate,
    handlePrepareCheck: actions.handlePrepareCheck,
  });
  const sceneBackground = useSceneBackground(output, state);

  return {
    ...session, ...actions, ...sceneBackground, statusDeltaHints, campaigns, autoPlay,
    setAction: (value: string) => dispatch({ type: "actionChanged", action: value }),
    setModel: (value: string) => dispatch({ type: "modelChanged", model: value }),
  };
}

export type GameSession = ReturnType<typeof useGameSession>;
