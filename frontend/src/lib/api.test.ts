import { afterEach, describe, expect, it, vi } from "vitest";

import {
  activateTimelineNode,
  createSession,
  fetchCampaignProgress,
  generateBackground,
  generateFromNovel,
  generateScene,
  getCampaign,
  getMemoryTrace,
  listSlots,
} from "./api";

/**
 * Pins the request/response mapping of the REST client.
 *
 * These run in Node with a stubbed global fetch — no jsdom, no browser. The
 * base URL is read at module load, so the assertions use its default.
 */

const BASE = "http://localhost:8000";

type Call = { url: string; init: RequestInit };

function stubFetch(response: { ok?: boolean; status?: number; body?: string }) {
  const calls: Call[] = [];
  const ok = response.ok ?? true;
  vi.stubGlobal("fetch", async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init });
    return {
      ok,
      status: response.status ?? (ok ? 200 : 500),
      text: async () => response.body ?? "",
      json: async () => JSON.parse(response.body ?? "null"),
    } as unknown as Response;
  });
  return calls;
}

const jsonBody = (init: RequestInit) => JSON.parse(String(init.body)) as Record<string, unknown>;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("error handling", () => {
  it("surfaces the detail field from a JSON error body", async () => {
    stubFetch({ ok: false, status: 422, body: JSON.stringify({ detail: "战役文件不存在" }) });

    await expect(getCampaign("missing.json")).rejects.toThrow("战役文件不存在");
  });

  it("falls back to the raw body when the error is not JSON", async () => {
    stubFetch({ ok: false, status: 502, body: "Bad Gateway" });

    await expect(getCampaign("x.json")).rejects.toThrow("Bad Gateway");
  });

  it("falls back to the status when the error body is empty", async () => {
    stubFetch({ ok: false, status: 503, body: "" });

    await expect(getCampaign("x.json")).rejects.toThrow("Request failed: 503");
  });
});

describe("createSession", () => {
  it("defaults to the campaign entry point when no campaign is supplied", async () => {
    const calls = stubFetch({ body: JSON.stringify({ session_id: "s" }) });

    await createSession("deepseek-v4-flash");

    expect(calls[0].url).toBe(`${BASE}/sessions`);
    expect(calls[0].init.method).toBe("POST");
    expect(jsonBody(calls[0].init)).toEqual({ model: "deepseek-v4-flash", campaign_filename: "default_campaign.json" });
  });

  it("defaults arc and session index to 0 when a campaign is given", async () => {
    const calls = stubFetch({ body: JSON.stringify({ session_id: "s" }) });

    await createSession("m", { campaignFilename: "c.json" });

    expect(jsonBody(calls[0].init)).toEqual({
      model: "m",
      campaign_filename: "c.json",
      arc_index: 0,
      session_index: 0,
    });
  });

  it("keeps an explicit arc and session index, and adds slot_name", async () => {
    const calls = stubFetch({ body: JSON.stringify({ session_id: "s" }) });

    await createSession("m", { campaignFilename: "c.json", arcIndex: 2, sessionIndex: 1, slotName: "晚祷" });

    expect(jsonBody(calls[0].init)).toMatchObject({ arc_index: 2, session_index: 1, slot_name: "晚祷" });
  });

  it("omits slot_name when it is not requested", async () => {
    const calls = stubFetch({ body: JSON.stringify({ session_id: "s" }) });

    await createSession("m");

    expect(jsonBody(calls[0].init)).not.toHaveProperty("slot_name");
  });
});

describe("generateScene", () => {
  it("maps camelCase parameters onto the snake_case request body", async () => {
    const calls = stubFetch({ body: JSON.stringify({ output: {} }) });

    await generateScene({
      sessionId: "s1",
      playerAction: "推门",
      model: "m",
      style: "黑暗",
      constraints: "别死人",
      slotName: "slot",
      timelineNodeId: 7,
    });

    expect(calls[0].url).toBe(`${BASE}/sessions/s1/generate`);
    expect(jsonBody(calls[0].init)).toEqual({
      player_action: "推门",
      model: "m",
      style: "黑暗",
      constraints: "别死人",
      slot_name: "slot",
      timeline_node_id: 7,
    });
  });
});

describe("URL construction", () => {
  it("encodes a campaign filename", async () => {
    const calls = stubFetch({ body: JSON.stringify({}) });

    await getCampaign("龙族·入学日.json");

    expect(calls[0].url).toBe(`${BASE}/campaigns/${encodeURIComponent("龙族·入学日.json")}`);
  });

  it("appends an encoded session_id when listing slots", async () => {
    const calls = stubFetch({ body: JSON.stringify({ slots: [] }) });

    await listSlots("a b/c");

    expect(calls[0].url).toBe(`${BASE}/campaigns/slots?session_id=${encodeURIComponent("a b/c")}`);
  });

  it("omits the query string when no session is given", async () => {
    const calls = stubFetch({ body: JSON.stringify({ slots: [] }) });

    await listSlots();

    expect(calls[0].url).toBe(`${BASE}/campaigns/slots`);
  });
});

describe("generateBackground", () => {
  it("resolves a relative image_url against the API base", async () => {
    stubFetch({ body: JSON.stringify({ image_url: "/static/bg/1.png", cached: true }) });

    const result = await generateBackground({ scenePrompt: "雨夜", location: "大厅" });

    expect(result.image_url).toBe(`${BASE}/static/bg/1.png`);
    expect(result.cached).toBe(true);
  });

  it("leaves an absolute image_url alone", async () => {
    stubFetch({ body: JSON.stringify({ image_url: "https://cdn.test/a.png", cached: false }) });

    const result = await generateBackground({ scenePrompt: "雨夜" });

    expect(result.image_url).toBe("https://cdn.test/a.png");
  });
});

describe("generateFromNovel", () => {
  it("posts FormData without setting a Content-Type", async () => {
    const calls = stubFetch({ body: JSON.stringify({ campaign: {} }) });

    await generateFromNovel(new File(["正文"], "novel.txt"));

    expect(calls[0].url).toBe(`${BASE}/campaigns/generate-from-novel`);
    expect(calls[0].init.body).toBeInstanceOf(FormData);
    // The browser must set the multipart boundary itself.
    expect(calls[0].init.headers).toBeUndefined();
  });

  it("throws the detail field on failure", async () => {
    stubFetch({ ok: false, status: 400, body: JSON.stringify({ detail: "文件为空" }) });

    await expect(generateFromNovel(new File([""], "empty.txt"))).rejects.toThrow("文件为空");
  });
});

describe("activateTimelineNode", () => {
  it("returns the activation payload", async () => {
    stubFetch({ body: JSON.stringify({ status: "activated", active_turn_id: 12 }) });

    const result = await activateTimelineNode("s1", 12);

    expect(result).toMatchObject({ status: "activated", active_turn_id: 12 });
  });
});

describe("getMemoryTrace", () => {
  it("requests the trace for the session", async () => {
    const calls = stubFetch({
      body: JSON.stringify({
        session_id: "s1",
        caps: { items: 20, npcs: 15, quests: 10, world_facts: 15 },
        nodes: [
          {
            node_id: 7,
            parent_id: 5,
            depth: 3,
            turn: 3,
            is_on_active_path: true,
            world_facts: { declared: ["新事实"], held: ["旧事实"] },
          },
        ],
      }),
    });

    const result = await getMemoryTrace("s1");

    expect(calls[0].url).toBe(`${BASE}/sessions/s1/memory-trace`);
    expect(calls[0].init.method).toBeUndefined();
    expect(result.caps.world_facts).toBe(15);
    expect(result.nodes[0].world_facts).toEqual({ declared: ["新事实"], held: ["旧事实"] });
  });

  it("surfaces the server error detail", async () => {
    stubFetch({ ok: false, status: 404, body: JSON.stringify({ detail: "Session not found" }) });

    await expect(getMemoryTrace("nope")).rejects.toThrow("Session not found");
  });
});

describe("fetchCampaignProgress", () => {
  it("accepts the persisted whole-campaign budget", async () => {
    stubFetch({ body: JSON.stringify({ turns_total: 7, max_turns_per_campaign: 50 }) });
    await expect(fetchCampaignProgress("s1")).resolves.toMatchObject({
      turns_total: 7, max_turns_per_campaign: 50,
    });
  });

  it.each([
    {},
    { turns_total: 7 },
    { turns_total: 7, max_turns_per_campaign: 0 },
    { turns_total: 7, max_turns_per_campaign: "50" },
    { turns_total: -1, max_turns_per_campaign: 50 },
    { turns_total: 1.5, max_turns_per_campaign: 50 },
  ])("ignores incomplete or invalid progress: %j", async (payload) => {
    stubFetch({ body: JSON.stringify(payload) });
    await expect(fetchCampaignProgress("s1")).resolves.toBeNull();
  });
});
