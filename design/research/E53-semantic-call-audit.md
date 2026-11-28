# E53 语义 LLM 调用审计：还剩哪些 0.6B 调用、为什么、下一步换什么

**Question.** 产品运行期还有哪些语义判断真的调用 Qwen3-0.6B？各自的输入输出、触发条件、
频率与耗时是多少？代码层面为什么现有微模型/规则还不能接手？

**Method.** 两条路分开读代码：行动侧（`local/semantics/actions/`，`game-model.ts:328-345`
分发）与结算侧（`local/semantics/settlement/`）。调用量从验收证据的 `generations`
记录数（一次 `engine.generate` 记一条）与 `[world-local task]` 日志统计；八场景证据
`10-scenarios-pi-2026-11-28T1041-fbe4.json`（q8、单引擎、`narrationModel=semantic`），
二十输入证据 `09-turns20-pi.json`。

## 1. 调用量（真实归因）

口径：页面 `WorldTurnRecord.semanticCalls` 每条记录带 task/key/source/ms/promptChars/
issues/raw/value，验收证据的 `product.semanticCalls` 原样保存；`source=model` 即一次语义
LLM 任务调用（内部重试不再拆分）。下表是两次冻结验收的证据汇总。

| 证据 | 回合 | 引擎生成记录 | LLM 任务调用 | 引擎累计耗时 | 回合墙钟 |
|---|---|---|---|---|---|
| 八场景 | 8 | 132 | 150 | 1,178 s | 858 s |
| 二十输入 | 20 | 200 | 344 | 1,755 s | 2,030 s |

二十输入按任务（n=调用数，p50 是 prompt 字符数）：

| 任务 | n | 累计耗时 | LLM | 规则/微模型 | promptChars p50 |
|---|---|---|---|---|---|
| action | 428 | 1,780.8 s | 159 | 269 | 1,165 |
| narration | 53 | 1,202.9 s | 53 | 0 | 664 |
| updates.subtasks | 33 | 211.2 s | 29 | 4 | 2,925 |
| updates.tasks | 33 | 168.2 s | 20 | 13 | 4,048 |
| targets | 328 | 98.9 s | 63 | 265 | 840 |
| updates.appearance | 292 | 63.4 s | 5 | 287 | 1,744 |
| updates.personality | 33 | 33.6 s | 3 | 30 | 2,782 |
| results | 292 | 19.5 s | 3 | 289 | 2,383 |
| updates.position | 292 | 14.9 s | 7 | 285 | 584 |
| updates.sanity | 33 | 7.8 s | 2 | 31 | 1,324 |
| continuation | 33 | 1.9 s | 0 | 33 | — |
| reaction | 4 | 0.2 s | 0 | 4 | — |

八场景同构（150 次 LLM：action 76、narration 24、targets 22、subtasks 14、tasks 8、
appearance 2、personality 2、sanity 1、position 1）。每回合约 17 次语义 LLM 调用。

- 结算侧 LLM 集中在 **tasks（任务达成，prompt 4,048 字）** 与 **subtasks（新增小任务，
  2,925 字）**——正是用户指定的前两项；两者在二十输入里共 70 次、379 s。
- 行动侧 LLM 调用最多（159 次），但 269 次已走微模型/规则；targets 的 63 次全部是规则
  弃权（否定、缺席人名、代词）。
- results / continuation / reaction 已全微模型：二十输入里 results 289/292、continuation
  33/33、reaction 4/4。
- prompt 普遍不长（多数 p50 < 1.5k 字），说明这些调用要的是判断与结构化输出，不是长文理解。

## 2. 行动侧（action / targets / reaction）

| 任务 | 现在由谁做 | LLM 触发条件 | LLM 输出 | 代码写明的替换障碍 |
|---|---|---|---|---|
| action | 三个 ONNX 判定头 + 行为头（`actions/index.ts:281-359`） | 判定头缺席/弃权/分数不齐，或行为头 p<0.4 | `{kind:act,text}` 或 `{kind:skip}` | 行动正文开放式；模板是闭集（`actions/candidates.ts:28-78`）；判定头阈值偏弃权（`index.ts:318`） |
| targets | 规则匹配 + ONNX 配对打分（`index.ts:422-456`） | 规则弃权：否定、缺席人名、代词（`micro/targets.ts:36-51`） | `{targets:[{targetId}]}` | 否定与指代"规则判不了"；打分头阈值默认 0，几乎全确认（`targets.ts:118-121`） |
| reaction | 五个触发类 + 三个判定头（`micro/reaction.ts:84-140`） | 微模型弃权或候选被拒 | 纯文本，无 JSON | 因果与开放式反应；置信门要求与来源重叠 <8 字（`reaction.ts:128-132`） |

行动族直接调 `engine.complete`（`actions/index.ts:133-139`），不走 `callJson`：没有
`maxPromptChars` 保护，也没有截断重试。

## 3. 结算侧（results / updates / continuation）

| 任务 | 现在由谁做 | LLM 触发条件 | LLM 输出 | 代码写明的替换障碍 |
|---|---|---|---|---|
| results | 微模型默认（`settlement/results.ts:193-227`） | 微模型无答案 | `{judgments[],facts[]}` | 微头只是复刻同一 schema；未注册实体检查是词法的（`results.ts:335`） |
| updates.position | programScene + localPosition + 微模型（`updates.ts:816-913`） | 三者都弃权 | 位置/场景 schema | 跨房间与不确定移动 |
| updates.appearance | 环境补丁 + 复用位置答案（`updates.ts:1014-1087`） | 仍有未覆盖实体 | 操作 schema | `micro/updates.ts:3-4`："Appearances stay with the LLM for now" |
| updates.tasks | 微提案器给支撑 + 判定（`updates.ts:1178-1230`） | 有支撑需要裁决 | `{achieved[],subtasks[]}` | 目标措辞重叠只是必要条件，不是决策（`updates.ts:2447`） |
| updates.subtasks | LLM 提案（`updates.ts:1444-1451`） | 有受影响任务 | `{subtasks:[{parentTaskId,goal}]}` | 新增目标是开放式内容；程序只做重复/外来/无根据过滤 |
| updates.personality | LLM（`updates.ts:1501-1507`） | 有新达成/恢复的任务 | 人格行 schema | 开放式特征句；程序只过滤事实回声与人名 |
| updates.sanity | LLM（`updates.ts:1549-1555`） | 人格有变化的角色 | 理智 schema | 人格到数值没有公式 |
| continuation | 微头默认（`continuation.ts:397-478`） | 微头无答案 | 提案 + 判定两段 | 候选文本开放式；微头只在自信时接管 |
| 任务达成判断 | 默认 LLM（`settlement/task-verifier.ts:114-146`） | 有支撑需要验证 | `{judgments:[{satisfied:yes|partial|no}]}` | 微验证器存在但"held-out 准确率太低，不能替换"（`page.tsx:624-625`），且只在 `?taskVerifier=micro` 下启用 |

## 4. 已有的"无 LLM"开关不是独立实验配置

`semanticArm=rules|classifier`（`page.tsx:1104-1114`）把 `complete` 代理成抛
`semantic_arm_abstain`，让每条 LLM 路径走兜底。这等价于"停用 LLM 后的降级"，不是
"规则 + 微模型接管"的独立配置——按要求不能拿它当验收证据。新的独立配置要显式给每个
任务接上规则/微模型，并对不确定情形做候选重选与保守结算，而不是直接跳过。

## 5. 下一步（按用户优先级）

1. **数据导出**：`semanticCalls` 已带 task/source/raw/value/issues，直接从冻结验收证据
   导出每个任务的 `(输入, 输出, 校验结果)`，作为替代实验的训练与评测集；缺的是把 raw
   转成结构化标签的脚本，不是新的埋点。
2. **任务达成判断**（优先级 1）：现有微验证器准确率不够。先落数据集——从真实回合里导出
   `(任务条件, 事件事实) → satisfied` 的标注，特征是结构化事件（主体/动作/对象/结果/地点），
   不是原始 prose。这同时是"共享结构化事件表示"的第一个落点。
3. **新增小任务**（优先级 2）：开放式目标生成，先做候选检索 + 排序 + 模板填充，
   允许弃权到"本轮不新增"，但不得以减少任务更新来虚增成功率。
4. 其余按 人格 → 理智 → 外貌 → 位置 → 行动结果 → NPC 自主行动 的顺序逐个替换。
5. 全部替换后，验收要证明 0.6B 未被下载/初始化/调用（网络记录、加载记录、调用计数），
   并比较世界状态、任务达成、交互自由度、叙事质量、耗时与峰值内存。

**Caveats.** 引擎生成记录（132/200）与任务调用（150/344）不是同一口径：前者含重试与
多段生成，后者按任务计。E18 的 106 条是第三种口径（按阶段）。代码行号来自 2026-11-28
的两次只读审计，改动后会漂移。

**Artifacts.** 本文件；证据 `10-scenarios-pi-2026-11-28T1041-fbe4.json`、`09-turns20-pi.json`。E53。
