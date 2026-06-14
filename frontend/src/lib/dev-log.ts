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
