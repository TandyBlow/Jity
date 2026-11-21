# Design: G5 非叙事语义验收

## Context

见 proposal。运行期语义任务在 `local/game-model.ts`、`local/semantics/`、`turn-execution/`；驱动已记录 `submission.calls`（task/key/ms/fallback/error/raw/attempts/coverage/stageMs）与 `actions`（act/skip 决定与 issue codes）。G3 证据显示：错误集中在 `updates`（未知角色、重复任务、上下文溢出）与 continuation 结论畸形。

## Decisions

### 1. 冻结场景

`turns-semantics-16.json` 以真实输入覆盖：

- act/skip：移动、观察、对话、等待、清点物品。
- 目标识别：合法目标、目标缺失、未知实体。
- 被迫反应/骰点准入：对峙、挥拳、共同移动。
- 共同结算：与 NPC 同行、群体对峙。
- 六阶段候选：任务达成询问、时间推进、外貌/个性触发。
- 继续判断：跑向热点、原地等待。

每个场景只写输入与目的，不写期望输出；通过/失败由真实运行与分类器判定。

### 2. 记录

`summarize-semantics.mjs` 从驱动 JSON 提取：

- 每回合 `actions` 的 act/skip 与来源（model/program/fallback）、issue codes。
- `submission.calls` 的 task、ms、fallback、error、raw、attempts、coverage、stageMs。
- continuation decision、stops。
- 计时（acceptedMs/doneMs）。

分类器标记硬违规：`unknown character`、`duplicate task decision`、`context_capacity_exceeded`、`request_malformed`（conclusion）、`conflicting positions`、同一 actor 重复行动。

### 3. 修复边界

- 允许：提示词、输入投影（允许 ID 列表、压缩状态）、确定性重试预算、校验消息。
- 禁止：固定 handback、固定 targets 为空、预写结果、运行时叙事检查、降门槛。
- 每个修复必须有前后运行证据；失败与重试保留。

### 4. 用户抽检

用户从 `artifacts/goal/semantics/` 抽检原始输出与分类，确认无硬语义违规（D-012）；技术自检与用户验收分别署名。

## Risks / Trade-offs

- [模型输出随机导致场景不稳定] → 分类记录每次真实结果，不追求固定通过；同一场景多次运行保留。
- [修复提示影响叙事质量] → G5 只动语义提示/投影，叙事质量归 G6。
- [上下文上限 11,000 字符是保守值] → 先按投影压缩与允许 ID 列表修，仍溢出再评估上下文/量化，记录决策。

## Non-Goals

- 不新增世界族（D-011）。
- 不做叙事质量评分（G6）。
- 不改 60/300 门槛。
