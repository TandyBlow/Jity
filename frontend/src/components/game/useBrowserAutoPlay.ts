"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getCampaign, getSessionProgress } from "@/lib/api";
import { activeGoalsFromState, chooseGoalAwareOption } from "@/lib/game/autoPlay";
import { formatActionWithCheckResult, resolveOptionCheck, rollCheck, seededRoll } from "@/lib/game/checks";
import type { GameState, StoryOutput } from "@/types";

type AutoPlayConfig = {
  enabled: boolean;
  sessionId: string;
  targetTurns: number;
  delayMs: number;
  seed: number;
  paused: boolean;
};

export type AutoPlayAnchor = { id: string; name: string; isNew: boolean };

export function useBrowserAutoPlay(input: {
  sessionId: string;
  selectedCampaign: string;
  state: GameState | null;
  output: StoryOutput;
  isLoading: boolean;
  pendingGenerate: string | null;
  error: string;
  handleGenerate: (action?: string, overrideSessionId?: string) => Promise<void>;
}) {
  const config = useMemo(readConfig, []);
  const [paused, setPaused] = useState(config.paused);
  const [selectedAction, setSelectedAction] = useState("");
  const [selectionReason, setSelectionReason] = useState("");
  const [revealedAnchors, setRevealedAnchors] = useState<AutoPlayAnchor[]>([]);
  const [status, setStatus] = useState<"idle" | "running" | "paused" | "complete" | "error">(
    config.enabled ? "running" : "idle",
  );
  const recentActions = useRef<string[]>([]);
  const lastScheduledTurn = useRef<number | null>(null);
  const scheduledTimer = useRef<number | null>(null);
  const submittedAction = useRef("");
  const retryAttempts = useRef(0);
  const previousAnchorIds = useRef<string[]>([]);
  const anchorNames = useRef<Record<string, string>>({});
  const goals = useMemo(() => activeGoalsFromState(input.state), [input.state]);
  const currentTurn = input.state?.turn ?? 0;
  const retryTurn = useRef(currentTurn);
  const isTargetSession = !config.sessionId || config.sessionId === input.sessionId;
  const query = new URLSearchParams({
    autoplay: "1",
    session: input.sessionId || config.sessionId,
    turns: String(config.targetTurns),
    delay: String(config.delayMs),
    seed: String(config.seed),
  }).toString();
  const resumeUrl = `/?${query}`;
  const timelineUrl = `/timeline?${query}&tab=anchors`;

  useEffect(() => {
    if (!config.enabled || !input.sessionId || !isTargetSession) return;
    window.sessionStorage.setItem(storageKey(input.sessionId), JSON.stringify({
      targetTurns: config.targetTurns,
      delayMs: config.delayMs,
      seed: config.seed,
      paused,
    }));
  }, [config, input.sessionId, isTargetSession, paused]);

  useEffect(() => {
    if (!config.enabled || !input.selectedCampaign) return;
    getCampaign(input.selectedCampaign).then((detail) => {
      const names: Record<string, string> = {};
      for (const arc of detail.campaign.arcs ?? []) {
        for (const campaignSession of arc.sessions ?? []) {
          for (const anchor of campaignSession.anchor_events ?? []) names[anchor.id] = anchor.name;
        }
      }
      anchorNames.current = names;
    }).catch(() => undefined);
  }, [config.enabled, input.selectedCampaign]);

  useEffect(() => {
    if (!config.enabled || !input.sessionId || !isTargetSession) return;
    getSessionProgress(input.sessionId).then((progress) => {
      const ids = progress.revealed_anchors ?? [];
      const previous = previousAnchorIds.current;
      setRevealedAnchors(ids.map((id) => ({
        id,
        name: anchorNames.current[id] || id,
        isNew: !previous.includes(id),
      })));
      previousAnchorIds.current = ids;
    }).catch(() => undefined);
  }, [config.enabled, currentTurn, input.sessionId, isTargetSession]);

  useEffect(() => {
    if (!config.enabled || !isTargetSession) return;
    if (paused) {
      setStatus("paused");
      return;
    }
    if (currentTurn >= config.targetTurns || input.output.game_over) {
      setStatus("complete");
      return;
    }
    setStatus("running");
    if (!input.sessionId || input.isLoading || input.pendingGenerate) return;

    if (retryTurn.current !== currentTurn) {
      retryTurn.current = currentTurn;
      retryAttempts.current = 0;
    }
    if (input.error) {
      if (!selectedAction || retryAttempts.current >= 10 || scheduledTimer.current !== null) {
        if (retryAttempts.current >= 10) setStatus("error");
        return;
      }
      const retryDelay = Math.min(30_000, 2_000 * (2 ** retryAttempts.current));
      setSelectionReason(`生成请求失败，将在 ${Math.ceil(retryDelay / 1000)} 秒后自动重试（${retryAttempts.current + 1}/10）`);
      scheduledTimer.current = window.setTimeout(() => {
        scheduledTimer.current = null;
        retryAttempts.current += 1;
        lastScheduledTurn.current = null;
        input.handleGenerate(submittedAction.current || selectedAction);
      }, retryDelay);
      return () => {
        if (scheduledTimer.current !== null) window.clearTimeout(scheduledTimer.current);
        scheduledTimer.current = null;
      };
    }
    if (!input.output.options.length || lastScheduledTurn.current === currentTurn || scheduledTimer.current !== null) return;

    const choice = chooseGoalAwareOption(
      input.output.options,
      goals,
      recentActions.current,
      config.seed + currentTurn * 104729,
    );
    // Auto-play drives no dice UI, so a check is rolled headlessly with a seeded
    // d20 and reported in the action text exactly like the manual path does.
    // The chosen index is resolved against the raw options because
    // chooseGoalAwareOption numbers the list after dropping blank entries.
    const optionIndex = input.output.options.findIndex((option) => option.trim() === choice.action);
    const check = optionIndex < 0 ? null : resolveOptionCheck(input.output, optionIndex);
    const roll = check
      ? rollCheck(check, seededRoll(config.seed + currentTurn * 7919))
      : null;
    const action = check && roll
      ? formatActionWithCheckResult(choice.action, check, roll)
      : choice.action;

    setSelectedAction(choice.action);
    setSelectionReason(roll ? `${choice.reason} | ${check?.name} ${roll.degree}` : choice.reason);
    recentActions.current = [...recentActions.current, choice.action].slice(-12);
    submittedAction.current = action;

    scheduledTimer.current = window.setTimeout(() => {
      scheduledTimer.current = null;
      lastScheduledTurn.current = currentTurn;
      input.handleGenerate(action);
    }, config.delayMs);
    return () => {
      if (scheduledTimer.current !== null) window.clearTimeout(scheduledTimer.current);
      scheduledTimer.current = null;
    };
  }, [
    config, currentTurn, goals, input.error, input.handleGenerate, input.isLoading,
    input.output.game_over, input.output.options, input.pendingGenerate, input.sessionId,
    isTargetSession, paused, selectedAction,
  ]);

  return {
    enabled: config.enabled && isTargetSession,
    targetTurns: config.targetTurns,
    delayMs: config.delayMs,
    status,
    paused,
    setPaused,
    selectedAction,
    selectionReason,
    goals,
    currentTurn,
    revealedAnchors,
    resumeUrl,
    timelineUrl,
  };
}

function readConfig(): AutoPlayConfig {
  if (typeof window === "undefined") {
    return { enabled: false, sessionId: "", targetTurns: 300, delayMs: 200, seed: 20260616, paused: false };
  }
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session") ?? "";
  let saved: { targetTurns?: number; delayMs?: number; seed?: number; paused?: boolean } = {};
  try {
    saved = sessionId ? JSON.parse(window.sessionStorage.getItem(storageKey(sessionId)) || "{}") : {};
  } catch { /* Ignore a malformed saved auto-play state. */ }
  const numberParam = (name: string, fallback: number, minimum: number) => {
    const parsed = Number(params.get(name));
    return params.has(name) && Number.isFinite(parsed) ? Math.max(minimum, Math.floor(parsed)) : fallback;
  };
  return {
    enabled: params.get("autoplay") === "1",
    sessionId,
    targetTurns: numberParam("turns", saved.targetTurns ?? 300, 1),
    delayMs: numberParam("delay", saved.delayMs ?? 200, 0),
    seed: numberParam("seed", saved.seed ?? 20260616, 0),
    paused: saved.paused ?? false,
  };
}

function storageKey(sessionId: string): string {
  return `jity_autoplay_${sessionId}`;
}
