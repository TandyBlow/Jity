import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
    id: "2026-06-15-context-memory",
    date: "2026-06-15",
    title: "第二阶段：强化 Context Memory",
    summary: "把原本偏临时记录的状态扩展成真正的游戏记忆系统：明确长期状态结构、稳定 NPC/任务/物品字段，并让每轮 AI 输出只提交增量记忆，由后端合并成下一轮 prompt 的上下文。",
    developer: "Codex",
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
  };
