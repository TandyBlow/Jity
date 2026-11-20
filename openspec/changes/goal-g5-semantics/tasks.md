# Tasks: G5 非叙事语义验收

## 1. 冻结场景

- [x] 1.1 `turns-semantics-16.json`：16 个真实输入，覆盖 act/skip、目标识别、反应/骰点、共同结算、六阶段、继续判断、合法失败、部分成功、未准入、已行动不重复、自动链、handback。
- [x] 1.2 场景文件不含期望输出或固定结果。

## 2. 证据与分类

- [x] 2.1 `summarize-semantics.mjs` 从驱动 JSON 提取 actions/submission calls/continuation/stops/timing，输出 `artifacts/goal/semantics/<stamp>.json`。
- [x] 2.2 分类器标出硬违规：unknown character、duplicate task decision、context_capacity_exceeded、request_malformed conclusion、conflicting positions、同一 actor 重复行动。
- [x] 2.3 跑真实 `/world-local`，保留原始输出、失败、重试、回退（run1 9 点 + run2 4 点；run3 因 HMR 作废）。

## 3. 修复

- [x] 3.1 针对实测硬违规修提示/输入投影/校验/重试预算：任务提示 characterId/basis、行对象修复、fact id 归属解析、上下文 11,600、295s 引擎中止、stage_unit 拒绝细节日志。
- [x] 3.2 不使用固定 handback、固定 targets 为空或预写结果。
- [ ] 3.3 重跑并更新分类与证据；未通过项保留为问题清单（run4 进行中）。

## 4. 用户抽检

- [ ] 4.1 给用户抽检清单（原始输出 + 分类）；技术自检与用户验收分别署名。

## Workflow follow-up

- 更新 `design/goal/ledger.md` R06–R10 与 G5 行、`decisions.md`（如需）。
- `openspec validate "goal-g5-semantics" --strict`，归档，按路径 commit，打 G5 tag。
