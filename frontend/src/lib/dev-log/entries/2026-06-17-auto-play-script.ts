import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
    id: "2026-06-17-auto-play-script",
    date: "2026-06-17",
    title: "自动跑剧情脚本和长轮次记录",
    summary: "新增自动剧情 playtest 脚本，用于连续创建会话、自动选择更能推进剧情的选项，并把每轮生成内容、选择记录、Context Memory 和 RAG Hits 追加到 Markdown 日志中，方便做 300 轮 x 3 次的稳定性观察。",
    developer: "Codex",
    areas: ["developer-tooling", "playtest", "backend", "llm"],
    changes: [
      "新增 scripts/auto_play.py，默认运行 3 个 session，每个 session 最多 300 轮，达到轮次后重新开始新会话。",
      "脚本会记录每轮所有可选项、实际选中的选项、选择分数、生成剧情、NPC 对话、状态变化、Context Memory 快照和 RAG Hits。",
      "自动选项策略偏向推进、继续、前往、调查、询问、检查、任务、地点、关键 NPC 或关键物品，并降低等待、拒绝、逃跑、沉默等被动选项权重。",
      "脚本按轮追加写入 Markdown 文件，默认输出到 playtest_logs/，即使长跑中断也能保留已经生成的内容。",
      "为生成请求增加 retries 参数，遇到临时网络或模型接口错误时会短暂等待并重试，降低长跑被偶发错误打断的概率。",
      "README 增加自动跑剧情的默认长跑命令、小规模试跑命令和常用参数说明。",
      "将 playtest_logs/ 加入 .gitignore，避免 900 轮剧情日志误提交到仓库。",
      "为了支持长剧情轮次，把提示词叙事目标调整为约 30 句，并提高 LLM max_tokens 上限。",
      "更新旧版 config.example.js 的示例模型名，保持示例配置和当前长文本生成需求一致。",
    ],
    relatedFiles: [
      "scripts/auto_play.py",
      "README.md",
      ".gitignore",
      "backend/app/services/llm_client.py",
      "backend/app/services/prompt_builder.py",
      "config.example.js",
      "frontend/src/lib/dev-log.ts",
    ],
    nextSteps: [
      "先用 --runs 1 --turns 5 做小规模试跑，确认输出格式和后端连接正常。",
      "再运行默认 3 x 300 轮长跑，检查日志里是否出现重复循环、记忆漂移、RAG 误命中或 JSON 修复失败。",
    ],
  };
