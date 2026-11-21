# Proposal: G5 非叙事语义验收

## Why

G3/final4 的真实运行暴露了非叙事语义问题：`updates` 拒绝未登记角色（`f1`）、重复任务决定、`context_capacity_exceeded`（11,578 > 11,000）、continuation 结论 `request_malformed`、跨组位置冲突 `lu receives conflicting positions in one point`，且 12 个计时点 0 次 `continue`。G5 需要冻结场景、记录原始输出与错误，修硬语义违规，而不是用固定 handback / 固定 targets / 预写结果冒充。

## What Changes

- 冻结 16 个真实页面场景（`turns-semantics-16.json`），覆盖 R06–R10：act/skip、目标识别、被迫反应、共同结算、六阶段候选、继续判断，以及合法失败、部分成功、未准入、已行动不重复、自动链与 handback。
- 驱动跑真实 `/world-local`，逐任务记录原始输出、结构/语义错误、重试、回退、实际耗时（复用 `submission.calls`/`actions`）。
- 新增 `summarize-semantics.mjs`：把一次运行整理成 `artifacts/goal/semantics/<stamp>.json`，分类每个场景并标出硬违规（未知实体、重复决定、上下文溢出、畸形结论、位置冲突、重复行动）。
- 针对硬违规修提示/输入投影/确定性校验/重试预算；禁止固定 handback、固定 targets 为空或预写结果。
- 用户抽检确认无硬语义违规（D-012）。

## Capabilities

None. 本变更是语义验收与针对性修复，不新增运行期能力契约；`.openspec.yaml` 设 `skip_specs: true`，原因记录于此。

## Impact

- 新增：`frontend/scripts/product-acceptance/turns-semantics-16.json`、`summarize-semantics.mjs`。
- 修改：`local/game-model.ts`/`local/semantics/**` 的提示、允许 ID 投影或校验（按实测）。
- 证据：`artifacts/goal/semantics/`（原始运行、分类、失败保留）。
- 文档：`ledger.md` R06–R10 行、`decisions.md` 若需新决定。
