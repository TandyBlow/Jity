"use client";

import { useEffect, useRef } from "react";

import { createSession, getSession, listCampaigns } from "@/lib/api";
import type { CampaignListItem, SessionResponse } from "@/types";
import type { GameSessionCore } from "@/components/game/useGameSession";

/** Initialize the console and consume one pending opening per fresh campaign. */
export function useGameEffects(
  core: GameSessionCore,
  extras: {
    setCampaigns: (campaigns: CampaignListItem[]) => void;
    handleGenerate: (action?: string, overrideSessionId?: string) => Promise<void>;
  },
  initialSession?: SessionResponse,
) {
  const { sessionId, model, pendingGenerate, dispatch, restoreSession } = core;
  const { setCampaigns, handleGenerate } = extras;

  const ACTIVE_SESSION_STORAGE_KEY = "jity_active_session_id";

  function rememberActiveSession(sessionId: string) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
    }
  }

  // Retain the request across React Strict Mode effect replay. In particular,
  // consume campaign_entry once and do not create a second campaign session.
  const bootRequest = useRef<Promise<SessionResponse> | null>(null);

  useEffect(() => {
    let mounted = true;

    async function loadInitialSession(): Promise<SessionResponse> {
      if (initialSession) return initialSession;
      const params = new URLSearchParams(window.location.search);
      const requestedSessionId = params.get("session");
      if (requestedSessionId) {
        const session = await getSession(requestedSessionId);
        if (!session.campaign_filename) throw new Error("该历史会话未关联战役，请新建战役。");
        return session;
      }

      let campaignOpts: { campaignFilename?: string; arcIndex?: number; sessionIndex?: number } | undefined;
      try {
        const entryJson = sessionStorage.getItem("campaign_entry");
        if (entryJson) {
          campaignOpts = JSON.parse(entryJson);
          sessionStorage.removeItem("campaign_entry");
        }
      } catch { /* Ignore malformed timeline entries. */ }

      if (campaignOpts?.campaignFilename) return createSession(model, campaignOpts);

      throw new Error("请选择战役或加载存档后进入游戏。");
    }

    bootRequest.current ??= loadInitialSession();
    bootRequest.current.then(async (session) => {
      if (!mounted) return;
      await restoreSession(session);
      if (mounted) rememberActiveSession(session.session_id);
    }).catch((err: Error) => {
      if (mounted) dispatch({ type: "requestFailed", error: err.message });
    }).finally(() => {
      if (mounted) dispatch({ type: "requestFinished" });
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

  // ── Load the opening for every fresh campaign, including its first arc ──
  useEffect(() => {
    if (!pendingGenerate || !sessionId) return;
    dispatch({ type: "openingConsumed" });
    handleGenerate(pendingGenerate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingGenerate, sessionId]);
}
