export type DevLogEntry = {
  id: string;
  date: string;
  title: string;
  summary: string;
  author: string;
  areas: string[];
  changes: string[];
  relatedFiles: string[];
  nextSteps?: string[];
};

export const devLogEntries: DevLogEntry[] = [
  {
    id: "2026-06-16-status-delta-and-json-repair",
    date: "2026-06-16",
    title: "状态变化提示、血统稳定恢复和 JSON 修复",
    summary: "增强游戏回合反馈和 AI 输出可靠性：前端直接提示本回合血统稳定/体力变化，后端统一处理血统稳定的自动恢复，并为模型 JSON 输出增加强制格式和二次修复。",
    author: "Codex",
    areas: ["backend", "frontend", "llm", "game-state"],
    changes: [
      "在主控制台剧情选项前新增状态变化提示，显示血统稳定和体力的本回合增减及对应原因说明。",
      "新增状态提示样式，区分损耗和恢复，让玩家更容易理解行动代价。",
      "后端状态合并时加入每回合 2 点血统稳定自动恢复，并在提示词中说明模型不要把自动恢复写入 sanity_delta。",
      "LLM 请求改用 response_format=json_object，并把最大输出 token 提升到 5000，减少剧情 JSON 被截断的概率。",
      "当模型输出首次解析失败时，自动发起一次 JSON 修复请求；若仍失败，会把原始输出和修复输出一并保存，方便排查。",
      "提示词增加字符串转义约束，要求对白引用避免未转义英文双引号，降低 JSON 解析错误。",
    ],
    relatedFiles: [
      "backend/app/services/game_state.py",
      "backend/app/services/llm_client.py",
      "backend/app/services/prompt_builder.py",
      "frontend/src/app/page.tsx",
      "frontend/src/app/globals.css",
      "frontend/src/lib/dev-log.ts",
    ],
    nextSteps: [
      "用真实 DeepSeek 输出连续跑几回合，确认状态提示、自动恢复和模型返回的 sanity_delta 不会重复计算。",
      "观察 model_outputs 中的失败记录，判断 JSON 修复提示是否还需要补充字段类型或截断处理规则。",
    ],
  },
  {
    id: "2026-06-15-context-memory",
    date: "2026-06-15",
    title: "第二阶段：强化 Context Memory",
    summary: "把原本偏临时记录的状态扩展成真正的游戏记忆系统：明确长期状态结构、稳定 NPC/任务/物品字段，并让每轮 AI 输出只提交增量记忆，由后端合并成下一轮 prompt 的上下文。",
    author: "Codex",
    areas: ["backend", "frontend", "game-state", "prompt"],
    changes: [
      "明确 state schema，补齐 current_location、items、npcs、quests、recent_events、world_facts 和 player_status。",
      "新增 ItemMemory、NPCMemory、QuestMemory、WorldFactMemory、PlayerStatus 和 MemoryUpdates 等结构化 schema。",
      "为 NPC、任务、物品和长期事实统一稳定字段，例如 name、status、description、relationship、objective、notes、source。",
      "后端状态合并改为 upsert/remove 规则：AI 只通过 memory_updates 提供本回合新增或变化的记忆，系统负责回合数、血统稳定、体力裁剪、状态归一化和去重合并。",
      "增加 world_facts 的系统推断规则，用于记录红色标记、L-13 编号、S级观察对象、执行部观察等关键长期事实。",
      "recent_events 改为保存 key_event 或自动摘要，限制最多 8 条、单条最多 120 字，避免把长篇 narration 无限塞进状态。",
      "Prompt 中拆分当前状态、Context Memory/长期记忆和最近事件，下一轮生成会带上当前位置、同行 NPC、任务、关键物品、长期事实和玩家状态。",
      "前端右侧 Context Memory 改成当前状态、同伴与 NPC、关键物品、任务、长期事实、最近事件等清晰分区。",
    ],
    relatedFiles: [
      "backend/app/schemas.py",
      "backend/app/services/game_state.py",
      "backend/app/services/prompt_builder.py",
      "frontend/src/app/page.tsx",
      "frontend/src/types.ts",
      "frontend/src/lib/dev-log.ts",
    ],
    nextSteps: [
      "连续生成多轮，确认当前地点、同行 NPC、正在进行任务、关键物品和最近事件都能稳定保留。",
      "检查下一轮 prompt 中的 Context Memory 是否只包含必要摘要，没有重复堆叠整段剧情文本。",
    ],
  },
  {
    id: "2026-06-15-knowledge-base-and-rag",
    date: "2026-06-15",
    title: "第三阶段：扩充 Knowledge Base 和 RAG",
    summary: "把知识库从单一样例扩展为按类型组织的 RAG 数据源，并增强轻量检索、结果落库和前端命中展示，为项目报告中的 RAG 演示打基础。",
    author: "Codex",
    areas: ["backend", "frontend", "rag", "knowledge-base"],
    changes: [
      "将知识库拆分为 npcs.json、locations.json、quests.json、rules.md 和 world_lore.md，并保留 cassell_lore.json 兼容已有样例。",
      "JSON 与 Markdown chunk 支持 source_type、keywords、title、content 和 importance，Markdown 可在标题后写元数据。",
      "KnowledgeBase 加载时跳过 README，自动解析 Markdown 元数据，并根据文件名推断 npc、location、quest、rule、world_lore 等来源类型。",
      "轻量检索增加中文 2-4 字 n-gram token 展开、关键词命中加权、标题命中加权和 importance 加权，提升临时通行卡、诺诺、图书馆等短查询命中率。",
      "ScenarioGenerator 会把本轮 retrieved_chunks 序列化写入 model_outputs，成功和失败输出都能追溯当时用了哪些知识。",
      "RAG Hit 返回内容增加 keywords 和 importance，前端展示来源类型、分数、标题、短内容和关键词 chip。",
      "更新 knowledge/README.md，说明知识库文件职责、JSON 字段和 Markdown 元数据格式。",
    ],
    relatedFiles: [
      "backend/app/database.py",
      "backend/app/schemas.py",
      "backend/app/services/knowledge_base.py",
      "backend/app/services/retriever.py",
      "backend/app/services/scenario_generator.py",
      "frontend/src/app/page.tsx",
      "frontend/src/types.ts",
      "knowledge/README.md",
      "knowledge/cassell_lore.json",
      "knowledge/locations.json",
      "knowledge/npcs.json",
      "knowledge/quests.json",
      "knowledge/rules.md",
      "knowledge/world_lore.md",
      "frontend/src/lib/dev-log.ts",
    ],
    nextSteps: [
      "用“临时通行卡”“诺诺”“图书馆”等输入做检索验收，确认 RAG Hits 能命中对应 NPC、地点、规则或任务资料。",
      "继续观察轻量哈希检索的误命中情况，后续再评估是否接入真正 embedding 服务。",
    ],
  },
  {
    id: "2026-06-13-scripted-opening-and-dev-log",
    date: "2026-06-13",
    title: "固定开场、AI 接管节点和开发日志",
    summary: "把游戏开场整理成可控的固定剧情，引导玩家进入三个调查方向；同时新增开发日志页面，方便记录后续代码改动。",
    author: "Codex",
    areas: ["backend", "frontend", "story", "developer-tooling"],
    changes: [
      "新增卡塞尔学院报到处大厅固定开场，并为三个初始玩家反应提供脚本化输出。",
      "固定开场结束后交给 AI 继续生成；未配置 DeepSeek API key 时返回 503，避免后续剧情继续使用本地兜底内容。",
      "更新提示词约束和 LLM 输出归一化，要求物品、NPC、任务等字段使用对象数组。",
      "调整前端初始剧情、默认行动和错误提示展示，移除 narrative_profile 请求字段。",
      "新增 STORY_OUTLINE.md，说明固定剧情结构、AI 接管节点和建议延展方向。",
      "新增 /dev-log 路由、结构化日志数据和主控制台入口，集中展示开发改动。",
      "生产环境默认隐藏开发日志页面，可通过 ENABLE_DEV_LOG=true 显式开启。",
    ],
    relatedFiles: [
      "STORY_OUTLINE.md",
      "backend/app/main.py",
      "backend/app/schemas.py",
      "backend/app/services/game_state.py",
      "backend/app/services/llm_client.py",
      "backend/app/services/prompt_builder.py",
      "backend/app/services/scenario_generator.py",
      "frontend/src/app/dev-log/page.tsx",
      "frontend/src/app/dev-log/DevLogView.tsx",
      "frontend/src/lib/dev-log.ts",
      "frontend/src/app/page.tsx",
      "frontend/src/app/globals.css",
      "frontend/src/lib/api.ts",
    ],
    nextSteps: [
      "配置 DeepSeek API key 后，从三个主调查方向各跑一轮，检查 AI 接管后的结构化输出质量。",
      "每次完成一组有意义的代码改动后，在 devLogEntries 顶部新增一条记录。",
    ],
  },
];
