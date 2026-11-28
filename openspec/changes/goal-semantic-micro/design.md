# Design: goal-semantic-micro

## Context

现役默认是「微型混合工作流」（D-121）：程序 → 微模型 → LLM 回退。E53 审计（`design/research/E53-semantic-call-audit.md`）给出二十输入 20 回合的真实归因：语义 LLM 任务调用 344 次，action 159、targets 63、narration 53、subtasks 29、tasks 20，其余 ≤7；结算侧 LLM 集中在任务达成（prompt p50 4,048 字）与新增小任务（2,925 字）。results 289/292、continuation 33/33、reaction 4/4 已由微模型接管。回退与重试路径已读：`callJson` 最多 2 次校验重试（截断时换短输出提示），失败抛 `JsonCallError`，各阶段自行决定保守结果。

本设计只覆盖语义工作流。叙事继续使用 1.7B（D-145）；`WorldState` schema 不变；`semanticArm=rules|classifier` 保留为历史对照臂。

## Goals / Non-Goals

**Goals**

- 每个语义端口的 LLM 调用点都有明确的程序/微模型替代物与弃权路径。
- 新 `semanticArm=micro-only`：语义引擎不构建、不加载、不请求；端口禁止 LLM；回合仍能提交。
- 任务达成判断与新增小任务先行，其他端口按 D-145 顺序跟进。
- 数据、标签、切分、基线与验收均可从仓库内脚本复算。

**Non-Goals**

- 不改叙事模型、不改叙事边界（D-004）。
- 不改 `WorldState` schema、运输协议与内核提交语义。
- 不做多世界生成、不做服务器端推理。
- 不把「拒绝行动 / 跳过更新 / 少 NPC 行为」当成功率。

## Decisions

### D1. 端口级替代，而不是一个通用小模型

每个职责单独定义输入投影、输出 schema、程序地板与弃权门；共享编码器可以复用（MiniRBT int8 已在用，10.5 MB/头），但不假设一个微型生成模型能接管所有职责。理由：E32 从句选择 F1 .906、分类头留出 8/9–9/10 与任务条件头 0.889 说明「分类/排序可学」，而 E45/E52 表明自由生成不可学。备选：单一 seq2seq 微型工作流（已被 D-046/D-049 的实体/开放字段全 0 否掉）。

### D2. 任务达成判断 = 条件分解（程序）+ 条件覆盖（微模型）+ 保守裁决

- 程序把目标分解为 time/location/item/target/confirmation/action/decision 条件（`micro/task-progress.ts` 已实现），并维护跨回合条件台账。
- 微条件头对 `(条件, 事实)` 输出 none/keyword/attempt/satisfied；程序地板检查动作动词、确认词与否定前缀。
- 裁决器只在全部条件 satisfied 且证据有效时输出 yes；否则 no/partial。弃权（低置信/模型不可用）→ 不达成，但记 `abstain_reason`，并在验收里单列「本应达成但被弃权」。
- 新裁决器的训练数据来自真实回合：任务目标 + 条件 + 事实 + 提交后的任务状态；标签优先用提交结果（achieved/pending）与程序可验证条件，LLM 判词只作银标并抽样人工核验。
- 备选：直接让微模型读整段 prompt 判定（`task-match` 头，yes 召回 3/5）——保留为对照臂。

### D3. 新增小任务 = 检索候选 + 排序 + 模板填充，允许「本轮不新增」

- 候选来源：本回合事实中的动作/对象/目标实体、父任务缺口条件、同场景待办。
- 排序器为微型对打分（父任务目标 × 候选目标），训练标签来自真实提交的新增子任务与人工拒绝例（重复、他人物、复述事实、无根据）。
- 生成只做受限模板填充（实体名 + 已登记动作/条件短语），不自由写句；未过门 → 不新增。
- 验收单列「被跳过的新增」与「错误新增」，防止用少新增换成功率。

### D4. 结构化事件经兼容适配层提供

结算事实已带结构化标记（`去向=`、`环境=`、`信息=`、`涉及=`）。适配层 `structured-events` 从 `(results, facts, state delta)` 生成事件记录：`actorId, targetIds, action, objectIds, result, degree, cause, location, info, envChanges, relations, source`，并带四态证据。适配层只读已提交数据，不改 schema；叙事侧按需读取。四态规则：有直接结算事实且条件覆盖 → present；明确否定/失败 → absent；只有动作未结算/证据不足 → insufficient；与既有状态矛盾 → conflict。

### D5. Micro-only 是独立臂，语义引擎不构建

- 新增 `?semanticArm=micro-only`：页面不创建、不加载语义引擎；叙事引擎照常（1.7B）。
- 所有端口注入 `llmPolicy: 'block'`；任何试图调用 LLM 的路径必须抛 `semantic_llm_blocked` 并由端口自己的保守实现接住，而不是让回合失败。
- 保守实现（首版）：
  - action：程序/微模板 → 失败则 `skip`（记录 `action_abstained`）。
  - targets：规则 + 打分器 → 失败则空目标（记录）。
  - reaction：微反应 → 失败则最保守的中性反应模板。
  - results：程序/微头 → 失败则逐成员 `no_change` 事实（保守，不写未结算动作）。
  - updates：各阶段弃权 → 该阶段无变化；tasks/subtasks 走 D2/D3；personality/sanity/appearance/position 走各自替代或空。
  - continuation：微头 → 失败则 handback。
- 每回合证据记录 `arm=micro-only`、`llmBlocked` 计数、每端口 `source` 与弃权原因。验收驱动已有模型请求记录，另加「语义引擎未创建」的运行时标记。

### D6. 数据导出与切分

- 输入：冻结证据 `results/product/evidence/09-turns20-pi.json`、`10-scenarios-pi-2026-11-28T1041-fbe4.json`、`10-offline-pi.json`、`12-scenarios-q4kv.json`；历史 `artifacts/goal/micro-workflow/records.jsonl` 只作补充。
- 脚本 `artifacts/goal/semantic-micro/export_calls.py` 把每个 `source=model` 调用与同回合 `semanticPrompts` 按顺序/任务签名对齐，输出 JSONL：`turn, task, key, prompt, raw, value, issues, ms, attempt`。
- 标签：任务达成用提交后的任务状态与条件覆盖；证据四态按 D4 规则；LLM 判词为银标。
- 切分：按场景/事实集/回合分组；冻结八场景与二十输入从训练、验证、阈值扫描中排除（脚本断言）。
- 大数据集落 `experiments/semantic-micro/`（gitignored）；仓库提交 manifest、哈希、脚本与小报告。

### D7. 模型与运行成本门

- 新模型优先 1e5–1e7 参数；沿用 MiniRBT 共享编码器 + 任务头时，int8 权重按现有 10.5 MB/头计。
- 训练在 HPC（PyTorch），导出 ONNX int8，浏览器用 onnxruntime-web；一致性门：同一组输入，PyTorch 与 ONNX 决策一致率 100%（阈值内），浏览器与 Node 决策一致。
- 延迟目标：语义阶段合计进入秒级；单端口 p50 目标 ≤50 ms（CPU WASM），需在验收报告实测。

### D8. 验收与证据

- 单元/集成：Vitest；新增端口测试覆盖正常、弃权、LLM 禁止三条路径。
- 页面：`accept-world-local.mjs` 增加 `--block-models=Qwen3-0.6B` 或等价断言（请求记录中 0 次该文件），并记录 `__worldArm.semanticEngine=absent`。
- 夹具：八场景 + 二十输入 + 离线 + 刷新恢复；指标沿用现有驱动，另加「被跳过合法变化」与「额外错误状态」。
- 对照：现役混合臂同夹具重跑，报告差异。

## Risks / Trade-offs

- [微型裁决器召回不足] → 弃权≠失败：保守不达成 + 单列计数；先用程序条件覆盖兜底，再逐步放宽阈值；保留 LLM 臂作对照，不删除。
- [固定场景过拟合] → 冻结数据不训练；按场景/事实集分组；新增独立场景集验证泛化。
- [Micro-only 回合卡死] → 每个端口必须有内核可接受的保守答案（D5）；用 D-125/D-128 的失败作回归样本。
- [结构化事件与现有事实串重复] → 适配层只读、可丢弃；事实串仍是提交与叙事的唯一依据。
- [权重体积增长] → 共享编码器 + 头，单头 10.5 MB；总量门在验收报告对比 0.6B 397 MB。

## Migration Plan

1. 本分支（`semantic-micro-only`）完成数据导出、审计与逐端口实验；默认行为不变。
2. 每个端口先以查询参数臂接入（`?taskVerifier=micro`、`?semanticArm=micro-only`），过冻结夹具后记录决策。
3. 全部端口通过后提出默认切换方案与兼容说明，由用户裁决；切换前的产品默认仍是现役混合工作流。
4. 回滚：查询参数强制旧臂；代码路径保留 LLM 端口。

## Open Questions

- 任务达成裁决器的「yes」召回门应与条件覆盖如何组合，需用真实提交结果做阈值扫描后定。
- 新增小任务的模板覆盖面能到多少，取决于事实/实体词表；先测再定是否引入受限生成。
