export type DialogueLine = {
  speaker: string;
  text: string;
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
};

export type GameState = {
  sanity: number;
  health: number;
  turn: number;
  current_location: string;
  items: Array<Record<string, string>>;
  npcs: Array<Record<string, string>>;
  quests: Array<Record<string, string>>;
  recent_events: string[];
};

export type RetrievedChunk = {
  id: string;
  title: string;
  source_type: string;
  content: string;
  score: number;
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
