"use client";

import { useMemo, useState } from "react";

import { getSessionHistory, listSlots } from "@/lib/api";
import { ENTRY_ACTION, SLOT_DEFAULT, initialOutput, loadingOutput } from "@/lib/game/initialOutput";
import { buildStatusDeltaHints } from "@/lib/game/format";
import { useGameActions } from "@/components/game/useGameActions";
import { useGameEffects } from "@/components/game/useGameEffects";
import { useSceneBackground } from "@/components/game/useSceneBackground";
import type {
  CampaignListItem,
  GameState,
  GenerateResponse,
  RetrievedChunk,
  SaveSlot,
  StoryOutput,
} from "@/types";

/** State surface + slot helpers shared with useGameActions. */
export type GameSessionCore = {
  sessionId: string;
  setSessionId: (sessionId: string) => void;
  setState: (state: GameState) => void;
  model: string;
  setModel: (model: string) => void;
  action: string;
  setAction: (action: string) => void;
  setOutput: (output: StoryOutput) => void;
  setOutputSource: (source: GenerateResponse["source"]) => void;
  setChunks: (chunks: RetrievedChunk[]) => void;
  setIsLoading: (isLoading: boolean) => void;
  setError: (error: string) => void;
  selectedSlot: string;
  setSelectedSlot: (slot: string) => void;
  setSelectedSlotId: (slotId: number | "") => void;
  selectedCampaign: string;
  setSelectedCampaign: (campaign: string) => void;
  pendingGenerate: string | null;
  setPendingGenerate: (action: string | null) => void;
  refreshSlots: (sessionId?: string, preferredSlotName?: string) => Promise<void>;
  restoreLastOutput: (sessionId: string, campaignFilename?: string | null) => Promise<void>;
};

export function useGameSession() {
  const [sessionId, setSessionId] = useState("");
  const [model, setModel] = useState("deepseek-v4-flash");
  const [state, setState] = useState<GameState | null>(null);
  const [output, setOutput] = useState<StoryOutput>(loadingOutput);
  const [outputSource, setOutputSource] = useState<GenerateResponse["source"]>("scripted");
  const [chunks, setChunks] = useState<RetrievedChunk[]>([]);
  const [action, setAction] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [slots, setSlots] = useState<SaveSlot[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<string>(SLOT_DEFAULT);
  const [selectedSlotId, setSelectedSlotId] = useState<number | "">("");
  const [campaigns, setCampaigns] = useState<CampaignListItem[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState("");
  const [pendingGenerate, setPendingGenerate] = useState<string | null>(null);

  const statusDeltaHints = useMemo(() => buildStatusDeltaHints(output), [output]);

  async function refreshSlots(currentSessionId = sessionId, preferredSlotName = selectedSlot) {
    if (!currentSessionId) {
      setSlots([]);
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
      return;
    }
    const updated = await listSlots(currentSessionId);
    const nextSlots = (updated.slots ?? []).filter((slot) => slot.campaign_id === currentSessionId);
    setSlots(nextSlots);
    const active = nextSlots.find((slot) => slot.slot_name === preferredSlotName)
      ?? nextSlots.find((slot) => slot.is_active);
    if (active) {
      setSelectedSlot(active.slot_name);
      setSelectedSlotId(active.id);
    } else {
      setSelectedSlot(SLOT_DEFAULT);
      setSelectedSlotId("");
    }
  }

  async function restoreLastOutput(nextSessionId: string, campaignFilename?: string | null) {
    setSelectedCampaign(campaignFilename ?? "");
    setAction("");
    const history = await getSessionHistory(nextSessionId);
    const lastAssistant = [...history.messages].reverse().find((message) => message.role === "assistant");
    if (lastAssistant) {
      setOutput(JSON.parse(lastAssistant.content) as StoryOutput);
      setOutputSource("llm");
    } else if (campaignFilename) {
      setOutput(loadingOutput);
      setPendingGenerate(ENTRY_ACTION);
    } else {
      setOutput(initialOutput);
      setOutputSource("scripted");
      setAction(initialOutput.options[0] ?? "");
    }
  }

  const core: GameSessionCore = {
    sessionId,
    setSessionId,
    setState: (next: GameState) => setState(next),
    model,
    setModel,
    action,
    setAction: (next: string) => setAction(next),
    setOutput: (next: StoryOutput) => setOutput(next),
    setOutputSource: (next: GenerateResponse["source"]) => setOutputSource(next),
    setChunks: (next: RetrievedChunk[]) => setChunks(next),
    setIsLoading: (next: boolean) => setIsLoading(next),
    setError: (next: string) => setError(next),
    selectedSlot,
    setSelectedSlot: (next: string) => setSelectedSlot(next),
    setSelectedSlotId: (next: number | "") => setSelectedSlotId(next),
    selectedCampaign,
    setSelectedCampaign: (next: string) => setSelectedCampaign(next),
    pendingGenerate,
    setPendingGenerate: (next: string | null) => setPendingGenerate(next),
    refreshSlots,
    restoreLastOutput,
  };

  const actions = useGameActions(core);

  useGameEffects(core, { setSlots, setCampaigns, handleGenerate: actions.handleGenerate });
  const sceneBackground = useSceneBackground(output, state);

  return {
    ...core, ...actions,
    ...sceneBackground,
    state, output, outputSource, chunks, isLoading, error,
    statusDeltaHints, slots, selectedSlotId, campaigns,
  };
}

export type GameSession = ReturnType<typeof useGameSession>;
