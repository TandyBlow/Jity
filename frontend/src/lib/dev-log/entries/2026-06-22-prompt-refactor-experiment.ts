import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
    id: "2026-06-22-prompt-refactor-experiment",
    date: "2026-06-22",
    title: "Prompt 重构验证实验",
    summary: "基于 6 轮实验（L0/L1/L2）识别出 prompt 设计为主要瓶颈后，对系统 prompt 进行深度重构：降低 temperature、精简 JSON schema、调整 L0 卡片位置、清理措辞，并设计三条件对照实验验证效果。",
    developer: "TandyBlow",
    areas: ["backend", "frontend", "llm", "prompt", "experiment"],
    changes: [
      "LLM temperature 从 0.9 降至 0.3，减少非 JSON 输出和随机漫步。",
      "Baseline JSON schema 精简为 8 字段（去掉 5 个状态追踪字段：sanity_delta、health_delta、items_update、npcs_update、quests_update），降低模型输出负担。",
      "L0 模式：8+5 字段 JSON（状态追踪字段标记为可选），L0 卡片从 prompt 顶部移至底部（叙事指令之后、JSON 格式之前），避免位置污染叙事指令。",
      "系统 prompt 措辞清理：DM→KP、删除冗余说明、强化 JSON 格式约束。",
      "评估方案：三步模糊匹配（规范化 + 关键词 + 嵌入相似度），评估叙事质量、状态追踪准确性和 JSON 合规率。",
      "前端新增战役选择器（campaign selector dropdown），支持从 Timeline 页面跳转时自动带入战役文件名。",
      "前端 createSession 支持 campaign/arc/session 参数，战役模式下自动触发开场生成。",
      "后端 POST /sessions 修复 entry_state 合并逻辑：不再仅 mid-campaign 合并，所有战役模式统一合并 entry_state（含 starting_state）。",
      "后端 /campaigns 列表过滤：跳过 schema 文件、下划线前缀调试文件、无 arcs 字段的非法 campaign。",
      "CORS 增加 localhost:3001 允许源，支持多前端开发端口。",
    ],
    relatedFiles: [
      "backend/app/main.py",
      "backend/app/services/llm_client.py",
      "backend/app/services/prompt_builder.py",
      "backend/app/services/scenario_generator.py",
      "backend/app/services/campaign_generator.py",
      "frontend/src/app/page.tsx",
      "frontend/src/lib/api.ts",
      "frontend/src/types.ts",
      "frontend/src/lib/dev-log.ts",
    ],
    nextSteps: [
      "运行 Baseline-new / L0-bot-full-new / L1-mix-k5-new 三条件各 10 轮（A+B 场景各 5 轮），收集 LLM 输出。",
      "用三步模糊匹配方案评估新旧数据，确认 prompt 改动是否提升 JSON 合规率和叙事质量。",
      "若 JSON 合规率显著提升，考虑将精简 schema 作为默认配置；否则回退部分字段。",
    ],
  };
