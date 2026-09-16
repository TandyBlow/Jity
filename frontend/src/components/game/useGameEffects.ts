"use client";

import { useEffect, useRef } from "react";

import { createSession, getSession, listCampaigns, listSlots } from "@/lib/api";
import { SLOT_DEFAULT } from "@/lib/game/initialOutput";
import type { CampaignListItem, SaveSlot, SessionResponse } from "@/types";
import type { GameSessionCore } from "@/components/game/useGameSession";

/** Side-effect effects for the game console (session init, campaign list, save slots). */
export function useGameEffects(
  core: GameSessionCore,
  extras: {
    setSlots: (slots: SaveSlot[]) => void;
    setCampaigns: (campaigns: CampaignListItem[]) => void;
    handleGenerate: (action?: string, overrideSessionId?: string) => Promise<void>;
  },
) {
  const { sessionId, model, selectedSlot, pendingGenerate, refreshSlots } = core;
  const { setSlots, setCampaigns, handleGenerate } = extras;

  const ACTIVE_SESSION_STORAGE_KEY = "jity_active_session_id";

  function rememberActiveSession(sessionId: string) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
    }
  }

  // Retain the request across React Strict Mode effect replay. In particular,
  // consume campaign_entry once and do not create a second free-play session.
  const bootRequest = useRef<Promise<SessionResponse> | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadInitialSession(): Promise<SessionResponse> {
      let campaignOpts: { campaignFilename?: string; arcIndex?: number; sessionIndex?: number } | undefined;
      try {
        const entryJson = sessionStorage.getItem("campaign_entry");
        if (entryJson) {
          campaignOpts = JSON.parse(entryJson);
          sessionStorage.removeItem("campaign_entry");
        }
      } catch { /* Ignore malformed timeline entries. */ }

      if (campaignOpts?.campaignFilename) return createSession(model, campaignOpts);

      const activeSessionId = window.localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
      if (activeSessionId) {
        try {
          return await getSession(activeSessionId);
        } catch {
          window.localStorage.removeItem(ACTIVE_SESSION_STORAGE_KEY);
        }
      }
      return createSession(model);
    }

    bootRequest.current ??= loadInitialSession();
    bootRequest.current.then(async (session) => {
      if (!mounted) return;
      rememberActiveSession(session.session_id);
      core.setSessionId(session.session_id);
      core.setState(session.state);
      core.setActiveTurnId(session.active_turn_id ?? null);
      core.setModel(session.model);
      core.setSelectedCampaign(session.campaign_filename ?? "");
      core.setChunks([]);
      await refreshSlots(session.session_id);
      await core.restoreLastOutput(session.session_id, session.campaign_filename, session.active_turn_id);
    }).catch((err: Error) => {
      if (mounted) core.setError(err.message);
    }).finally(() => {
      if (mounted) core.setIsLoading(false);
    });

    return () => { mounted = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Load campaigns ──
  useEffect(() => {
    listCampaigns()
      .then((r) => {
        setCampaigns(r.campaigns ?? []);
      })
      .catch((err) => console.error("listCampaigns failed:", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Load save slots ──
  useEffect(() => {
    if (!sessionId) {
      setSlots([]);
      core.setSelectedSlot(SLOT_DEFAULT);
      core.setSelectedSlotId("");
      return;
    }
    listSlots(sessionId).then(r => {
      const nextSlots = (r.slots ?? []).filter((slot) => slot.campaign_id === sessionId);
      setSlots(nextSlots);
      const active = nextSlots.find((slot) => slot.is_active)
        ?? nextSlots.find((slot) => slot.slot_name === selectedSlot);
      if (active) {
        core.setSelectedSlot(active.slot_name);
        core.setSelectedSlotId(active.id);
      } else {
        core.setSelectedSlot(SLOT_DEFAULT);
        core.setSelectedSlotId("");
      }
    }).catch((err) => console.error("listSlots failed:", err));
  /* selectedSlot intentionally excluded: changing preferred slot name while
     session stays the same should not reload the list — only a new session does */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // ── Load the opening for every fresh campaign, including its first arc ──
  useEffect(() => {
    if (!pendingGenerate || !sessionId) return;
    core.setPendingGenerate(null);
    handleGenerate(pendingGenerate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingGenerate, sessionId]);
}
