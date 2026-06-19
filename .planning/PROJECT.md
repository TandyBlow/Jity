# Jity — AI 驱动的克苏鲁跑团文字冒险

## What This Is

Jity 是一个 AI Game Master 主持的克苏鲁神话 TRPG 文字冒险游戏。玩家在网页端输入行动，AI GM 生成叙事、对话和选项，推进调查和恐怖体验。核心产品是 **Campaign Narrative Engine**——一个让 AI GM 主持跨多个 session 长篇战役的系统，通过结构化锚点事件（anchor events）和叙事连贯性追踪，防止 AI 在长上下文窗口中遗忘关键信息或随机漫步。

目标用户是单人跑团玩家——想要连贯的、有深度的 AI GM 体验，不需要人类 DM。

## Core Value

AI GM 维持长期叙事连贯性——不被上下文窗口限制遗忘关键信息，不随机漫步。v1.5 在此基础上增加"预置世界观深度"——AI 不只是不遗忘，还能引用原著细节（如龙族小说的卡塞尔学院、混血种体系、角色关系）。

## Requirements

### Validated

v1 已完成并验证（5 阶段，18 计划，143 测试）：

- ✓ **STACK-01~08**: FastAPI/Pydantic/FAISS 升级，openai SDK 替换 httpx，json_repair 集成，tiktoken，transitions FSM，Tailwind CSS v4 — v1
- ✓ **FOUND-01~07**: schemas/ 包拆分，PromptInput dataclass，消息历史注入，风格锚点，pytest 基础设施 — v1
- ✓ **CAMP-05**: 标准化 campaign.json 格式，Pydantic schema + 版本迁移链 v1→v2→v3 — v1
- ✓ **CAMP-01~01b**: CampaignManager 加载/校验 campaign.json，opening_scene 覆盖 ScriptedStory — v1
- ✓ **CAMP-04~04a**: 独立 campaign_progress 表，transitions FSM 集成 — v1
- ✓ **CAMP-02~02b**: 锚点事件系统，混合触发器（硬筛 + LLM 确认），单锚点/回合 + 冷却 — v1
- ✓ **CAMP-03~03a**: CampaignManager 上下文注入，token 预算检查 — v1
- ✓ **CAMP-08~08a**: Session 前情提要（LLM 压缩 "Previously on..."），双份存储 — v1
- ✓ **CAMP-06~06b**: AI 战役生成（deepseek-v4-pro），schema 校验 + 人类审查，前端策展编辑器 — v1
- ✓ **CAMP-07~07c**: 动态分支检测，LLM fact extraction 替代硬编码关键词，world_facts 自动 RAG re-index — v1
- ✓ **CAMP-09~09c**: 叙事健康监控，隐式引导注入，auto_play.py 基线校准 — v1
- ✓ **CAMP-10~10a**: 发现时间线 UI，system-known vs player-confirmed 区分 — v1
- ✓ **HARD-01~05**: context_strategy 接口，RAG embedding 升级，选项策略配置化，并发安全 — v1
- ✓ **DONE-01**: auto_play.py 270 回合无崩溃，所有锚点触发，剧终状态正确 — v1

### Active

v1.5 — Post-Launch Content Pipeline（Phase 6）：

**基线核心：**
- [ ] **CAMP-PACE-01**: Session 自动推进 — turn_in_session >= max_turns_per_session 触发 FSM end_session，自动 recap + 下一 session opening
- [ ] **CAMP-PACE-02**: 任意 Arc 选择进入 — API + UI 支持从指定 arc_index/session_index 启动战役，entry_state 覆盖游戏状态

**扩展功能：**
- [ ] **CAMP-14**: 战役存档槽 — 多战役进度并行，命名存档，加载/恢复/删除
- [ ] **CAMP-06x**: 小说→战役自动生成 — 上传 TXT → 编码检测 → 章节边界识别 → 逐章锚点提取 → 跨章组装 → campaign.json → 人工审核
- [ ] **NPC-01**: NPC 关系追踪 — 好感度/敌意跨 session 持久化，affinity [-10,+10]，session 边界衰减，recap 注入 top-3 关系变化
- [ ] **CAMP-15**: 难度配置接口 — campaign.json difficulty 字段 + 参数映射（temperature/sanity_multiplier/clue_style），不做前端 UI
- [ ] **CAMP-16**: 战役 metadata — campaign.json description/tags/estimated_duration 字段

### Out of Scope

v2 推迟项目（不在当前路线图中）：

- **SANE-01~04**: 疯狂系统增强（疯狂表、恐惧症获取、现实检定、非自愿行动）—— 推迟到 v2
- **CTXW-01~04**: 完整上下文窗口管理（滚动层次摘要、永久正典分离、中 session 压缩触发）—— 接口在 v1 中预留，完整方案推迟到 v2
- **CONT-01~03**: 内容与社区（封面图生成、社区战役市场、战役文件导入/导出）—— 推迟到 v2
- **MULT-01~02**: 多人 TRPG 支持（回合同步、共享状态、人类 DM 工具）—— 推迟到 post-v2
- **难度选择器 UI** — campaign.json 有 difficulty 字段但前端不暴露选择器，v1 验证后再做
- **战役封面/浏览页面** — 前端视觉升级，v1 功能完整后做
- **全自动小说→战役管线（无人审核）** — 质量不可靠，始终保留人工审核门
- **LLM 合成 mid-campaign entry state** — v1 使用预编写 entry_state，LLM 合成推迟到 Phase 7
- **龙族 I/II/III 精校内容包** — 是内容创建而非代码工程，Phase 6c 独立进行
- **D&D 5e 规则模拟** — Jity 是克苏鲁神话，CoC 机制（百分制、理智、调查）≠ D&D
- **战斗地图/战术战斗** — 叙事优先设计，战斗是叙事节拍而非战术小游戏
- **语音输入/TTS 旁白** — 中文 TTS 质量不一致，文本优先
- **移动原生应用** — Web 优先，需要时 PWA
- **Token/能源货币化** — 破坏用户信任，采用公平订阅模式
- **重度内容审核** — 破坏恐怖内容，采用最小透明过滤

## Context

**技术栈**: Python/FastAPI 后端 + Next.js/React/TypeScript 前端 + SQLite (WAL 模式)。LLM 通过 DeepSeek API（openai SDK）。RAG 通过 FAISS + DeepSeek embedding。零外部基础设施——单用户本地 TRPG。

**当前代码库状态**: 5 阶段全部执行完毕。backend/ 含完整的 ScenarioGenerator、CampaignManager（含 FSM/anchor/recap/context injection）、PromptBuilder、LLMClient。frontend/ 含 GM 控制台、策展编辑器、发现时间线 UI。143 pytest 测试通过。知识库包含龙族世界观（卡塞尔学院、混血种、NPC）。

**已知问题**:
- Campaign 系统从未通过 HTTP API 端到端运行——CampaignManager.load() 未被任何 API 路径调用
- session_messages 表缺少 campaign_session_index 列——recap 无法按 session 边界过滤消息
- _is_first_turn_of_session() 检查 state["turn"]==0 只在第一次为真
- game_sessions 表缺少 campaign_id 列——存档槽与游戏会话之间无关联
- option_config.json 文件不存在——max_turns_per_session 默认值无处读取

**审阅产物**: CEO plan 和 eng review 已完成（2026-06-19），Phase 6 详细实现方案在 `~/.gstack/projects/Jity/ceo-plans/2026-06-19-session-pacing-dragon-clan.md`。10 个外部声音发现已解决。

## Constraints

- **技术栈**: Python/FastAPI + Next.js/React + SQLite only。不允许新语言或框架
- **依赖**: MIT 兼容。不允许 LangChain/LlamaIndex（~50 依赖）。不允许 SQLAlchemy/PostgreSQL/pgvector（过度杀伤）
- **零构建步骤**: `uvicorn` + `npm run dev`
- **API 兼容**: 不破坏现有 `/sessions` API。新增 `/campaigns` 端点
- **测试框架**: pytest 是边界——不允许更重的测试框架
- **单用户**: 本地 TRPG，无并发用户、无分布式系统
- **DeepSeek API**: 模型 `deepseek-v4-flash`（日常）和 `deepseek-v4-pro`（创意生成）。API key 从环境变量读取

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| CampaignManager 中间注入管线 | LLM 保持叙事判断，只提供结构化上下文 | ✓ Good |
| 独立 campaign_progress 表 | 战役进度与游戏状态关注点分离 | ✓ Good |
| schemas/ 包拆分 | schemas.py 膨胀到 300+ 行 | ✓ Good |
| PromptInput dataclass | 6 参数 → 1 参数 | ✓ Good |
| 混合触发条件（硬筛 + LLM 确认） | 合并到主 prompt，零额外 API 调用 | ✓ Good |
| auto_play.py 270 回合 = v1 完成 | 可量化的成功标准 | ✓ Good |
| 单锚点触发策略 | 每回合最多一个，按优先级排序 | ✓ Good |
| 战役开场覆盖 ScriptedStory | ScriptedStory 作为默认 fallback | ✓ Good |
| Phase 6 = v1.5 桥梁 | v1 完成和 v2 开始之间的中间里程碑 | — Pending |
| v1.5 核心：session 自动推进 + arc 选择 | 让现有 3-arc 战役可完整体验 | — Pending |
| 小说→战役自动生成管线 | 核心差异化功能，降低内容创作门槛 | — Pending |
| 存档槽自增 id PK | SQLite 表重建迁移，支持多槽 | — Pending |
| FSM arc 边界单一路径 | skip resume_session，直接 arc_transition | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-19 after project re-initialization (CEO + eng review context)*
