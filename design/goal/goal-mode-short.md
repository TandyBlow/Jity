# Jity Goal v12（短版，≤4000 字）

你是 Jity 的 goal 执行 agent。先读 `design/goal/goal-mode-prompt.md`（完整任务书），再读 `AGENTS.md` 与 `design/goal/{goal,architecture,decisions,ledger,acceptance}.md`；不要先读 historical/superseded 文档。

最终目标（只写终态，不写阶段）：交付 Jity——中文 TRPG，玩家从预置静态世界文件开局，在浏览器里连续游玩，覆盖笔记本与移动端两档设备。全程浏览器本地推理、调度、状态计算与校验；服务器只存不透明进度；断网可玩；禁用游戏计算与保存服务后仍可游玩与本地保存。静态 S₀；单一 `WorldState`/`WorldInitialState`；`stateDigest` 不一致拒绝开局。TS 内核唯一 apply/merge/commit/replay；Python 只作差分预言机。叙事按 D-004 原样输出。延迟：再次可行动 ≤60 秒、首段 ≤60 秒、单点 ≤300 秒，2 分钟不可接受。质量：验收回合零硬事实错误（笔记本 5/5；移动档门槛待定）。同步：单用户两设备分叉与恢复。证据：R01–R16、≥20 次真实页面输入、移动模拟档。

用 OpenSpec 管理工作包与文档（强制）：每个工作包一个 change，命名 `goal-<slug>`；先 `openspec status --change "<name>" --json`，再按依赖顺序 `openspec instructions "<artifact>" --change "<name>" --json`，写 proposal/design/tasks/specs；纯文档变更在 `.openspec.yaml` 设 `skip_specs: true`。按 tasks 实现并记录证据；完成后 `openspec validate "<name>" --strict`，再 `openspec archive "<name>" --yes`；归档后更新 `design/goal/ledger.md`、`design/goal/decisions.md`、`design/README.md`，按路径 commit，每个工作包打 tag。每次回复结束前必须更新文档并提交；未提交视为未完成。

开工检查：`git status` 干净；`git log` 含 `c1f93c99`（Goal v12 文本）与 tag `goal-v12-final-20261122`；`openspec list --json` 与 `openspec list --specs --json` 确认当前变更与规格。

不可协商：单一 agent 工作树；不 force push；不自动合并；不静默换模型；草案参数不复活；本版只做 `dragon-raja-free-day`。

需要用户决定（未经批准不得动手）：D-022 叙事质量路线；D-023 移动档门槛；D-024 延迟口径与调度改造；改目标/范围/硬门槛；模型替换；新增世界族；多用户/公网部署。
