import type {
  CampaignDetailResponse,
  CampaignListResponse,
  GenerateResponse,
  SessionHistoryResponse,
  SessionResponse,
  WorldFactMemory,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text || `Request failed: ${response.status}`;
    try {
      const payload = JSON.parse(text) as { detail?: string };
      message = payload.detail || message;
    } catch {
      // Keep the raw response text when the error body is not JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function createSession(model?: string): Promise<SessionResponse> {
  return request<SessionResponse>("/sessions", {
    method: "POST",
    body: JSON.stringify({ model }),
  });
}

export function generateScene(params: {
  sessionId: string;
  playerAction: string;
  model?: string;
  style?: string;
  constraints?: string;
}): Promise<GenerateResponse> {
  return request<GenerateResponse>(`/sessions/${params.sessionId}/generate`, {
    method: "POST",
    body: JSON.stringify({
      player_action: params.playerAction,
      model: params.model,
      style: params.style,
      constraints: params.constraints,
    }),
  });
}

export function getSessionHistory(sessionId: string): Promise<SessionHistoryResponse> {
  return request<SessionHistoryResponse>(`/sessions/${sessionId}/history`);
}

// ── Campaign API ──

export function listCampaigns(): Promise<CampaignListResponse> {
  return request<CampaignListResponse>("/campaigns");
}

export function getCampaign(filename: string): Promise<CampaignDetailResponse> {
  return request<CampaignDetailResponse>(`/campaigns/${encodeURIComponent(filename)}`);
}

export function getSessionProgress(sessionId: string): Promise<{
  session_id: string;
  revealed_anchors: string[];
  arc_index: number;
  session_index: number;
  world_facts: WorldFactMemory[];
}> {
  return request<{
    session_id: string;
    revealed_anchors: string[];
    arc_index: number;
    session_index: number;
    world_facts: WorldFactMemory[];
  }>(`/sessions/${sessionId}/progress`);
}
