import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
    id: "2026-06-16-status-delta-and-json-repair",
    date: "2026-06-16",
    title: "状态变化提示、血统稳定恢复和 JSON 修复",
    summary: "增强游戏回合反馈和 AI 输出可靠性：前端直接提示本回合血统稳定/体力变化，后端统一处理血统稳定的自动恢复，并为模型 JSON 输出增加强制格式和二次修复。",
    developer: "Codex",
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
  };
