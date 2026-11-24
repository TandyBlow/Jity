import type { Page } from "@playwright/test";

import type {
  CampaignDetailResponse,
  CampaignListItem,
  GameState,
  MemoryUpdates,
  SaveSlot,
  SessionResponse,
  StoryOutput,
  TimelineNodeDetail,
  TimelineNodeSummary,
  TurnContext,
} from "../src/types";

/**
 * Frozen API payloads for the visual baseline.
 *
 * These are deliberately inlined copies rather than imports from `src/`, so that
 * editing app copy or defaults does not silently shift the baseline screenshots.
 * A baseline that moves for reasons unrelated to CSS is worse than no baseline.
 */

export const SESSION_ID = "e2e-baseline-session";
export const CAMPAIGN_FILENAME = "e2e_baseline_campaign.json";
export const ACTIVE_TURN_ID = 7;
export const MODEL = "deepseek-v4-flash";

// 1536x730 is the author's real browser viewport: a 1536x864 screen at 125%
// scaling, less browser chrome. 1024x768 is the narrow-desktop target.
export const VIEWPORTS = [
  { name: "1536x730", width: 1536, height: 730 },
  { name: "1024x768", width: 1024, height: 768 },
];

/**
 * Shared by capture and verify so adding a route to one cannot silently skip
 * it in the other.
 */
export const SHOTS: Array<{
  name: string;
  path: string;
  ready: string;
  /** Restrict a shot to some viewports — e.g. a layout that only exists below a breakpoint. */
  only?: string[];
}> = [
  { name: "console", path: "/", ready: ".narration" },
  { name: "console-drawer", path: "/?memory=1", ready: ".memory-drawer-panel", only: ["1024x768"] },
  { name: "timeline-story", path: `/timeline?session=${SESSION_ID}`, ready: ".story-timeline-layout" },
  { name: "timeline-anchors", path: `/timeline?session=${SESSION_ID}&tab=anchors`, ready: ".anchor-tree" },
  { name: "timeline-clues", path: `/timeline?session=${SESSION_ID}&tab=clues`, ready: ".clue-board" },
  { name: "timeline-trace", path: `/timeline?session=${SESSION_ID}&tab=trace`, ready: ".trace-board" },
  { name: "curator", path: "/curator", ready: ".timeline-layout" },
  { name: "dev-log", path: "/dev-log", ready: ".dev-log-list" },
];

const NARRATION = `雨是在你下车后三分钟开始变大的。

你拖着那只从婶婶家带来的旧行李箱，站在卡塞尔学院报到处大厅门口。箱轮卡在门槛细缝里，发出一声很丢人的"咔哒"。你低头用力拽了两下，没拽动。

大厅里没人笑。

这反而更可怕。

头顶的水晶吊灯亮得像某种审判现场，光落在黑色大理石地面上，碎成一片片冰冷的白。周围来来往往的学生都穿着深色制服，肩线挺拔，步伐安静，眼神锐利得不像是在上大学，更像是刚从某个不许写进新闻里的军事训练基地出来。

你看见一个男生手里拎着小提琴盒，盒角却露出金属锁扣。另一个女生路过报到台时，袖口下方闪过一枚细小的银色徽章。投影屏正在滚动新生名单，你的名字混在一串英文、编号和血红色的校徽之间，像一只误入狼群的土狗。

你咽了口唾沫。`;

const DIALOGUE = [
  {
    speaker: "诺诺",
    text: `路明非对吧？

古德里安教授让我来接你。

不过说实话，你看起来比档案里还要……朴素一点。`,
  },
  {
    speaker: "路明非",
    text: `学姐好……那个，这里到底有什么不普通的？`,
  },
];

const OPTIONS = [
  `愣住两秒，然后硬着头皮打招呼："学姐好……那个，这里到底有什么不普通的？"`,
  `下意识后退半步，抓紧行李箱拉杆："等等，你怎么知道我的名字？这是什么整蛊节目吗？"`,
  `试图挤出个笑脸，但声音有点抖："照片？什么照片？我那张高考准考证上的照片可丑了……"`,
];

const OPTION_CHECKS = [
  null,
  { requires_check: true, name: "意志检定", skill: "意志", system: "d20", expression: "1d20", target: 12, difficulty: "普通", stakes: "失败则被对方看出你在撒谎" },
  null,
];

const MEMORY_UPDATES: MemoryUpdates = {
  current_location: "卡塞尔学院报到处大厅",
  items_upserted: [
    { name: "临时通行卡", status: "owned", description: "卡面火漆纹路像刚被点燃过", location: "口袋" },
  ],
  items_removed: [],
  npcs_upserted: [
    {
      name: "诺诺",
      status: "present",
      relationship: "引路人",
      current_location: "报到处大厅门口",
      description: "红发，校服外套随意搭在肩上",
      notes: "古德里安教授派来接人",
    },
  ],
  quests_upserted: [
    { name: "完成入学报到", status: "active", objective: "找到报到台并确认自己的身份档案" },
  ],
  world_facts_upserted: [
    { name: "卡塞尔学院不是普通大学", status: "known", description: "学生步伐安静、眼神锐利", source: "现场观察" },
    { name: "新生名单在投影屏滚动", status: "suspected", description: "你的名字混在英文与编号之间" },
  ],
  player_status_patch: {
    condition: "新生报到中，略紧张",
    danger_level: "medium",
    current_goal: "完成卡塞尔学院入学报到",
  },
  key_event: "被红发女孩诺诺从背后拍了拍肩膀",
};

export const storyOutput: StoryOutput = {
  narration: NARRATION,
  dialogue: DIALOGUE,
  scene_prompt: "dark gothic academy registration hall, nervous freshman, crystal chandelier",
  sanity_delta: -3,
  health_delta: 0,
  options: OPTIONS,
  option_checks: OPTION_CHECKS as StoryOutput["option_checks"],
  game_over: false,
  game_over_reason: "",
  current_location: "卡塞尔学院报到处大厅",
  // The legacy delta lists the server still merges, ahead of memory_updates.
  items_gained: [{ name: "银色徽章", description: "某个女生袖口下闪过" }],
  items_lost: [],
  npcs_encountered: [{ name: "古德里安教授", disposition: "未露面，仅被提及" }],
  quests_updated: [],
  memory_updates: MEMORY_UPDATES,
  npc_relations_delta: null,
};

export const turnContext: TurnContext = {
  recorded: true,
  retrieved_chunks: [
    { id: "lore-1", title: "卡塞尔学院简介", source_type: "location", content: "学院位于芝加哥郊外，表面是一所私立大学。", score: 0.82, keywords: ["学院", "入学"], importance: 4 },
    { id: "npc-1", title: "诺诺", source_type: "npc_profile", content: "红发女生，古德里安教授的学生。", score: 0.71, keywords: ["诺诺"], importance: 3 },
  ],
  token_count: 4820,
  latency_ms: 3120,
  word_count: 392,
  prompt_sections: {
    campaign_context: "## 战役上下文\n第一幕 · 火之晨曦 / 入学日\n已揭示锚点：抵达卡塞尔学院",
    system_prompt: "你是桌面 RPG 的中文 GM 辅助系统。\n当前状态：\n- 当前地点：卡塞尔学院报到处大厅",
    messages: "## 最近对话历史\n[玩家]: 硬着头皮走向报到台。",
    rag_chunks: "RAG 检索到的相关知识：\n[location] 卡塞尔学院简介\n学院位于芝加哥郊外。",
    player_action: "玩家行动：愣住两秒，然后硬着头皮打招呼。",
  },
  prompt_text: "## 导演指令\n[导演指令] 回应玩家的招呼，让诺诺点破档案的存在。\n\n## 战役上下文\n第一幕 · 火之晨曦 / 入学日",
};

export const gameState: GameState = {
  sanity: 78,
  health: 92,
  turn: ACTIVE_TURN_ID,
  current_location: "卡塞尔学院报到处大厅",
  items: [
    { name: "旧行李箱", status: "持有", description: "婶婶家带来的，箱轮有点卡", location: "手边", notes: "箱角贴着一张褪色的行李牌" },
    { name: "临时通行卡", status: "持有", description: "卡面火漆纹路像刚被点燃过", location: "口袋" },
    { name: "银色徽章", status: "仅目击", description: "某个女生袖口下闪过", location: "不明" },
  ],
  npcs: [
    { name: "诺诺", status: "已接触", relationship: "引路人", current_location: "报到处大厅门口", description: "红发，校服外套随意搭在肩上" },
    { name: "古德里安教授", status: "仅提及", relationship: "未知", current_location: "未知", notes: "似乎提前看过你的档案" },
  ],
  quests: [
    { name: "完成入学报到", status: "进行中", objective: "找到报到台并确认自己的身份档案", description: "你不确定这份档案里写了什么" },
    { name: "搞清这里是什么地方", status: "进行中", objective: "从诺诺口中问出这所学校的真实性质" },
  ],
  world_facts: [
    { name: "卡塞尔学院不是普通大学", status: "known", description: "学生们步伐安静、眼神锐利，更像受过军事训练", source: "现场观察" },
    { name: "新生名单在投影屏滚动", status: "suspected", description: "你的名字混在英文、编号和血红色校徽之间", notes: "也许排名有含义" },
    { name: "小提琴盒里的金属锁扣", status: "suspected", description: "那个男生拎的琴盒盒角露出金属件" },
  ],
  player_status: {
    condition: "新生报到中，略紧张",
    danger_level: "medium",
    current_goal: "完成卡塞尔学院入学报到",
    notes: "行李还卡在门槛上",
  },
  recent_events: [
    "下车后三分钟，雨突然变大",
    "行李箱轮子卡进报到处门槛",
    "发现大厅里的学生不像普通大学生",
    "投影屏上出现了自己的名字",
    "被红发女孩诺诺从背后拍了拍肩膀",
    "诺诺提到古德里安教授让她来接人",
    "意识到对方早已知道自己的身份",
    "被迫在众目睽睽下回答",
  ],
};

export const sessionResponse: SessionResponse = {
  session_id: SESSION_ID,
  game_name: "龙族·入学日",
  model: MODEL,
  state: gameState,
  campaign_filename: CAMPAIGN_FILENAME,
  active_turn_id: ACTIVE_TURN_ID,
};

export const saveSlots: SaveSlot[] = [
  { id: 1, campaign_id: SESSION_ID, slot_name: "报到日傍晚", arc_index: 0, session_index: 0, turn_in_session: ACTIVE_TURN_ID, last_played: "2026-09-20T10:12:00", campaign_filename: CAMPAIGN_FILENAME, is_active: true, head_turn_id: ACTIVE_TURN_ID },
  { id: 2, campaign_id: SESSION_ID, slot_name: "自动存档", arc_index: 0, session_index: 0, turn_in_session: 4, last_played: "2026-09-19T22:40:00", campaign_filename: CAMPAIGN_FILENAME },
];

export const campaignList: CampaignListItem[] = [
  { filename: CAMPAIGN_FILENAME, title: "龙族·入学日", version: 3, arc_count: 3 },
  { filename: "black_moon_tide.json", title: "黑月之潮", version: 2, arc_count: 2 },
];

export const timelineNodes: TimelineNodeSummary[] = [
  { id: 1, parent_id: null, depth: 0, label: "开场", player_action: "（入场）环顾四周，了解当前处境。", narration_preview: "雨是在你下车后三分钟开始变大的。", location: "卡塞尔学院报到处大厅", turn: 1, source: "scripted", created_at: "2026-09-20T09:00:00", is_active: false, is_on_active_path: true },
  { id: 3, parent_id: 1, depth: 1, label: "T2", player_action: "站到角落先观察一会儿。", narration_preview: "你贴着墙根挪了几步，试着不引起任何人注意。", location: "卡塞尔学院报到处大厅", turn: 2, source: "llm", created_at: "2026-09-20T09:05:00", is_active: false, is_on_active_path: true },
  { id: 5, parent_id: 3, depth: 2, label: "T4", player_action: "硬着头皮走向报到台。", narration_preview: "报到台后面的女生抬起头，视线在你和行李箱之间来回。", location: "卡塞尔学院报到处台", turn: 4, source: "llm", created_at: "2026-09-20T09:20:00", is_active: false, is_on_active_path: true },
  { id: 6, parent_id: 3, depth: 2, label: "T4·支线", player_action: "抓住那个拎小提琴盒的男生搭话。", narration_preview: "对方停下脚步，琴盒在他手里转了半圈。", location: "卡塞尔学院报到处大厅", turn: 4, source: "llm", created_at: "2026-09-20T09:22:00", is_active: false, is_on_active_path: false },
  { id: ACTIVE_TURN_ID, parent_id: 5, depth: 3, label: "T7", player_action: "愣住两秒，然后硬着头皮打招呼。", narration_preview: "你回头，看见一个红发女孩站在雨幕和大厅灯光交界的地方。", location: "卡塞尔学院报到处大厅", turn: ACTIVE_TURN_ID, source: "llm", created_at: "2026-09-20T10:10:00", is_active: true, is_on_active_path: true },
];

export const timelineNodeDetail: TimelineNodeDetail = {
  id: ACTIVE_TURN_ID,
  session_id: SESSION_ID,
  parent_id: 5,
  depth: 3,
  player_action: OPTIONS[0],
  output: storyOutput,
  state: gameState,
  campaign_progress: { arc_index: 0, session_index: 0, revealed_anchors: ["anchor_arrival", "anchor_nono"] },
  context: turnContext,
  caps: { items: 20, npcs: 15, quests: 10, world_facts: 15 },
  declared: {
    items: {
      upserted: [
        { name: "银色徽章", description: "某个女生袖口下闪过" },
        { name: "临时通行卡", status: "owned", description: "卡面火漆纹路像刚被点燃过", location: "口袋" },
      ],
      removed: [],
    },
    npcs: {
      upserted: [
        { name: "古德里安教授", disposition: "未露面，仅被提及" },
        { name: "诺诺", status: "present", relationship: "引路人", current_location: "报到处大厅门口" },
      ],
      removed: [],
    },
    quests: {
      upserted: [{ name: "完成入学报到", status: "active", objective: "找到报到台并确认自己的身份档案" }],
      removed: [],
    },
    world_facts: {
      upserted: [
        { name: "卡塞尔学院不是普通大学", status: "known", description: "学生步伐安静、眼神锐利" },
        { name: "新生名单在投影屏滚动", status: "suspected", description: "你的名字混在英文与编号之间" },
        { name: "小提琴盒里的金属锁扣", status: "suspected", description: "那个男生拎的琴盒盒角露出金属件" },
      ],
      removed: [],
    },
  },
  memory: {
    items: { declared: ["临时通行卡", "银色徽章"], held: ["临时通行卡", "旧行李箱", "银色徽章"] },
    npcs: { declared: ["诺诺", "古德里安教授"], held: ["诺诺", "古德里安教授"] },
    quests: { declared: ["完成入学报到"], held: ["完成入学报到", "搞清这里是什么地方"] },
    // The third fact never lands: the category is at its cap of 15.
    world_facts: {
      declared: ["卡塞尔学院不是普通大学", "新生名单在投影屏滚动", "小提琴盒里的金属锁扣"],
      held: ["卡塞尔学院不是普通大学", "新生名单在投影屏滚动"],
    },
  },
  model: MODEL,
  source: "llm",
  created_at: "2026-09-20T10:10:00",
};

/**
 * Declared-versus-held names per turn. Node 7 declares a world fact the cap
 * rejects, which is the case the trace tab exists to make visible.
 */
export const memoryTrace = {
  session_id: SESSION_ID,
  caps: { items: 20, npcs: 15, quests: 10, world_facts: 15 },
  nodes: timelineNodes.map((node) => ({
    node_id: node.id,
    parent_id: node.parent_id,
    depth: node.depth,
    turn: node.turn,
    is_on_active_path: node.is_on_active_path,
    items: { declared: ["临时通行卡"], held: ["临时通行卡", "旧行李箱"] },
    npcs: { declared: ["诺诺"], held: ["诺诺", "古德里安教授"] },
    quests: { declared: ["完成入学报到"], held: ["完成入学报到", "搞清这里是什么地方"] },
    world_facts:
      node.id === ACTIVE_TURN_ID
        ? {
            declared: ["卡塞尔学院不是普通大学", "新生名单在投影屏滚动", "小提琴盒里的金属锁扣"],
            // The third one never lands: world_facts is at its cap of 15.
            held: ["卡塞尔学院不是普通大学", "新生名单在投影屏滚动"],
          }
        : { declared: ["卡塞尔学院不是普通大学"], held: ["卡塞尔学院不是普通大学"] },
  })),
};

export const campaignDetail: CampaignDetailResponse = {
  filename: CAMPAIGN_FILENAME,
  campaign: {
    version: 3,
    title: "龙族·入学日",
    core_conflict: "一个普通高中生被卷入古老血统的战争，必须在隐瞒与坦白之间做出选择。",
    constraints: "关键 NPC 不能突然死亡；不要跳出当前入学调查。",
    starting_state: {},
    arcs: [
      {
        name: "第一幕 · 火之晨曦",
        goal: "完成报到，确认自己的血统身份，并第一次直面学院的真实规则。",
        sessions: [
          {
            name: "入学日",
            opening_scene: "卡塞尔学院报到处大厅，暴雨。",
            max_turns_per_session: 30,
            anchor_events: [
              { id: "anchor_arrival", name: "抵达卡塞尔学院", description: "玩家拖着行李箱走进报到处大厅，第一次看见非普通学生的举止。", priority: 1, trigger_conditions: { location: "卡塞尔学院报到处大厅" } },
              { id: "anchor_nono", name: "诺诺现身", description: "诺诺受古德里安教授委托来接人，并点破档案的存在。", priority: 2, trigger_conditions: { npc_present: "诺诺" } },
              { id: "anchor_blood_test", name: "血统检测", description: "玩家在无意中触发血统反应，被教员注意到。", priority: 3, trigger_conditions: { location: "卡塞尔学院检测室" } },
            ],
          },
          {
            name: "第一课",
            opening_scene: "阶梯教室，光线从高窗斜切进来。",
            max_turns_per_session: 30,
            anchor_events: [
              { id: "anchor_first_class", name: "第一堂课", description: "教员在课堂上展示了某种不该被普通人看见的东西。", priority: 1, trigger_conditions: { location: "阶梯教室" } },
            ],
          },
        ],
      },
      {
        name: "第二幕 · 悼亡者之瞳",
        goal: "在一场死伤中理解学院的代价，并决定站在哪一边。",
        sessions: [
          {
            name: "雨夜",
            opening_scene: "学院后山，雨还没停。",
            max_turns_per_session: 30,
            anchor_events: [
              { id: "anchor_night_raid", name: "夜袭", description: "不明身份的人闯进后山，第一次出现真正的伤亡。", priority: 1, trigger_conditions: { location: "学院后山" } },
            ],
          },
        ],
      },
      {
        name: "第三幕 · 黑月之潮",
        goal: "在日本分部面对一场无法两全的抉择。",
        sessions: [
          {
            name: "抵达日本",
            opening_scene: "成田机场到达层，湿热的空气扑面而来。",
            max_turns_per_session: 30,
            anchor_events: [
              { id: "anchor_japan_arrival", name: "抵达日本分部", description: "玩家见到日本分部的负责人，并意识到两边的关系并不融洽。", priority: 1, trigger_conditions: { location: "日本分部" } },
              { id: "anchor_first_meeting", name: "第一次会面", description: "与关键人物初次会面，立场暴露。", priority: 2, trigger_conditions: { npc_present: "源稚生" } },
            ],
          },
        ],
      },
    ],
  },
};

export const sessionProgress = {
  session_id: SESSION_ID,
  revealed_anchors: ["anchor_arrival", "anchor_nono"],
  arc_index: 0,
  session_index: 0,
  world_facts: gameState.world_facts,
};

/**
 * Deterministic stand-in for a generated scene background. An SVG gradient
 * base64-encoded so it survives being embedded in a CSS `url("...")`.
 */
const SCENE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22304a"/><stop offset="0.55" stop-color="#131a26"/><stop offset="1" stop-color="#080a0e"/></linearGradient></defs><rect width="96" height="96" fill="url(#g)"/></svg>`;
export const SCENE_BACKGROUND_DATA_URI = `data:image/svg+xml;base64,${Buffer.from(SCENE_SVG).toString("base64")}`;

/**
 * Intercept every backend call so the app never touches http://localhost:8000.
 * Without this the screenshots depend on live LLM output and a database, which
 * makes before/after diffing meaningless.
 */
export async function installApiMocks(page: Page): Promise<void> {
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    const isApi = url.port === "8000" || url.port === "8010";
    if (!isApi) {
      await route.continue();
      return;
    }

    const path = url.pathname;
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/campaigns") return json({ campaigns: campaignList });
    if (path === "/campaigns/slots") return json({ slots: saveSlots });
    if (path === `/campaigns/${CAMPAIGN_FILENAME}`) return json(campaignDetail);
    if (path === "/backgrounds/generate") return json({ image_url: SCENE_BACKGROUND_DATA_URI, cached: true });
    if (path === `/sessions/${SESSION_ID}`) return json(sessionResponse);
    if (path === `/sessions/${SESSION_ID}/progress`) return json(sessionProgress);
    if (path === `/sessions/${SESSION_ID}/timeline`) {
      return json({ session_id: SESSION_ID, active_node_id: ACTIVE_TURN_ID, campaign_filename: CAMPAIGN_FILENAME, nodes: timelineNodes });
    }
    if (path === `/sessions/${SESSION_ID}/memory-trace`) return json(memoryTrace);
    if (path.startsWith(`/sessions/${SESSION_ID}/timeline/`)) return json(timelineNodeDetail);
    if (path === `/sessions/${SESSION_ID}/history`) return json({ session_id: SESSION_ID, messages: [] });

    await json({ detail: `unmocked endpoint: ${path}` }, 404);
  });
}

/** Seed the session id before app code runs, so the console does not create one. */
export async function seedSession(page: Page): Promise<void> {
  await page.addInitScript((sessionId) => {
    window.localStorage.setItem("jity_active_session_id", sessionId);
  }, SESSION_ID);
}
