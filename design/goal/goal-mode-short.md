# Jity Goal v11（短版，≤4000 字）

你是 Jity 的 goal 执行 agent。先读 `design/goal/goal-mode-prompt.md`（完整任务书），再读 `AGENTS.md` 与 `design/goal/{goal,architecture,decisions,ledger,acceptance}.md`；不要先读 historical/superseded 文档，背景按 `design/README.md` 标签查。

开工检查：`git status` 干净；`git log` 包含文档基线 `830bbd4f`；代码基线 `695e6bd4`；tag `goal-mode-baseline-20261120`；`openspec list --json` 与 `openspec list --specs --json` 确认当前变更与规格。

工作方式（强制）：每个 goal line 建一个 OpenSpec change，命名 `goal-g<N>-<slug>`；先 `openspec status --change "<name>" --json`，再按依赖顺序 `openspec instructions "<artifact>" --change "<name>" --json`，写 proposal/design/tasks/specs；按 tasks 实现并记录证据；完成后 `openspec validate "<name>" --strict`，再 `openspec archive "<name>" --yes`；归档后更新 `design/goal/ledger.md`（状态/证据/缺口）、`design/goal/decisions.md`（新决定）、`design/README.md`（新文档），按路径 commit，每个 goal line 打 tag。每次回复结束前必须更新文档并提交；未提交视为未完成。

执行顺序：G1 已完成；从 G3 模型资产与 60/300 计时开始，然后 G2 内核差分 → G4 页面接线 → G5/G6 语义与叙事 → G7 两设备同步 → G8 20 输入验收。

不可协商：浏览器本地推理、调度、状态计算与校验；服务器只存进度；禁用游戏 API 与保存服务后仍可玩。静态 S0；单一 `WorldState`/`WorldInitialState`；`stateDigest` 不一致拒绝开局。TS 内核唯一 apply/merge/commit/replay；Python 只作差分预言机。叙事按 2026-11-11 原样输出；运行期只判空，不检查、不裁改、不程序补写。60 秒首段、300 秒单点；20 次真实页面输入；R01–R16；离线、服务器关闭、两设备分叉、用户签字。本版只做 `dragon-raja-free-day`；草案参数已删除，不复活。单一 agent 树；不 force push；不自动合并；不静默换模型。

需要用户决定：改目标/范围/硬门槛；G6 后是否加事实门；模型替换；新增世界族；多用户/公网部署。
