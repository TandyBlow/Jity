# Proposal: G5 非叙事语义复开（16 例技术读评后续）

## Why

G5 曾按分类器「硬违规 0」归档，但 2026-11-21 的 16 例叙事技术读评发现分类器没覆盖的上游事实缺陷：s02/s05/s16 给路明非凭空识别带、s03 fact「紧闭的门」与 lane「门敞开」相反、s09 占位句入账、s06 judgment 与 fact 不一致、s07 同一 fact 双挂。归档与 tag 保留为历史，本变更按复核重开 G5，修事实层并重跑证据。

## What Changes

- results 事实拒绝新增四类：占位句（`〈…做了什么…谁回应…〉`）、状态字段行（`id=`/`位置为`/`精神为`）、给无识别带的角色写识别带、把已敞开地点写成门紧闭；均带回归测试。
- 叙事标准 prompt 增加「物品只属于持有者」「只有结算结果里实际发生的动作才算发生」两条；行动回声启发式因误杀合法短结果已回退。
- 保留 s06 judgment/fact 不一致为未修问题，需单独设计；s07 双挂在读取层已有改写/去重。
- 复跑 16 例（D-018 后代码）并重做技术读评；计时与 judge 策略的冲突按 D-017/D-018 记录。

## Capabilities

None. 本变更是语义校验与提示修复，不新增运行期能力；`skip_specs: true`。

## Impact

- `local/semantics/settlement/results.ts`、`local/prompt.ts` 与测试。
- 证据：`artifacts/goal/narration/read-16-20261121.md`、`audit-16-*-raw-20261121.txt`。
- `design/goal/ledger.md` G5/G6；G5 归档与 tag 不重写历史。
