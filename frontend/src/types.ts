export type DialogueLine = {
  speaker: string;
  text: string;
};

export type ItemMemory = {
  name: string;
  status?: string;
  description?: string;
  location?: string;
  notes?: string;
};

export type NPCMemory = {
  name: string;
  // The model still emits this older key for NPCs; the server folds it into
  // `relationship` before merging, so it only appears in raw declarations.
  disposition?: string;
  status?: string;
  relationship?: string;
  current_location?: string;
  description?: string;
  notes?: string;
};

export type QuestMemory = {
  name: string;
  status?: string;
  description?: string;
  objective?: string;
  notes?: string;
};

export type WorldFactMemory = {
  name: string;
  status?: string;
  description?: string;
  source?: string;
  notes?: string;
};

export type PlayerStatus = {
  condition?: string;
  danger_level?: string;
  current_goal?: string;
  notes?: string;
};

export type MemoryUpdates = {
  current_location?: string;
  items_upserted?: ItemMemory[];
  items_removed?: ItemMemory[];
  npcs_upserted?: NPCMemory[];
  quests_upserted?: QuestMemory[];
  world_facts_upserted?: WorldFactMemory[];
  player_status_patch?: PlayerStatus;
  key_event?: string;
};

export type StoryOptionCheck = {
  requires_check?: boolean;
  name?: string;
  skill?: string;
  system?: string;
  expression?: string;
  target?: number;
  difficulty?: "容易" | "普通" | "困难" | "极难";
  stakes?: string;
};

/**
 * Shape of one entry in the legacy delta lists. The server merges these into
 * state before `memory_updates` does, so a name may appear in both.
 */
export type StoryDeltaEntry = Record<string, unknown>;

export type StoryOutput = {
  narration: string;
  dialogue: DialogueLine[];
  scene_prompt: string;
  sanity_delta: number;
  health_delta: number;
  options: string[];
  option_checks?: Array<StoryOptionCheck | null>;
  game_over: boolean;
  game_over_reason: string;
  current_location: string;
  items_gained?: StoryDeltaEntry[];
  items_lost?: StoryDeltaEntry[];
  npcs_encountered?: StoryDeltaEntry[];
  quests_updated?: StoryDeltaEntry[];
  memory_updates?: MemoryUpdates;
  npc_relations_delta?: StoryDeltaEntry[] | null;
};

export type GameState = {
  sanity: number;
  health: number;
  turn: number;
  current_location: string;
  items: ItemMemory[];
  npcs: NPCMemory[];
  quests: QuestMemory[];
  world_facts: WorldFactMemory[];
  player_status: PlayerStatus;
  recent_events: string[];
};

export type RetrievedChunk = {
  id: string;
  title: string;
  source_type: string;
  content: string;
  score: number;
  keywords?: string[];
  importance?: number;
};

export type SessionResponse = {
  session_id: string;
  game_name: string;
  model: string;
  state: GameState;
  campaign_filename?: string | null;
  active_turn_id?: number | null;
};

export type GenerateResponse = {
  session_id: string;
  state: GameState;
  output: StoryOutput;
  retrieved_chunks: RetrievedChunk[];
  model_output_id: number | null;
  used_model: string;
  source: "scripted" | "llm" | "examiner_blocked";
  timeline_node_id: number;
  parent_timeline_node_id: number;
};

export type SessionMessage = {
  id: number;
  role: string;
  content: string;
  created_at: string;
};

export type SessionHistoryResponse = {
  session_id: string;
  messages: SessionMessage[];
};

export type TimelineNodeSummary = {
  id: number;
  parent_id: number | null;
  depth: number;
  label: string;
  player_action: string;
  narration_preview: string;
  location: string;
  turn: number;
  source: GenerateResponse["source"];
  created_at: string;
  is_active: boolean;
  is_on_active_path: boolean;
};

export type TimelineResponse = {
  session_id: string;
  active_node_id: number | null;
  campaign_filename?: string | null;
  nodes: TimelineNodeSummary[];
};

/**
 * What was injected into one turn's prompt. `recorded` is false for turns
 * stored before the prompt was persisted; the other keys are then empty
 * rather than absent, so the client never has to guess which case it hit.
 */
export type TurnContext = {
  recorded: boolean;
  retrieved_chunks: RetrievedChunk[];
  token_count: number;
  latency_ms: number;
  word_count: number;
  prompt_sections: Record<string, string>;
  prompt_text: string;
};

export type TimelineNodeDetail = {
  id: number;
  session_id: string;
  parent_id: number | null;
  depth: number;
  player_action: string;
  output: StoryOutput | null;
  state: GameState;
  campaign_progress: Record<string, unknown>;
  context: TurnContext;
  /** Category limits, so a full category can be told apart from a quiet one. */
  caps: Record<MemoryCategory, number>;
  /**
   * The turn's declaration in merge order, exactly as the server folds it.
   * Server-derived for the same reason `memory` is.
   */
  declared: Record<MemoryCategory, { upserted: StoryDeltaEntry[]; removed: StoryDeltaEntry[] }>;
  /** Folded server-side; the client must not re-derive the merge order. */
  memory: MemoryTraceEntry;
  model: string;
  source: GenerateResponse["source"];
  created_at: string;
};

export type MemoryCategory = "items" | "npcs" | "quests" | "world_facts";

/** Names a turn declared, and the names state held once it was merged. */
export type MemoryTraceEntry = Record<MemoryCategory, { declared: string[]; held: string[] }>;

export type MemoryTraceNode = MemoryTraceEntry & {
  node_id: number;
  parent_id: number | null;
  depth: number;
  turn: number;
  is_on_active_path: boolean;
};

export type MemoryTraceResponse = {
  session_id: string;
  caps: Record<MemoryCategory, number>;
  nodes: MemoryTraceNode[];
};

// ── Campaign types (CAMP-10) ──

export type AnchorTriggerConditions = {
  location?: string | null;
  npc_present?: string | null;
  item_held?: string | null;
};

export type CampaignAnchorEvent = {
  id: string;
  name: string;
  description: string;
  priority: number;
  trigger_conditions: AnchorTriggerConditions;
};

export type CampaignSession = {
  name: string;
  opening_scene: string;
  max_turns_per_session?: number;
  anchor_events: CampaignAnchorEvent[];
};

export type CampaignArc = {
  name: string;
  goal: string;
  sessions: CampaignSession[];
};

export type CampaignSchema = {
  version: number;
  title: string;
  core_conflict: string;
  arcs: CampaignArc[];
  constraints: string;
  starting_state: Record<string, unknown>;
};

export type CampaignListItem = {
  filename: string;
  title: string;
  version: number;
  arc_count: number;
};

export type CampaignListResponse = {
  campaigns: CampaignListItem[];
};

export type CampaignDetailResponse = {
  filename: string;
  campaign: CampaignSchema;
};

export type SaveSlot = {
  id: number;
  campaign_id: string;
  slot_name: string;
  arc_index: number;
  session_index: number;
  turn_in_session: number;
  last_played: string;
  campaign_filename?: string | null;
  is_active?: boolean;
  head_turn_id?: number | null;
};
