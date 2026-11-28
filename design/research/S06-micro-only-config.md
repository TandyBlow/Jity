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

## 结果（冻结八场景，2026-11-29）

证据 `results/product/evidence/smoke-micro-only-frozen8-20261129.json`：**8/8 COMPLETED、0 failures**。

| 指标 | micro-only | 混合臂 |
|---|---|---|
| 回合等待 | **16.5–37.8 s** | 61.8–170.2 s |
| 模型请求 | **仅 `qwen3-1.7b-narr-lora` 1 次**；0.6B **0 次** | 0.6B + 1.7B |
| `__worldArm.semanticEngine` | **absent** | present |
| action | micro 116 / program 8 / **model 0** | 76 次模型结果 |
| targets | program 114 / fallback 10 / **model 0** | 22 次 |
| results | micro 123 / program 1（保守 no-change）/ **model 0** | 3 次 |
| updates | program 312 / **model 0** | position/appearance/personality/sanity 共 17 次 |
| continuation | micro 16 / **model 0** | — |
| narration | model 24（1.7B） | 24 |
| 角色最终位置 | 与混合臂 **0 差异** | — |
| 任务达成 | turn1 四个、turn6 route；无 kit | 同左 + kit |
| 最终任务集合 | 73（无 task_22） | 74 |

**结论**：这是第一个在冻结八场景上完全不加载、不调用语义 0.6B 的可玩版本；回合 16.5–37.8 秒，位置与混合臂一致，任务只少了严格标准下误判的 `lu_kit`。结果阶段有一次微模型弃权，按保守 no-change 提交；position/appearance/personality/sanity 全部走保守无变化，targets 有 10 次空目标弃权。

**未解决/风险**

- NPC 行动全部来自模板闭集，10 次目标识别弃权返回空目标；交互自由度与叙事质量尚未读评。
- 任务台账仍是 `createMicroGoalTasks` 内存 Map：刷新会丢未完成累计，历史回退可能保留失效证据（下一工作包：持久化/回滚）。
- 累计证据最终仍由行为克隆模型裁决（S01 控制臂），严格多事实金标模型未训练；本结果证明“可运行、零 0.6B”，不证明“任务语义正确”。
- 叙事仍用 1.7B，符合 S06 范围。

## 台账持久化（用户复核后补）

`createMicroGoalTasks` 现在提供 `exportLedger/importLedger/resetLedger`；`LocalGameSnapshot` 新增可选 `goalTaskLedger`，`session.ts` 在每次保存时写入、恢复时调用 `onRestoreGoalTaskLedger`。页面在创建会话时把两个回调接到 goal 端口上。测试覆盖：

- `goal-verifier.test.ts`：累计一条条件 → 导出 → 新端口导入 → 另一条条件到达后以 `cross_turn` 达成；
- `session-recovery.test.ts`：`goalTaskLedger` 随快照保存并在 restore 时回灌；
- 旧存档没有该字段时按空台账处理。

仍未做：历史回退（history 选中）时的台账回滚——当前台账只随 head 保存，不会在只读历史里变化；如果将来允许从历史分叉，需要按分叉点重建台账，已记入开放项。

**语义裁决的边界**：台账解决的是“证据是否齐全”，最终仍由行为克隆模型对累计证据打分；它不是严格多事实金标模型。下一步训练严格金标裁决器前，所有 micro-only 结论只声明“能跑、零 0.6B”，不声明“任务语义正确”。
