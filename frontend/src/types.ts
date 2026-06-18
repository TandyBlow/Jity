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

export type StoryOutput = {
  narration: string;
  dialogue: DialogueLine[];
  scene_prompt: string;
  sanity_delta: number;
  health_delta: number;
  options: string[];
  game_over: boolean;
  game_over_reason: string;
  current_location: string;
  memory_updates?: MemoryUpdates;
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
};

export type GenerateResponse = {
  session_id: string;
  state: GameState;
  output: StoryOutput;
  retrieved_chunks: RetrievedChunk[];
  model_output_id: number | null;
  used_model: string;
  source: "scripted" | "llm";
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

export type CampaignProgressData = {
  campaign_id: string;
  arc_index: number;
  session_index: number;
  revealed_anchors: string[];
  completed_arcs: number[];
};
