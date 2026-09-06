"use client";

import { useEffect } from "react";

import { createSession, listCampaigns, listSlots } from "@/lib/api";
import { ENTRY_ACTION, SLOT_DEFAULT } from "@/lib/game/initialOutput";
import type { CampaignListItem, SaveSlot } from "@/types";
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

  // ── Session init ──
  useEffect(() => {
    let mounted = true;

    let campaignOpts: { campaignFilename?: string; arcIndex?: number; sessionIndex?: number } | undefined;
    try {
      const entryJson = sessionStorage.getItem("campaign_entry");
      if (entryJson) {
        const entry = JSON.parse(entryJson);
        sessionStorage.removeItem("campaign_entry");
        campaignOpts = {
          campaignFilename: entry.campaignFilename,
          arcIndex: entry.arcIndex,
          sessionIndex: entry.sessionIndex,
        };
      }
    } catch {
      // Ignore parse errors
    }

    createSession(model, campaignOpts)
      .then(async (session) => {
        if (!mounted) return;
        core.setSessionId(session.session_id);
        core.setState(session.state);
        core.setModel(session.model);
        core.setSelectedSlot(SLOT_DEFAULT);
        core.setSelectedSlotId("");
        refreshSlots(session.session_id, SLOT_DEFAULT).catch((err) => console.error("refreshSlots failed:", err));
        if (campaignOpts?.campaignFilename && (campaignOpts.arcIndex || 0) > 0) {
          core.setPendingGenerate(ENTRY_ACTION);
        }
      })
      .catch((err: Error) => core.setError(err.message));
    return () => { mounted = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Load campaigns ──
  useEffect(() => {
    listCampaigns()
      .then((r) => {
        setCampaigns(r.campaigns ?? []);
        try {
          const entryJson = sessionStorage.getItem("campaign_entry");
          if (entryJson) {
            const entry = JSON.parse(entryJson);
            if (entry.campaignFilename) core.setSelectedCampaign(entry.campaignFilename);
          }
        } catch { /* ignore */ }
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

  // ── Auto-generate after session created for mid-campaign entry ──
  useEffect(() => {
    if (!pendingGenerate || !sessionId) return;
    core.setPendingGenerate(null);
    handleGenerate(pendingGenerate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingGenerate, sessionId]);
}
