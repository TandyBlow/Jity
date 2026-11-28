# S06 micro-only 配置：禁用语义引擎，所有端口走程序/微模型（设计）

**Question.** 把所有语义端口接到程序/微模型，并在页面层不构建、不加载语义 0.6B，回合还能不能提交？哪些阶段需要保守答案，代价是什么？

**现状（E53/E54）**：行动族已可 template-only（S05），tasks/subtasks 已可程序/微模型（S03/S04）；仍会调 LLM 的点：results 微模型弃权（3/292）、position（7/292）、appearance（5/292）、personality（3/33）、sanity（2/33），以及 continuation/reaction 的极少弃权。

**配置**

- `semanticArm=micro-only`（新值）：不创建、不加载 `Qwen3-0.6B`；语义端口注入一个直接抛 `semantic_llm_blocked` 的 stub，任何误调用都进证据。
- 行动族：`templateOnly` + `targetsNoLlm`；反应微模型弃权时用中性模板。
- tasks/subtasks：`microGoalTasks`（严格门）+ `programSubtasks`。
- 保守答案（每个阶段都必须给内核可提交的结果）：
  - results 微模型弃权 → 每位成员一条 `no_change` 判定与「没有变化」事实；不写未结算动作。
  - position/appearance 无程序答案 → 无变化。
  - personality → 保持原个性（无变化）。
  - sanity → 保持当前理智值。
  - continuation 微模型弃权 → handback。
- 叙事仍由 1.7B 生成；微模型不参与叙事。

**证据**

- `__worldArm.semanticEngine='absent'`、`taskStage='goal'`、`subtasks='program'`、`action='template'`、`targets='rule'`；
- 模型请求记录中 `/models/Qwen3-0.6B` 请求数 0、语义引擎初始化 0；
- 每阶段 `source` 与弃权原因；回合提交、状态差分、任务集合。

**验收**

- 冻结八场景 8/8 提交、0 failures；与严格任务臂/混合臂比较状态、任务、叙事；
- 明确统计被跳过的合法变化、被拒绝的动作、减少的 NPC 行为与反应；
- 若回合卡死，先修保守答案，不允许靠减少更新或提前交还来通过。

**风险**：保守 no-change 会丢失合法变化；必须先测量差异，再决定哪些阶段值得补微模型。S06。

## 用户复核后的修正（2026-11-28）

1. **任务条件改为跨事实/跨回合台账**：程序用 `strictConditionHits` 判定每条事实覆盖了哪些条件（动作/确认必须命中条件自身的词），台账按任务累计；全部条件都有 completed 事实后，把累计证据拼成一段交给 goal 模型做一次最终判断（阈值 0.5）。不再要求单条事实覆盖全部条件，也不再用单事实分数卡每个条件。证据里保留 `condition -> factId/factText` 映射。
2. **删除父任务派生子任务的模板**：该模板只是父目标第一步的复述，独立价值不足；程序子任务只保留从结构化事实标记生成、且与父任务不同的候选。
3. 两回合累计（拿起护目镜 → 戴好并确认）页面验证进行中；若通过，`task_lu_goggles` 应在第二回合以 `basis=cross_turn` 达成，而 `task_lu_kit` 仍因缺少“拿到/装备”条件保持 pending。
