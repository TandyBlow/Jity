# E54 语义调用职责全审计（E53 第二版：回退、重试与能力分类）

**Question.** 现役语义工作流里，哪些判断真的调用 Qwen3-0.6B？每项职责的正常路径、弃权回退、校验重试与异常结果分别是什么？哪些部分程序已经能做，哪些需要语言理解、抽取或开放生成？

**Method.** 只读代码（`frontend/src/lib/world-engine/local/semantics/**`、`local/micro/**`、`local/game-model.ts`）+ 冻结验收证据复算（`artifacts/goal/semantic-micro/audit_counts.py`）。口径：`WorldTurnRecord.product.semanticCalls` 每条记录带 `task/key/source/ms/promptChars/issues/attempts/error/raw`。**重要修正（E53 口径错误）**：行动族（action/targets/reaction）每次引擎尝试单独记一行（`attempt:true`，`source=model`），成功后再记一行结果（`source=micro|model|program`）；因此 E53 把「尝试行 + 结果行」相加，高估了 action/targets 的 LLM 调用。E54 分开记：结果行、引擎尝试行、引擎调用合计。叙事（1.7B）不在去 LLM 范围内，表中保留只为对照。

## 1. 调用量（复算）

二十输入（`09-turns20-pi.json`，COMPLETED，20 回合）：

| 任务 | 结果行 n | model 结果 | 引擎尝试行 | 引擎调用合计 | 其他来源 | model 累计 s | p50 ms | promptChars p50 | issues |
|---|---|---|---|---|---|---|---|---|---|
| action | 292 | 23 | 136 | **136** | micro 249 / program 20 | 1,182.2 | 5,114 | 1,165 | 290 |
| targets | 296 | 31 | 32 | **32** | program 265 | 98.6 | 1,446 | 840 | 559 |
| results | 292 | 3 | — | **3** | micro 289 | 16.5 | 5,686 | 2,383 | 0 |
| updates.appearance | 292 | 5 | — | **5** | program 287 | 63.4 | 3,284 | 1,744 | 0 |
| updates.position | 292 | 7 | — | **7** | program 285 | 14.9 | 2,344 | 584 | 0 |
| updates.personality | 33 | 3 | — | **3** | program 30 | 33.6 | 5,782 | 2,782 | 0 |
| updates.sanity | 33 | 2 | — | **2** | program 31 | 7.8 | 3,898 | 1,324 | 0 |
| updates.subtasks | 33 | 29 | — | **29** | program 4 | 211.2 | 6,893 | 2,925 | 0 |
| updates.tasks | 33 | 20 | — | **20** | program 13 | 168.2 | 9,308 | 4,048 | 0 |
| continuation | 33 | 0 | — | **0** | micro 33 | 0 | — | — | 0 |
| reaction | 4 | 0 | — | **0** | micro 4 | 0 | — | — | 4 |
| narration（对照，不在范围） | 53 | 53 | — | **53** | — | 1,202.9 | 21,564 | 664 | 0 |
| **语义合计（不含叙事）** | **1,633** | **123** | **168** | **237** | — | **1,796.4** | — | — | — |

- action 136 次尝试中 23 次产出 model 结果，其余 113 次被拒/修复后落到微模板、micro 结果或 fallback。
- targets 32 次尝试中 31 次产出 model 结果；1 次 `fallback`（空目标）。
- E53 的 159/63 是「尝试 + 结果」相加；本表按引擎调用计为 136/32。

八场景（`10-scenarios-pi-2026-11-28T1041-fbe4.json`，COMPLETED，8 回合）：语义引擎调用合计 **105**（action 65、targets 12、tasks 8、subtasks 14、appearance 2、position 1、personality 2、sanity 1）；results 0（123/123 micro）、continuation 0（16/16 micro）、reaction 0（1/1 micro）；加叙事 24 次共 129 个引擎调用，E53 的 132 为生成记录口径。离线两回合（`10-offline-pi.json`）：语义引擎调用 22（action 14、targets 4、tasks 2、subtasks 2），其余全程序/微模型。

复算命令：`PYTHONUTF8=1 python -X utf8 artifacts/goal/semantic-micro/audit_counts.py`（表按 `source=model` 行计，含尝试行；引擎调用合计需减去 action/targets 的 model 结果行）。

## 2. 行动侧

### action（`semantics/actions/index.ts`，分发 `game-model.ts:328-349`）

判定顺序（先命中先返回，`source` 即证据）：

1. 主角冻结命令 → `program`（`index.ts:240`）。
2. 不在主角场景且 `judgeOffscreen=false` → `program` skip（`:254`）。
3. 三评分头 + 已校验模板候选 → `micro`（`:281-334`）；阈值 task≥0.5、scene≥0.5、领先第二 ≥0.2。
4. 行为分类头（6 类）→ `micro`（`:335-359`）；模板被拒记 `template_failed`。
5. 模板兜底（`judgedFallback` 或首个合法模板）交给 LLM 修复路径（`:363-375`）。
6. LLM `generate`（`:376-397`）：`action_is_task_goal` 时换 omitTasks 提示或模板兜底；两次都无可用输出 → `fallback` skip（`:407-408`）。

输出：`{kind:'act'|'skip', text, structured?}`。20 输入 action 引擎调用 136 次（23 次产出 model 结果，113 次被拒/修复后转微模板或 fallback）；249 次 `template_action`；21 条 `absent_character_in_action`。LLM 走 `engine.complete` 而非 `callJson`（无 maxPromptChars 保护）。

未解决：NPC 行动句是开放式；模板候选是闭集（`actions/candidates.ts`），判定头偏弃权。替代方向：候选解码（类别/目标/去向）+ 排序头；弃权 skip 并计数。

### targets（`actions/index.ts:411-471`）

1. 无可见候选 → `program` 空目标（`:416-420`）。
2. 规则提议 + 打分器校验（`micro/targets.ts`）：否定、缺席人名、代词歧义时规则弃权 → LLM（`:422-446`）。
3. LLM 兜底（`:458-471`），失败 → 空目标 `fallback`。

输出：`{targets:[{targetId}]}`。20 输入 targets 引擎调用 32 次（31 次产出 model 结果，1 次修复重试）；LLM 触发包括规则弃权（`micro_abstained` 31）、校验拒绝（`micro_rejected`）与端口异常（`micro_failed`）。未解决：否定、多人代词、跨房间点名。替代方向：场景候选排序头 + 否定/存在性证据。

### reaction（`actions/index.ts:474-525`）

触发分类 + 意图候选 + 三 judge 头 + 合理性门（`micro/reaction.ts:84-140`）：低置信或与来源行动重叠 ≥8 字 → 弃权 LLM。输出纯文本。20 输入 4/4 micro；八场景 1/1 micro。未解决：开放式反应句与因果；弃权时用中性模板并计数。

## 3. 结算侧

| 任务 | 正常路径 | LLM 触发 | LLM 输出 | 失败/异常后的保守结果 |
|---|---|---|---|---|
| results | 微头逐成员 5 类 + 事实模板（`settlement/results.ts:193-227`） | 微头返回 null（3/292） | `{judgments[],facts[]}` | `callJson` 最多 3 次，末次允许丢弃无可见结果的事实；仍失败则该结算点失败 |
| position | programScene / 本地位置 / 微移动头（`updates.ts:73-99,815-997`） | 三者都弃权（7/292） | 位置 schema | `stageFailure`：本阶段无变化，`fallback:true` |
| appearance | 环境补丁 + 复用位置答案（`updates.ts:1014-1119`） | 仍有未覆盖实体（5/292） | 操作 schema | 同上 |
| tasks | 微提案器 → 验证器（`updates.ts:1178-1230`） | 提案缺席或验证器拒绝后走 LLM（20/33） | `{unchanged/achieved, subtasks}` | `stageFailure`；strictSupport 下无依据的达成被拒 |
| subtasks | 无程序提案；只在有事实且受影响任务时调 LLM（`updates.ts:1393-1467`） | 有受影响任务（29/33） | `{subtasks:[{parentTaskId,goal}]}` | 程序过滤重复/他人物/复述事实/无根据；失败无新增 |
| personality | 无程序提案；只在新达成/恢复时调 LLM（`updates.ts:1470-1539`） | 有触发（3/33） | 个性操作 | 可选阶段：失败记 `optionalStageError`，无变化 |
| sanity | 只对个性变化者调 LLM（`updates.ts:1542-1580`） | 有个性变化（2/33） | 0–100 整数 | 失败保留当前理智 |
| continuation | 微型四头（`continuation.ts:397-478`） | 微头弃权（0/33） | 提案 + 判定 | 策略停机或 handback |
| task verifier | LLM 默认（`task-verifier.ts:114-146`）；`?taskVerifier=micro` 用对头 | 有支持需裁决 | `{satisfied:yes/no/partial}` | 解析失败抛错；调用方丢弃该达成 |

## 4. 校验、重试与异常（`settlement/engine-call.ts`）

- `callJson`：默认 2 次尝试（results 3 次），首次 temperature=0，重试 0.2；结构校验失败追加错误与格式提醒重试；截断时改用短输出提示；超过 `maxPromptChars` 直接抛 `context_capacity_exceeded`；两次失败抛 `JsonCallError` 并保留每次 raw。
- 行动族（action/targets/reaction）直接 `engine.complete`，不走 `callJson`，没有统一截断/重试保护；失败由 `generate` 返回 fallback 候选。
- 阶段失败不升级为回合失败（除 results、tasks/subtasks 的必需阶段外），但会留下 `fallback:true` 与 `optionalStageError`。
- 证据里行动族的每次尝试单独成行；20 输入 action 136 次引擎调用中第二次尝试 0 次，targets 32 次中修复重试 1 次（`turn.actions[].calls` 可复算）。阶段任务（results/updates）的重试在单行 `calls` 内，不拆分。

## 5. 能力分类

| 职责 | 程序可计算 | 语言理解 | 抽取 | 开放生成 |
|---|---|---|---|---|
| 骰点、准入、组冻结、合并、回放 | ✅ 全部 | — | — | — |
| 位置合法性、槽位、包含关系 | ✅ 图结构校验 | 跨房间/不确定移动 | 目的地短语 | — |
| 任务条件分解、台账、覆盖 | ✅ 条件与生命周期 | 达成语义、部分完成 | 依据事实 | — |
| 新增小任务 | 重复/外来/无根据过滤 | 是否需要新目标 | 新目标实体 | 目标句 |
| 人格 | 触发扫描、格式过滤 | 是否变化 | 变化类型 | 特征句 |
| 理智 | 0–100 边界、配对提交 | 变化幅度 | — | — |
| 外貌/环境 | 补丁、差分、词表 | 选择哪个分句 | 变化短语 | 外观句 |
| 行动结果 | 骰点、程序确认（移动/转移/环境） | 成败、部分成功 | 对象/去向/信息 | 结果句 |
| 行动理解 | 主角命令、场景范围 | act/skip、复合拆解 | 子动作/目标/物品 | 行动句 |
| 目标识别 | 同房间候选、规则点名 | 否定、代词、缺席 | — | — |
| 被迫反应 | 触发分类、合理性门 | 反应选择 | — | 反应句 |
| 继续推进 | 策略停机、预算 | 是否继续 | — | 候选行动 |

## 6. 现有替代组件（已测）

- results 微头 289/292；continuation 四头 33/33；reaction 4/4（二十输入）。
- targets 规则 + 打分器 265/328 程序、63 LLM；打分器单独过报，否定/代词仍弃权。
- action 三头 + 行为头 249/428；模板闭集。
- 任务条件头：82 行、留出 18 行、准确率 0.889（3 个留出任务）；条件+事实输入；部署为 `task-condition-int8.onnx`。
- 任务对验证器：80 行，留出 20 行；satisfaction yes 3/5、partial 1/5；`page.tsx` 注明留出不够，只在 `?taskVerifier=micro` 启用。
- env/info 存在性头留出 env 8/9、info 9/10；抽取头 top1 12/14（bigram 12/14）；support-info 5/10 不上新。

## 7. 未解决能力与首个实验

1. **任务达成**：验证器 yes 召回不足；LLM 判词是银标。先做 `(条件, 事实, 提交状态)` 分组数据集，用提交结果与程序覆盖做金标，再训条件级裁决器。
2. **新增小任务**：开放生成；改为候选检索 + 排序 + 模板填充，允许本轮不新增，单独统计被跳过的合法新增。
3. **人格/理智**：无微模型；先做「是否变化」二分类 + 模板句，理智用确定性映射并保守保持。
4. **外貌/位置**：D-136 残余（子地点/容器 locality）；先修程序 locality，再评估选择性微头。
5. **行动**：开放行动句；先做候选解码 + 排序，skip 计数。
6. **目标**：否定/代词；候选排序 + 存在性证据。
7. **反应**：开放句；中性模板兜底 + 弃权计数。

## 8. 数据与证据

- 输入证据：`results/product/evidence/09-turns20-pi.json`（56 MB，20 回合）、`10-scenarios-pi-2026-11-28T1041-fbe4.json`（20 MB，8 回合）、`10-offline-pi.json`（4 MB，2 回合）、`12-scenarios-q4kv.json`（对照）。
- 每条 `source=model` 调用的完整 prompt 在同回合 `product.semanticPrompts`（按时间顺序）；`semanticCalls` 保存 raw/value/issues/attempts。导出脚本见任务 1.2。
- 历史 `artifacts/goal/micro-workflow/records.jsonl`（559 条，4 runs）可作补充，但提示词已过时，只作对照。

## Caveats

- 行号基于 `semantic-micro-only@` 2026-11-28 分支起点，改动后漂移。
- `source=model` 与 `engine.generate` 计数口径不同（重试、多段生成）；本表按任务调用计。
- 八场景与二十输入的 model 数包含叙事（分别 24、53 次），语义合计列已扣除。
- 离线证据只有 2 回合，不能单独支撑泛化结论。

**Artifacts.** 本文件；`artifacts/goal/semantic-micro/audit_counts.py`；证据文件同上。E54，对应 D-145 第 1 条。
