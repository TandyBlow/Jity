# 语义工作流交接（2026-11-28，交给语义 Agent）

本文件由叙事 Agent 在交接时写。此后叙事 Agent 不再修改语义相关代码、配置与实验。
所有改动都已提交并推送 `agent` 分支。

## 1. 今天已改并已验收的语义配置

- **D-142（已采纳）**：语义上下文默认从 12288 改为 **8192**。
  - 代码：`frontend/src/app/world-local/page.tsx` 新增 `DEFAULT_SEMANTIC_CTX = 8_192`，
    引擎与 `__worldArm` 记录共用；URL 覆盖 `?semanticCtx=` 仍可用（2048–32768）。
  - 门槛证据：二十输入 20/20 + 刷新恢复 20→20
    （`results/product/evidence/09-turns20-pi.json`）；八场景 8/8、0 problems
    （`10-scenarios-pi-2026-11-28T1041-fbe4.json`）；离线 2/2
    （`10-offline-pi.json`）；改默认后冒烟 1/1、51.3 s
    （`11-smoke-default-ctx8192.json`）。
  - 依据：E42 统计 64,423 次真实语义调用，最大 6,797 tokens，无一次超过 8192。
- **D-144（不采纳）**：q4 KV 不采用。同八场景夹具在 `kv=q4_0` 下 5/8 回合出问题
  （sc02/sc03 叙事空输出、sc05 结算未完成、sc06 超时、sc07/sc08 正文过短），q8 对照 0/8。
  证据 `12-scenarios-q4kv.json`。KV 保持 q8_0。
- **4096 上下文不要试**：E42 实测最大 6,797 tokens，4096 会溢出。

## 2. 审计结论（E53，`design/research/E53-semantic-call-audit.md`）

口径：`WorldTurnRecord.semanticCalls`（页面已记录，验收证据保存在
`turn.product.semanticCalls`），每条含 task/key/source/ms/promptChars/issues/raw/value，
`source=model` 即一次语义 LLM 任务调用。

二十输入 20 回合的实测：

| 任务 | 调用数 | 耗时 | 其中 LLM | promptChars p50 |
|---|---|---|---|---|
| action | 428 | 1,780.8 s | 159 | 1,165 |
| narration | 53 | 1,202.9 s | 53 | 664 |
| updates.subtasks | 33 | 211.2 s | 29 | 2,925 |
| updates.tasks | 33 | 168.2 s | 20 | 4,048 |
| targets | 328 | 98.9 s | 63 | 840 |
| updates.appearance | 292 | 63.4 s | 5 | 1,744 |
| updates.personality | 33 | 33.6 s | 3 | 2,782 |
| results | 292 | 19.5 s | 3 | 2,383 |
| updates.position | 292 | 14.9 s | 7 | 584 |
| updates.sanity | 33 | 7.8 s | 2 | 1,324 |
| continuation | 33 | 1.9 s | 0 | — |
| reaction | 4 | 0.2 s | 0 | — |

要点：
- 结算侧 LLM 集中在 **任务达成（updates.tasks）** 与 **新增小任务（updates.subtasks）**；
  results / continuation / reaction 已 100% 微模型或规则。
- 行动侧 LLM 最多（159 次），但 269 次已走微模型/规则；targets 的 63 次全是规则弃权
  （否定、缺席人名、代词）。
- 八场景（8 回合）同构：150 次 LLM 任务调用。

代码路径（两路只读审计，行号 2026-11-28）：
- 分发：`local/game-model.ts:328-345`。
- 行动侧：`local/semantics/actions/index.ts`（action 281-397、targets 415-471、
  reaction 479-525），微模型在 `micro/targets.ts`、`micro/reaction.ts`。
- 结算侧：`semantics/settlement/{results,updates,continuation,task-verifier}.ts`；
  `updates.tasks` 1178-1357，`subtasks` 1396-1451，`personality` 1472-1539，
  `sanity` 1543-1578，`appearance` 1014-1113，`position` 816-996。
- 任务达成微验证器已存在，但 `page.tsx:624-625` 注明 held-out 准确率不够，
  只在 `?taskVerifier=micro` 下启用。
- `semanticArm=rules|classifier`（`page.tsx:1104-1114`）把 `complete` 代理成抛
  `semantic_arm_abstain`，是"停用 LLM 后走兜底"，不是独立规则+微模型配置。

## 3. 未完成事项（供接手）

1. 把 `semanticCalls` 的 `(输入, 输出, issues)` 导出成每个任务的训练/评测集；
   raw 与 value 都在证据里，缺的只是导出脚本。
2. 任务达成判断：微验证器准确率不够，需要特征化数据集（结构化事件 + 任务条件）。
3. 新增小任务：开放式目标生成，现有程序只做重复/外来/无根据过滤。
4. 人格、理智、外貌、位置四项没有微模型，LLM 输入输出见 E53 表。
5. 新目标要求的独立"规则+微模型、禁止语义 LLM"配置尚未建立。
6. 验收器修复：回合把世界打完结时页面显示"本轮已交还"但无新条目，现已立即结束并记
   `no_entry_added`（af9e263e）；仍有其他停止行未覆盖，跑夹具时注意 `turn_timeout`。

## 4. 叙事侧的接口需求（协商用）

叙事微模型需要结构化事件而不是自然语言事实串。当前 `facts` 文本存在主语丢失
（如"的红色识别带在胸前微微发烫"），E51 留出集 2/30 因此只能丢人名。请语义侧在事实
记录里保留 `actorId`（或动作主体 id）与 `targetId`；叙事侧先用适配层从现有记录补充，
不改结算程序。

## 5. 边界

- 叙事 Agent 不再修改：`local/semantics/**`、`local/micro/**`、`schedule.ts` 的任务语义、
  语义引擎配置与提示词、`page.tsx` 里的语义臂开关。
- 产品入口与公共接口的改动需协调；叙事实验走独立目录
  `experiments/narration-standalone/` 与 `artifacts/goal/narration-standalone/`。
