import type {
  CampaignDetailResponse,
  CampaignListResponse,
  CampaignSchema,
  GenerateResponse,
  SaveSlot,
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

export function createSession(
  model?: string,
  options?: {
    campaignFilename?: string;
    arcIndex?: number;
    sessionIndex?: number;
    slotName?: string;
  },
): Promise<SessionResponse> {
  const body: Record<string, unknown> = { model };
  if (options?.campaignFilename) {
    body.campaign_filename = options.campaignFilename;
    body.arc_index = options.arcIndex ?? 0;
    body.session_index = options.sessionIndex ?? 0;
    body.slot_name = options.slotName ?? "default";
  }
  return request<SessionResponse>("/sessions", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function generateScene(params: {
  sessionId: string;
  playerAction: string;
  model?: string;
  style?: string;
  constraints?: string;
  slotName?: string;
}): Promise<GenerateResponse> {
  return request<GenerateResponse>(`/sessions/${params.sessionId}/generate`, {
    method: "POST",
    body: JSON.stringify({
      player_action: params.playerAction,
      model: params.model,
      style: params.style,
      constraints: params.constraints,
      slot_name: params.slotName,
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

// ── Save Slot API ──

export function listSlots(sessionId?: string): Promise<{
  slots: SaveSlot[];
}> {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return request(`/campaigns/slots${query}`);
}

export function createSlot(slotName: string, sessionId: string, sourceSlotName?: string): Promise<{ status: string; slot_name: string; campaign_id: string }> {
  return request("/campaigns/slots", {
    method: "POST",
    body: JSON.stringify({ slot_name: slotName, session_id: sessionId, source_slot_name: sourceSlotName }),
  });
}

export function loadSlot(slotId: number): Promise<{ status: string; slot: SaveSlot; session: SessionResponse }> {
  return request(`/campaigns/slots/${slotId}/load`, { method: "POST" });
}

// ── Campaign Generation API ──

export function generateCampaign(prompt: string): Promise<{ campaign?: CampaignSchema; saved_to?: string; detail?: string }> {
  return request("/campaigns/generate", {
    method: "POST",
    body: JSON.stringify({ prompt }),
  });
}

export async function generateFromNovel(file: File): Promise<{
  campaign?: CampaignSchema;
  extraction_errors?: string[];
  detail?: string;
}> {
  const formData = new FormData();
  formData.append("file", file);

  // FormData requires no Content-Type header (browser sets multipart boundary)
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const response = await fetch(`${baseUrl}/campaigns/generate-from-novel`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: "上传失败" }));
    throw new Error((payload as { detail?: string }).detail ?? "上传失败");
  }

  return response.json();
}

export function saveCampaign(filename: string, campaign: unknown): Promise<{ status?: string; detail?: string }> {
  return request("/campaigns/save", {
    method: "POST",
    body: JSON.stringify({ filename, campaign }),
  });
}