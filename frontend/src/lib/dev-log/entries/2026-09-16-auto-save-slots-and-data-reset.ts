import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
  id: "2026-09-16-auto-save-slots-and-data-reset",
  date: "2026-09-16",
  title: "自动存档槽、跨会话存档切换与本地数据重置",
  summary: "新开一局自动生成带时间戳的存档槽，设置与侧栏显示全部会话的存档并可跨会话切换；同时清理测试会话数据，保留三个战役与主存档。",
  developer: "zjr",
  areas: ["backend", "frontend", "save-slots", "database", "tests"],
  changes: [
    "确认游戏数据全部持久化在 SQLite（game_sessions、story_turns、session_messages、campaign_progress），关闭终端或浏览器不丢失；前端 localStorage 只存会话指针。",
    "新建战役会话未指定槽名时自动生成 auto_YYYYMMDD_HHMMSS 存档槽，替换默认 default 槽名；冒烟测试等显式槽名不受影响。",
    "存档列表改为返回全部会话的槽，不再按当前会话过滤；设置与侧栏下拉展示槽名、战役名、A/S 进度与最后游玩时间，选中任意槽即可切换到对应会话。",
    "槽选中逻辑改为按当前会话匹配首选槽名或 is_active 槽，避免多个会话同槽名时误选。",
    "CreateSessionRequest.slot_name 默认值改为 None；前端 createSession 仅在显式提供时才传 slot_name。",
    "重新加载测试改用会话的 active_slot_name，与生产环境 get_campaign_manager_for_session 行为一致。",
    "本地数据重置：按 session 隔离删除 102 个测试/冒烟会话及其消息、时间线节点、模型输出和进度行，保留主存档 00fb40e9 与三个龙族战役文件；VACUUM 后数据库从 17.6MB 降至 13.4MB，完整性检查通过。",
    "验证：357 项后端测试全部通过，前端构建通过；端到端验证自动槽命名、全部槽列表与 is_active 标记正确。",
  ],
  relatedFiles: [
    "backend/app/routers/sessions.py",
    "backend/app/schemas/game/requests_responses.py",
    "backend/app/repositories/campaign_progress.py",
    "backend/tests/test_campaign_openings.py",
    "frontend/src/components/game/SettingsMenu.tsx",
    "frontend/src/components/game/SidePanel.tsx",
    "frontend/src/components/game/useGameActions.ts",
    "frontend/src/components/game/useGameEffects.ts",
    "frontend/src/components/game/useGameSession.ts",
    "frontend/src/lib/api.ts",
    "frontend/src/lib/game/format.ts",
  ],
  nextSteps: [
    "用真实 LLM 验证跨会话切换存档后的续写连续性，确认切换后战役与剧情恢复正确。",
    "考虑为自动槽提供重命名与删除入口，避免大量时间戳槽难以辨认。",
    "备份文件 jity.sqlite3.bak 确认无误后可手动删除。",
  ],
};
