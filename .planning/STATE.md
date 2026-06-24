# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-19)

**Core value:** AI GM 维持长期叙事连贯性——不被上下文窗口限制遗忘关键信息，不随机漫步。v1.5 增加预置世界观深度（龙族小说）。
**Current focus:** v1.5 — Phase 6（Session Pacing）

## Current Position

Phase: 6 of 8 (Session Pacing)
Plans: 4/4 planned, 0/4 executed (06-01 through 06-04)
Status: Ready to execute — All 4 plans written, 19 tasks defined
Last activity: 2026-06-24 — Code audit & fixes

Progress: [████████████████████░░░] 71% (18/28 plans across all phases)

## Performance Metrics

**Velocity:**
- Total plans completed: 18
- v1 phases: 5/5 complete (18 plans, 143 tests)
- v1.5 phases: 0/3 complete

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation | 4/4 | ✓ Complete | - |
| 2. Campaign Core | 5/5 | ✓ Complete | - |
| 3. Narrative Quality | 4/4 | ✓ Complete | - |
| 4. UI & Polish | 2/2 | ✓ Complete | - |
| 5. Pre-Launch Hardening | 3/3 | ✓ Complete | - |
| 6. Session Pacing | 4/4 planned | Ready to execute | - |
| 7. Content Pipeline | 5/5 planned | Ready to execute | - |
| 8. Content Creation | 1/1 planned | Ready to execute | - |

## Accumulated Context

### Decisions

Key decisions from PROJECT.md affecting current work:

- CampaignManager 中间注入管线 — LLM 保持叙事判断，只提供结构化上下文
- 独立 campaign_progress 表 — 战役进度与游戏状态关注点分离
- Phase 6 = v1.5 桥梁 — v1 完成和 v2 开始之间的中间里程碑
- v1.5 核心：session 自动推进 + arc 选择 — 让现有 3-arc 战役可完整体验
- 小说→战役自动生成管线 — 核心差异化功能，降低内容创作门槛
- 存档槽自增 id PK — SQLite 表重建迁移，支持多槽
- FSM arc 边界单一路径 — skip resume_session，直接 arc_transition

### Pending TODOs

- Campaign Wiring 集成验证 — 必须在 Phase 6 实现前完成（外部声音 #1 发现）
- session_messages 表加 campaign_session_index 列（外部声音 #2）
- _is_first_turn_of_session() 修复（外部声音 #3）
- PromptBuilder.build() 返回 composite（外部声音 #5）
- entry_state 显式加入 SessionSchema（外部声音 #7）
- game_sessions 加 campaign_id 列（外部声音 #8）

### Blockers/Concerns

- **Campaign 系统从未端到端验证** (external voice #1): CampaignManager.load() 从未通过 API 调用。FSM/anchor/recap 全部未在集成层面测试。Phase 6 开始前必须用 WIRE 计划修复
- **DeepSeek model name deprecation**: `deepseek-chat` 于 2026-07-24 废弃，已迁移到 `deepseek-v4-flash`
- **JSON parse fragility**: json_repair + openai SDK json_schema 已解决

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Sanity system | Madness tables, phobia acquisition, reality checks (SANE-01~04) | Deferred to v2 | 2026-06-18 |
| Context window | Full hierarchical summarization (CTXW-01~04) | Interface in v1, full in v2 | 2026-06-18 |
| Content | Cover image generation, community marketplace (CONT-01~03) | Deferred to v2 | 2026-06-18 |
| Multiplayer | Turn sync, shared state, DM tools (MULT-01~02) | Deferred to post-v2 | 2026-06-18 |
| 难度选择器 UI | Frontend difficulty picker | Deferred to post-v1.5 | 2026-06-19 |
| 战役封面/浏览页 | Rich campaign browser UI | Deferred to post-v1.5 | 2026-06-19 |

## Session Continuity

Last session: 2026-06-24
Stopped at: Phase 6 ready to execute. Code audit completed — 28 issues found, 7 fix categories applied.
Resume file: None
