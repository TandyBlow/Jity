import type { DevLogEntry } from "@/lib/dev-log/types";

export const entry: DevLogEntry = {
  id: "2026-10-11-memory-review-and-local-startup",
  date: "2026-10-11",
  title: "跨幕记忆与物品一致性修复、本地启动保护",
  summary: "保留跨幕记忆快照，补齐物品别名消歧和消耗状态约束，避免背包容量截断丢失新物品，并让联合启动脚本保护已有服务。",
  developer: "Codex",
  areas: ["backend", "memory", "campaign", "scripts", "tests"],
  changes: [
    "记录已推送到 zjrrrr 的提交 b1a9efa（记忆与物品修复）和 cc35321（启动脚本修复）；本条补充 10 月 1 日记录未覆盖的改动。",
    "跨幕重置 NPC、近期事件和场景提示词时保留分支所属的完整记忆快照，包括长期摘要与待摘要输入；清理运行时缓存后从保留的快照重新加载，避免历史线索在进入下一幕时被删除。",
    "本地 Examiner 支持按规范名称与显式 aliases 查找物品，规范名称优先；同一别名对应多个物品时要求使用明确名称。SCORE 先建立各物品身份再注册别名，避免共享别名将不同物品合并或误删其中一个。",
    "新增 consumed 状态，将 used/consumed/消耗映射为已消耗，将 discarded 映射为丢失。已消耗的同一物品身份不能通过普通获得、recovered 或 repaired 复活；损毁物品仍允许显式 repaired。该约束在快照序列化与恢复后继续生效。",
    "物品终态同时校验顶层 items_gained/items_lost 和 memory_updates，移除不可用物品并保留状态记录；提示词同步列出 consumed、destroyed 和 discarded 等状态。约束针对结构化状态，不代表已完成任意叙事文本的事实审查。",
    "取消背包列表的 20 项截断，避免获得的新任务物品被静默丢弃、背包与物品状态记录不一致；NPC、任务和长期事实仍保留原有容量限制。",
    "联合启动脚本使用 lsof 检查配置的端口；端口已有监听进程时跳过对应服务启动，不截断该服务的已有日志。监听进程的服务身份未校验，端口占用本身不证明 Jity 服务可用。",
    "退出或子进程异常时仅清理本次脚本启动的进程，保留已有服务；支持自定义前后端端口。两个端口都被占用时直接退出，不启动新进程。",
    "本次提交前相关后端测试 94 项通过，启动脚本测试 5 项通过，git diff --check 通过；后端有 3 条 SWIG 依赖弃用警告。测试覆盖跨幕线索检索与注入、别名歧义、物品终态恢复、容量边界、SQLite 快照恢复与事务回滚，以及端口占用和启动失败。",
    "上述验证为离线回归；本次未重新运行真实模型长剧情、前端生产构建或页面验收。约 19 MB 的 docs/evidence/ 验证材料保留在本地，未随上述提交推送。",
  ],
  relatedFiles: [
    "backend/app/schemas/agent_io/memory_branches.py",
    "backend/app/services/agents/examiner.py",
    "backend/app/services/game_state/entry_state.py",
    "backend/app/services/game_state/manager.py",
    "backend/app/services/memory/score_tracker.py",
    "backend/app/services/prompt_builder/builder.py",
    "backend/app/services/scenario_generator/opening_scene.py",
    "backend/tests/test_memory_review_regressions.py",
    "scripts/start_local.sh",
    "scripts/tests/test_start_local.py",
  ],
  nextSteps: [
    "将 zjrrrr 与 master 的 Examiner、生成持久化和前端改动整合后重新验证，当前分支通过不等同于合并版本已通过。",
    "补充真实模型跨幕线索与物品一致性评估，并将存档删除入口接到首页实际使用的 SettingsMenu。",
  ],
};
