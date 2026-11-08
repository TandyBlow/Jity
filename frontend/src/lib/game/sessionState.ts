import { ENTRY_ACTION, SLOT_DEFAULT, loadingOutput } from "@/lib/game/initialOutput";
import type {
  CampaignProgressSummary, GameState, GenerateResponse, RetrievedChunk,
  SaveSlot, SessionResponse, StoryOutput, TimelineNodeDetail, TurnReport,
} from "@/types";

export type GameSessionState = {
  sessionId: string;
  model: string;
  state: GameState | null;
  activeTurnId: number | null;
  output: StoryOutput;
  turnReport: TurnReport | null;
  campaignProgress: CampaignProgressSummary | null;
  outputSource: GenerateResponse["source"];
  chunks: RetrievedChunk[];
  action: string;
  isLoading: boolean;
  error: string;
  slots: SaveSlot[];
  selectedSlot: string;
  selectedSlotId: number | "";
  selectedCampaign: string;
  pendingGenerate: string | null;
  restoreVersion: number;
};

export const initialSessionState: GameSessionState = {
  sessionId: "", model: "deepseek-v4-flash", state: null, activeTurnId: null,
  output: loadingOutput, turnReport: null, campaignProgress: null,
  outputSource: "scripted", chunks: [], action: "", isLoading: true, error: "",
  slots: [], selectedSlot: SLOT_DEFAULT, selectedSlotId: "",
  selectedCampaign: "default_campaign.json", pendingGenerate: null, restoreVersion: 0,
};

type SessionSnapshot = {
  session: SessionResponse;
  node: TimelineNodeDetail | null;
  slots: SaveSlot[];
  preferredSlotName: string;
};

export type GameSessionEvent =
  | { type: "requestStarted" }
  | { type: "requestFinished" }
  | { type: "requestFailed"; error: string }
  | { type: "turnSucceeded"; response: GenerateResponse }
  | ({ type: "sessionRestored" } & SessionSnapshot)
  | { type: "slotsRefreshed"; sessionId: string; slots: SaveSlot[]; preferredSlotName: string }
  | { type: "openingConsumed" }
  | { type: "actionChanged"; action: string }
  | { type: "modelChanged"; model: string };

function slotSelection(
  slots: SaveSlot[], sessionId: string, preferredSlotName: string,
): Pick<GameSessionState, "slots" | "selectedSlot" | "selectedSlotId"> {
  const current = slots.filter((slot) => slot.campaign_id === sessionId);
  const active = current.find((slot) => slot.slot_name === preferredSlotName)
    ?? current.find((slot) => slot.is_active);
  // Deleting the current save must not redirect later autosaves into another slot.
  return { slots, selectedSlot: active?.slot_name ?? (preferredSlotName || SLOT_DEFAULT), selectedSlotId: active?.id ?? "" };
}

/** Apply a complete server result together; callers never synchronize individual fields. */
export function gameSessionReducer(state: GameSessionState, event: GameSessionEvent): GameSessionState {
  switch (event.type) {
    case "requestStarted":
      return { ...state, isLoading: true, error: "" };
    case "requestFinished":
      return { ...state, isLoading: false };
    case "requestFailed":
      return { ...state, error: event.error };
    case "turnSucceeded": {
      const r = event.response;
      return {
        ...state, sessionId: r.session_id, state: r.state, activeTurnId: r.timeline_node_id,
        output: r.output, turnReport: { memory: r.memory, declared: r.declared, caps: r.caps },
        campaignProgress: r.campaign_progress ?? null, outputSource: r.source,
        chunks: r.retrieved_chunks, model: r.used_model, action: "", error: "", pendingGenerate: null,
      };
    }
    case "sessionRestored": {
      const { session, node, slots, preferredSlotName } = event;
      const campaign = session.campaign_filename ?? "";
      const hasOutput = !!node?.output;
      return {
        ...state, sessionId: session.session_id, state: session.state,
        activeTurnId: node?.id ?? session.active_turn_id ?? null, model: session.model,
        selectedCampaign: campaign, ...slotSelection(slots, session.session_id, preferredSlotName),
        output: node?.output ?? loadingOutput, outputSource: node?.output ? node.source : "scripted",
        turnReport: node?.output ? { memory: node.memory, declared: node.declared, caps: node.caps } : null,
        // Node progress is a persistence snapshot, not the toolbar's summary.
        // Clear the old summary so StoryPanel fetches the restored campaign budget.
        campaignProgress: null, chunks: [], action: "", restoreVersion: state.restoreVersion + 1,
        pendingGenerate: !hasOutput && campaign ? ENTRY_ACTION : null,
        error: !hasOutput && !campaign ? "该历史会话未关联战役，请新建战役。" : "",
      };
    }
    case "slotsRefreshed":
      if (event.sessionId !== state.sessionId) return state;
      return { ...state, ...slotSelection(event.slots, event.sessionId, event.preferredSlotName) };
    case "openingConsumed":
      return { ...state, pendingGenerate: null };
    case "actionChanged":
      return { ...state, action: event.action };
    case "modelChanged":
      return { ...state, model: event.model };
  }
}
